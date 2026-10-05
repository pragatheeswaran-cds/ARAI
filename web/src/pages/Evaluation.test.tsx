import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, type Experiment, type Metric } from "../api";
import { workerState } from "./Datasets";
import { Evaluation } from "./Evaluation";

// Every name and scope below is deliberately not the wording the report uses: the page must find numbers by
// code, ranking and slice alone (API contract 1.3.0).
const metric = (code: string, value: number | null, ranking: string | null, slice: string, over: Partial<Metric> = {}): Metric => ({
  code, ranking, slice, name: "reworded " + code, scope: "reworded scope", value, numerator: null, denominator: null, lower_95: null, upper_95: null, ...over,
});
const ranking = (id: string, slice: string, precision: number, household: number): Metric[] => [
  metric("precision", precision, id, slice, { numerator: precision * 1000, denominator: 1000 }),
  metric("recall", 0.6, id, slice),
  metric("review_rate.legit_heavy_returner", 0.07, id, slice),
  metric("review_rate.defective_product_buyer", 0.02, id, slice),
  metric("review_rate.benign_household", household, id, slice),
  metric("recall.temporary_use_return", 0.68, id, slice),
];
const report: Experiment = {
  summary: { experiment_id: "EXP", config_hash: "h", selection_status: "selected", selected_model_id: "m-0123456789abcdef0123", selected_candidate_id: "hgb_leaf15",
    final_test_status: "passed" },
  synthetic_only: true,
  baseline_metrics: ranking("raw_return_rate", "validation", 0.243, 0.031),
  candidates: [{ candidate_id: "hgb_leaf15", ordinal: 2, status: "passed", reasons: [], metrics: ranking("hgb_leaf15", "validation", 0.707, 0.019) }],
  per_world_metrics: [metric("precision", 0.252, "raw_return_rate", "world:W2201"), metric("precision", 0.703, "hgb_leaf15", "world:W2201")],
  sensitivity_metrics: [
    metric("precision", 0.972, "hgb_leaf15", "budget:0.01"), metric("recall", 0.174, "hgb_leaf15", "budget:0.01"),
    metric("precision", 0.325, "raw_return_rate", "budget:0.01"), metric("recall", 0.058, "raw_return_rate", "budget:0.01"),
    metric("precision", 0.715, "hgb_leaf15", "test"), metric("precision", 0.239, "raw_return_rate", "test"),
  ],
  style_metrics: [], wardrobing_metrics: [], coverage_limitations: ["A limitation in plain words."], report_only_evidence_metrics: true,
  reference_metrics: [
    ...ranking("analyst_rulebook", "validation", 0.353, 0.034),
    metric("calibration.best_supervised_precision", 0.694, null, "calibration", { lower_95: 0.75, upper_95: 0.85 }),
    metric("ablation.all", 0.694, "hgb_leaf15", "ablation"), metric("ablation.without_claims", 0.552, "hgb_leaf15", "ablation"),
    metric("ablation.without_timing", 0.561, "hgb_leaf15", "ablation"), metric("ablation.without_claims_and_timing", 0.384, "hgb_leaf15", "ablation"),
    metric("ablation.rule", 0.237, "raw_return_rate", "ablation"),
    metric("group_review_rate.repeat_genuine_claimant", 0.158, "hgb_leaf15", "honest_groups"),
    metric("group_review_rate.repeat_genuine_claimant", 0.067, "raw_return_rate", "honest_groups"),
    metric("group_review_rate.benign_household", 0.02, "hgb_leaf15", "honest_groups"),
    metric("group_review_rate.benign_household", 0.039, "raw_return_rate", "honest_groups"),
    metric("precision", 0.144, "raw_return_rate", "stress:W2505", { scope: "W2505: per-account action rate x0.5" }),
    metric("precision", 0.523, "hgb_leaf15", "stress:W2505"), metric("gate_passed", 1, "hgb_leaf15", "stress:W2505"),
    metric("precision", 0.441, "raw_return_rate", "stress:W2506", { scope: "W2506: per-account action rate x2" }),
    metric("precision", 0.846, "hgb_leaf15", "stress:W2506"), metric("gate_passed", 1, "hgb_leaf15", "stress:W2506"),
  ],
  error_account: [metric("errors.false_positives.count", 416, null, "validation")],
  difficulty_calibration: { calibrated: false, levers: [], record_ref: "records/x.md" },
};

