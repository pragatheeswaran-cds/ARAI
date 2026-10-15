import { useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ApiError, api, newKey, type Case, type Community, type Curves, type Disposition, type ReviewKind, type ScoreDistribution, type Signal } from "../api";
import { useReviewer, useWorkspace } from "../App";
import { Chips, GateBadge, SCORE_HELP, StateBadge, TierBadge, workflowNote } from "../components/CustomerTable";
import { Badge, Callout, CopyId, ErrorBox, LoadState, PageTitle, Panel, Row, Stat, ist, label, number, percent, rupees, shortId, useLoad } from "../components/ui";
import { CLEARED_REASON, GATE_HELP, GATE_LABEL, STATE_LABEL, TIER_LABEL, clearedHeavyReturner, rawRate } from "../derive";

const TABS = ["evidence", "returns", "linked accounts", "notes"] as const;
type Tab = (typeof TABS)[number];
const SHARES = new Set(["share", "share of requested units", "share of claim lines", "share of window", "share of item-return lines"]);
const PANEL_LABEL = { expected: "Expected vs actual", returns: "Return behaviour", linked: "Linked accounts", wardrobing: "Wardrobing" } as const;
const MEMO_REASON: Record<string, string> = {
  no_api_key: "This deployment has no key for the drafting model, so no memo is drafted. The evidence panels are complete without it.",
  declined: "The drafting model declined this case twice.",
  not_json: "The draft was not valid JSON twice.",
  api_unreachable: "The drafting model could not be reached.",
  error: "Drafting failed.",
};

function signalValue(signal: Signal): string {
  if (signal.value === null) return "not available";
  if (SHARES.has(signal.unit) || signal.unit === "share") return percent(signal.value);
  if (signal.unit === "score") return signal.value.toFixed(2);
  const value = number(signal.value, Number.isInteger(signal.value) ? 0 : 1);
  return signal.denominator === null ? `${value} ${signal.unit}` : `${value} / ${number(signal.denominator)} ${signal.unit.replace(/^(units )?of /, "")}`;
}
const signalOf = (data: Case, code: string) => data.signals.find((s) => s.code === code) ?? null;
const valueOf = (data: Case, code: string) => signalOf(data, code)?.value ?? null;

// ---------------------------------------------------------------- header
/** One sentence for a customer outside the queue: the templated cleared reason, never generated text. */
function ClearedHeader({ data }: { data: Case }) {
  const { run } = useWorkspace();
  const c = data.customer;
  if (c.eligibility_status !== "eligible" || c.selected_for_review || !c.cleared_reason) return null;
  const heavy = run ? clearedHeavyReturner(c, run) : false;
  const rate = rawRate(c);
  return (
    <Callout>
      <strong>Not in the review queue{heavy ? ", although a heavy returner" : ""}.</strong> {CLEARED_REASON[c.cleared_reason]}.
      {heavy && run?.heavy_returner_cutoff !== null && run && rate !== null && (
        <> Raw return rate {percent(rate, 0)}, at or above this run's heavy-returner cutoff of {percent(run.heavy_returner_cutoff, 0)}.</>
      )}{" "}
      The model read the basket, the claims and the timing, not the rate alone.
    </Callout>
  );
}

