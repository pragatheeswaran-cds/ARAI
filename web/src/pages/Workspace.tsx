// The workspace pages the Penpot sidebar names and no board draws (decision 8): Investigations (the cases I have open),
// Network Graph (groups of linked accounts), Audit Log (who did what to which case) and Profile (read-only, from the sign-in).
import { Link, useParams, useSearchParams } from "react-router-dom";
import { allPages, api, type CommunityGroup, type Review } from "../api";
import { useSession, useWorkspace } from "../App";
import { CustomerTable, TierBadge } from "../components/CustomerTable";
import { Badge, Callout, LoadState, PageTitle, Panel, Row, ist, label, number, percent, useLoad } from "../components/ui";
import { caseId } from "../derive";

// ---------------------------------------------------------------- investigations
export function Investigations() {
  const { runId = "" } = useParams();
  const { fallback, run } = useWorkspace();
  const mine = useLoad(() => allPages((cursor) => api.customers(runId, { review_only: false, mine: true }, cursor, 100), 5), [runId]);
  return (
    <>
      <PageTitle title="Investigations">The cases you opened in this snapshot that are still in review or escalated.</PageTitle>
      <Panel>
        <LoadState state={mine} empty={!!mine.data && mine.data.length === 0}>
          You have no open case in this snapshot. Open one from the <Link to={`/runs/${runId}/customers`}>Risk Queue</Link>.
        </LoadState>
        {mine.data && mine.data.length > 0 && <CustomerTable runId={runId} customers={mine.data} fallback={fallback} run={run} />}
      </Panel>
    </>
  );
}

// ---------------------------------------------------------------- network graph
const SIZE = 420;

/** Members on a circle, an edge for every pair that shares identifiers; a heavier edge where their claims matched. */
function GroupGraph({ group, runId }: { group: CommunityGroup; runId: string }) {
  const radius = SIZE / 2 - 54;
  const place = new Map(
    group.members.map((member, index) => {
      const angle = (index / group.members.length) * 2 * Math.PI - Math.PI / 2;
      return [member.customer_id, { x: SIZE / 2 + radius * Math.cos(angle), y: SIZE / 2 + radius * Math.sin(angle) }];
    }),
  );
  return (
    <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="network" role="img" aria-label={`Linked accounts of group ${group.id}: ${group.members.length} accounts, ${group.edges.length} links`}>
      {group.edges.map((edge) => {
        const a = place.get(edge.a);
        const b = place.get(edge.b);
        if (!a || !b) return null;
        return (
          <line key={edge.a + edge.b} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={edge.coordinated_claim_matches ? "#b45309" : "#9ca3af"} strokeWidth={edge.coordinated_claim_matches ? 2.5 : 1.2}>
            <title>
              {edge.a} and {edge.b} share: {edge.types.join(", ")}
              {edge.coordinated_claim_matches ? ` / ${edge.coordinated_claim_matches} matched claim(s)` : ""}
            </title>
          </line>
        );
      })}
      {group.members.map((member) => {
        const at = place.get(member.customer_id)!;
        return (
          <Link key={member.customer_id} to={`/runs/${runId}/profiles/${member.customer_id}`}>
            <circle cx={at.x} cy={at.y} r="13" fill={member.selected_for_review ? "#374151" : "#fff"} stroke="#374151" strokeWidth="1.5">
              <title>
                {member.customer_id}: {member.selected_for_review ? "selected for review" : "not selected"}
                {member.risk_score !== null ? ` / score ${member.risk_score.toFixed(1)}` : ""}
              </title>
            </circle>
            <text x={at.x} y={at.y + 28} textAnchor="middle" fontSize="10" fill="#374151">
              {member.customer_id.split("-").pop()}
            </text>
          </Link>
        );
      })}
    </svg>
  );
}

