import { describe, expect, it } from "vitest";
import type { Customer, Run, Style } from "./api";
import { clearedHeavyReturner, groupByCommunity, headlinePair, stepper, thresholdFor } from "./derive";

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
