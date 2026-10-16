import { describe, expect, it } from "vitest";
import type { Customer, Run, Style } from "./api";
import { clearedHeavyReturner, earlierDecisionNote, groupByCommunity, headlinePair, historyNote, latestSnapshotRun, snapshotDate, stepper, thresholdFor } from "./derive";

const run = (over: Partial<Run>): Run =>
  ({
    run_id: "run-1", dataset_id: "d", world_id: "W1", model_id: "m", model_kind: "supervised", status: "succeeded", stage: "done", progress: 1,
    cutoff: "2026-09-09T18:29:59Z", created_at: "2026-10-01T10:00:00Z", completed_at: "2026-10-01T10:00:50Z", error: null, eligible_count: 100,
    excluded_count: 5, selected_count: 5, model_only_count: 1, baseline_only_count: 1, warnings: [], review_budget: 5, threshold_score: 95,
    median_score: 50, mean_return_rate: 0.2, eligible_requested_units: 20, eligible_purchased_units: 100, graph_edges: 3, heavy_returner_cutoff: 0.4,
    community_count: 1, ring_count: 1, memos: null, styles_with_verdict: 2,
    stage_log: [
      { stage: "validate", at: "2026-10-01T10:00:00Z" }, { stage: "features", at: "2026-10-01T10:00:05Z" }, { stage: "eligibility", at: "2026-10-01T10:00:20Z" },
      { stage: "scoring", at: "2026-10-01T10:00:25Z" }, { stage: "evidence", at: "2026-10-01T10:00:30Z" }, { stage: "publish", at: "2026-10-01T10:00:45Z" },
    ],
    ...over,
  }) as Run;
const customer = (over: Partial<Customer>): Customer =>
  ({
    customer_id: "W1-C1", eligibility_status: "eligible", raw_score: 1, risk_score: 50, rank: 50, selected_for_review: false, baseline_rank: 50, baseline_selected: false,
    support_counts: { mature_sale_lines: 9, mature_purchased_units: 10, mature_requested_units: 5, all_requested_units: 5 }, evidence_tags: [], wardrobing_status: "no_elevated_signal",
    latest_disposition: null, basket_expectation: null, cleared_reason: "below_threshold", community: null, tier: "LOW", gate_outcome: "WARNING", primary_signals: [],
    workflow: { state: "auto_logged", opened_by: null, opened_at: null, decided_by: null, decided_at: null }, ...over,
  }) as Customer;
const style = (over: Partial<Style>): Style =>
  ({
    style_id: "S1", category: "jacket", state: "quality", mature_sale_lines: 40, purchased_units: 100, requested_units: 30, unique_returners: 20, raw_return_rate: 0.3,
    shrunk_return_rate: 0.25, damage_share: 0.4, claim_share: 0.1, linked_claim_share: 0, linked_claimers: 0, quality_signal: true, targeting_signal: false, name: "Brand jacket",
    median_return_day: 3, share_in_last_five_days: 0.1, flagged_returner_share: { numerator: 2, denominator: 20, share: 0.1 }, ring_returners: 0, median_returner_score: 50,
    reason_codes: [], ...over,
  }) as Style;

