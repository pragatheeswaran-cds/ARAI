// Rules the UI applies itself, each in one place (frontend data plan, section 4). Every rule reads fields the API serves
// and mirrors a server rule where one exists. Nothing here changes a score, a rank or a selection.
import type { Customer, Dataset, GateOutcome, Run, Style, Tier, WorkflowState } from "./api";

/** The dataset as the run strip names it: world and purpose. */
export const datasetName = (run: Run, dataset?: Dataset | null) => (dataset ? `${run.world_id} · ${dataset.purpose.replaceAll("_", " ")}` : run.world_id);

/** The eight real stages of a run, as the stepper groups them. There is no second pass. */
export const STEPPER = [
  { name: "ingest", stages: ["validate"], title: "Ingest", detail: "Load and validate the snapshot" },
  { name: "features", stages: ["features", "eligibility"], title: "Features", detail: "Features, relationship graph, eligibility" },
  { name: "detection", stages: ["scoring"], title: "Detection", detail: "Frozen model, reference percentile, rank, review set" },
  { name: "investigation", stages: ["evidence", "publish"], title: "Investigation", detail: "Evidence, communities, attribution, publish" },
] as const;
export type Step = (typeof STEPPER)[number]["name"];

export type StepState = { name: Step; title: string; detail: string; status: "done" | "active" | "waiting" | "stopped"; seconds: number | null };

/** Per step: done, active, waiting or stopped, with the elapsed seconds derived from consecutive stage_log entries and completed_at. */
export function stepper(run: Run): StepState[] {
  const began = new Map(run.stage_log.map((entry) => [entry.stage, new Date(entry.at).getTime()]));
  const times = run.stage_log.map((entry) => new Date(entry.at).getTime());
  const end = run.completed_at ? new Date(run.completed_at).getTime() : run.status === "running" ? Date.now() : null;
  const finished = run.status === "succeeded";
  const stopped = run.status === "failed" || run.status === "interrupted";
  return STEPPER.map((step) => {
    const starts = step.stages.map((stage) => began.get(stage)).filter((t): t is number => t !== undefined);
    if (!starts.length) return { ...step, status: stopped ? "stopped" : "waiting", seconds: null };
    const start = Math.min(...starts);
    const last = Math.max(...starts);
    const next = times.filter((t) => t > last).sort((a, b) => a - b)[0];
    const stepEnd = next ?? end;
    const active = !finished && !stopped && next === undefined;
    const status = finished || next !== undefined ? "done" : stopped ? "stopped" : active ? "active" : "waiting";
    return { ...step, status, seconds: stepEnd === null || stepEnd === undefined ? null : Math.max(0, Math.round((stepEnd - start) / 1000)) };
  });
}

/** A customer outside the queue whose raw return rate is at or above the run's heavy-returner cutoff. */
export function clearedHeavyReturner(customer: Customer, run: Run): boolean {
  const s = customer.support_counts;
  return (
    customer.eligibility_status === "eligible" &&
    !customer.selected_for_review &&
    run.heavy_returner_cutoff !== null &&
    s.mature_purchased_units > 0 &&
    s.mature_requested_units / s.mature_purchased_units >= run.heavy_returner_cutoff
  );
}

export const rawRate = (customer: Customer): number | null => {
  const s = customer.support_counts;
  return s.mature_purchased_units ? s.mature_requested_units / s.mature_purchased_units : null;
};

/** The one-line cleared reason, rendered from its template key; never generated text. */
export const CLEARED_REASON: Record<NonNullable<Customer["cleared_reason"]>, string> = {
  size_bracketing: "size bracketing · consistent with the basket",
  high_return_styles: "buys high-return styles · expected rate is high",
  as_basket_predicts: "returns at the rate the basket predicts",
  below_threshold: "below the review threshold",
};

