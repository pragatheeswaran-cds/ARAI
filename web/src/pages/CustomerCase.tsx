import { useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ApiError, api, newKey, type Case, type Disposition, type Signal } from "../api";
import { useWorkspace } from "../App";
import { SCORE_HELP, tagLabel } from "../components/CustomerTable";
import { Badge, Callout, ErrorBox, LoadState, PageTitle, Panel, Row, Stat, ist, label, number, percent, rupees, shortId, useLoad } from "../components/ui";

const TABS = ["evidence", "timeline", "relationships", "notes"] as const;
type Tab = (typeof TABS)[number];
const SHARES = new Set(["share", "share of requested units", "share of claim lines", "share of window", "share of item-return lines"]);

function signalValue(signal: Signal): string {
  if (signal.value === null) return "not available";
  if (SHARES.has(signal.unit) || signal.unit === "share") return percent(signal.value);
  if (signal.unit === "score") return signal.value.toFixed(2);
  const value = number(signal.value, Number.isInteger(signal.value) ? 0 : 1);
  return signal.denominator === null ? `${value} ${signal.unit}` : `${value} / ${number(signal.denominator)} ${signal.unit.replace(/^(units )?of /, "")}`;
}

function Evidence({ data, runId }: { data: Case; runId: string }) {
  const byCode = Object.fromEntries(data.signals.map((s) => [s.code, s]));
  const order = ["mature_requested_units", "expected_requested_units", "raw_return_rate", "expected_return_rate", "residual_z", "claim_lines",
    "claim_share", "coordinated_claim_share", "requested_refund_ratio", "late_return_lines", "median_window_ratio", "damage_reason_share",
    "open_window_share"];
  const w = data.wardrobing;
  return (
    <div className="grid">
      <Panel title="Returns in context">
        {order.filter((code) => byCode[code]).map((code) => (
          <Row key={code} name={byCode[code].label} note={byCode[code].source_refs.length ? `${byCode[code].source_refs.length} source line(s) in the timeline` : undefined}>
            {signalValue(byCode[code])}
          </Row>
        ))}
        <h3>Styles this customer returned or claimed on</h3>
        {data.styles.length === 0 && <p className="muted">No return request on any style.</p>}
        {data.styles.map((style) => (
          <Row key={style.style_id} name={<Link to={`/runs/${runId}/styles/${style.style_id}`}>{style.style_id}</Link>} note={style.category}>
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
          <p className="muted">{w.status === "insufficient_evidence" ? "No item return to assess." : "No timing signal fired."}</p>
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
  );
}

function Timeline({ data, runId }: { data: Case; runId: string }) {
  if (data.timeline.length === 0) return <Panel title="Observed transactions">No order or return is recorded for this customer.</Panel>;
  const names: Record<string, string> = { purchase: "Order line", return_request: "Return requested", transaction_claim: "Transaction claim" };
  return (
    <Panel title="Observed transactions">
      <p className="muted">Every sale line and return request before the cutoff, oldest first, with its source key.</p>
      <ol className="timeline">
        {data.timeline.map((event) => (
          <li className="event" key={event.source_ref}>
            <strong>
              {event.event_type === "purchase" ? ist(event.observed_at, false) : ist(event.observed_at)} / {names[event.event_type] ?? label(event.event_type)}
            </strong>
            <small>
              {event.description}
              {event.amount_inr !== null && event.amount_inr > 0 ? ` / ${rupees(event.amount_inr)}${event.event_type === "purchase" ? "" : " refunded"}` : ""}
            </small>
            <small>
              {event.style_id && <Link to={`/runs/${runId}/styles/${event.style_id}`}>{event.style_id}</Link>} {event.sku} / {event.source_ref}
            </small>
          </li>
        ))}
      </ol>
    </Panel>
  );
}

function Relationships({ data, runId }: { data: Case; runId: string }) {
  const count = data.signals.find((s) => s.code === "supported_neighbor_count");
  const fanout = data.signals.find((s) => s.code === "max_identifier_fanout");
  return (
    <Panel title="Observed relationship support">
      <Callout>
        A link needs at least two shared identifier types (address, device, payment). A value used by more than 25 accounts is ignored. Sharing
        is not guilt: households share too. These counts are shown as evidence and are not inputs to the model.
      </Callout>
      {count && <Row name={count.label}>{count.value ?? 0}</Row>}
      {fanout && <Row name={fanout.label}>{fanout.value ?? 0}</Row>}
      {data.neighbors.length === 0 ? (
        <p className="muted">No account shares two identifier types with this customer.</p>
      ) : (
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Account</th>
                <th scope="col">Shared identifier types</th>
                <th scope="col">Shared values</th>
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
                  <td>{n.shared_types.join(" + ")}</td>
                  <td>{n.shared_value_count}</td>
                  <td>{n.max_value_fanout} accounts</td>
                  <td>{n.coordinated_claim_matches ? `${n.coordinated_claim_matches} of this customer's claims` : "none"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function Notes({ data, runId, onAppended }: { data: Case; runId: string; onAppended: () => void }) {
  const [reviewer, setReviewer] = useState(() => localStorage.getItem("arai.reviewer") ?? "");
  const [disposition, setDisposition] = useState<Disposition>("needs_investigation");
  const [note, setNote] = useState("");
  const [key, setKey] = useState(newKey);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [saved, setSaved] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!reviewer.trim() || !note.trim()) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await api.appendReview(runId, data.customer.customer_id, { reviewer_name: reviewer.trim(), disposition, note: note.trim(), idempotency_key: key });
      localStorage.setItem("arai.reviewer", reviewer.trim());
      setNote("");
      setKey(newKey()); // a new note needs a new key; a retry of the same note reuses the old one
      setSaved(true);
      onAppended();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure : new ApiError(0, null));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title="Append an analyst opinion">
      <p className="muted">
        Notes are append only and stay with this customer across runs of the same world. To correct a note, add a new one. The reviewer name is
        free text, not a verified identity.
      </p>
      <form onSubmit={submit}>
        <div className="filters">
          <label>
            Reviewer name
            <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} required maxLength={100} placeholder="Your name" />
          </label>
          <label>
            Disposition
            <select value={disposition} onChange={(e) => setDisposition(e.target.value as Disposition)}>
              <option value="needs_investigation">Needs investigation</option>
              <option value="likely_legitimate">Likely legitimate</option>
              <option value="unresolved">Unresolved</option>
            </select>
          </label>
        </div>
        <label>
          Evidence-based note
          <textarea value={note} onChange={(e) => setNote(e.target.value)} required maxLength={4000} />
        </label>
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Saving..." : "Append note"}
        </button>
        <span role="status" className="small">
          {saved ? " Note appended. Earlier notes are unchanged." : ""}
        </span>
      </form>
      {error && <ErrorBox error={error} />}
      <h3>{data.reviews.length ? `${data.reviews.length} note(s), oldest first` : "No note yet"}</h3>
      {data.reviews.map((review) => (
        <article className="note" key={review.review_id}>
          <Badge text={review.disposition} tone="green" />
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

export function CustomerCase() {
  const { runId = "", customerId = "" } = useParams();
  const { fallback } = useWorkspace();
  const [params, setParams] = useSearchParams();
  const tab = (TABS as readonly string[]).includes(params.get("tab") ?? "") ? (params.get("tab") as Tab) : "evidence";
  const state = useLoad(() => api.customerCase(runId, customerId), [runId, customerId]);
  const data = state.data;
  return (
    <>
      <Link className="button back" to={`/runs/${runId}/customers`}>
        Back to customer queue
      </Link>
      <PageTitle title={`Customer ${customerId}`}>Observed evidence for a human reviewer. It is not a finding of misconduct.</PageTitle>
      <LoadState state={state} />
      {data && (
        <>
          <div className="stats">
            <Stat
              name="Review status"
              value={data.customer.eligibility_status !== "eligible" ? "Not ranked" : data.customer.selected_for_review ? "Selected" : "Not selected"}
              note={
                data.customer.rank
                  ? `Rank ${number(data.customer.rank)} / ${data.customer.support_counts.mature_sale_lines} mature sale lines`
                  : `${data.customer.support_counts.mature_sale_lines} mature sale line(s): too little history to rank`
              }
            />
            <Stat
              name={fallback ? "Return-rate percentile" : "Reference percentile"}
              value={<span title={SCORE_HELP}>{data.customer.risk_score === null ? "n/a" : data.customer.risk_score.toFixed(1)}</span>}
              note={
                fallback || !data.customer.baseline_rank
                  ? "Against training scores; not a probability"
                  : `Not a probability / return-rate rule: rank ${number(data.customer.baseline_rank)}, ${data.customer.baseline_selected ? "selected" : "not selected"} by the rule`
              }
            />
            <Stat
              name="Requested / mature units"
              value={`${data.customer.support_counts.mature_requested_units} / ${data.customer.support_counts.mature_purchased_units}`}
              note={data.customer.evidence_tags.length ? data.customer.evidence_tags.map(tagLabel).join("; ") : "None of the listed observations"}
            />
            <Stat name="Wardrobing indicator" value={label(data.wardrobing.status)} note="Separate from the model score" />
          </div>
          <div className="tabs" role="tablist" aria-label="Case sections">
            {TABS.map((name) => (
              <button
                key={name}
                type="button"
                role="tab"
                aria-selected={tab === name}
                className={tab === name ? "active" : ""}
                onClick={() => setParams(name === "evidence" ? {} : { tab: name }, { replace: true })}
              >
                {label(name)}
                {name === "notes" && data.reviews.length ? ` (${data.reviews.length})` : ""}
              </button>
            ))}
          </div>
          {tab === "evidence" && <Evidence data={data} runId={runId} />}
          {tab === "timeline" && <Timeline data={data} runId={runId} />}
          {tab === "relationships" && <Relationships data={data} runId={runId} />}
          {tab === "notes" && <Notes data={data} runId={runId} onAppended={state.reload} />}
        </>
      )}
    </>
  );
}
