import { Link } from "react-router-dom";
import type { Customer, PrimarySignal, Run } from "../api";
import { CLEARED_REASON, GATE_HELP, GATE_LABEL, OUTCOME_LABEL, STATE_LABEL, TIER_HELP, TIER_LABEL, caseId, clearedHeavyReturner, earlierDecisionNote, groupByCommunity, historyNote, notObserved, rawRate } from "../derive";
import { Badge, label, number, percent, rupees, useModelDetail } from "./ui";

export const SCORE_HELP =
  "Position of this customer's score among the frozen training scores (0-100). It is not a probability of abuse and not the rank in this batch.";

const TAG_LABELS: Record<string, string> = {
  repeat_claims: "two or more claims",
  linked_claims: "claims matched by a linked account",
  late_returns: "two or more late returns",
  returns_above_expected: "returns well above expected",
  supported_links: "shares identifiers with other accounts",
};
export const tagLabel = (tag: string) => TAG_LABELS[tag] ?? label(tag);
export const TAGS = Object.keys(TAG_LABELS);

const SHARE_UNITS = new Set(["share", "share of claim lines", "share of requested units"]);
/** The value behind a chip, for its tooltip. */
export function signalTooltip(signal: PrimarySignal): string {
  if (signal.value === null) return signal.label;
  const value = SHARE_UNITS.has(signal.unit) ? percent(signal.value, 0) : signal.unit === "score" ? signal.value.toFixed(2) : number(signal.value);
  const of = signal.denominator !== null && !SHARE_UNITS.has(signal.unit) ? ` of ${number(signal.denominator)} ${signal.unit.replace(/^of /, "")}` : "";
  const family = signal.family ? ` / family: ${label(signal.family)}` : " / evidence only, not a model input";
  return `${signal.label}: ${value}${of} / tag ${signal.tag}${family}`;
}

/** The same observations in two or three words, for a queue row that stays on one line; the chip's tooltip has the full phrase. */
const SHORT_LABELS: Record<string, string> = {
  repeat_claims: "Repeat claims",
  linked_claims: "Linked claims",
  late_returns: "Late returns",
  returns_above_expected: "Above expected",
  supported_links: "Shared identifiers",
};

/** Up to three plain-language chips, in the order the score breakdown ranks their families. */
export function Chips({ signals, short = false }: { signals: PrimarySignal[]; short?: boolean }) {
  if (!signals.length) return <span className="muted">{short ? "none listed" : "none of the listed observations"}</span>;
  return (
    <>
      {signals.map((signal) => (
        <span key={signal.tag} className={`chip family-${signal.family ?? "none"}`} title={signalTooltip(signal)}>
          {short ? SHORT_LABELS[signal.tag] ?? signal.label : signal.label}
        </span>
      ))}
    </>
  );
}

export function TierBadge({ tier }: { tier: Customer["tier"] }) {
  return tier ? <Badge text={TIER_LABEL[tier]} className={`tier-${tier}`} title={TIER_HELP} /> : <span className="muted">not ranked</span>;
}
export function GateBadge({ gate }: { gate: Customer["gate_outcome"] }) {
  return gate ? <Badge text={GATE_LABEL[gate]} className={`gate-${gate}`} title={GATE_HELP} /> : <span className="muted">n/a</span>;
}
export function workflowNote(customer: Customer): string | null {
  const w = customer.workflow;
  if (w.state === "in_review" || w.state === "escalated") return `opened by ${w.opened_by}`;
  return w.decided_by ? `${w.outcome ? OUTCOME_LABEL[w.outcome] + ", " : ""}by ${w.decided_by}` : null;
}
export function StateBadge({ customer, compact = false }: { customer: Customer; compact?: boolean }) {
  const note = workflowNote(customer);
  const history = historyNote(customer);
  const decided = earlierDecisionNote(customer);
  return (
    <>
      <Badge text={STATE_LABEL[customer.workflow.state]} className={`state-${customer.workflow.state}`} tone="gray" />
      {!compact && note && <small>{note}</small>}
      {!compact && decided && <small className="history decided">{decided}</small>}
      {!compact && history && <small className="history">{history}</small>}
    </>
  );
}