export const TIER_LABEL: Record<Tier, string> = { HIGH: "High", MEDIUM: "Medium", LOW: "Low" };
export const TIER_HELP = "Anchored to the queue, not to fixed bands: High is selected for review, Medium scores 90 or above and is not selected, Low is every other ranked customer.";
export const GATE_LABEL: Record<GateOutcome, string> = { ESCALATE: "Escalate", HOLD: "Hold", WARNING: "Warning", LOW: "Low" };
export const GATE_HELP =
  "A stated presentation rule over the run's results, not a model output. Escalate: selected and in a ring or with the wardrobing indicator elevated. Hold: selected otherwise. Warning: not selected but Medium or at or above the heavy-returner cutoff. Low: the rest.";

export const STATE_LABEL: Record<WorkflowState, string> = {
  new: "New",
  in_review: "In review",
  awaiting_approval: "Awaiting approval",
  approved: "Approved",
  rejected: "Rejected",
  auto_logged: "Auto-logged",
};

/** The style verdict: five labels, mixed_or_uncertain kept apart (decision D8). */
export const VERDICT: Record<Style["state"], { label: string; owner: string; sentence: string }> = {
  quality: { label: "Quality issue", owner: "Merchandising", sentence: "An unusual product: many returns name a quality reason." },
  targeting: { label: "Abuse target", owner: "Returns policy", sentence: "An ordinary product returned by an unusual set of buyers: linked accounts claim on it within days of each other." },
  mixed_or_uncertain: { label: "Mixed / uncertain", owner: "Merchandising and returns policy", sentence: "Elevated on both counts; read the evidence before deciding whose problem it is." },
  no_elevated_signal: { label: "Normal", owner: "No action", sentence: "Enough sales to judge, and neither signal fires." },
  insufficient_support: { label: "Not enough data", owner: "No action", sentence: "Fewer than 20 mature sale lines: the estimate leans on the category." },
  no_return_evidence: { label: "No returns", owner: "No action", sentence: "Enough sales and no return or claim at all." },
};
export const lowVolume = (style: Style) => style.state === "insufficient_support" || style.mature_sale_lines < 20;

/** The headline pair: the highest-rate quality style beside a targeting style of lower rate; null when either is missing. */
export function headlinePair(styles: Style[]): { quality: Style; targeting: Style } | null {
  const quality = styles.filter((s) => s.state === "quality" && s.raw_return_rate !== null).sort((a, b) => (b.raw_return_rate ?? 0) - (a.raw_return_rate ?? 0))[0];
  if (!quality) return null;
  const targeting = styles
    .filter((s) => s.state === "targeting" && s.raw_return_rate !== null && (s.raw_return_rate ?? 0) < (quality.raw_return_rate ?? 0))
    .sort((a, b) => (b.raw_return_rate ?? 0) - (a.raw_return_rate ?? 0))[0];
  return targeting ? { quality, targeting } : null;
}

/** The queue, grouped so the members of one community sit together under their first member (ring grouping). */
export function groupByCommunity(customers: Customer[]): { lead: Customer; members: Customer[] }[] {
  const groups: { lead: Customer; members: Customer[] }[] = [];
  const byId = new Map<string, { lead: Customer; members: Customer[] }>();
  for (const customer of customers) {
    const id = customer.community?.id;
    if (id && byId.has(id)) byId.get(id)!.members.push(customer);
    else {
      const group = { lead: customer, members: [] as Customer[] };
      groups.push(group);
      if (id) byId.set(id, group);
    }
  }
  return groups;
}

/** The score at which the queue would hold `size` customers, read off the distribution's bins (lower edges). */
export function thresholdFor(bins: { lower: number; at_or_above: number }[], size: number): number | null {
  const sorted = [...bins].sort((a, b) => b.lower - a.lower);
  for (const bin of sorted) if (bin.at_or_above >= size) return bin.lower;
  return sorted.length ? sorted[sorted.length - 1].lower : null;
}

export const seconds = (value: number | null) => (value === null ? "" : value < 60 ? `${value}s` : `${Math.floor(value / 60)}m ${value % 60}s`);

