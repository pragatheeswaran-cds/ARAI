import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { Customer, ExperimentSummary, Health } from "./api";
import { fallbackReason } from "./App";
import { CustomerTable } from "./components/CustomerTable";
import { ist, percent } from "./components/ui";

const health = (over: Partial<Health>): Health => ({
  alive: true, scoring_ready: true, promoted_model_ready: false, model_kind: "baseline_fallback", queue_depth: 0, worker_seconds_since_seen: 1, ...over,
});
const summary = (over: Partial<ExperimentSummary>): ExperimentSummary => ({
  experiment_id: "EXP", config_hash: "h", selection_status: "selected", selected_model_id: null, selected_candidate_id: "hgb_leaf15",
  final_test_status: "not_run", ...over,
});
const customer = (over: Partial<Customer>): Customer => ({
  customer_id: "W1-C1", eligibility_status: "eligible", raw_score: 1.2, risk_score: 97.3, rank: 3, selected_for_review: true, baseline_rank: 40,
  baseline_selected: false, support_counts: { mature_sale_lines: 9, mature_purchased_units: 10, mature_requested_units: 4, all_requested_units: 5 },
  evidence_tags: ["repeat_claims"], wardrobing_status: "no_elevated_signal", latest_disposition: null, basket_expectation: null, cleared_reason: null, ...over,
});

describe("fallback banner", () => {
  it("is absent when a promoted model is ready", () => {
    expect(fallbackReason(health({ promoted_model_ready: true, model_kind: "supervised" }), summary({}))).toBeNull();
  });
  it("tells a missing selection from a failed gate and from a failed test", () => {
    expect(fallbackReason(health({}), null)).toMatch(/selection has not been completed/);
    expect(fallbackReason(health({}), summary({ selection_status: "no_selected_model" }))).toMatch(/No candidate passed/);
    expect(fallbackReason(health({}), summary({ final_test_status: "failed" }))).toMatch(/failed its final test/);
    expect(fallbackReason(health({}), summary({ final_test_status: "not_run" }))).toMatch(/final test has not been run/);
  });
  it("says scoring is blocked when no bundle is valid", () => {
    expect(fallbackReason(health({ scoring_ready: false, model_kind: null }), summary({}))).toMatch(/Scoring is blocked/);
  });
});

describe("customer table", () => {
  const show = (fallback: boolean, rows: Customer[]) =>
    render(
      <MemoryRouter>
        <CustomerTable runId="run-1" customers={rows} fallback={fallback} />
      </MemoryRouter>,
    );
  it("shows the return-rate rule beside the model rank with neutral wording", () => {
    show(false, [customer({})]);
    expect(screen.getByText("Return-rate rule")).toBeInTheDocument();
    expect(screen.getByText("not selected by the rule")).toBeInTheDocument();
    expect(screen.queryByText(/caught|missed|cleared|fraud/i)).toBeNull();
  });
  it("hides the comparison under baseline fallback and relabels the score", () => {
    show(true, [customer({})]);
    expect(screen.queryByText("Return-rate rule")).toBeNull();
    expect(screen.getByText(/Return-rate percentile/)).toBeInTheDocument();
  });
  it("shows an unranked customer as insufficient history, never as low risk", () => {
    show(false, [customer({ eligibility_status: "insufficient_history", rank: null, risk_score: null, raw_score: null, baseline_rank: null,
      selected_for_review: false })]);
    expect(screen.getByText("insufficient history")).toBeInTheDocument();
    expect(screen.getByText(/fewer than 3 mature sale lines/)).toBeInTheDocument();
    expect(screen.queryByText(/low risk/i)).toBeNull();
  });
});

describe("formatting", () => {
  it("shows a missing ratio as n/a, never as zero", () => {
    expect(percent(null)).toBe("n/a");
    expect(percent(0.5)).toBe("50.0%");
  });
  it("shows stored UTC times in India Standard Time", () => {
    expect(ist("2026-09-09T18:29:59Z")).toBe("09 Sept 2026, 23:59 IST");
  });
});
