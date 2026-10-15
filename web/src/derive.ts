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
