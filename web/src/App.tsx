import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { NavLink, Navigate, Route, Routes, useLocation, useMatch } from "react-router-dom";
import { API, ApiError, SIGNED_OUT_EVENT, allPages, api, setCsrfToken, type Dataset, type ExperimentSummary, type Health, type Me, type NotificationList, type Run } from "./api";
import { ErrorBox, ModelDetailToggle, PageTitle, ist, number, shortId, useLoad, useModelDetail } from "./components/ui";
import { datasetName, latestSnapshotRun } from "./derive";
import { CustomerCase } from "./pages/CustomerCase";
import { CustomerProfile, CustomerSearch } from "./pages/CustomerProfile";
import { AuditLog, Investigations, NetworkGraph, Profile } from "./pages/Workspace";
import { ChangePassword, PasswordSignIn } from "./pages/Account";
import { CustomerQueue } from "./pages/CustomerQueue";
import { Datasets } from "./pages/Datasets";
import { Evaluation } from "./pages/Evaluation";
import { Overview } from "./pages/Overview";
import { PeopleAndAccess } from "./pages/People";
import { StyleDetailPage, StyleQueue } from "./pages/Styles";

type Workspace = {
  health: Health | null;
  runs: Run[];
  run: Run | null; // the run in the address bar, otherwise the latest succeeded run
  dataset: Dataset | null; // the run's dataset, for its name
  experiment: ExperimentSummary | null;
  fallback: boolean;
  reload: () => void;
};

const WorkspaceContext = createContext<Workspace>({ health: null, runs: [], run: null, dataset: null, experiment: null, fallback: false, reload: () => {} });
export const useWorkspace = () => useContext(WorkspaceContext);

/** Who is signed in (contract 1.16.0, AM-69): from the session, never typed. `can` reads the user's permissions. */
type Session = { me: Me; can: (permission: string) => boolean; signOut: () => void };
const SessionContext = createContext<Session>({ me: null as unknown as Me, can: () => false, signOut: () => {} });
export const useSession = () => useContext(SessionContext);

/** What the sign-in page says when Keycloak's answer was refused (contract 1.17.0: /?signin_error=<code>). */
export function signInMessage(code: string): string {
  switch (code) {
    case "no_role":
      return "You signed in to Keycloak, but your account is in none of the ARAI groups. Ask an administrator to add you to arai-viewers, arai-reviewers or arai-approvers.";
    case "sign_in_expired":
      return "That sign-in took longer than ten minutes or was already used. Please sign in again.";
    case "sign_in_failed":
      return "Keycloak did not complete the sign-in. Please try again.";
    case "invalid_token":
      return "Keycloak's answer could not be verified, so nobody was signed in. If this happens again, tell the administrator.";
    case "user_disabled":
      return "Your ARAI account is disabled. Ask an administrator to enable it.";
    case "single_sign_on_unavailable":
      return "Keycloak cannot be reached right now. Try again in a minute; if it persists, tell the administrator.";
    default:
      return "The sign-in did not complete. Please try again.";
  }
}

/** The sign-in page: the development login's people (laptops and demos), Keycloak single sign-on (AM-70), or a user
 *  name and a password (AM-81). The instance says which (contract 3.4.0); before that contract, a missing development
 *  login meant single sign-on. */
