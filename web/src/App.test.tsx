import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { Customer, ExperimentSummary, Health } from "./api";
import { fallbackReason, signInMessage } from "./App";
import { eventDetail } from "./pages/People";
import { CustomerTable } from "./components/CustomerTable";
import { ist, percent } from "./components/ui";

const health = (over: Partial<Health>): Health => ({
  alive: true, scoring_ready: true, promoted_model_ready: false, model_kind: "baseline_fallback", queue_depth: 0, worker_seconds_since_seen: 1, ...over,
});
const summary = (over: Partial<ExperimentSummary>): ExperimentSummary => ({
  experiment_id: "EXP", config_hash: "h", selection_status: "selected", selected_model_id: null, selected_candidate_id: "hgb_leaf15",
  final_test_status: "not_run", git_sha: null, train_seeds: [], validation_seeds: [], test_seeds: [], demo_seeds: [], stress_seeds: [], ...over,
});
const customer = (over: Partial<Customer>): Customer => ({
  customer_id: "W1-C1", eligibility_status: "eligible", raw_score: 1.2, risk_score: 97.3, rank: 3, selected_for_review: true, baseline_rank: 40,
  baseline_selected: false, support_counts: { mature_sale_lines: 9, mature_purchased_units: 10, mature_requested_units: 4, all_requested_units: 5 },
  evidence_tags: ["repeat_claims"], wardrobing_status: "no_elevated_signal", latest_disposition: null, basket_expectation: null, cleared_reason: null, community: null, tier: "HIGH", gate_outcome: "HOLD", primary_signals: [],
  workflow: { state: "new", opened_by: null, opened_by_user_id: null, opened_at: null, decided_by: null, decided_at: null }, previous: null, earlier_decision: null, ...over,
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
  it("shows the served tier, recommendation, chips, group and workflow state with their wording", () => {
    show(false, [
      customer({
        gate_outcome: "ESCALATE",
        primary_signals: [{ tag: "repeat_claims", label: "Two or more transaction claims", family: "claims", value: 3, denominator: 5, unit: "of return lines" }],
        community: { id: "W1-L1", kind: "ring", size: 4 },
        workflow: { state: "in_review", opened_by: "Asha", opened_by_user_id: "usr-asha", opened_at: "2026-10-15T10:00:00Z", decided_by: null, decided_at: null },
      }),
    ]);
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.getByText("Escalate")).toBeInTheDocument();
    expect(screen.getByTitle(/Two or more transaction claims: 3 of 5/)).toBeInTheDocument();
    expect(screen.getByText("ring")).toBeInTheDocument();
    expect(screen.getByText("In review")).toBeInTheDocument();
    expect(screen.getByText("opened by Asha")).toBeInTheDocument();
    expect(screen.queryByText(/probability|fraud/i)).toBeNull();
  });
  it("shows a cleared heavy returner with its templated reason", () => {
    render(
      <MemoryRouter>
        <CustomerTable
          runId="run-1"
          customers={[customer({ selected_for_review: false, tier: "LOW", gate_outcome: "WARNING", cleared_reason: "size_bracketing", risk_score: 60, rank: 400 })]}
          fallback={false}
          run={{ heavy_returner_cutoff: 0.3 } as unknown as import("./api").Run}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText(/cleared heavy returner · size bracketing · consistent with the basket/)).toBeInTheDocument();
    expect(screen.getByText("Warning")).toBeInTheDocument();
  });
  it("shows an unranked customer as insufficient history, never as low risk", () => {
    show(false, [customer({ eligibility_status: "insufficient_history", rank: null, risk_score: null, raw_score: null, baseline_rank: null,
      selected_for_review: false, tier: null, gate_outcome: null })]);
    expect(screen.getByText("insufficient history")).toBeInTheDocument();
    expect(screen.getByText("not ranked")).toBeInTheDocument();
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

describe("single sign-on refusals", () => {
  it("names the cause the server gives, and never shows a bare code", () => {
    expect(signInMessage("no_role")).toContain("none of the ARAI groups");
    expect(signInMessage("sign_in_expired")).toContain("ten minutes");
    expect(signInMessage("single_sign_on_unavailable")).toContain("cannot be reached");
    expect(signInMessage("user_disabled")).toContain("disabled");
    expect(signInMessage("something_new")).toBe("The sign-in did not complete. Please try again.");
  });
});

describe("the sign-in log", () => {
  it("says what happened in words, from the entry's detail", () => {
    expect(eventDetail({ kind: "user_disabled", detail: { by: "u1", by_name: "Admin", sessions_ended: 2, reason: "left the team" } })).toBe(
      "by Admin / 2 sessions ended / reason: left the team",
    );
    expect(eventDetail({ kind: "role_change", detail: { from: ["reviewer (keycloak_group)"], to: [] } })).toBe("from reviewer (keycloak_group) to no role");
    expect(eventDetail({ kind: "refused", detail: { status: 403, permission: "administer", path: "/api/v1/admin/users" } })).toBe(
      "403 / needs administer / /api/v1/admin/users",
    );
    expect(eventDetail({ kind: "session_ended", detail: { reason: "max_age" } })).toBe("max age");
  });
});