// ---------------------------------------------------------------- contract 1.14.0: what was not observed, money, hand-off
const ABSENT_PHRASE: Record<string, string> = {
  repeat_claims: "no repeated transaction claims",
  linked_claims: "no claims matched by a linked account",
  late_returns: "no late returns",
  returns_above_expected: "returns within the basket's expectation",
  supported_links: "no linked accounts",
};
/** For a customer outside the queue, the evidence it does not carry, as one clause ("no late returns, no linked accounts"). */
export function notObserved(customer: Pick<Customer, "absent_signals">): string {
  return (customer.absent_signals ?? []).map((tag) => ABSENT_PHRASE[tag] ?? tag.replace(/_/g, " ")).join(", ");
}

/** Indian rupees in lakh for the Overview's totals: 5214288 -> "INR 52.1 lakh". */
export function inrLakh(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : `INR ${(value / 100000).toFixed(1)} lakh`;
}

type CaseLike = {
  run_id: string;
  world_id: string;
  model_id: string;
  customer: Customer;
  timeline: { event_type: string; observed_at: string; order_id: string | null; order_line_no: number | null; sku: string | null; quantity: number | null; reason_code: string | null; day_in_window: number | null; window_days: number | null; line_status: string | null; amount_inr: number | null }[];
  rules_fired: { label: string; fired: boolean | null }[];
  wardrobing: { status: string };
  community: { id: string; kind: string; size: number } | null;
  reviews: { created_at: string; reviewer_name: string; kind: string; disposition: string; note: string }[];
};
const money = (v: number | null | undefined) => (v === null || v === undefined ? "n/a" : "INR " + v.toLocaleString("en-IN", { maximumFractionDigits: 2 }));
const words = (v: string | null | undefined) => (v ?? "n/a").replace(/_/g, " ");
/** A plain-text hand-off of one case for the returns-policy or service team: the evidence, the return lines and the notes. */
export function caseSummary(data: CaseLike): string {
  const c = data.customer;
  const b = c.basket_expectation;
  const w = c.workflow;
  const lines = [
    "ARAI case hand-off",
    `Customer ${c.customer_id} / world ${data.world_id} / run ${data.run_id} / model ${data.model_id}`,
    "Observed evidence for a human reviewer. It is not a finding of misconduct. Synthetic data only.",
    "",
    c.rank
      ? `Score ${c.risk_score?.toFixed(2)} (a percentile against the training scores, not a probability) / rank ${c.rank} / tier ${words(c.tier)} / recommendation ${words(c.gate_outcome)}`
      : "Not ranked: fewer than three mature sale lines",
    `Status ${words(w.state)}${w.opened_by ? `, opened by ${w.opened_by}` : ""}${w.decided_by ? `, decided by ${w.decided_by}` : ""}`,
    `Return-rate rule: ${c.baseline_rank ? `rank ${c.baseline_rank}, ${c.baseline_selected ? "selected" : "not selected"}` : "not ranked"}`,
    b ? `Requested ${b.actual_units} of ${b.purchased_units} mature units; expected ${b.expected_units.toFixed(1)}${b.band_low !== null && b.band_high !== null ? ` (normal band ${b.band_low.toFixed(1)} to ${b.band_high.toFixed(1)})` : ""}` : "No mature purchase yet",
    `Refunds paid ${money(c.refunded_inr)}, of which ${money(c.claim_refunded_inr)} on transaction claims (withdrawn and rejected requests carry none)`,
    `Primary signals: ${c.primary_signals.length ? c.primary_signals.map((s) => s.label).join("; ") : "none"}`,
    c.absent_signals?.length ? `Not observed: ${notObserved(c)}` : "",
    `Linked accounts: ${data.community ? `${data.community.kind} of ${data.community.size} (${data.community.id})` : "none"}`,
    `Wardrobing indicator: ${words(data.wardrobing.status)}`,
    `Analyst rules that would have fired: ${data.rules_fired.filter((r) => r.fired).map((r) => r.label).join("; ") || "none"}`,
    "",
    "Return lines (requested, order/line, SKU, units, reason, day in window, status, refund):",
    ...data.timeline
      .filter((e) => e.event_type !== "purchase")
      .map((e) => `- ${e.observed_at.slice(0, 10)} ${e.order_id ?? ""}/${e.order_line_no ?? ""} ${e.sku ?? ""} x${e.quantity ?? ""} ${words(e.reason_code)}${e.event_type === "transaction_claim" ? " (transaction claim)" : ""}, ${e.day_in_window !== null && e.window_days !== null ? `day ${e.day_in_window} of ${e.window_days}` : "no window day"}, ${words(e.line_status)}${e.line_status === "withdrawn" ? " (not counted)" : ""}, ${money(e.amount_inr)}`),
    "",
    "Notes, oldest first:",
    ...(data.reviews.length ? data.reviews.map((r) => `- ${r.created_at.slice(0, 16).replace("T", " ")} UTC ${r.reviewer_name} (${words(r.kind)}, ${words(r.disposition)}): ${r.note}`) : ["- none"]),
  ];
  return lines.filter((line, i) => line !== "" || lines[i - 1] !== "").join("\n") + "\n";
}

