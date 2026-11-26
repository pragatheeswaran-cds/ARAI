import { useState, type FormEvent } from "react";
import { ApiError, api, type AdminUser, type AuthEvent, type AuthEventKind, type Role } from "../api";
import { useSession } from "../App";
import { Badge, Callout, ErrorBox, LoadState, PageTitle, Panel, ist, label, useLoad, type Loaded } from "../components/ui";
import { PASSWORD_MIN_LENGTH } from "./Account";

type Action = "disable" | "enable" | "end-sessions";

const KINDS: AuthEventKind[] = ["sign_in", "sign_out", "session_ended", "refused", "export", "role_change", "user_disabled", "user_enabled", "sessions_ended", "user_created", "password_changed", "password_reset"];
const SOURCE: Record<string, string> = { keycloak_group: "Keycloak group", bootstrap: "bootstrap admin", dev: "development list", local: "set by an admin" };
const ROLES: Role[] = ["viewer", "reviewer", "approver", "admin"];
const ROLE_HELP: Record<Role, string> = {
  viewer: "reads every screen",
  reviewer: "opens, clears and escalates cases; exports",
  approver: "also closes escalated cases",
  admin: "datasets, runs, people and access; does not review",
};
const SIGN_IN: Record<AdminUser["sign_in"], string> = { keycloak: "Keycloak", development_login: "development login", password: "password" };
const ACTION_WORDS: Record<Action, { button: string; done: string; help: string }> = {
  disable: { button: "Disable", done: "disabled", help: "Ends every session now, stops their bearer tokens and refuses their next sign-in until enabled." },
  enable: { button: "Enable", done: "enabled", help: "They may sign in again. Sessions ended by the disable stay ended." },
  "end-sessions": { button: "End sessions", done: "signed out everywhere", help: "Signs them out now; they may sign in again, with roles read afresh." },
};

/** One line for an entry of the sign-in log: what happened, from the entry's detail (never a token or password). */
export function eventDetail(event: Pick<AuthEvent, "kind" | "detail">): string {
  const d = event.detail as Record<string, unknown>;
  const by = d.by_name ? `by ${d.by_name}` : "";
  const reason = d.reason ? `reason: ${d.reason}` : "";
  const parts: string[] = [];
  switch (event.kind) {
    case "role_change":
      parts.push(by, `from ${(d.from as string[] | undefined)?.join(", ") || "no role"} to ${(d.to as string[] | undefined)?.join(", ") || "no role"}`);
      break;
    case "user_created":
      parts.push(by, (d.roles as string[] | undefined)?.length ? `roles: ${(d.roles as string[]).join(", ")}` : "", d.from ? `was a persona of the ${d.from}` : "");
      break;
    case "password_reset":
    case "password_changed":
      parts.push(by, typeof d.sessions_ended === "number" && d.sessions_ended > 0 ? `${d.sessions_ended} session${d.sessions_ended === 1 ? "" : "s"} ended` : "");
      break;
    case "refused":
      parts.push(String(d.status ?? ""), d.reason ? label(String(d.reason)) : d.permission ? `needs ${d.permission}` : "", String(d.path ?? ""), d.locked_minutes ? `account locked for ${d.locked_minutes} minutes` : "");
      break;
    case "user_disabled":
    case "user_enabled":
    case "sessions_ended":
      parts.push(by, typeof d.sessions_ended === "number" ? `${d.sessions_ended} session${d.sessions_ended === 1 ? "" : "s"} ended` : "", reason);
      break;
    case "session_ended":
      parts.push(d.reason ? label(String(d.reason)) : "");
      break;
    case "sign_in":
      parts.push(d.mode === "oidc" ? "Keycloak" : d.mode === "dev" ? "development login" : d.mode === "password" ? "password" : "");
      break;
    case "export":
      parts.push(d.run_id ? `queue of run ${d.run_id}` : "");
      break;
    default:
      parts.push(reason);
  }
  return parts.filter(Boolean).join(" / ");
}

function Roles({ user }: { user: AdminUser }) {
  if (!user.roles.length) return <span className="muted">none</span>;
  return (
    <>
      {user.roles.map((r) => (
        <span key={r.role} className="role">
          <Badge text={r.role} tone={r.role === "admin" ? "amber" : "plain"} />
          <small>{SOURCE[r.source] ?? r.source}</small>
        </span>
      ))}
    </>
  );
}