function SignIn({ onSignedIn }: { onSignedIn: (me: Me) => void }) {
  const mode = useLoad(() => api.authMode().then((answer) => answer.auth_mode), []);
  const users = useLoad(() => (mode.data === "dev" ? api.devUsers() : Promise.resolve(null)), [mode.data]);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const sso = mode.data === "oidc";
  // a refused Keycloak answer comes back as ?signin_error=<code>: read it once, then take it off the address
  const [refused] = useState(() => new URLSearchParams(window.location.search).get("signin_error"));
  const here = new URL(window.location.href);
  here.searchParams.delete("signin_error");
  const returnTo = here.pathname + here.search;
  useEffect(() => {
    if (refused) window.history.replaceState(null, "", returnTo + window.location.hash);
  }, [refused, returnTo]);
  const signIn = async (name: string) => {
    setBusy(name);
    setError(null);
    try {
      onSignedIn(await api.devLogin(name));
    } catch (failure) {
      setError(failure instanceof ApiError ? failure : new ApiError(0, null));
    } finally {
      setBusy(null);
    }
  };
  return (
    <>
      <div className="strip">SYNTHETIC DATA ONLY / Simulated customers and returns / No real person or production accuracy claim</div>
      <main id="main" className="signin">
        <div className="brand">ARAI.</div>
        <PageTitle title="Sign in">Every note and decision is recorded under the person who signed in.</PageTitle>
        {refused && (
          <p className="error" role="alert">
            {signInMessage(refused)}
          </p>
        )}
        {mode.loading ? (
          <p className="muted">Loading...</p>
        ) : mode.error ? (
          <ErrorBox error={mode.error} retry={mode.reload} />
        ) : mode.data === "password" ? (
          <PasswordSignIn onSignedIn={onSignedIn} />
        ) : sso ? (
          <>
            <p className="small">Sign in with your organisation account. Your roles come from your Keycloak groups.</p>
            <p>
              <a className="button primary" href={`${API}/auth/login?return_to=${encodeURIComponent(returnTo)}`}>
                Sign in with Keycloak
              </a>
            </p>
          </>
        ) : (
          <>
            <p className="small">Development login: choose who you are. Single sign-on through Keycloak replaces this list on a shared deployment.</p>
            <div className="signin-users">
              {(users.data?.users ?? []).map((user) => (
                <button key={user.display_name} type="button" className="primary" disabled={busy !== null} onClick={() => signIn(user.display_name)}>
                  {user.display_name}
                  <small>{user.roles.join(", ")}</small>
                </button>
              ))}
            </div>
          </>
        )}
        {error && <ErrorBox error={error} />}
      </main>
    </>
  );
}

/** The run strip: what the queue is cut from, the budget and its edge, when it was scored, and how far its memos are. */
function RunStrip({ run, dataset }: { run: Run; dataset: Dataset | null }) {
  const inProgress = run.status === "queued" || run.status === "running";
  return (
    <div className="runstrip" aria-label="Run strip">
      <span>
        Dataset <strong>{datasetName(run, dataset)}</strong>
      </span>
      <span>
        Customers scored <strong>{number(run.eligible_count)}</strong> <span className="muted">(+{number(run.excluded_count)} unranked)</span>
      </span>
      <span>
        Alerts in queue <strong>{number(run.selected_count)}</strong>
        {run.review_budget !== null && <span className="muted"> of {number(run.review_budget)} budget</span>}
      </span>
      {run.threshold_score !== null && (
        <span title="The reference percentile of the last customer inside the budget; the queue is everyone at or above it">
          Queue threshold <strong>{run.threshold_score.toFixed(1)}</strong>
        </span>
      )}
      <span>
        Scored <strong>{ist(run.completed_at)}</strong>
      </span>
      {run.memos && !run.memos.complete && (
        <span className="muted" role="status">
          Memos drafting: {number(run.memos.ok + run.memos.unavailable)} of {number(run.memos.selected)}
        </span>
      )}
      {inProgress && <span role="status">New run in progress: {run.stage}</span>}
    </div>
  );
}

/** The sidebar and top-bar icons: plain line drawings, hidden from assistive technology (the link text names the page). */
const ICONS: Record<string, ReactNode> = {
  home: <path d="M3 11l9-8 9 8M5 10v10h14V10" />,
  queue: <path d="M4 5h16v14H4zM8 9h8M8 13h8" />,
  box: <path d="M12 3l8 4.5v9L12 21l-8-4.5v-9zM4 7.5l8 4.5 8-4.5M12 12v9" />,
  chart: <path d="M5 20V10M12 20V4M19 20v-7" />,
  gear: (
    <>
      <circle cx="12" cy="12" r="3.5" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1" />
    </>
  ),
  people: (
    <>
      <circle cx="9.5" cy="8" r="3.5" />
      <path d="M3 20v-1a4 4 0 0 1 4-4h5a4 4 0 0 1 4 4v1M21 20v-1a4 4 0 0 0-3-3.9M15.5 4.6a3.5 3.5 0 0 1 0 6.8" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21a8 8 0 0 1 16 0" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M16 16l5 5" />
    </>
  ),
  network: (
    <>
      <circle cx="12" cy="5" r="2.5" />
      <circle cx="5" cy="18" r="2.5" />
      <circle cx="19" cy="18" r="2.5" />
      <path d="M11 7.2L6.2 15.8M13 7.2l4.8 8.6M7.5 18h9" />
    </>
  ),
  file: <path d="M6 3h8l4 4v14H6zM14 3v4h4M9 12h6M9 16h6" />,
  bell: <path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4zM10 20a2 2 0 0 0 4 0" />,
};