export function reviewBadge(customer: Customer) {
  if (customer.eligibility_status !== "eligible") return <Badge text="insufficient history" tone="gray" />;
  return customer.selected_for_review ? <Badge text="selected for review" tone="amber" /> : <Badge text="not selected" tone="gray" />;
}

/** Row selection for bulk actions: the chosen customers and how to change them. */
export type Selection = { chosen: Set<string>; toggle: (customerId: string) => void; setAll: (customerIds: string[], on: boolean) => void };
type Props = { runId: string; customers: Customer[]; fallback: boolean; compact?: boolean; run?: Run | null; grouped?: boolean; selection?: Selection; showRule?: boolean };

/** Everything the one-line status cell leaves out, for its tooltip. */
function statusTooltip(c: Customer): string | undefined {
  const parts = [workflowNote(c), earlierDecisionNote(c), historyNote(c), c.latest_disposition ? `latest note: ${label(c.latest_disposition)}` : "no note yet"];
  return parts.filter(Boolean).join(" / ") || undefined;
}

/** The queue table: one line per case (AM-80). What a row leaves out is in its tooltips and on the case page.
 *  The return-rate rule's rank is model detail: it shows with `showRule` (a list that compares the two rankings) or when
 *  the reader has switched model detail on, and never under baseline fallback, where the model and the rule are one ranking.
 *  With `grouped`, members of one community sit under their first member so a ring reads as one block. */