// ---------------------------------------------------------------- evidence: why this score
function Breakdown({ data }: { data: Case }) {
  const b = data.score_breakdown;
  const score = data.customer.risk_score;
  if (!b || score === null) {
    return (
      <Panel title="Why this score">
        <p className="muted">{score === null ? "No score: this customer is not ranked." : "No breakdown was recorded for this run."}</p>
      </Panel>
    );
  }
  const widest = Math.max(1, ...b.families.map((f) => Math.abs(f.delta_points)));
  return (
    <Panel title="Why this score" aside={<span className="small">score {score.toFixed(1)}</span>}>
      <p className="muted">
        The score the frozen model gives when one feature family sits at typical values ({b.typical_from === "training" ? "the training median" : "this snapshot's median"}) and
        everything else stays as observed. A family that lowers the score when set to typical is one the score leans on. These are not parts that add
        up to the score.
      </p>
      <div className="tablewrap">
        <table className="breakdown">
          <thead>
            <tr>
              <th scope="col">Feature family</th>
              <th scope="col">Score with it at typical values</th>
              <th scope="col">Change</th>
              <th scope="col" title="The counterfactual: would this customer still be in the queue, everyone else unchanged?">
                Without it
              </th>
            </tr>
          </thead>
          <tbody>
            {b.families.map((f) => (
              <tr key={f.family}>
                <th scope="row">
                  {f.label}
                  <small>{f.feature_count ? `${f.feature_count} feature(s)` : "not read by this bundle"}</small>
                </th>
                <td>{f.score_without.toFixed(1)}</td>
                <td>
                  <span className="delta-track" aria-hidden="true">
                    <span
                      className="delta-bar"
                      style={{
                        left: f.delta_points < 0 ? `${50 - (Math.abs(f.delta_points) / widest) * 50}%` : "50%",
                        width: `${(Math.abs(f.delta_points) / widest) * 50}%`,
                      }}
                    />
                  </span>{" "}
                  {f.delta_points > 0 ? "+" : ""}
                  {f.delta_points.toFixed(1)}
                </td>
                <td>
                  {f.in_queue_without ? "still in the queue" : "out of the queue"}
                  <small>tier {TIER_LABEL[f.tier_without]}</small>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>Analyst rules that would have fired</h3>
      <ul className="facts">
        {data.rules_fired.map((rule) => (
          <li key={rule.rule_id}>
            {rule.fired === null ? "n/a" : rule.fired ? "Fired" : "Not fired"}: {rule.label}
          </li>
        ))}
      </ul>
      <p className="muted">The rulebook is a report-only reference. It is not part of the score.</p>
    </Panel>
  );
}

// ---------------------------------------------------------------- evidence: expected vs actual
function Expected({ data }: { data: Case }) {
  const b = data.customer.basket_expectation;
  if (!b) return <Panel title="Expected vs actual returns"><p className="muted">No mature purchase yet, so there is no expectation.</p></Panel>;
  const top = Math.max(b.actual_units, b.band_high ?? b.expected_units, b.expected_units) * 1.15 || 1;
  const pct = (v: number) => `${Math.min(100, (v / top) * 100)}%`;
  const bracketing = signalOf(data, "bracketing_units");
  const kept = signalOf(data, "bracketing_kept_units");
  const medianDay = valueOf(data, "median_return_day");
  const rate = valueOf(data, "raw_return_rate");
  const expectedRate = valueOf(data, "expected_return_rate");
  return (
    <Panel title="Expected vs actual returns" aside={<span className="small">units on mature sale lines</span>}>
      <Row name="Actual units requested for return">{number(b.actual_units)} of {number(b.purchased_units)} bought</Row>
      <Row name="Expected for this basket" note="From other customers who bought the same products">
        {b.expected_units.toFixed(1)}
      </Row>
      <Row name="Normal band" note="Expected plus or minus two standard deviations">
        {b.band_low !== null && b.band_high !== null ? `${b.band_low.toFixed(1)} to ${b.band_high.toFixed(1)}` : "not available"}
      </Row>
      <Row name="Residual z" note="Heuristic, not a significance test">
        {b.z === null ? "n/a" : b.z.toFixed(2)}
      </Row>
      <div className="band-chart" role="img" aria-label={`Actual ${b.actual_units} against a normal band of ${b.band_low?.toFixed(1)} to ${b.band_high?.toFixed(1)}`}>
        {b.band_low !== null && b.band_high !== null && <span className="band-range" style={{ left: pct(b.band_low), width: `calc(${pct(b.band_high)} - ${pct(b.band_low)})` }} />}
        <span className="band-expected" style={{ left: pct(b.expected_units) }} title={`expected ${b.expected_units.toFixed(1)}`} />
        <span className="band-mark" style={{ left: pct(b.actual_units) }} title={`actual ${b.actual_units}`} />
      </div>
      <div className="band-scale" aria-hidden="true">
        <span>0</span>
        <span>band {b.band_low?.toFixed(0) ?? "?"} to {b.band_high?.toFixed(0) ?? "?"} / actual {b.actual_units}</span>
        <span>{top.toFixed(0)}</span>
      </div>
      <h3>Why the expectation is where it is</h3>
      <ul className="facts">
        <li>
          Return rate {percent(rate, 0)} against {percent(expectedRate, 0)} expected for the products bought.
        </li>
        {bracketing && bracketing.value !== null && bracketing.denominator && (
          <li>
            {number(bracketing.value)} of {number(bracketing.denominator)} units were bought as two or more sizes of one style in one order
            {kept && kept.value !== null ? `; ${number(kept.value)} of those were kept` : ""}.
          </li>
        )}
        {medianDay !== null && <li>Median return request on day {number(medianDay)} after delivery.</li>}
      </ul>
    </Panel>
  );
}

function Evidence({ data, runId }: { data: Case; runId: string }) {
  const byCode = Object.fromEntries(data.signals.map((s) => [s.code, s]));
  const order = ["claim_lines", "claim_share", "coordinated_claim_share", "requested_refund_ratio", "late_return_lines", "median_window_ratio",
    "damage_reason_share", "open_window_share"];
  const w = data.wardrobing;
  return (
    <>
      <Breakdown data={data} />
      <Expected data={data} />
      <div className="grid even">
        <Panel title="Claims, timing and composition">
          {order.filter((code) => byCode[code]).map((code) => (
            <Row key={code} name={byCode[code].label} note={byCode[code].source_refs.length ? `${byCode[code].source_refs.length} source line(s) in the timeline` : undefined}>
              {signalValue(byCode[code])}
            </Row>
          ))}
          <h3>Styles this customer returned or claimed on</h3>
          {data.styles.length === 0 && <p className="muted">No return request on any style.</p>}
          {data.styles.map((style) => (
            <Row key={style.style_id} name={<Link to={`/runs/${runId}/styles/${style.style_id}`}>{style.name}</Link>} note={`${style.style_id} / ${style.category}`}>
              <Badge text={style.state} tone={style.state === "targeting" || style.state === "mixed_or_uncertain" ? "amber" : "gray"} />
            </Row>
          ))}
          <Callout>
            Expected values come from other customers who bought the same products. Evidence about a product never clears, or condemns, a customer
            by itself.
          </Callout>
        </Panel>
        <Panel title="Wardrobing indicator">
          <Badge text={w.status} tone={w.status === "elevated" ? "amber" : "gray"} />
          <Row name="Indicator score" note="Integer points from the signals below; separate from the model score">
            {w.indicator_score === null ? "not available" : `${w.indicator_score} / 100`}
          </Row>
          {w.signals.length === 0 ? (
            <p className="muted">{w.status === "insufficient_evidence" ? "No item return to assess." : w.status === "incomplete" ? "Too few other customers in this snapshot to compare with." : "No signal fired."}</p>
          ) : (
            w.signals.map((signal) => (
              <Row key={signal.code} name={signal.label}>
                {signalValue(signal)}
              </Row>
            ))
          )}
          <p className="muted">{w.limitation}</p>
        </Panel>
      </div>
    </>
  );
}

// ---------------------------------------------------------------- return behaviour
function Returns({ data, runId }: { data: Case; runId: string }) {
  const returns = data.timeline.filter((e) => e.event_type !== "purchase");
  const purchases = data.timeline.filter((e) => e.event_type === "purchase");
  const orders = new Map<string, typeof purchases>();
  for (const p of purchases) if (p.order_id) orders.set(p.order_id, [...(orders.get(p.order_id) ?? []), p]);
  const bracketed = Array.from(orders.values()).filter((lines) => new Set(lines.map((l) => l.style_id)).size < lines.length);
  return (
    <>
      <Panel title="Return behaviour" aside={<span className="small">{returns.length} request line(s)</span>}>
        {returns.length === 0 ? (
          <p className="muted">No return request is recorded for this customer.</p>
        ) : (
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Requested</th>
                  <th scope="col">Order / line</th>
                  <th scope="col">Style / SKU / size</th>
                  <th scope="col">Units</th>
                  <th scope="col">Reason code</th>
                  <th scope="col">Day in window</th>
                  <th scope="col">Item received</th>
                  <th scope="col">Refund</th>
                </tr>
              </thead>
              <tbody>
                {returns.map((e) => (
                  <tr key={e.source_ref}>
                    <td>
                      {ist(e.observed_at)}
                      <small>{e.event_type === "transaction_claim" ? "transaction claim" : "return request"}</small>
                    </td>
                    <td>
                      {e.order_id ?? ""}
                      <small>line {e.order_line_no ?? ""}</small>
                    </td>
                    <td>
                      {e.style_id && <Link to={`/runs/${runId}/styles/${e.style_id}`}>{e.style_id}</Link>}
                      <small>
                        {e.sku} {e.size ? `/ size ${e.size}` : ""}
                      </small>
                    </td>
                    <td>{e.quantity ?? ""}</td>
                    <td>
                      {e.reason_code ? label(e.reason_code) : ""}
                      <small>
                        {e.reason_group ? label(e.reason_group) : ""}
                        {e.linked_claim ? " / a linked account claimed on this style within 7 days" : ""}
                      </small>
                    </td>
                    <td>{e.day_in_window !== null && e.window_days !== null ? `day ${e.day_in_window} of ${e.window_days}` : ""}</td>
                    <td>{e.item_received === null ? <span className="muted">no item due back</span> : e.item_received ? "yes" : "no"}</td>
                    <td>{e.amount_inr ? rupees(e.amount_inr) : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Callout>Reason codes come from the codebook. The customer's free-text reason is never read or shown.</Callout>
      </Panel>
      <Panel title="Orders" aside={<span className="small">{purchases.length} sale line(s) in {orders.size} order(s)</span>}>
        {bracketed.length > 0 && (
          <p className="small">
            {bracketed.length} order(s) hold two or more sizes of one style (size bracketing):{" "}
            {bracketed.map((lines) => lines[0].order_id).join(", ")}.
          </p>
        )}
        <ol className="timeline">
          {purchases.map((e) => (
            <li className="event" key={e.source_ref}>
              <strong>
                {ist(e.observed_at, false)} / order {e.order_id} line {e.order_line_no}
              </strong>
              <small>
                {e.quantity} x {e.style_id ? <Link to={`/runs/${runId}/styles/${e.style_id}`}>{e.style_id}</Link> : ""} {e.sku} size {e.size} / {e.line_status ? label(e.line_status) : ""}
                {e.window_days ? ` / ${e.window_days}-day window` : ""} {e.amount_inr ? `/ ${rupees(e.amount_inr)}` : ""}
              </small>
              <small>{e.source_ref}</small>
            </li>
          ))}
        </ol>
      </Panel>
    </>
  );
}

// ---------------------------------------------------------------- linked accounts
function Group({ community, self, runId }: { community: Community; self: string; runId: string }) {
  const { run } = useWorkspace();
  const ringRate = community.purchased_units ? community.requested_units / community.purchased_units : null;
  const mean = run?.mean_return_rate ?? null;
  return (
    <Panel title={`Linked accounts: ${community.kind === "ring" ? "ring pattern" : "household pattern"}`} aside={<Badge text={community.kind} tone={community.kind === "ring" ? "amber" : "gray"} />}>
      <p className="muted">
        {community.size} accounts linked by two or more shared identifier types.{" "}
        {community.kind === "ring"
          ? `Ring pattern: ${community.coordinated_claim_matches ? `${community.coordinated_claim_matches} coordinated claim match(es) on the same style within 7 days` : ""}${
              community.coordinated_claim_matches && community.selected_count >= 2 ? ", and " : ""
            }${community.selected_count >= 2 ? `${community.selected_count} members selected for review` : ""}.`
          : "Household pattern: no coordinated claim, at most one member selected for review."}{" "}
        {ringRate !== null && (
          <>
            Across the group {percent(ringRate, 0)} of mature units came back
            {mean !== null ? `, against ${percent(mean, 0)} for the run` : ""}.
          </>
        )}
      </p>
      <div className="nodes" aria-label="Members">
        {community.members.map((m) => (
          <div key={m.customer_id} className={"node" + (m.customer_id === self ? " self" : "")}>
            {m.customer_id === self ? <strong>{m.customer_id}</strong> : <Link to={`/runs/${runId}/customers/${m.customer_id}`}>{m.customer_id}</Link>}
            <small>
              {m.risk_score === null ? "unranked" : `score ${m.risk_score.toFixed(1)}`}
              {m.rank ? ` / rank ${number(m.rank)}` : ""} / {m.selected_for_review ? "selected" : "not selected"}
            </small>
            <small>
              {m.mature_requested_units} of {m.mature_purchased_units} units returned
            </small>
          </div>
        ))}
      </div>
      <h3>Edges between members</h3>
      <ul className="facts">
        {community.edges.map((e) => (
          <li key={e.a + e.b}>
            {e.a} and {e.b}: {e.types.join(" + ")}
            {e.coordinated_claim_matches ? ` / ${e.coordinated_claim_matches} coordinated claim match(es)` : ""}
          </li>
        ))}
      </ul>
      <p className="muted">
        Method: {community.method === "louvain" ? "one part of a large component, split by Louvain" : "a whole connected component"}. The kind is a stated rule over observed
        evidence; membership is not guilt, and a household shares identifiers too.
      </p>
    </Panel>
  );
}

function Linked({ data, runId }: { data: Case; runId: string }) {
  const count = signalOf(data, "supported_neighbor_count");
  const fanout = signalOf(data, "max_identifier_fanout");
  return (
    <>
      {data.community ? (
        <Group community={data.community} self={data.customer.customer_id} runId={runId} />
      ) : (
        <Panel title="Linked accounts">
          <p className="muted">No account shares two identifier types with this customer.</p>
        </Panel>
      )}
      <Panel title="Observed relationship support">
        <Callout>
          A link needs at least two shared identifier types (address, device, payment). A value used by more than 25 accounts is ignored. Sharing
          is not guilt: households share too. These counts are shown as evidence and are not inputs to the model.
        </Callout>
        {count && <Row name={count.label}>{count.value ?? 0}</Row>}
        {fanout && <Row name={fanout.label}>{fanout.value ?? 0}</Row>}
        {data.neighbors.length > 0 && (
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Account</th>
                  <th scope="col">Score / rank</th>
                  <th scope="col">Shared identifier types</th>
                  <th scope="col">Largest group on one value</th>
                  <th scope="col">Same-style claims within 7 days</th>
                </tr>
              </thead>
              <tbody>
                {data.neighbors.map((n) => (
                  <tr key={n.customer_id}>
                    <td>
                      <Link className="link" to={`/runs/${runId}/customers/${n.customer_id}`}>
                        {n.customer_id}
                      </Link>
                    </td>
                    <td>
                      {n.risk_score === null ? "unranked" : n.risk_score.toFixed(1)}
                      <small>{n.rank ? `rank ${number(n.rank)} / ${n.selected_for_review ? "selected" : "not selected"}` : ""}</small>
                    </td>
                    <td>{n.shared_types.join(" + ")}</td>
                    <td>{n.max_value_fanout} accounts</td>
                    <td>{n.coordinated_claim_matches ? `${n.coordinated_claim_matches} of this customer's claims` : "none"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}

// ---------------------------------------------------------------- memo
function MemoPanel({ data }: { data: Case }) {
  const m = data.memo;
  const gate = data.customer.gate_outcome;
  return (
    <Panel title="Investigation memo" aside={<Badge text={m.status === "ok" ? "draft" : m.status} tone={m.status === "ok" ? "green" : "gray"} />}>
      {m.status === "ok" ? (
        <div className="memo">
          <h3>Summary</h3>
          <p>{m.summary}</p>
          <h3>Key evidence</h3>
          <ul className="facts">
            {m.key_evidence.map((item, i) => (
              <li key={i}>
                {item.statement}
                <small>
                  {PANEL_LABEL[item.panel]} / {number(item.value, Number.isInteger(item.value) ? 0 : 2)}
                  {item.denominator !== null ? ` of ${number(item.denominator, Number.isInteger(item.denominator) ? 0 : 2)}` : ""}
                </small>
              </li>
            ))}
          </ul>
          <h3>Alternative explanations</h3>
          <ul className="facts">
            {m.alternative_explanations.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
          <h3>Recommended action</h3>
          <p>
            {m.recommended_action ? GATE_LABEL[m.recommended_action] : "n/a"}
            {gate && m.recommended_action && m.recommended_action !== gate ? <small> (the gate rule says {GATE_LABEL[gate]}; read the summary for why)</small> : null}
          </p>
          <p className="small">
            A draft from the case as shown, checked against it: every number cited is a value or denominator of the case. {m.model} / {ist(m.generated_at)} / attempt {m.attempts}.
          </p>
        </div>
      ) : m.status === "pending" ? (
        <p className="muted" role="status">
          Being drafted. The evidence panels are complete; the memo arrives after the run.
        </p>
      ) : m.status === "not_selected" ? (
        <p className="muted">No memo: memos are drafted for customers in the review queue only.</p>
      ) : (
        <p className="muted">
          Memo unavailable. {MEMO_REASON[m.reason ?? ""] ?? `The draft did not pass the check (${m.reason}).`}
          {m.attempts ? ` ${m.attempts} attempt(s).` : ""}
        </p>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------- decision
function Decision({ data, runId, onChanged }: { data: Case; runId: string; onChanged: () => void }) {
  const { name, setName } = useReviewer();
  const w = data.customer.workflow;
  const selected = data.customer.selected_for_review;
  const [disposition, setDisposition] = useState<Disposition>("needs_investigation");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<ReviewKind | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const mine = !!name.trim() && w.opened_by === name.trim();
  const act = async (kind: ReviewKind, override?: Disposition, text?: string) => {
    if (!name.trim()) {
      setError(new ApiError(422, { error_code: "reviewer_required", message: "Enter your name in the run strip first.", request_id: "", details: [] }));
      return;
    }
    const body = text ?? note.trim();
    if (!body) {
      setError(new ApiError(422, { error_code: "note_required", message: "A note is required with every action.", request_id: "", details: [] }));
      return;
    }
    if ((kind === "approve" || kind === "reject") && (override ?? disposition) === "unresolved") {
      setError(new ApiError(422, { error_code: "decision_needs_reading", message: "Choose a reading (needs investigation or likely legitimate) before approving or rejecting.", request_id: "", details: [] }));
      return;
    }
    setBusy(kind);
    setError(null);
    setDone(null);
    try {
      await api.appendReview(runId, data.customer.customer_id, { reviewer_name: name.trim(), kind, disposition: override ?? disposition, note: body, idempotency_key: newKey() });
      setNote("");
      setDone(kind);
      onChanged();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure : new ApiError(0, null));
    } finally {
      setBusy(null);
    }
  };
  return (
    <Panel title="Decision" aside={<StateBadge customer={data.customer} compact />}>
      <Row name="Status" note={w.opened_at ? `opened by ${w.opened_by} / ${ist(w.opened_at)}` : undefined}>
        {STATE_LABEL[w.state]}
      </Row>
      {w.decided_by && (
        <Row name="Decided by" note={ist(w.decided_at)}>
          {w.decided_by}
        </Row>
      )}
      {mine && (w.state === "in_review" || w.state === "awaiting_approval") && (
        <Callout>You opened this case. A different reviewer must approve or reject it.</Callout>
      )}
      <form
        className="decision"
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
        }}
      >
        <div className="filters">
          <label>
            Reviewer
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" maxLength={100} />
          </label>
          <label>
            Your reading
            <select value={disposition} onChange={(e) => setDisposition(e.target.value as Disposition)}>
              <option value="needs_investigation">Needs investigation</option>
              <option value="likely_legitimate">Likely legitimate</option>
              <option value="unresolved">Unresolved</option>
            </select>
          </label>
        </div>
        <label>
          Note (required with every action)
          <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={4000} placeholder="What you looked at and why" />
        </label>
        {selected ? (
          <>
            {(w.state === "new" || w.state === "approved" || w.state === "rejected" || w.state === "auto_logged") && (
              <button type="button" className="primary" disabled={busy !== null} onClick={() => act("open")}>
                {w.state === "new" || w.state === "auto_logged" ? "Open case" : "Reopen case"}
              </button>
            )}
            {w.state === "in_review" && (
              <button type="button" disabled={busy !== null} onClick={() => act("request_approval")}>
                Request approval
              </button>
            )}
            {(w.state === "in_review" || w.state === "awaiting_approval") && (
              <>
                <button type="button" className="primary" disabled={busy !== null} onClick={() => act("approve")} title={mine ? "The server will refuse: you opened this case" : undefined}>
                  Approve
                </button>
                <button type="button" disabled={busy !== null} onClick={() => act("reject")} title={mine ? "The server will refuse: you opened this case" : undefined}>
                  Reject
                </button>
              </>
            )}
          </>
        ) : (
          <>
            <p className="small">Outside the queue: record whether you agree with the run leaving this customer in the log.</p>
            <button type="button" disabled={busy !== null} onClick={() => act("feedback", "likely_legitimate", note.trim() || "Agree: left in the log.")}>
              Agree
            </button>
            <button type="button" disabled={busy !== null} onClick={() => act("feedback", "needs_investigation", note.trim() || "Disagree: this deserves a look.")}>
              Disagree
            </button>
          </>
        )}
        <button type="button" disabled={busy !== null} onClick={() => act("note")}>
          Add a note only
        </button>
        <span role="status" className="small">
          {busy ? " Saving..." : done ? ` Recorded (${label(done)}).` : ""}
        </span>
      </form>
      {error && <ErrorBox error={error} />}
      <p className="muted">
        The gate rule says {data.customer.gate_outcome ? GATE_LABEL[data.customer.gate_outcome] : "n/a"} for this case. It is a presentation rule, not a decision;
        the decision is yours and a second person's. Every action is appended, never edited.
      </p>
    </Panel>
  );
}

// ---------------------------------------------------------------- threshold slider
function Slider({ data, distribution, curves }: { data: Case; distribution: ScoreDistribution | null; curves: Curves | null }) {
  const { run } = useWorkspace();
  const [threshold, setThreshold] = useState<number | null>(null);
  if (!distribution) return null;
  const edges = distribution.bins.map((b) => b.lower);
  const budgetEdge = distribution.threshold_score !== null ? edges.filter((e) => e <= (distribution.threshold_score as number)).at(-1) ?? 0 : 0;
  const t = threshold ?? budgetEdge;
  const bin = distribution.bins.find((b) => b.lower === t) ?? distribution.bins[0];
  const size = bin.at_or_above;
  const score = data.customer.risk_score;
  const inQueue = score !== null && score >= t;
  const heavy = curves ? [...curves.points].sort((a, b) => Math.abs(a.k - size) - Math.abs(b.k - size))[0] : null;
  const maxCount = Math.max(1, ...distribution.bins.map((b) => b.count));
  return (
    <Panel title="If the threshold moved" aside={<span className="small">queue at any score</span>}>
      <div className="histogram" aria-hidden="true">
        {distribution.bins.map((b) => (
          <span key={b.lower} className={b.lower >= t ? "above" : ""} style={{ height: `${(b.count / maxCount) * 100}%` }} title={`${b.lower}-${b.upper}: ${b.count}`} />
        ))}
      </div>
      <input
        type="range"
        className="slider"
        min={0}
        max={100 - distribution.bin_width}
        step={distribution.bin_width}
        value={t}
        onChange={(e) => setThreshold(Number(e.target.value))}
        aria-label="Score threshold"
      />
      <p>
        At a threshold of <strong>{t}</strong> the queue holds <strong>{number(size)}</strong> of {number(distribution.eligible_count)} eligible customers
        {distribution.review_budget !== null ? ` (budget ${number(distribution.review_budget)}${run?.threshold_score !== null && run ? `, cut at ${run.threshold_score.toFixed(1)}` : ""})` : ""}.
        This customer {score === null ? "has no score" : inQueue ? "would be in the queue" : "would be outside the queue"}.
      </p>
      {heavy && (
        <p className="small">
          Synthetic truth, evaluation only: a queue of {number(heavy.k)} would hold {number(heavy.model_abusers_caught)} of {number(curves!.abusers)} abusers and{" "}
          {number(heavy.model_legitimate_heavy_reviewed)} of {number(curves!.legitimate_heavy_returners)} legitimate heavy returners
          {heavy.k !== size ? ` (nearest published point)` : ""}.
        </p>
      )}
      {threshold !== null && threshold !== budgetEdge && (
        <button type="button" onClick={() => setThreshold(null)}>
          Back to the budget cut
        </button>
      )}
      <p className="muted">Counts over this run's stored scores. Moving the slider changes nothing about the run.</p>
    </Panel>
  );
}

// ---------------------------------------------------------------- notes
function Notes({ data, runId }: { data: Case; runId: string }) {
  return (
    <Panel title={data.reviews.length ? `${data.reviews.length} entr(ies), oldest first` : "No entry yet"}>
      <p className="muted">
        Entries are append only and stay with this customer across runs of the same world. To correct one, add another. The reviewer name is free
        text, not a verified identity.
      </p>
      {data.reviews.map((review) => (
        <article className="note" key={review.review_id}>
          <Badge text={review.kind} tone={review.kind === "approve" ? "green" : review.kind === "reject" ? "amber" : "gray"} /> <Badge text={review.disposition} tone="green" />
          <p>{review.note}</p>
          <small>
            {review.reviewer_name} / {ist(review.created_at)} / written on run {shortId(review.run_id, 12)}
            {review.run_id === runId ? " (this run)" : " (another run of this world)"} / bundle {shortId(review.model_id, 14)}
          </small>
        </article>
      ))}
    </Panel>
  );
}

// ---------------------------------------------------------------- page
export function CustomerCase() {
  const { runId = "", customerId = "" } = useParams();
  const { fallback, run, experiment, dataset } = useWorkspace();
  const [params, setParams] = useSearchParams();
  const tab = (TABS as readonly string[]).includes(params.get("tab") ?? "") ? (params.get("tab") as Tab) : "evidence";
  const state = useLoad(() => api.customerCase(runId, customerId), [runId, customerId]);
  const extras = useLoad(async () => {
    const distribution = await api.scoreDistribution(runId).catch(() => null);
    const curves = experiment && run ? await api.curves(experiment.experiment_id, runId).catch(() => null) : null;
    return { distribution, curves };
  }, [runId, experiment?.experiment_id]);
  const data = state.data;
  const c = data?.customer;
  const configHash = experiment && run && experiment.selected_model_id === run.model_id ? experiment.config_hash : null;
  return (
    <>
      <Link className="button back" to={`/runs/${runId}/customers`}>
        Back to case queue
      </Link>
      <PageTitle title={`Case ${customerId}`}>
        Observed evidence for a human reviewer. It is not a finding of misconduct. <CopyId id={customerId} showId={false} />
      </PageTitle>
      <LoadState state={state} />
      {data && c && (
        <>
          <ClearedHeader data={data} />
          <div className="stats">
            <Stat
              name={fallback ? "Return-rate percentile" : "Score and tier"}
              value={
                <span title={SCORE_HELP}>
                  {c.risk_score === null ? "n/a" : c.risk_score.toFixed(1)} <TierBadge tier={c.tier} />
                </span>
              }
              note={c.rank ? `Rank ${number(c.rank)} of ${number(run?.eligible_count ?? 0)} / not a probability` : `${c.support_counts.mature_sale_lines} mature sale line(s): too little history to rank`}
            />
            <Stat name="Recommendation" value={<GateBadge gate={c.gate_outcome} />} note={<span title={GATE_HELP}>A stated rule over the run's results, not a model output</span>} />
            <Stat
              name="Status"
              value={<StateBadge customer={c} compact />}
              note={[workflowNote(c), c.selected_for_review ? "selected for review" : c.eligibility_status === "eligible" ? "not selected: in the log" : "not ranked"].filter(Boolean).join(" / ")}
            />
            <Stat
              name="Linked accounts"
              value={c.community ? `${c.community.size} / ${c.community.kind}` : "none"}
              note={c.community ? "Membership is evidence, not guilt" : "No account shares two identifier types"}
            />
          </div>
          <div className="grid">
            <div>
              <div
                className="tabs"
                role="tablist"
                aria-label="Case sections"
                onKeyDown={(event) => {
                  // the tabs pattern: Left and Right move between tabs and select the one that gets focus
                  if (event.key !== "ArrowRight" && event.key !== "ArrowLeft" && event.key !== "Home" && event.key !== "End") return;
                  const at = TABS.indexOf(tab);
                  const next = event.key === "Home" ? 0 : event.key === "End" ? TABS.length - 1 : (at + (event.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length;
                  event.preventDefault();
                  setParams(TABS[next] === "evidence" ? {} : { tab: TABS[next] }, { replace: true });
                  document.getElementById(`tab-${TABS[next].replace(" ", "-")}`)?.focus();
                }}
              >
                {TABS.map((name) => (
                  <button
                    key={name}
                    type="button"
                    role="tab"
                    id={`tab-${name.replace(" ", "-")}`}
                    aria-controls="case-panel"
                    aria-selected={tab === name}
                    tabIndex={tab === name ? 0 : -1}
                    className={tab === name ? "active" : ""}
                    onClick={() => setParams(name === "evidence" ? {} : { tab: name }, { replace: true })}
                  >
                    {name}
                    {name === "notes" && data.reviews.length ? ` (${data.reviews.length})` : ""}
                  </button>
                ))}
              </div>
              <div id="case-panel" role="tabpanel" aria-labelledby={`tab-${tab.replace(" ", "-")}`}>
                {tab === "evidence" && (
                  <Panel title="Primary signals">
                    <Chips signals={c.primary_signals} />
                  </Panel>
                )}
                {tab === "evidence" && <Evidence data={data} runId={runId} />}
                {tab === "returns" && <Returns data={data} runId={runId} />}
                {tab === "linked accounts" && <Linked data={data} runId={runId} />}
                {tab === "notes" && <Notes data={data} runId={runId} />}
              </div>
            </div>
            <div>
              <MemoPanel data={data} />
              <Decision data={data} runId={runId} onChanged={state.reload} />
              <Slider data={data} distribution={extras.data?.distribution ?? null} curves={extras.data?.curves ?? null} />
              <p className="small manifest">
                Run {run?.run_id ?? runId} / bundle {run?.model_id ?? ""}
                {configHash ? ` / config ${configHash.slice(0, 16)}` : ""}
                {dataset ? ` / dataset ${dataset.manifest_hash.slice(0, 16)}` : ""}
                {data.memo.generated_at ? ` / memo ${ist(data.memo.generated_at)}` : ""}
              </p>
            </div>
          </div>
        </>
      )}
    </>
  );
}
