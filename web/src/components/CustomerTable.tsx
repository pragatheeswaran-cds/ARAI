import { Link } from "react-router-dom";
import type { Customer, PrimarySignal, Run } from "../api";
import { CLEARED_REASON, GATE_HELP, GATE_LABEL, STATE_LABEL, TIER_HELP, TIER_LABEL, clearedHeavyReturner, groupByCommunity, rawRate } from "../derive";
import { Badge, CopyId, label, number, percent } from "./ui";

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

/** Up to three plain-language chips, in the order the score breakdown ranks their families. */
export function Chips({ signals }: { signals: PrimarySignal[] }) {
  if (!signals.length) return <span className="muted">none of the listed observations</span>;
  return (
    <>
      {signals.map((signal) => (
        <span key={signal.tag} className={`chip family-${signal.family ?? "none"}`} title={signalTooltip(signal)}>
          {signal.label}
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
  return w.state === "in_review" || w.state === "awaiting_approval" ? `opened by ${w.opened_by}` : w.decided_by ? `by ${w.decided_by}` : null;
}
export function StateBadge({ customer, compact = false }: { customer: Customer; compact?: boolean }) {
  const note = workflowNote(customer);
  return (
    <>
      <Badge text={STATE_LABEL[customer.workflow.state]} className={`state-${customer.workflow.state}`} tone="gray" />
      {!compact && note && <small>{note}</small>}
    </>
  );
}

export function reviewBadge(customer: Customer) {
  if (customer.eligibility_status !== "eligible") return <Badge text="insufficient history" tone="gray" />;
  return customer.selected_for_review ? <Badge text="selected for review" tone="amber" /> : <Badge text="not selected" tone="gray" />;
}

type Props = { runId: string; customers: Customer[]; fallback: boolean; compact?: boolean; run?: Run | null; grouped?: boolean };

/** The queue table. Under baseline fallback the model and the rule are the same ranking, so the comparison column is hidden.
 *  With `grouped`, members of one community sit under their first member so a ring reads as one block. */
export function CustomerTable({ runId, customers, fallback, compact = false, run = null, grouped = false }: Props) {
  const rows = grouped ? groupByCommunity(customers).flatMap((g) => [{ c: g.lead, member: false }, ...g.members.map((c) => ({ c, member: true }))]) : customers.map((c) => ({ c, member: false }));
  return (
    <div className="tablewrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Rank / customer</th>
            <th scope="col" title={SCORE_HELP}>
              {fallback ? "Return-rate percentile" : "Score"} <span aria-hidden="true">(?)</span>
            </th>
            <th scope="col" title={TIER_HELP}>
              Tier
            </th>
            <th scope="col" title={GATE_HELP}>
              Recommendation
            </th>
            <th scope="col">Primary signals</th>
            {!compact && <th scope="col">Linked accounts</th>}
            {!fallback && !compact && (
              <th scope="col" title="Rank of the same customer when customers are ordered by raw return rate alone">
                Return-rate rule
              </th>
            )}
            <th scope="col" title="Units requested for return on mature sale lines; rejected requests count, withdrawn ones do not">
              Requested / mature units
            </th>
            {!compact && <th scope="col">Status</th>}
            {!compact && <th scope="col">Latest note</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ c, member }) => {
            const s = c.support_counts;
            const rate = rawRate(c);
            const cleared = run ? clearedHeavyReturner(c, run) : false;
            return (
              <tr key={c.customer_id} className={member ? "member" : undefined}>
                <td>
                  {c.rank ? <strong>{number(c.rank)}</strong> : <Badge text="insufficient history" tone="gray" />}{" "}
                  <Link className="link" to={`/runs/${runId}/customers/${c.customer_id}`}>
                    {c.customer_id}
                  </Link>
                  <CopyId id={c.customer_id} showId={false} />
                  {!c.rank && <small>Not ranked: fewer than 3 mature sale lines</small>}
                  {c.cleared_reason && (
                    <small>
                      {cleared ? "cleared heavy returner · " : ""}
                      {CLEARED_REASON[c.cleared_reason]}
                    </small>
                  )}
                </td>
                <td>{c.risk_score === null ? "n/a" : c.risk_score.toFixed(1)}</td>
                <td>
                  <TierBadge tier={c.tier} />
                </td>
                <td>
                  <GateBadge gate={c.gate_outcome} />
                </td>
                <td>
                  <Chips signals={c.primary_signals} />
                </td>
                {!compact && (
                  <td>
                    {c.community ? (
                      <>
                        <Badge text={c.community.kind} tone={c.community.kind === "ring" ? "amber" : "gray"} />
                        <small>
                          <Link to={`/runs/${runId}/customers?show=all&community_id=${encodeURIComponent(c.community.id)}`}>{c.community.size} accounts</Link>
                        </small>
                      </>
                    ) : (
                      <span className="muted">none</span>
                    )}
                  </td>
                )}
                {!fallback && !compact && (
                  <td>
                    {c.baseline_rank ? `Rank ${number(c.baseline_rank)}` : "n/a"}
                    <small>{c.baseline_rank ? (c.baseline_selected ? "selected by the rule" : "not selected by the rule") : ""}</small>
                  </td>
                )}
                <td>
                  {s.mature_requested_units} / {s.mature_purchased_units}
                  <small>
                    {rate !== null ? percent(rate, 0) + " of mature units" : "no mature units"} / {s.mature_sale_lines} lines
                  </small>
                </td>
                {!compact && (
                  <td>
                    <StateBadge customer={c} />
                  </td>
                )}
                {!compact && (
                  <td>{c.latest_disposition ? <Badge text={c.latest_disposition} tone="green" /> : <span className="muted">no note</span>}</td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