export function NetworkGraph() {
  const { runId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const groups = useLoad(() => api.communities(runId), [runId]);
  const items = groups.data?.items ?? [];
  const chosen = items.find((g) => g.id === params.get("group")) ?? items[0] ?? null;
  return (
    <>
      <PageTitle title="Network Graph">
        Groups of accounts that share an address, a device or a payment method. Membership is evidence for a reviewer, not guilt.
      </PageTitle>
      <LoadState state={groups} empty={!!groups.data && items.length === 0}>
        No account in this run shares identifiers with another one.
      </LoadState>
      {chosen && (
        <div className="grid">
          <Panel title={`Group ${chosen.id}`} aside={<Badge text={chosen.kind} tone={chosen.kind === "ring" ? "amber" : "gray"} />}>
            <GroupGraph group={chosen} runId={runId} />
            <p className="small muted">
              A filled circle is an account selected for review. A line joins two accounts that share identifiers; a heavier, darker line means their
              claims on the same style matched within days. Hover a line or a circle for its details; select a circle to open the customer.
            </p>
            <Row name="Accounts">{number(chosen.size)}</Row>
            <Row name="Selected for review">{number(chosen.selected_count)}</Row>
            <Row name="Matched claims between members">{number(chosen.coordinated_claim_matches)}</Row>
            <Row name="Units returned / bought">
              {number(chosen.requested_units)} / {number(chosen.purchased_units)} ({percent(chosen.purchased_units ? chosen.requested_units / chosen.purchased_units : null, 0)})
            </Row>
            <div className="tablewrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Customer</th>
                    <th scope="col">Risk Score</th>
                    <th scope="col">In the queue</th>
                    <th scope="col">Units returned / bought</th>
                  </tr>
                </thead>
                <tbody>
                  {chosen.members.map((m) => (
                    <tr key={m.customer_id}>
                      <td>
                        <Link className="link" to={`/runs/${runId}/profiles/${m.customer_id}`}>
                          {m.customer_id}
                        </Link>
                      </td>
                      <td>{m.risk_score === null ? "n/a" : m.risk_score.toFixed(1)}</td>
                      <td>{m.selected_for_review ? <TierBadge tier={chosen.kind === "ring" ? "CRITICAL" : "HIGH"} /> : <span className="muted">no</span>}</td>
                      <td>
                        {m.mature_requested_units} / {m.mature_purchased_units}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <Panel title={`Groups in this run (${number(items.length)})`}>
            <div className="tablewrap small-table">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Group</th>
                    <th scope="col">Kind</th>
                    <th scope="col">Accounts</th>
                    <th scope="col">In the queue</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((g) => (
                    <tr key={g.id} className={g.id === chosen.id ? "current" : undefined}>
                      <td>
                        <button type="button" className="quiet" aria-pressed={g.id === chosen.id} onClick={() => setParams({ group: g.id }, { replace: true })}>
                          {g.id}
                        </button>
                      </td>
                      <td>
                        <Badge text={g.kind} tone={g.kind === "ring" ? "amber" : "gray"} />
                      </td>
                      <td>{number(g.size)}</td>
                      <td>{number(g.selected_count)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Callout>
              A ring is a group whose claims matched or whose members sit in the queue together; a household shares an address and a device and
              nothing else. Rings are listed first.
            </Callout>
          </Panel>
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------- audit log
const ACTION: Record<Review["kind"], string> = {
  note: "Note",
  feedback: "Feedback",
  open: "Opened",
  clear: "Cleared",
  escalate: "Escalated",
  close: "Closed",
  request_approval: "Escalated (earlier workflow)",
  approve: "Closed (earlier workflow)",
  reject: "Closed (earlier workflow)",
};

export function AuditLog() {
  const { run } = useWorkspace();
  const { can } = useSession();
  const runId = run?.run_id ?? "";
  const log = useLoad(() => (runId ? api.decisions(runId) : Promise.resolve(null)), [runId]);
  const items = log.data?.items ?? [];
  return (
    <>
      <PageTitle title="Audit Log">Who opened, cleared, escalated or closed which case in this snapshot, newest first. Entries are append-only.</PageTitle>
      <Panel>
        {!runId && <div className="empty">No scored run is selected.</div>}
        {runId && (
          <LoadState state={log} empty={!!log.data && items.length === 0}>
            No case has been opened in this snapshot yet.
          </LoadState>
        )}
        {items.length > 0 && (
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">When</th>
                  <th scope="col">Who</th>
                  <th scope="col">Action</th>
                  <th scope="col">Case</th>
                  <th scope="col">Reading</th>
                  <th scope="col">Note</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => (
                  <tr key={r.review_id}>
                    <td>{ist(r.created_at)}</td>
                    <td>
                      {r.reviewer_name}
                      {!r.author.verified && <small>unverified name</small>}
                    </td>
                    <td>{ACTION[r.kind]}</td>
                    <td>
                      <Link className="link" to={`/runs/${r.run_id}/customers/${r.customer_id}`}>
                        {caseId(r.customer_id)}
                      </Link>
                      <small>{r.customer_id}</small>
                    </td>
                    <td>{label(r.disposition)}</td>
                    <td>{r.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {log.data?.next_cursor && <p className="small muted">Showing the latest 50 entries.</p>}
      </Panel>
      <Callout>
        Sign-ins, refused requests and exports are recorded too.{" "}
        {can("administer") ? <Link to="/admin/people">Open them under People &amp; access.</Link> : "An administrator can read them under People & access."}
      </Callout>
    </>
  );
}

// ---------------------------------------------------------------- profile
export function Profile() {
  const { me } = useSession();
  return (
    <>
      <PageTitle title="Profile">Your account as ARAI knows it. It is read from your sign-in and cannot be edited here.</PageTitle>
      <div className="grid even">
        <Panel title={me.display_name} aside={<Badge text={me.status} tone={me.status === "active" ? "green" : "amber"} />}>
          <Row name="Role">{me.roles.map(label).join(", ")}</Row>
          <Row name="Email Address">{me.email ?? "not provided by the sign-in"}</Row>
          <Row name="What you can do">{me.permissions.map(label).join(", ")}</Row>
        </Panel>
        <Panel title="Account Information">
          <Row name="Account Status">{label(me.status)}</Row>
          <Row name="Account Created">{ist(me.created_at)}</Row>
          <Row name="Last Login">{ist(me.last_sign_in_at)}</Row>
          <Row name="This session ends" note={`or after ${me.idle_minutes} minutes without a request`}>
            {ist(me.session_expires_at)}
          </Row>
        </Panel>
      </div>
      <Callout>
        {me.auth_mode === "oidc"
          ? "Your name, email, password and groups are managed in your organisation's single sign-on (Keycloak). Change them there; ARAI reads them at each sign-in."
          : "This instance uses the development login: people and their roles come from its configuration, and there is no password to change."}
      </Callout>
    </>
  );
}