function RolePicks({ value, onChange }: { value: Role[]; onChange: (roles: Role[]) => void }) {
  return (
    <fieldset>
      <legend>Roles</legend>
      <div className="role-picks">
        {ROLES.map((role) => (
          <label key={role} title={ROLE_HELP[role]}>
            <input type="checkbox" checked={value.includes(role)} onChange={(event) => onChange(event.target.checked ? [...value, role] : value.filter((r) => r !== role))} />
            {role}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

type AccountEdit = { kind: "add" } | { kind: "roles"; user: AdminUser } | { kind: "password"; user: AdminUser };

/** Accounts with a password (contract 3.4.0, AM-81): add a person, set roles, or give a new password to pass on. */
function AccountForm({ edit, selfId, onDone, onCancel }: { edit: AccountEdit; selfId: string; onDone: (message: string) => void; onCancel: () => void }) {
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [roles, setRoles] = useState<Role[]>(edit.kind === "roles" ? edit.user.roles.map((r) => r.role) : ["reviewer"]);
  const [password, setPassword] = useState("");
  const [shown, setShown] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const needsPassword = edit.kind !== "roles";
  const ready = roles.length > 0 && (!needsPassword || password.length >= PASSWORD_MIN_LENGTH) && (edit.kind !== "add" || username.trim().length >= 2);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (edit.kind === "add") {
        const made = await api.adminCreateUser({ username: username.trim(), display_name: displayName.trim() || null, roles, password });
        onDone(`${made.display_name}: account created. Pass the password on; they choose their own at the first sign-in.`);
      } else if (edit.kind === "roles") {
        const updated = await api.adminSetRoles(edit.user.user_id, roles);
        onDone(`${updated.display_name}: roles are now ${updated.roles.map((r) => r.role).join(", ")}.`);
      } else {
        const updated = await api.adminResetPassword(edit.user.user_id, password);
        onDone(`${updated.display_name}: new password set and sessions ended. Pass it on; they choose their own at the next sign-in.`);
      }
    } catch (failure) {
      setError(failure instanceof ApiError ? failure : new ApiError(0, null));
    } finally {
      setBusy(false);
    }
  };
  const title = edit.kind === "add" ? "Add a person" : edit.kind === "roles" ? `Roles of ${edit.user.display_name}` : `New password for ${edit.user.display_name}`;
  return (
    <form className="confirm" aria-label={title} onSubmit={(event) => void submit(event)}>
      <p>
        <strong>{title}</strong>
        {edit.kind === "password" && " Ends their sessions now and lifts a lock. They must choose their own password at the next sign-in."}
        {edit.kind === "roles" && " Applies at their next request."}
      </p>
      {edit.kind === "add" && (
        <>
          <label>
            User name (what they type to sign in: letters, digits, dot, dash, underscore)
            <input value={username} maxLength={50} autoCapitalize="none" spellCheck={false} autoComplete="off" required onChange={(event) => setUsername(event.target.value)} />
          </label>
          <label>
            Name shown on notes and decisions (optional; the user name when empty)
            <input value={displayName} maxLength={100} autoComplete="off" onChange={(event) => setDisplayName(event.target.value)} />
          </label>
        </>
      )}
      {edit.kind !== "password" && <RolePicks value={roles} onChange={setRoles} />}
      {edit.kind === "roles" && edit.user.user_id === selfId && <p className="small muted">You cannot take the admin role from your own account.</p>}
      {needsPassword && (
        <label>
          {edit.kind === "add" ? "First password" : "New password"} (at least {PASSWORD_MIN_LENGTH} characters; you pass it on, it is not shown again)
          <input type={shown ? "text" : "password"} value={password} maxLength={200} autoComplete="new-password" spellCheck={false} required onChange={(event) => setPassword(event.target.value)} />
        </label>
      )}
      {needsPassword && (
        <label className="inline">
          <input type="checkbox" checked={shown} onChange={(event) => setShown(event.target.checked)} /> Show the password while typing
        </label>
      )}
      <div className="actions">
        <button type="submit" className="primary" disabled={busy || !ready}>
          {edit.kind === "add" ? "Create account" : edit.kind === "roles" ? "Save roles" : "Set password"}
        </button>
        <button type="button" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
      {error && <ErrorBox error={error} />}
    </form>
  );
}

function People({ users, onChanged }: { users: Loaded<{ items: AdminUser[] }>; onChanged: () => void }) {
  const { me } = useSession();
  const accounts = me.auth_mode === "password";
  const [edit, setEdit] = useState<AccountEdit | null>(null);
  const [pending, setPending] = useState<{ user: AdminUser; action: Action } | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const confirm = async () => {
    if (!pending) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await api.adminAction(pending.user.user_id, pending.action, reason.trim() || undefined);
      setMessage(`${updated.display_name}: ${ACTION_WORDS[pending.action].done}.`);
      setPending(null);
      setReason("");
      onChanged();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure : new ApiError(0, null));
    } finally {
      setBusy(false);
    }
  };
  const ask = (user: AdminUser, action: Action) => {
    setEdit(null);
    setPending({ user, action });
    setReason("");
    setMessage(null);
    setError(null);
  };
  return (
    <Panel title="People">
      <Callout>
        {accounts
          ? "People sign in with a user name and a password kept by ARAI. Add a person here, set their roles, or give them a new password to pass on; a password you set must be replaced by the person at their next sign-in. Passwords are stored only as a hash and are never shown."
          : me.auth_mode === "oidc"
            ? "Roles come from Keycloak groups (arai-viewers, arai-reviewers, arai-approvers, arai-admins) and are read at each sign-in. Change them in Keycloak; to apply a change before the person's session ends, end their sessions here. Roles are not edited in ARAI."
            : "Roles come from the development login's list (AUTH_DEV_USERS) and are read at each sign-in. On a shared deployment they come from Keycloak groups. Roles are not edited in ARAI."}
      </Callout>
      {accounts && (
        <p className="actions">
          <button
            type="button"
            className="primary"
            disabled={busy}
            onClick={() => {
              setPending(null);
              setMessage(null);
              setEdit({ kind: "add" });
            }}
          >
            Add a person
          </button>
        </p>
      )}
      {message && (
        <p role="status" className="small">
          {message}
        </p>
      )}
      <LoadState state={users} empty={users.data?.items.length === 0} />
      {!!users.data?.items.length && (
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Person</th>
                <th>Sign-in</th>
                <th>Roles</th>
                <th>Status</th>
                <th>Last sign-in</th>
                <th>Last activity</th>
                <th>Open sessions</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {(users.data?.items ?? []).map((user) => {
                const self = user.user_id === me.user_id;
                return (
                  <tr key={user.user_id}>
                    <td>
                      <strong>{user.display_name}</strong>
                      {self && <span className="muted"> (you)</span>}
                      <small>{user.email ?? "no e-mail"}</small>
                    </td>
                    <td>{SIGN_IN[user.sign_in]}</td>
                    <td>
                      <Roles user={user} />
                    </td>
                    <td>
                      <Badge text={user.status} tone={user.status === "active" ? "green" : "gray"} />
                      {user.locked && <Badge text="locked" tone="amber" title="Too many wrong passwords; sign-in is refused for a few minutes. A new password lifts it." />}
                      {user.must_change_password && <small>must choose a password</small>}
                    </td>
                    <td>{ist(user.last_sign_in_at)}</td>
                    <td>{ist(user.last_seen_at)}</td>
                    <td>{user.open_sessions}</td>
                    <td className="row-actions">
                      {user.status === "active" ? (
                        !self && (
                          <button type="button" disabled={busy} onClick={() => ask(user, "disable")}>
                            Disable
                          </button>
                        )
                      ) : (
                        <button type="button" disabled={busy} onClick={() => ask(user, "enable")}>
                          Enable
                        </button>
                      )}
                      {user.open_sessions > 0 && !self && (
                        <button type="button" disabled={busy} onClick={() => ask(user, "end-sessions")}>
                          End sessions
                        </button>
                      )}
                      {accounts && user.sign_in === "password" && (
                        <>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => {
                              setPending(null);
                              setMessage(null);
                              setEdit({ kind: "roles", user });
                            }}
                          >
                            Roles
                          </button>
                          {!self && (
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => {
                                setPending(null);
                                setMessage(null);
                                setEdit({ kind: "password", user });
                              }}
                            >
                              New password
                            </button>
                          )}
                        </>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {edit && (
        <AccountForm
          key={edit.kind + (edit.kind === "add" ? "" : edit.user.user_id)}
          edit={edit}
          selfId={me.user_id}
          onCancel={() => setEdit(null)}
          onDone={(text) => {
            setEdit(null);
            setMessage(text);
            onChanged();
          }}
        />
      )}
      {pending && (
        <form
          className="confirm"
          aria-label="Confirm the action"
          onSubmit={(event) => {
            event.preventDefault();
            void confirm();
          }}
        >
          <p>
            <strong>
              {ACTION_WORDS[pending.action].button} {pending.user.display_name}?
            </strong>{" "}
            {ACTION_WORDS[pending.action].help}
          </p>
          <label>
            Reason, for the sign-in log (optional)
            <input value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} />
          </label>
          <div className="actions">
            <button type="submit" className="primary" disabled={busy}>
              {ACTION_WORDS[pending.action].button}
            </button>
            <button type="button" disabled={busy} onClick={() => setPending(null)}>
              Cancel
            </button>
          </div>
        </form>
      )}
      {error && <ErrorBox error={error} />}
    </Panel>
  );
}

function SignInLog({ people, version }: { people: AdminUser[]; version: number }) {
  const [kind, setKind] = useState("");
  const [userId, setUserId] = useState("");
  const [more, setMore] = useState<{ items: AuthEvent[]; cursor: string | null } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const filters = { kind: kind || undefined, user_id: userId || undefined };
  const first = useLoad(() => {
    setMore(null);
    return api.authEvents(filters);
  }, [kind, userId, version]);
  const items = [...(first.data?.items ?? []), ...(more?.items ?? [])];
  const cursor = more ? more.cursor : first.data?.next_cursor ?? null;
  const loadMore = async () => {
    if (!cursor) return;
    setLoadingMore(true);
    try {
      const page = await api.authEvents(filters, cursor);
      setMore({ items: [...(more?.items ?? []), ...page.items], cursor: page.next_cursor });
    } finally {
      setLoadingMore(false);
    }
  };
  return (
    <Panel title="Sign-in log">
      <p className="small">Append only: sign-ins, sign-outs, ended sessions, refused requests, exports, role changes, new accounts, password changes and the actions above. Never a password.</p>
      <div className="filters">
        <label>
          What
          <select value={kind} onChange={(event) => setKind(event.target.value)}>
            <option value="">Everything</option>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {label(k)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Person
          <select value={userId} onChange={(event) => setUserId(event.target.value)}>
            <option value="">Everyone</option>
            {people.map((p) => (
              <option key={p.user_id} value={p.user_id}>
                {p.display_name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <LoadState state={first} empty={!first.loading && !first.error && items.length === 0} />
      {items.length > 0 && (
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>What</th>
                <th>Person</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {items.map((event) => (
                <tr key={event.event_id}>
                  <td>{ist(event.at)}</td>
                  <td>{label(event.kind)}</td>
                  <td>{event.display_name ?? <span className="muted">unknown</span>}</td>
                  <td>
                    {eventDetail(event)}
                    {event.request_id && <small>request {event.request_id}</small>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {cursor && (
        <p>
          <button type="button" disabled={loadingMore} onClick={() => void loadMore()}>
            {loadingMore ? "Loading..." : "Load older entries"}
          </button>
        </p>
      )}
    </Panel>
  );
}

/** People and access (contract 2.0.0, AM-71): who has signed in, their roles and where those come from, and the sign-in log. */
export function PeopleAndAccess() {
  const { can } = useSession();
  const people = useLoad(() => (can("administer") ? api.adminUsers() : Promise.resolve({ items: [] as AdminUser[] })), []);
  const [version, setVersion] = useState(0);
  if (!can("administer")) {
    return (
      <>
        <PageTitle title="People & access">Only an admin sees this page.</PageTitle>
      </>
    );
  }
  return (
    <>
      <PageTitle title="People & access">
        Everyone who has signed in or has an account, their roles and where each comes from, and the append-only sign-in log. An admin can disable a person or end their sessions; nobody reviews from here.
      </PageTitle>
      <People
        users={people}
        onChanged={() => {
          setVersion((v) => v + 1);
          people.reload();
        }}
      />
      <SignInLog people={people.data?.items ?? []} version={version} />
    </>
  );
}