const show = async (data: Experiment) => {
  vi.spyOn(api, "experiment").mockResolvedValue(data);
  render(
    <MemoryRouter initialEntries={["/experiments/EXP"]}>
      <Routes>
        <Route path="/experiments/:experimentId" element={<Evaluation />} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByText("How often each ranking is right");
};

afterEach(() => vi.restoreAllMocks());

describe("evaluation page", () => {
  it("finds every figure by code, ranking and slice, whatever the report calls it", async () => {
    await show(report);
    const scorecard = screen.getByRole("row", { name: /Boosted trees, 15 leaves.*Candidate model/ });
    expect(within(scorecard).getByText("70.7%")).toBeInTheDocument();
    expect(within(scorecard).getByText("1.9%")).toBeInTheDocument(); // household review rate
    expect(within(screen.getByRole("row", { name: /Analyst rulebook/ })).getByText("35.3%")).toBeInTheDocument();
    expect(within(screen.getByRole("row", { name: /Top 1%/ })).getByText("97.2% / 17.4%")).toBeInTheDocument();
    expect(within(screen.getByRole("row", { name: /^W2201/ })).getByText("70.3%")).toBeInTheDocument();
    expect(screen.getByText("Boosted trees, 15 leaves: precision")).toBeInTheDocument(); // the final test, named by the page
    expect(screen.getByText("416")).toBeInTheDocument(); // a count is shown as a count
  });

  it("leads with what the result depends on and whom the model wrongly reviews", async () => {
    await show(report);
    expect(screen.getByText("Without claim and timing features")).toBeInTheDocument();
    const caveat = screen.getByText("Read this first.").parentElement!;
    expect(caveat).toHaveTextContent("55.2% without the claim features, 56.1% without the timing features and 38.4% without both");
    expect(caveat).toHaveTextContent("more often by the model (15.8%) than by the rule (6.7%); the gate has no check for them");
    expect(caveat).toHaveTextContent("from 52% to 85%");
    expect(caveat).toHaveTextContent("not met");
    const group = screen.getByRole("row", { name: /Two or more genuinely failed deliveries/ });
    expect(within(group).getByText("model reviews this group more often than the rule")).toBeInTheDocument();
    expect(within(screen.getByRole("row", { name: /Household members \(gate group\)/ })).queryByText(/more often/)).toBeNull();
    expect(screen.getByRole("row", { name: /Two or more genuinely failed deliveries/ })).not.toHaveTextContent("(gate group)");
    expect(screen.queryByRole("columnheader", { name: /Repeat genuine claimants reviewed/ })).toBeNull(); // not a gate group here
    const stress = screen.getByRole("row", { name: /W2505: per-account action rate x0.5/ });
    expect(within(stress).getByText("52.3%")).toBeInTheDocument();
    expect(within(stress).getByText("passed")).toBeInTheDocument();
  });

  it("says so when the dependence and stress steps were not run, instead of showing blanks as results", async () => {
    await show({ ...report, reference_metrics: report.reference_metrics.filter((m) => m.slice === "validation" || m.slice === "calibration") });
    expect(screen.getAllByText(/Not measured for this experiment yet/)).toHaveLength(2);
    expect(screen.getByText("Without timing features")).toBeInTheDocument();
  });
});

describe("evaluation page, experiment with a gate leg for repeat genuine claimants", () => {
  const gated: Experiment = {
    ...report,
    baseline_metrics: [...report.baseline_metrics, metric("review_rate.repeat_genuine_claimant", 0.067, "raw_return_rate", "validation")],
    candidates: [{ ...report.candidates[0], candidate_id: "hgb_leaf15_w6",
      metrics: [...ranking("hgb_leaf15_w6", "validation", 0.75, 0.017), metric("review_rate.repeat_genuine_claimant", 0.049, "hgb_leaf15_w6", "validation")] }],
    summary: { ...report.summary, selected_candidate_id: "hgb_leaf15_w6" },
    reference_metrics: report.reference_metrics.map((m) =>
      m.code === "group_review_rate.repeat_genuine_claimant" && m.ranking !== "raw_return_rate" ? { ...m, value: 0.049, ranking: "hgb_leaf15_w6" } : m),
  };
  it("shows the fourth leg in the scorecard and says the group is gated and weighted", async () => {
    await show(gated);
    expect(screen.getByRole("columnheader", { name: /Repeat genuine claimants reviewed/ })).toBeInTheDocument();
    const row = screen.getByRole("row", { name: /repeat claimants weighted x6.*Candidate model/ });
    expect(within(row).getByText("4.9%")).toBeInTheDocument();
    const caveat = screen.getByText("Read this first.").parentElement!;
    expect(caveat).toHaveTextContent("are a gate group: the model sends 4.9% of them for review against 6.7% for the rule");
    expect(caveat).toHaveTextContent("simulation truth that real data would not have");
    expect(screen.getByRole("row", { name: /Two or more genuinely failed deliveries/ })).toHaveTextContent("(gate group)");
  });
  it("shows the fifth leg, for customers with one genuine failure, when the experiment has it", async () => {
    const five: Experiment = {
      ...gated,
      baseline_metrics: [...gated.baseline_metrics, metric("review_rate.one_genuine_failure", 0.05, "raw_return_rate", "validation")],
      candidates: [{ ...gated.candidates[0], candidate_id: "hgb_leaf15_w6_s3",
        metrics: [...gated.candidates[0].metrics.map((m) => ({ ...m, ranking: "hgb_leaf15_w6_s3" })),
          metric("review_rate.one_genuine_failure", 0.015, "hgb_leaf15_w6_s3", "validation")] }],
      summary: { ...gated.summary, selected_candidate_id: "hgb_leaf15_w6_s3" },
    };
    await show(five);
    expect(screen.getByRole("columnheader", { name: /One genuine failure reviewed/ })).toBeInTheDocument();
    const row = screen.getByRole("row", { name: /repeat claimants x6, one failure x3.*Candidate model/ });
    expect(within(row).getByText("1.5%")).toBeInTheDocument();
  });
});

describe("worker state", () => {
  it("tells a working worker from a silent one and from none", () => {
    expect(workerState(1.4)).toBe("Running");
    expect(workerState(400)).toMatch(/Not seen for 400 seconds/);
    expect(workerState(null)).toMatch(/No worker has reported/);
  });
});