describe("derived rules", () => {
  it("maps the eight real stages onto four steps with elapsed times from the stage log", () => {
    const steps = stepper(run({}));
    expect(steps.map((s) => [s.name, s.status, s.seconds])).toEqual([
      ["ingest", "done", 5], ["features", "done", 20], ["detection", "done", 5], ["investigation", "done", 20],
    ]);
    const running = stepper(run({ status: "running", completed_at: null, stage_log: [{ stage: "validate", at: "2026-10-01T10:00:00Z" }, { stage: "features", at: "2026-10-01T10:00:05Z" }] }));
    expect(running.map((s) => s.status)).toEqual(["done", "active", "waiting", "waiting"]);
    const stopped = stepper(run({ status: "interrupted", stage_log: [{ stage: "validate", at: "2026-10-01T10:00:00Z" }] }));
    expect(stopped.map((s) => s.status)).toEqual(["stopped", "stopped", "stopped", "stopped"]);
    expect(stepper(run({ status: "queued", stage_log: [], completed_at: null })).every((s) => s.status === "waiting")).toBe(true);
  });
  it("calls a customer a cleared heavy returner only outside the queue and at or above the run's cutoff", () => {
    const r = run({});
    expect(clearedHeavyReturner(customer({}), r)).toBe(true);                                       // 5 of 10 = 50% >= 40%
    expect(clearedHeavyReturner(customer({ selected_for_review: true }), r)).toBe(false);
    expect(clearedHeavyReturner(customer({ support_counts: { mature_sale_lines: 9, mature_purchased_units: 10, mature_requested_units: 3, all_requested_units: 3 } }), r)).toBe(false);
    expect(clearedHeavyReturner(customer({}), run({ heavy_returner_cutoff: null }))).toBe(false);
  });
  it("groups a community's members under its first member and keeps everyone else in rank order", () => {
    const ring = { id: "W1-L1", kind: "ring" as const, size: 2 };
    const rows = [customer({ customer_id: "a", community: ring }), customer({ customer_id: "b" }), customer({ customer_id: "c", community: ring })];
    const groups = groupByCommunity(rows);
    expect(groups.map((g) => [g.lead.customer_id, g.members.map((m) => m.customer_id)])).toEqual([["a", ["c"]], ["b", []]]);
  });
  it("pairs the highest-rate quality style with a targeting style of lower rate, or nothing", () => {
    const styles = [style({ style_id: "Q1", raw_return_rate: 0.3 }), style({ style_id: "Q2", raw_return_rate: 0.5 }), style({ style_id: "T1", state: "targeting", raw_return_rate: 0.4 }), style({ style_id: "T2", state: "targeting", raw_return_rate: 0.6 })];
    expect(headlinePair(styles)?.quality.style_id).toBe("Q2");
    expect(headlinePair(styles)?.targeting.style_id).toBe("T1");
    expect(headlinePair([style({})])).toBeNull();
  });
  it("reads the threshold for a queue size off the distribution's bins", () => {
    const bins = [{ lower: 90, at_or_above: 3 }, { lower: 95, at_or_above: 1 }, { lower: 85, at_or_above: 10 }];
    expect(thresholdFor(bins, 1)).toBe(95);
    expect(thresholdFor(bins, 5)).toBe(85);
    expect(thresholdFor([], 5)).toBeNull();
  });
});

describe("contract 1.14.0 helpers", () => {
  it("says what a cleared customer does not show, in plain words", async () => {
    const { notObserved } = await import("./derive");
    expect(notObserved({ absent_signals: ["repeat_claims", "late_returns", "supported_links"] })).toBe("no repeated transaction claims, no late returns, no linked accounts");
    expect(notObserved({ absent_signals: null })).toBe("");
  });
  it("writes totals in lakh", async () => {
    const { inrLakh } = await import("./derive");
    expect(inrLakh(5214288)).toBe("INR 52.1 lakh");
    expect(inrLakh(null)).toBe("n/a");
  });
  it("builds a case hand-off with the evidence, the return lines and the notes, and no truth", async () => {
    const { caseSummary } = await import("./derive");
    const text = caseSummary({
      run_id: "run-1", world_id: "W1", model_id: "m-1",
      customer: {
        customer_id: "W1-C1", rank: 3, risk_score: 99.5, tier: "HIGH", gate_outcome: "HOLD", baseline_rank: 900, baseline_selected: false,
        basket_expectation: { actual_units: 12, purchased_units: 29, expected_units: 5.7, sd: 2, band_low: 1.5, band_high: 10, z: 2.9 },
        workflow: { state: "in_review", opened_by: "Asha", opened_at: "2026-10-15T10:00:00Z", decided_by: null, decided_at: null },
        refunded_inr: 12345, claim_refunded_inr: 2000, primary_signals: [{ tag: "late_returns", label: "Two or more late returns" }], absent_signals: null,
      } as unknown as Customer,
      timeline: [
        { event_type: "purchase", observed_at: "2026-01-01", order_id: "O1", order_line_no: 1, sku: "S1", quantity: 1, reason_code: null, day_in_window: null, window_days: 30, line_status: "delivered", amount_inr: 1000 },
        { event_type: "return_request", observed_at: "2026-01-20T10:00:00+05:30", order_id: "O1", order_line_no: 1, sku: "S1", quantity: 1, reason_code: "changed_my_mind", day_in_window: 12, window_days: 30, line_status: "withdrawn", amount_inr: 0 },
      ],
      rules_fired: [{ label: "Return rate at or above the 90th percentile", fired: true }, { label: "Two claims", fired: false }],
      wardrobing: { status: "possible" }, community: { id: "W1-LX", kind: "ring", size: 3 },
      reviews: [{ created_at: "2026-10-15T10:00:00Z", reviewer_name: "Asha", kind: "open", disposition: "needs_investigation", note: "Checked the timing." }],
    });
    expect(text).toContain("Customer W1-C1 / world W1 / run run-1");
    expect(text).toContain("not a finding of misconduct");
    expect(text).toContain("Requested 12 of 29 mature units; expected 5.7 (normal band 1.5 to 10.0)");
    expect(text).toContain("Refunds paid INR 12,345, of which INR 2,000 on transaction claims");
    expect(text).toContain("withdrawn (not counted)");
    expect(text).toContain("Linked accounts: ring of 3 (W1-LX)");
    expect(text).toContain("Analyst rules that would have fired: Return rate at or above the 90th percentile\n");
    expect(text).toContain("Asha (open, needs investigation): Checked the timing.");
    expect(text).not.toContain("purchase");
    expect(text.toLowerCase()).not.toContain("fraud");
  });
});