// ---------------------------------------------------------------- snapshots of one world (contract 1.15.0, decision AM-68)
/** A snapshot named by its cutoff date in IST, e.g. "09 Aug 2026" (a cutoff is the last second of that day). */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function snapshotDate(cutoff: string | null | undefined): string {
  if (!cutoff) return "n/a";
  const date = new Date(cutoff);
  if (Number.isNaN(date.getTime())) return cutoff.slice(0, 10);
  // the IST calendar date, spelt the same in every browser (locales disagree on "Sep" and "Sept")
  const local = new Date(date.getTime() + 330 * 60 * 1000);
  return `${String(local.getUTCDate()).padStart(2, "0")} ${MONTHS[local.getUTCMonth()]} ${local.getUTCFullYear()}`;
}

export const HISTORY_LABEL: Record<"all" | "new_in_queue" | "repeat_in_queue" | "decided_before", string> = {
  all: "Any",
  new_in_queue: "New to the queue since the previous snapshot",
  repeat_in_queue: "Also in the previous snapshot's queue",
  decided_before: "Decided on an earlier snapshot",
};

type HistoryLike = Pick<Customer, "selected_for_review" | "previous" | "earlier_decision">;

/** Where the customer stood in the previous snapshot, in one phrase; null when there is no previous snapshot or nothing to say
 *  (outside the queue then and now). */
export function historyNote(customer: HistoryLike): string | null {
  const before = customer.previous;
  if (!before) return null;
  const when = snapshotDate(before.cutoff);
  if (!before.present) return `new account since ${when}`;
  const rank = before.rank ? `rank ${before.rank.toLocaleString("en-IN")}` : "not ranked";
  if (customer.selected_for_review) return before.selected_for_review ? `also in the ${when} queue (${rank})` : `new to the queue since ${when} (${rank} then)`;
  return before.selected_for_review ? `left the queue since ${when} (${rank} then)` : null;
}

/** The latest earlier snapshot whose review ended in a decision, in one phrase; null without one. */
export function earlierDecisionNote(customer: HistoryLike): string | null {
  const decision = customer.earlier_decision;
  if (!decision) return null;
  return `${decision.state} on the ${snapshotDate(decision.cutoff)} snapshot by ${decision.decided_by}`;
}

/** The newest succeeded run of the latest snapshot: the workspace opens there, whatever order snapshots were scored in. */
export function latestSnapshotRun<T extends Pick<Run, "status" | "cutoff">>(runs: T[]): T | null {
  let best: T | null = null;
  for (const run of runs) {           // runs arrive newest first, so the first run of the latest cutoff is the newest of it
    if (run.status !== "succeeded") continue;
    if (!best || new Date(run.cutoff).getTime() > new Date(best.cutoff).getTime()) best = run;
  }
  return best;
}
