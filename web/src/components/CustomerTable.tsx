import { Link } from "react-router-dom";
import type { Customer } from "../api";
import { Badge, label, number, percent } from "./ui";

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

export function reviewBadge(customer: Customer) {
  if (customer.eligibility_status !== "eligible") return <Badge text="insufficient history" tone="gray" />;
  return customer.selected_for_review ? <Badge text="selected for review" tone="amber" /> : <Badge text="not selected" tone="gray" />;
}

/** The queue table. Under baseline fallback the model and the rule are the same ranking, so the comparison column is hidden. */
export function CustomerTable({ runId, customers, fallback }: { runId: string; customers: Customer[]; fallback: boolean }) {
  return (
    <div className="tablewrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Customer / rank</th>
            <th scope="col" title={SCORE_HELP}>
              {fallback ? "Return-rate percentile" : "Reference percentile"} <span aria-hidden="true">(?)</span>
            </th>
            {!fallback && (
              <th scope="col" title="Rank of the same customer when customers are ordered by raw return rate alone">
                Return-rate rule
              </th>
            )}
            <th scope="col">Requested / mature units</th>
            <th scope="col">Measured evidence</th>
            <th scope="col">Wardrobing indicator</th>
            <th scope="col">Review</th>
            <th scope="col">Latest note</th>
          </tr>
        </thead>
        <tbody>
          {customers.map((c) => {
            const s = c.support_counts;
            return (
              <tr key={c.customer_id}>
                <td>
                  <Link className="link" to={`/runs/${runId}/customers/${c.customer_id}`}>
                    {c.customer_id}
                  </Link>
                  <small>{c.rank ? `Rank ${number(c.rank)}` : "Not ranked: fewer than 3 mature sale lines"}</small>
                </td>
                <td>{c.risk_score === null ? "n/a" : c.risk_score.toFixed(1)}</td>
                {!fallback && (
                  <td>
                    {c.baseline_rank ? `Rank ${number(c.baseline_rank)}` : "n/a"}
                    <small>{c.baseline_rank ? (c.baseline_selected ? "selected by the rule" : "not selected by the rule") : ""}</small>
                  </td>
                )}
                <td>
                  {s.mature_requested_units} / {s.mature_purchased_units}
                  <small>
                    {s.mature_purchased_units ? percent(s.mature_requested_units / s.mature_purchased_units, 0) + " of mature units" : "no mature units"} /{" "}
                    {s.mature_sale_lines} lines
                  </small>
                </td>
                <td>
                  {c.evidence_tags.length ? (
                    c.evidence_tags.map((tag) => (
                      <span key={tag} className="tagline">
                        {tagLabel(tag)}
                      </span>
                    ))
                  ) : (
                    <span className="muted">none of the listed observations</span>
                  )}
                </td>
                <td>
                  <Badge text={c.wardrobing_status} tone={c.wardrobing_status === "elevated" ? "amber" : "gray"} />
                </td>
                <td>{reviewBadge(c)}</td>
                <td>{c.latest_disposition ? <Badge text={c.latest_disposition} tone="green" /> : <span className="muted">no note</span>}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