describe("snapshots of one world (contract 1.15.0)", () => {
  const before = (over: object) => ({ cutoff: "2026-08-09T18:29:59Z", run_id: "run-aug", present: true, rank: 40, risk_score: 96.1, selected_for_review: true, workflow_state: null, ...over });
  it("names a snapshot by its cutoff date in IST", () => {
    expect(snapshotDate("2026-08-09T18:29:59Z")).toBe("09 Aug 2026");
    expect(snapshotDate(null)).toBe("n/a");
  });
  it("places a customer against the previous snapshot in one phrase", () => {
    expect(historyNote({ selected_for_review: true, previous: null, earlier_decision: null })).toBeNull();
    expect(historyNote({ selected_for_review: true, previous: before({}), earlier_decision: null })).toBe("also in the 09 Aug 2026 queue (rank 40)");
    expect(historyNote({ selected_for_review: true, previous: before({ selected_for_review: false, rank: 1200 }), earlier_decision: null })).toBe(
      "new to the queue since 09 Aug 2026 (rank 1,200 then)",
    );
    expect(historyNote({ selected_for_review: false, previous: before({}), earlier_decision: null })).toBe("left the queue since 09 Aug 2026 (rank 40 then)");
    expect(historyNote({ selected_for_review: false, previous: before({ selected_for_review: false }), earlier_decision: null })).toBeNull();
    expect(historyNote({ selected_for_review: true, previous: before({ present: false, rank: null, selected_for_review: null }), earlier_decision: null })).toBe(
      "new account since 09 Aug 2026",
    );
  });
  it("says how an earlier snapshot's review ended", () => {
    const decision = { state: "rejected" as const, decided_by: "Ravi", decided_at: "2026-08-12T10:00:00Z", cutoff: "2026-08-09T18:29:59Z" };
    expect(earlierDecisionNote({ selected_for_review: true, previous: null, earlier_decision: decision })).toBe("rejected on the 09 Aug 2026 snapshot by Ravi");
  });
  it("opens the workspace on the newest run of the latest snapshot, whatever order snapshots were scored in", () => {
    const runs = [
      { run_id: "aug-rescore", status: "succeeded" as const, cutoff: "2026-08-09T18:29:59Z" },
      { run_id: "sep-running", status: "running" as const, cutoff: "2026-09-09T18:29:59Z" },
      { run_id: "sep", status: "succeeded" as const, cutoff: "2026-09-09T18:29:59Z" },
      { run_id: "sep-older", status: "succeeded" as const, cutoff: "2026-09-09T18:29:59Z" },
      { run_id: "jul", status: "succeeded" as const, cutoff: "2026-07-09T18:29:59Z" },
    ];
    expect(latestSnapshotRun(runs)?.run_id).toBe("sep");
    expect(latestSnapshotRun([])).toBeNull();
  });
});