export function CustomerTable({ runId, customers, fallback, compact = false, run = null, grouped = false, selection, showRule = false }: Props) {
  const [detail] = useModelDetail();
  const rule = !fallback && !compact && (showRule || detail);
  const selectable = customers.filter((c) => c.selected_for_review).map((c) => c.customer_id);
  const allChosen = !!selection && selectable.length > 0 && selectable.every((id) => selection.chosen.has(id));
  const rows = grouped ? groupByCommunity(customers).flatMap((g) => [{ c: g.lead, member: false }, ...g.members.map((c) => ({ c, member: true }))]) : customers.map((c) => ({ c, member: false }));
  return (
    <div className="tablewrap">
      <table className="dense">
        <thead>
          <tr>
            {selection && (
              <th scope="col">
                <input type="checkbox" aria-label="Select all listed cases" checked={allChosen} onChange={(e) => selection.setAll(selectable, e.target.checked)} />
              </th>
            )}
            <th scope="col" title="Position in this snapshot's ranking; 1 is the first case to read">
              Rank
            </th>
            <th scope="col" title="A case is one customer in this run; the number is the customer's own">
              Case ID
            </th>
            <th scope="col">Customer ID</th>
            <th scope="col" title={SCORE_HELP}>
              {fallback ? "Return-rate percentile" : "Score"}
            </th>
            <th scope="col" title={TIER_HELP}>
              Level
            </th>
            <th scope="col" title="Up to three observations, the one the score leans on most first. Point at one for its numbers.">
              Pattern(s)
            </th>
            {!compact && (
              <th scope="col" title="Refunds paid on refunded return lines. An asterisk marks an amount partly paid on transaction claims; point at it for the part.">
                Refunded (INR)
              </th>
            )}
            <th scope="col" title="Units requested for return on mature sale lines (rejected requests count, withdrawn ones do not) over the units bought on them">
              Return %
            </th>
            {!compact && (
              <th scope="col" title="Accounts in this customer's linked-account group, the customer included">
                Accounts
              </th>
            )}
            {!compact && (
              <th scope="col" title="Where the review stands in this snapshot. Point at it for who opened or decided it, earlier snapshots and the latest note.">
                Status
              </th>
            )}
            <th scope="col" title={GATE_HELP}>
              Next step
            </th>
            {rule && (
              <th scope="col" title="Rank of the same customer when customers are ordered by raw return rate alone">
                Return-rate rule
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ c, member }) => {
            const s = c.support_counts;
            const rate = rawRate(c);
            const cleared = run ? clearedHeavyReturner(c, run) : false;
            const why = c.cleared_reason ? `${CLEARED_REASON[c.cleared_reason]}${c.absent_signals?.length ? ` · ${notObserved(c)}` : ""}` : undefined;
            const decided = earlierDecisionNote(c);
            return (
              <tr key={c.customer_id} className={member ? "member" : undefined}>
                {selection && (
                  <td>
                    {c.selected_for_review && (
                      <input type="checkbox" aria-label={`Select ${caseId(c.customer_id)}`} checked={selection.chosen.has(c.customer_id)} onChange={() => selection.toggle(c.customer_id)} />
                    )}
                  </td>
                )}
                <td className="rank" title={c.rank ? undefined : "Not ranked: fewer than 3 mature sale lines"}>
                  {c.rank ? number(c.rank) : <span className="muted">n/a</span>}
                </td>
                <td>
                  <strong>{caseId(c.customer_id)}</strong>
                </td>
                <td title={why ? `Not selected: ${why}` : undefined}>
                  <Link className="link" to={`/runs/${runId}/customers/${c.customer_id}`}>
                    {c.customer_id}
                  </Link>
                  {!c.rank && (
                    <>
                      {" "}
                      <Badge text="insufficient history" tone="gray" title="Not ranked: fewer than 3 mature sale lines" />
                    </>
                  )}
                  {cleared && why && <small>cleared heavy returner · {why}</small>}
                </td>
                <td>{c.risk_score === null ? "n/a" : c.risk_score.toFixed(1)}</td>
                <td>
                  <TierBadge tier={c.tier} />
                </td>
                <td className="patterns">
                  <Chips signals={c.primary_signals} short />
                </td>
                {!compact && (
                  <td title={c.claim_refunded_inr ? `${rupees(c.claim_refunded_inr)} of it on transaction claims` : undefined}>
                    {c.refunded_inr !== null && c.refunded_inr !== undefined ? number(c.refunded_inr) : <span className="muted">n/a</span>}
                    {c.claim_refunded_inr ? <abbr title={`${rupees(c.claim_refunded_inr)} of it on transaction claims`}> *</abbr> : null}
                  </td>
                )}
                <td title={`${s.mature_requested_units} of ${s.mature_purchased_units} units on ${s.mature_sale_lines} mature sale lines`}>
                  {rate !== null ? percent(rate, 0) : <span className="muted">n/a</span>}{" "}
                  <span className="muted">
                    {s.mature_requested_units}/{s.mature_purchased_units}
                  </span>
                </td>
                {!compact && (
                  <td>
                    {c.community ? (
                      <>
                        <Link to={`/runs/${runId}/customers?show=all&community_id=${encodeURIComponent(c.community.id)}`}>{c.community.size}</Link>{" "}
                        <Badge text={c.community.kind} tone={c.community.kind === "ring" ? "amber" : "gray"} />
                      </>
                    ) : (
                      "1"
                    )}
                  </td>
                )}
                {!compact && (
                  <td title={statusTooltip(c)}>
                    <StateBadge customer={c} compact />
                    {decided && (
                      <>
                        {" "}
                        <Badge text={`earlier: ${label(c.earlier_decision?.outcome ?? "decided")}`} tone="gray" title={decided} />
                      </>
                    )}
                  </td>
                )}
                <td>
                  <GateBadge gate={c.gate_outcome} />
                </td>
                {rule && (
                  <td>
                    {c.baseline_rank ? `Rank ${number(c.baseline_rank)}` : "n/a"}
                    {c.baseline_rank ? <span className="muted"> {c.baseline_selected ? "selected by the rule" : "not selected by the rule"}</span> : null}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