function Icon({ name }: { name: keyof typeof ICONS }) {
  return (
    <svg className="icon" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {ICONS[name]}
    </svg>
  );
}

/** The bell: what happened for the signed-in person in the last thirty days. Opening it records that they looked. */
function Notifications() {
  const [open, setOpen] = useState(false);
  const [list, setList] = useState<NotificationList | null>(null);
  const location = useLocation();
  useEffect(() => {
    let live = true;
    api.notifications().then(
      (found) => live && setList(found),
      () => undefined,
    );
    return () => {
      live = false;
    };
  }, [location.pathname]);
  useEffect(() => setOpen(false), [location.pathname]);
  const unread = list?.unread ?? 0;
  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && unread) api.notificationsSeen().then(() => setList((current) => (current ? { ...current, unread: 0 } : current)), () => undefined);
  };
  return (
    <div className="bell">
      <button type="button" className="quiet" aria-expanded={open} aria-label={`Notifications: ${unread} new`} onClick={toggle}>
        <Icon name="bell" />
        {unread > 0 && <span className="bell-count">{unread}</span>}
      </button>
      {open && (
        <div className="bell-panel" role="region" aria-label="Notifications">
          <strong>Notifications</strong>
          {!list || list.items.length === 0 ? (
            <p className="muted">Nothing in the last thirty days.</p>
          ) : (
            <ul>
              {list.items.slice(0, 12).map((item) => (
                <li key={item.kind + item.id} className={item.unread ? "unread" : undefined}>
                  <NavLink to={item.customer_id ? `/runs/${item.run_id}/customers/${item.customer_id}` : `/runs/${item.run_id}/customers`}>{item.text}</NavLink>
                  <small>{ist(item.at)}</small>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

/** Who is signed in, their roles and Sign out, at the right of the top bar. */
function SignedIn() {
  const { me, signOut } = useSession();
  return (
    <div className="signedin small" aria-label="Signed in">
      <Notifications />
      <NavLink to="/profile" className="profile-link" aria-label="Profile">
        <Icon name="user" />
      </NavLink>
      <span>
        Signed in as <strong>{me.display_name}</strong> <span className="muted">({me.roles.join(", ")})</span>
      </span>
      <button type="button" className="quiet" onClick={signOut}>
        Sign out
      </button>
    </div>
  );
}

/** The right of the workspace header. The analyst view names the snapshot; model detail adds the run and the bundle. */
function RunContext({ run, modelLabel }: { run: Run; modelLabel: string }) {
  const [detail] = useModelDetail();
  return (
    <>
      <strong>{detail ? `Run ${shortId(run.run_id, 12)} / ${modelLabel}` : `Snapshot of ${ist(run.cutoff, false)}`}</strong>
      <br />
      {detail ? `Bundle ${shortId(run.model_id, 14)} / Cutoff ${ist(run.cutoff)}` : `Cutoff ${ist(run.cutoff)}`}
      <br />
      <ModelDetailToggle />
    </>
  );
}

/** Why the return-rate ranking is active, in the words the situation calls for. */
export function fallbackReason(health: Health | null, experiment: ExperimentSummary | null): string | null {
  if (!health || health.promoted_model_ready) return null;
  if (!health.scoring_ready) return "No valid scoring bundle is available. Scoring is blocked until a model or the baseline is activated.";
  const tail = " The return-rate ranking is active. Evidence remains available; no trained-model result is claimed.";
  if (!experiment || experiment.selection_status === "not_completed") return "Baseline only: model selection has not been completed." + tail;
  if (experiment.selection_status === "no_selected_model") return "No candidate passed the validation gate." + tail;
  if (experiment.final_test_status === "failed") return "The selected model failed its final test and was not promoted." + tail;
  if (experiment.final_test_status === "unverifiable") return "The final test could not be verified, so no model was promoted." + tail;
  return "A model was selected on validation but its final test has not been run, so it is not promoted." + tail;
}

function Shell({ children }: { children: ReactNode }) {
  const { run, dataset, health, experiment } = useWorkspace();
  const { can } = useSession();
  const location = useLocation();
  useEffect(() => {
    document.getElementById("main")?.focus();
  }, [location.pathname]);
  const reason = fallbackReason(health, experiment);
  const runLink = (suffix: string) => (run ? `/runs/${run.run_id}/${suffix}` : "/datasets");
  const modelLabel = !run ? "No scored run" : run.model_kind === "baseline_fallback" ? "Return-rate baseline" : `Model (${run.model_kind})`;
  return (
    <>
      <div className="strip">SYNTHETIC DATA ONLY / Simulated customers and returns / No real person or production accuracy claim</div>
      <div className="topbar">
        <div className="topbar-brand">
          <Icon name="box" />
          Adaptive Return Abuse Intelligence
        </div>
        <SignedIn />
      </div>
      <div className="shell">
        <aside>
          <nav aria-label="Main">
            <NavLink to="/overview">
              <Icon name="home" />
              Dashboard
            </NavLink>
            <NavLink to={runLink("customers")}>
              <Icon name="queue" />
              Risk Queue
            </NavLink>
            <NavLink to={runLink("investigations")}>
              <Icon name="search" />
              Investigations
            </NavLink>
            <NavLink to={runLink("profiles")}>
              <Icon name="people" />
              Customers
            </NavLink>
            <NavLink to={runLink("network")}>
              <Icon name="network" />
              Network Graph
            </NavLink>
            <NavLink to={runLink("styles")}>
              <Icon name="box" />
              Products / SKU
            </NavLink>
            <NavLink to={experiment ? `/experiments/${experiment.experiment_id}` : "/experiments/none"}>
              <Icon name="chart" />
              Analytics
            </NavLink>
            <NavLink to="/datasets">
              <Icon name="gear" />
              Configuration
            </NavLink>
            <NavLink to="/audit">
              <Icon name="file" />
              Audit Log
            </NavLink>
            {can("administer") && (
              <NavLink to="/admin/people">
                <Icon name="people" />
                People &amp; access
              </NavLink>
            )}
          </nav>
          <div className="footnote">
            Indian apparel / INR
            <br />
            Human investigation support
            <br />
            Signals are not proof of misconduct
          </div>
        </aside>
        <div className="workspace">
          <header>
            <div>
              <div className="small">Returns analyst workspace</div>
              <strong>{run ? `World ${run.world_id}` : "No scored run selected"}</strong>
            </div>
            <div className="small context" aria-label="Run context">
              {run ? <RunContext run={run} modelLabel={modelLabel} /> : <strong>Register a dataset and score it to begin</strong>}
            </div>
          </header>
          {run && <RunStrip run={run} dataset={dataset} />}
          {reason && (
            <div className="banner" role="status">
              {reason}
            </div>
          )}
          <main id="main" tabIndex={-1}>
            {children}
          </main>
          <footer className="bottom">
            Investigation signals are not proof of misconduct. Synthetic data only; no production accuracy claim.
            <br />
            Every note and decision is recorded under the signed-in reviewer. This instance uses the development login.
          </footer>
        </div>
      </div>
    </>
  );
}

export default function App() {
  const [session, setSession] = useState<{ me: Me | null; checked: boolean }>({ me: null, checked: false });
  useEffect(() => {
    let live = true;
    api.me().then(
      (me) => {
        setCsrfToken(me.csrf_token);
        if (live) setSession({ me, checked: true });
      },
      () => live && setSession({ me: null, checked: true }),
    );
    const ended = () => {
      setCsrfToken(null);
      setSession({ me: null, checked: true });
    };
    window.addEventListener(SIGNED_OUT_EVENT, ended);
    return () => {
      live = false;
      window.removeEventListener(SIGNED_OUT_EVENT, ended);
    };
  }, []);
  if (!session.checked) return <p className="muted">Checking sign-in...</p>;
  if (!session.me) {
    return (
      <SignIn
        onSignedIn={(me) => {
          setCsrfToken(me.csrf_token);
          setSession({ me, checked: true });
        }}
      />
    );
  }
  const me = session.me;
  const refresh = () =>
    api.me().then(
      (fresh) => {
        setCsrfToken(fresh.csrf_token);
        setSession({ me: fresh, checked: true });
      },
      () => setSession({ me: null, checked: true }),
    );
  const signOut = () => {
    api.logout().finally(() => {
      setCsrfToken(null);
      // under single sign-on, end the Keycloak session too; it sends the browser back to this site's sign-in page
      if (me.sso_logout_url) window.location.assign(me.sso_logout_url);
      else setSession({ me: null, checked: true });
    });
  };
  if (me.must_change_password) {
    // AM-81: a password an admin set is replaced by the person's own before anything else is served
    return (
      <>
        <div className="strip">SYNTHETIC DATA ONLY / Simulated customers and returns / No real person or production accuracy claim</div>
        <main id="main" className="signin">
          <div className="brand">ARAI.</div>
          <PageTitle title="Choose your password">
            Signed in as {me.display_name}. The password you signed in with was given to you; choose your own before you continue.
          </PageTitle>
          <ChangePassword forced onChanged={() => void refresh()} />
          <p>
            <button type="button" className="quiet" onClick={signOut}>
              Sign out
            </button>
          </p>
        </main>
      </>
    );
  }
  return (
    <SessionContext.Provider value={{ me, can: (permission) => me.permissions.includes(permission as Me["permissions"][number]), signOut }}>
      <Workbench />
    </SessionContext.Provider>
  );
}

function Workbench() {
  const match = useMatch("/runs/:runId/*");
  const loaded = useLoad(async () => {
    const [health, runs, experiments, datasets] = await Promise.all([
      api.health().catch(() => null),
      allPages((cursor) => api.runs(undefined, cursor), 5).catch(() => [] as Run[]),
      api.experiments().catch(() => ({ items: [] as ExperimentSummary[], next_cursor: null })),
      allPages((cursor) => api.datasets(cursor), 5).catch(() => [] as Dataset[]),
    ]);
    return { health, runs, datasets, experiment: experiments.items.at(-1) ?? null };
  }, []);
  const workspace = useMemo<Workspace>(() => {
    const runs = loaded.data?.runs ?? [];
    const fromUrl = match?.params.runId ? runs.find((r) => r.run_id === match.params.runId) : undefined;
    const run = fromUrl ?? latestSnapshotRun(runs);
    const health = loaded.data?.health ?? null;
    return {
      health,
      runs,
      run,
      dataset: run ? (loaded.data?.datasets ?? []).find((d) => d.dataset_id === run.dataset_id) ?? null : null,
      experiment: loaded.data?.experiment ?? null,
      fallback: run ? run.model_kind === "baseline_fallback" : !!health && !health.promoted_model_ready,
      reload: loaded.reload,
    };
  }, [loaded.data, loaded.reload, match?.params.runId]);

  return (
    <WorkspaceContext.Provider value={workspace}>
      <Shell>
        <Routes>
          <Route path="/" element={<Navigate to="/overview" replace />} />
          <Route path="/overview" element={<Overview />} />
          <Route path="/datasets" element={<Datasets />} />
          <Route path="/runs/:runId/customers" element={<CustomerQueue />} />
          <Route path="/runs/:runId/customers/:customerId" element={<CustomerCase />} />
          <Route path="/runs/:runId/investigations" element={<Investigations />} />
          <Route path="/runs/:runId/profiles" element={<CustomerSearch />} />
          <Route path="/runs/:runId/profiles/:customerId" element={<CustomerProfile />} />
          <Route path="/runs/:runId/network" element={<NetworkGraph />} />
          <Route path="/audit" element={<AuditLog />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/runs/:runId/styles" element={<StyleQueue />} />
          <Route path="/runs/:runId/styles/:styleId" element={<StyleDetailPage />} />
          <Route path="/experiments/:experimentId" element={<Evaluation />} />
          <Route path="/admin/people" element={<PeopleAndAccess />} />
          <Route
            path="*"
            element={
              <>
                <PageTitle title="Unknown page">There is nothing at this address.</PageTitle>
                <div className="empty">
                  <NavLink to="/overview">Go to the overview</NavLink>
                </div>
              </>
            }
          />
        </Routes>
      </Shell>
    </WorkspaceContext.Provider>
  );
}
