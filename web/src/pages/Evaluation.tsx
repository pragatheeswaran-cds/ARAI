import { useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError, allPages, api, type Candidate, type Curves, type Experiment, type ExperimentSummary, type Metric, type TruthExample } from "../api";
import { useWorkspace } from "../App";
import { Badge, Callout, LoadState, PageTitle, Panel, Row, Stat, label, number, percent, useLoad } from "../components/ui";

// A metric is identified by code, ranking and slice (API contract 1.3.0). Its name and scope are display text:
// this page shows them and never selects by them, so the report can be reworded without a column going blank.
const RULE = "raw_return_rate";
const SEGMENTS = [
  ["review_rate.legit_heavy_returner", "Heavy returners"],
  ["review_rate.defective_product_buyer", "Defective-product buyers"],
  ["review_rate.benign_household", "Household members"],
  ["review_rate.repeat_genuine_claimant", "Repeat genuine claimants"],
  ["review_rate.one_genuine_failure", "One genuine failure"],
] as const;
const ACTIONS = [
  ["recall.deceptive_nonreceipt_claim", "Deceptive non-receipt claims"],
  ["recall.deceptive_contents_claim", "Deceptive contents claims"],
  ["recall.temporary_use_return", "Temporary-use returns"],
  ["recall.coordinated_action", "Coordinated (ring) claims"],
] as const;
const BUDGETS = [
  ["0.01", "1%"],
  ["0.05", "5%"],
  ["0.1", "10%"],
] as const;
const HONEST_GROUPS = [
  ["repeat_genuine_claimant", "Two or more genuinely failed deliveries"],
  ["one_genuine_failure", "Exactly one genuinely failed delivery"],
  ["no_genuine_failure", "No genuine delivery failure"],
  ["legit_heavy_returner", "Heavy returners"],
  ["defective_product_buyer", "Defective-product buyers"],
  ["benign_household", "Household members"],
] as const;
const TEST_MEASURES: Record<string, string> = {
  precision: "precision",
  recall: "recall",
  "review_rate.legit_heavy_returner": "heavy returners reviewed",
  "review_rate.defective_product_buyer": "defective-product buyers reviewed",
  "review_rate.benign_household": "household members reviewed",
  "review_rate.repeat_genuine_claimant": "repeat genuine claimants reviewed",
  "review_rate.one_genuine_failure": "customers with one genuine failure reviewed",
};
const NAMES: Record<string, string> = {
  raw_return_rate: "Return-rate rule (baseline)",
  logreg_c1: "Logistic regression",
  hgb_leaf15: "Boosted trees, 15 leaves",
  hgb_leaf31: "Boosted trees, 31 leaves",
  hgb_leaf15_w4: "Boosted trees, repeat claimants weighted x4",
  hgb_leaf15_w6: "Boosted trees, repeat claimants weighted x6",
  hgb_leaf15_w8: "Boosted trees, repeat claimants weighted x8",
  hgb_leaf15_w6_s2: "Boosted trees, repeat claimants x6, one failure x2",
  hgb_leaf15_w6_s3: "Boosted trees, repeat claimants x6, one failure x3",
  hgb_leaf15_w8_s3: "Boosted trees, repeat claimants x8, one failure x3",
  iforest_256: "Isolation forest, 256 samples",
  iforest_1024: "Isolation forest, 1,024 samples",
  analyst_rulebook: "Analyst rulebook",
  volume_only_logreg: "Volume-only model",
};
const ROLE_COLOR = { baseline: "#eb6834", reference: "#1baf7a", candidate: "#2a78d6" } as const;
const ROLE_LABEL = { baseline: "Return-rate rule", reference: "Report-only reference", candidate: "Candidate model" } as const;

type RowData = { id: string; name: string; role: keyof typeof ROLE_COLOR; metrics: Metric[]; status: string; reasons: string[] };

const find = (metrics: Metric[], code: string) => metrics.find((m) => m.code === code) ?? null;
const pick = (metrics: Metric[], slice: string, code: string, ranking?: string) =>
  metrics.find((m) => m.slice === slice && m.code === code && (ranking === undefined || m.ranking === ranking)) ?? null;
const fraction = (m: Metric | null) => (m && m.numerator !== null && m.denominator !== null ? `${number(m.numerator)} / ${number(m.denominator)}` : "");
const slices = (metrics: Metric[], prefix: string) =>
  Array.from(new Set(metrics.map((m) => m.slice ?? "").filter((slice) => slice.startsWith(prefix))));

function rows(experiment: Experiment): RowData[] {
  const reference = (id: string): Metric[] =>
    experiment.reference_metrics.filter((m) => m.ranking === id && (m.slice === "validation" || m.slice === "dry_run"));
  return [
    { id: RULE, name: NAMES[RULE], role: "baseline", metrics: experiment.baseline_metrics, status: "comparison", reasons: [] },
    { id: "analyst_rulebook", name: NAMES.analyst_rulebook, role: "reference", metrics: reference("analyst_rulebook"), status: "report only", reasons: [] },
    { id: "volume_only_logreg", name: NAMES.volume_only_logreg, role: "reference", metrics: reference("volume_only_logreg"), status: "report only", reasons: [] },
    ...experiment.candidates.map((c: Candidate) => ({
      id: c.candidate_id,
      name: NAMES[c.candidate_id] ?? c.candidate_id,
      role: "candidate" as const,
      metrics: c.metrics,
      status: c.status,
      reasons: c.reasons,
    })),
  ];
}

/** Precision of every ranking at the review budget: one measure, one axis, bars from zero. The table below is the full view. */
function PrecisionChart({ data }: { data: RowData[] }) {
  const values = data.map((row) => ({ row, metric: find(row.metrics, "precision") })).filter((v) => v.metric?.value !== null && v.metric);
  const max = Math.max(0.01, ...values.map((v) => v.metric!.value as number));
  const scale = Math.min(1, Math.ceil(max * 10) / 10);
  return (
    <figure className="chart" aria-label="Precision at the 5% review budget by ranking">
      <figcaption>Of the customers each ranking sends for review, the share who really abused returns (precision at the 5% budget)</figcaption>
      <div className="legend">
        {(Object.keys(ROLE_COLOR) as (keyof typeof ROLE_COLOR)[]).map((role) => (
          <span key={role}>
            <i style={{ background: ROLE_COLOR[role] }} aria-hidden="true" /> {ROLE_LABEL[role]}
          </span>
        ))}
      </div>
      {values.map(({ row, metric }) => (
        <div className="bar-row" key={row.id} tabIndex={0} title={`${row.name}: ${percent(metric!.value)} (${fraction(metric)} reviews were abusers)`}>
          <span className="bar-name">{row.name}</span>
          <span className="bar-track">
            <span className="bar" style={{ width: `${((metric!.value as number) / scale) * 100}%`, background: ROLE_COLOR[row.role] }} />
            <span className="bar-value">{percent(metric!.value)}</span>
          </span>
        </div>
      ))}
      <div className="axis" aria-hidden="true">
        <span>0%</span>
        <span>{percent(scale / 2, 0)}</span>
        <span>{percent(scale, 0)}</span>
      </div>
    </figure>
  );
}

function Scorecard({ data }: { data: RowData[] }) {
  const segments = SEGMENTS.filter(([code]) => data.some((row) => find(row.metrics, code)));
  return (
    <div className="tablewrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Ranking</th>
            <th scope="col">Precision at 5%</th>
            <th scope="col">Recall</th>
            {segments.map(([, text]) => (
              <th scope="col" key={text} title="Share of this honest group that the ranking would send for review">
                {text} reviewed
              </th>
            ))}
            <th scope="col">Gate</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row) => {
            const precision = find(row.metrics, "precision");
            const recall = find(row.metrics, "recall");
            return (
              <tr key={row.id}>
                <th scope="row">
                  {row.name}
                  <small>{ROLE_LABEL[row.role]}</small>
                </th>
                <td>
                  {percent(precision?.value)}
                  <small>
                    {fraction(precision)}
                    {precision?.lower_95 !== null && precision?.lower_95 !== undefined ? ` / spread ${percent(precision.lower_95)} to ${percent(precision.upper_95)}` : ""}
                  </small>
                </td>
                <td>
                  {percent(recall?.value)}
                  <small>{fraction(recall)}</small>
                </td>
                {segments.map(([code]) => {
                  const m = find(row.metrics, code);
                  return (
                    <td key={code}>
                      {percent(m?.value)}
                      <small>{fraction(m)}</small>
                    </td>
                  );
                })}
                <td>
                  <Badge text={row.status} tone={row.status === "passed" ? "green" : row.status === "rejected" || row.status === "error" ? "amber" : "gray"} />
                  {row.reasons.map((reason) => (
                    <small key={reason}>{reason}</small>
                  ))}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function MetricList({ metrics }: { metrics: Metric[] }) {
  if (!metrics.length) return <p className="muted">Not available for this experiment yet.</p>;
  return (
    <>
      {metrics.map((m, i) => {
        const isCount = m.code?.endsWith(".count") ?? false;
        return (
          <Row key={i} name={m.name} note={m.scope}>
            {m.value === null ? "n/a" : isCount ? number(m.value) : percent(m.value)}
            {fraction(m) ? <span className="muted"> ({fraction(m)})</span> : null}
          </Row>
        );
      })}
    </>
  );
}

/** Honest groups: how much of each the model and the rule would send for review. The first row is not a gate group. */
function HonestGroups({ experiment }: { experiment: Experiment }) {
  const gated = (group: string) => experiment.baseline_metrics.some((m) => m.code === `review_rate.${group}`);
  const metrics = experiment.reference_metrics.filter((m) => m.slice === "honest_groups");
  if (!metrics.length) return <p className="muted">Not measured for this experiment yet (run the ablation step and publish again).</p>;
  const cell = (group: string, rule: boolean) =>
    metrics.find((m) => m.code === `group_review_rate.${group}` && (m.ranking === RULE) === rule) ?? null;
  return (
    <div className="tablewrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Honest customers</th>
            <th scope="col">Reviewed by the model</th>
            <th scope="col">Reviewed by the rule</th>
          </tr>
        </thead>
        <tbody>
          {HONEST_GROUPS.map(([group, text]) => {
            const model = cell(group, false);
            const rule = cell(group, true);
            if (!model || !rule) return null;
            const worse = model.value !== null && rule.value !== null && model.value > rule.value;
            return (
              <tr key={group}>
                <th scope="row">
                  {text}
                  {gated(group) ? " (gate group)" : ""}
                  {worse && <small>model reviews this group more often than the rule</small>}
                </th>
                <td>
                  {percent(model.value)}
                  <small>{fraction(model)}</small>
                </td>
                <td>
                  {percent(rule.value)}
                  <small>{fraction(rule)}</small>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Stress worlds: one simulation setting changed per world, scored with the frozen models. */
function StressWorlds({ experiment, selectedId }: { experiment: Experiment; selectedId: string | null }) {
  const worlds = slices(experiment.reference_metrics, "stress:");
  if (!worlds.length) return <p className="muted">Not measured for this experiment yet (run the stress step and publish again).</p>;
  return (
    <div className="tablewrap">
      <table>
        <thead>
          <tr>
            <th scope="col">World and what was changed</th>
            <th scope="col">Rule precision</th>
            <th scope="col">Model precision</th>
            <th scope="col">Gate against the rule</th>
          </tr>
        </thead>
        <tbody>
          {worlds.map((slice) => {
            const rule = pick(experiment.reference_metrics, slice, "precision", RULE);
            const model = selectedId ? pick(experiment.reference_metrics, slice, "precision", selectedId) : null;
            const gate = selectedId ? pick(experiment.reference_metrics, slice, "gate_passed", selectedId) : null;
            return (
              <tr key={slice}>
                <th scope="row">{rule?.scope ?? slice.slice("stress:".length)}</th>
                <td>{percent(rule?.value)}</td>
                <td>{model ? percent(model.value) : "n/a"}</td>
                <td>{gate ? <Badge text={gate.value === 1 ? "passed" : "not passed"} tone={gate.value === 1 ? "green" : "amber"} /> : "n/a"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Abusers caught against alerts used, both rankings, from the published truth joined to the workspace run (synthetic only).
 *  One measure per axis; the budget is a marker, the two statements at it are text; hover reads the nearest point. */
function HeroCurves({ experimentId }: { experimentId: string }) {
  const { run } = useWorkspace();
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const state = useLoad<{ curves: Curves | null; mismatch: boolean }>(async () => {
    if (!run || run.status !== "succeeded") return { curves: null, mismatch: false };
    try {
      return { curves: await api.curves(experimentId, run.run_id, 400), mismatch: false };
    } catch (failure) {
      if (failure instanceof ApiError && failure.code === "world_mismatch") return { curves: null, mismatch: true };
      throw failure;
    }
  }, [experimentId, run?.run_id]);
  if (!run) return <p className="muted">Curves need a scored run on the demonstration world; none is selected.</p>;
  if (state.data?.mismatch) return <p className="muted">The selected run is not on the snapshot whose truth was published (another world, or an earlier snapshot of the demonstration world, when fewer customers had acted), so no curve is drawn for it.</p>;
  const curves = state.data?.curves ?? null;
  if (!curves) return <LoadState state={state} />;
  const W = 640, H = 300, L = 48, R = 16, T = 12, B = 36;
  const points = curves.points;
  const maxK = curves.eligible_count || 1;
  const maxY = Math.max(1, curves.abusers);
  const x = (k: number) => L + ((W - L - R) * k) / maxK;
  const y = (v: number) => T + (H - T - B) * (1 - v / maxY);
  const path = (pick: (p: Curves["points"][number]) => number) => points.map((p, i) => `${i ? "L" : "M"}${x(p.k).toFixed(1)},${y(pick(p)).toFixed(1)}`).join(" ");
  const budget = curves.review_budget;
  const at = (k: number) => [...points].sort((a, b) => Math.abs(a.k - k) - Math.abs(b.k - k))[0];
  const atBudget = budget ? at(budget) : null;
  const shown = hover !== null ? at(hover) : atBudget;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(maxK * f));
  return (
    <>
      <figure className="chart" aria-label="Abusers caught against alerts used, model and return-rate rule">
        <figcaption>Of {number(curves.abusers)} simulated abusers among {number(curves.eligible_count)} eligible customers, how many the first k alerts of each ranking contain</figcaption>
        <div className="legend">
          <span>
            <i style={{ background: ROLE_COLOR.candidate }} aria-hidden="true" /> Selected model
          </span>
          <span>
            <i style={{ background: ROLE_COLOR.baseline }} aria-hidden="true" /> Return-rate rule
          </span>
          <span className="muted">dashed marker: the review budget of {number(budget)}</span>
        </div>
        <svg
          className="curve"
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          onMouseMove={(e) => {
            const box = e.currentTarget.getBoundingClientRect();
            const k = Math.round(((e.clientX - box.left) / box.width * W - L) / (W - L - R) * maxK);
            setHover(Math.max(1, Math.min(maxK, k)));
          }}
          onMouseLeave={() => setHover(null)}
        >
          {[0, 0.5, 1].map((f) => (
            <g key={f}>
              <line x1={L} x2={W - R} y1={y(maxY * f)} y2={y(maxY * f)} stroke="#e1e0d9" />
              <text x={L - 6} y={y(maxY * f) + 4} textAnchor="end" fontSize="11" fill="#898781">
                {number(Math.round(maxY * f))}
              </text>
            </g>
          ))}
          {ticks.map((k) => (
            <text key={k} x={x(k)} y={H - B + 16} textAnchor="middle" fontSize="11" fill="#898781">
              {number(k)}
            </text>
          ))}
          <text x={(L + W - R) / 2} y={H - 4} textAnchor="middle" fontSize="11" fill="#52514e">
            alerts used (queue size k)
          </text>
          <line x1={L} x2={W - R} y1={y(0)} y2={y(0)} stroke="#c9c8c1" />
          {budget && <line x1={x(budget)} x2={x(budget)} y1={T} y2={y(0)} stroke="#52514e" strokeDasharray="4 4" />}
          <path d={path((p) => p.baseline_abusers_caught)} fill="none" stroke={ROLE_COLOR.baseline} strokeWidth="2" />
          <path d={path((p) => p.model_abusers_caught)} fill="none" stroke={ROLE_COLOR.candidate} strokeWidth="2" />
          {shown && (
            <g>
              <line x1={x(shown.k)} x2={x(shown.k)} y1={T} y2={y(0)} stroke="#898781" strokeWidth="1" />
              <circle cx={x(shown.k)} cy={y(shown.model_abusers_caught)} r="4" fill={ROLE_COLOR.candidate} stroke="#fcfcfb" strokeWidth="2" />
              <circle cx={x(shown.k)} cy={y(shown.baseline_abusers_caught)} r="4" fill={ROLE_COLOR.baseline} stroke="#fcfcfb" strokeWidth="2" />
            </g>
          )}
        </svg>
        {shown && (
          <p className="small" role="status">
            At {number(shown.k)} alerts{budget === shown.k ? " (the budget)" : ""}: the model's queue holds {number(shown.model_abusers_caught)} abusers and{" "}
            {number(shown.model_legitimate_heavy_reviewed)} legitimate heavy returners; the rule's holds {number(shown.baseline_abusers_caught)} abusers and{" "}
            {number(shown.baseline_legitimate_heavy_reviewed)} legitimate heavy returners.
          </p>
        )}
      </figure>
      {atBudget && (
        <div className="stats">
          <Stat name="Abusers caught at the budget" value={`${number(atBudget.model_abusers_caught)} of ${number(curves.abusers)}`} note={`model / the rule catches ${number(atBudget.baseline_abusers_caught)}`} />
          <Stat
            name="Alerts spent on legitimate heavy returners"
            value={`${number(atBudget.model_legitimate_heavy_reviewed)} of ${number(curves.legitimate_heavy_returners)}`}
            note={`model / the rule spends ${number(atBudget.baseline_legitimate_heavy_reviewed)}; heavy means a rate at or above ${percent(curves.heavy_returner_cutoff, 0)}`}
          />
        </div>
      )}
      <button type="button" onClick={() => setTable((t) => !t)}>
        {table ? "Hide the table" : "Show the points as a table"}
      </button>
      {table && (
        <div className="tablewrap small-table">
          <table>
            <thead>
              <tr>
                <th scope="col">k</th>
                <th scope="col">Model: abusers</th>
                <th scope="col">Model: legitimate heavy returners</th>
                <th scope="col">Rule: abusers</th>
                <th scope="col">Rule: legitimate heavy returners</th>
              </tr>
            </thead>
            <tbody>
              {points.map((p) => (
                <tr key={p.k}>
                  <th scope="row">{number(p.k)}</th>
                  <td>{number(p.model_abusers_caught)}</td>
                  <td>{number(p.model_legitimate_heavy_reviewed)}</td>
                  <td>{number(p.baseline_abusers_caught)}</td>
                  <td>{number(p.baseline_legitimate_heavy_reviewed)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function Manifest({ summary }: { summary: ExperimentSummary }) {
  const { run, dataset } = useWorkspace();
  const seeds = (list: number[]) => (list.length ? list.join(", ") : "not in this report");
  return (
    <Panel title="Run manifest">
      <div className="manifest">
        <Row name="Experiment">{summary.experiment_id}</Row>
        <Row name="Config hash">
          <code>{summary.config_hash}</code>
        </Row>
        <Row name="Publishing commit" note="Recorded when the report was published; verification only, no refit">
          <code>{summary.git_sha ?? "not in this report (republish to record it)"}</code>
        </Row>
        <Row name="Training seeds">{seeds(summary.train_seeds)}</Row>
        <Row name="Validation seeds">{seeds(summary.validation_seeds)}</Row>
        <Row name="Test seeds">{seeds(summary.test_seeds)}</Row>
        <Row name="Demonstration seed">{seeds(summary.demo_seeds)}</Row>
        {run && (
          <Row name="Scored run" note={`bundle ${run.model_id}`}>
            <code>{run.run_id}</code>
          </Row>
        )}
        {dataset && (
          <Row name="Dataset hash" note={`${dataset.world_id} / schema ${dataset.schema_version}`}>
            <code>{dataset.manifest_hash}</code>
          </Row>
        )}
      </div>
    </Panel>
  );
}

function TruthReveal({ experimentId }: { experimentId: string }) {
  const { run } = useWorkspace();
  const [shown, setShown] = useState(false);
  const truth = useLoad(async () => {
    if (!shown) return null;
    // the export lists abusers first, so paging stops at the first page that reaches honest customers
    const examples: TruthExample[] = [];
    let cursor: string | null = null;
    let world: string | null = null;
    for (let page = 0; page < 200; page++) {
      const result = await api.truth(experimentId, cursor);
      world = result.world_id;
      examples.push(...result.items);
      cursor = result.next_cursor;
      if (!cursor || result.items.some((item) => item.y_abuse === 0)) break;
    }
    let selected: Set<string> | null = null;
    let ruleSelected: Set<string> | null = null;
    if (run && run.status === "succeeded" && run.world_id === world) {
      const [model, rule] = await Promise.all([
        allPages((cursor) => api.customers(run.run_id, { review_only: true }, cursor, 100)),
        allPages((cursor) => api.customers(run.run_id, { review_only: false, comparison: "baseline_only" }, cursor, 100)),
      ]);
      selected = new Set(model.map((c) => c.customer_id));
      ruleSelected = new Set([...rule.map((c) => c.customer_id), ...model.filter((c) => c.baseline_selected).map((c) => c.customer_id)]);
    }
    return { examples, world, selected, ruleSelected };
  }, [shown, experimentId, run?.run_id]);
  const data = truth.data;
  const abusers = data ? data.examples.filter((e) => e.y_abuse === 1) : [];
  const hit = (set: Set<string> | null) => (set ? abusers.filter((e) => set.has(e.customer_id)).length : 0);
  return (
    <Panel title="Simulation truth reveal">
      <p className="muted">
        Private labels of the simulated demonstration world. They exist only because the data is synthetic, and they are shown on this page only,
        never on a customer or style page.
      </p>
      {!shown && (
        <button type="button" onClick={() => setShown(true)}>
          Reveal simulated truth
        </button>
      )}
      {shown && <LoadState state={truth} empty={!!data && data.examples.length === 0}>No truth export was published for this experiment.</LoadState>}
      {data && data.examples.length > 0 && (
        <>
          <Row name="Simulated world">{data.world}</Row>
          <Row name="Customers who abused returns in the simulation" note="Including customers with too little history to rank">
            {number(abusers.length)}
          </Row>
          {data.selected && data.ruleSelected ? (
            <>
              <Row name="Selected by the model in the current run, and really abusers">
                {number(hit(data.selected))} of {number(data.selected.size)} ({percent(hit(data.selected) / Math.max(1, data.selected.size))})
              </Row>
              <Row name="Selected by the return-rate rule in the current run, and really abusers">
                {number(hit(data.ruleSelected))} of {number(data.ruleSelected.size)} ({percent(hit(data.ruleSelected) / Math.max(1, data.ruleSelected.size))})
              </Row>
            </>
          ) : (
            <p className="muted">Open a run of world {data.world} to see how its review list compares with this truth.</p>
          )}
          <div className="tablewrap small-table">
            <table>
              <thead>
                <tr>
                  <th scope="col">Customer</th>
                  <th scope="col">Simulated truth</th>
                  <th scope="col">What they did</th>
                  {data.selected && <th scope="col">Current run</th>}
                </tr>
              </thead>
              <tbody>
                {abusers.slice(0, 40).map((e) => (
                  <tr key={e.customer_id}>
                    <td>{e.customer_id}</td>
                    <td>abused returns</td>
                    <td>{e.action_types.map(label).join(", ")}</td>
                    {data.selected && <td>{data.selected.has(e.customer_id) ? "selected by the model" : "not selected"}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="small">First 40 of {number(abusers.length)} simulated abusers shown.</p>
        </>
      )}
    </Panel>
  );
}

export function Evaluation() {
  const { experimentId = "" } = useParams();
  const state = useLoad(() => (experimentId === "none" ? Promise.resolve(null) : api.experiment(experimentId)), [experimentId]);
  const experiment = state.data;
  if (experimentId === "none") {
    return (
      <>
        <PageTitle title="Evaluation">No experiment has been published to this service.</PageTitle>
        <Panel>
          <div className="empty">Model selection has not been completed. The return-rate ranking is the only scoring mode available.</div>
        </Panel>
      </>
    );
  }
  const data = experiment ? rows(experiment) : [];
  const summary = experiment?.summary;
  const selected = data.find((row) => row.id === summary?.selected_candidate_id) ?? null;
  const baseline = data[0];
  const scope = experiment?.baseline_metrics[0]?.scope ?? "";
  const references = experiment?.reference_metrics ?? [];
  const testMetrics = experiment ? experiment.sensitivity_metrics.filter((m) => m.slice === "test" && m.code !== null && m.code in TEST_MEASURES) : [];
  const worlds = experiment ? slices(experiment.per_world_metrics, "world:") : [];
  // what the result depends on (training worlds, out of fold)
  const all = pick(references, "ablation", "ablation.all");
  const noTiming = pick(references, "ablation", "ablation.without_timing");
  const noClaims = pick(references, "ablation", "ablation.without_claims");
  const neither = pick(references, "ablation", "ablation.without_claims_and_timing");
  const ablationRule = pick(references, "ablation", "ablation.rule");
  const floor = neither ?? noTiming;
  const target = pick(references, "calibration", "calibration.best_supervised_precision");
  const repeatModel = references.find((m) => m.slice === "honest_groups" && m.code === "group_review_rate.repeat_genuine_claimant" && m.ranking !== RULE) ?? null;
  const repeatRule = pick(references, "honest_groups", "group_review_rate.repeat_genuine_claimant", RULE);
  const repeatGated = !!experiment?.baseline_metrics.some((m) => m.code === "review_rate.repeat_genuine_claimant");
  const stress = selected
    ? slices(references, "stress:")
        .map((slice) => pick(references, slice, "precision", selected.id)?.value)
        .filter((value): value is number => typeof value === "number")
    : [];
  return (
    <>
      <PageTitle title="Evaluation">
        Offline comparison on simulated worlds. This is the only page that uses simulated truth. Nothing here is a claim about real customers.
      </PageTitle>
      <LoadState state={state} />
      {experiment && summary && (
        <>
          <div className="stats">
            <Stat
              name="Validation"
              value={summary.selection_status === "selected" ? "Model selected" : summary.selection_status === "no_selected_model" ? "No winner" : "Not completed"}
              note={summary.selected_candidate_id ? NAMES[summary.selected_candidate_id] ?? summary.selected_candidate_id : "Point-estimate gate at the 5% budget"}
            />
            <Stat name="Final test" value={label(summary.final_test_status)} note="Run once on untouched worlds; no runner-up" />
            <Stat
              name="Promoted to scoring"
              value={summary.selected_model_id ? "Yes" : "No"}
              note={summary.selected_model_id ? `Bundle ${summary.selected_model_id.slice(0, 16)}...` : "The return-rate baseline is active"}
            />
            <Stat
              name={neither ? "Without claim and timing features" : "Without timing features"}
              value={percent(floor?.value)}
              note="Same model family, training worlds: what is left without the signals this simulation makes sharp. Details below."
            />
          </div>
          <Callout>
            <strong>Read this first.</strong> Simulated data only.{" "}
            {noClaims && neither ? (
              <>
                Two signals carry the model, and how sharply they separate abusers is a setting of this simulation: how much of what a customer
                asks back is a transaction claim, and item returns made late in the return window. On training worlds the model reaches{" "}
                {percent(all?.value)} with every feature, {percent(noClaims.value)} without the claim features, {percent(noTiming?.value)} without
                the timing features and {percent(neither.value)} without both, against {percent(ablationRule?.value)} for the rule.{" "}
              </>
            ) : (
              <>
                The model's precision leans on when in the return window items come back, which this simulation makes sharper than real behaviour
                would be: without any timing feature it is {percent(noTiming?.value)} against {percent(ablationRule?.value)} for the rule on
                training worlds.{" "}
              </>
            )}
            {repeatModel && repeatRule && repeatModel.value !== null && repeatRule.value !== null && (
              <>
                {repeatModel.value > repeatRule.value ? (
                  <>
                    Honest customers whose deliveries genuinely failed more than once are sent for review more often by the model (
                    {percent(repeatModel.value)}) than by the rule ({percent(repeatRule.value)});{" "}
                    {repeatGated ? "the gate checks this group on validation and test worlds" : "the gate has no check for them"}.{" "}
                  </>
                ) : (
                  <>
                    Honest customers whose deliveries genuinely failed more than once are a gate group: the model sends{" "}
                    {percent(repeatModel.value)} of them for review against {percent(repeatRule.value)} for the rule. It was trained to
                    weigh them more heavily, which uses simulation truth that real data would not have.{" "}
                  </>
                )}
              </>
            )}
            {stress.length > 0 && (
              <>
                Across the stress worlds the model's precision runs from {percent(Math.min(...stress), 0)} to {percent(Math.max(...stress), 0)}{" "}
                as simulation settings change: quote the gap to the rule, not the level.{" "}
              </>
            )}
            {target && target.value !== null && target.lower_95 !== null && (
              <>
                The development target of {percent(target.lower_95, 0)} to {percent(target.upper_95, 0)} for the best model was{" "}
                <strong>{target.value < target.lower_95 ? "not met" : "met"}</strong> ({percent(target.value)} on training worlds), and no
                difficulty setting was changed to reach it.
              </>
            )}
          </Callout>
          <Panel title="Abusers caught against alerts used">
            <p className="muted">
              Synthetic truth of the demonstration world joined to the selected run. The marker is the review budget; the two statements at it are what
              the queue buys and what it costs.
            </p>
            <HeroCurves experimentId={experimentId} />
          </Panel>
          <Panel title="How often each ranking is right">
            <p className="muted">Measured on: {scope}.</p>
            <PrecisionChart data={data} />
            <Scorecard data={data} />
            <Callout>
              The gate: strictly higher precision than the return-rate rule and no higher review rate in each honest group shown, at the 5%
              budget. The heavy-returner group is defined on return rate itself, so the rule always does worst there; the other groups are
              the informative checks. The rulebook and the volume-only model are references and can never be selected. Spreads come from
              resampling whole simulated worlds; they are not significance tests.
            </Callout>
          </Panel>
          <div className="grid">
            <Panel title="What kinds of abuse are found">
              <p className="muted">Share of each kind of abuser caught within the 5% budget. One customer can be in more than one row.</p>
              <div className="tablewrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Kind of abuse</th>
                      <th scope="col">Return-rate rule</th>
                      <th scope="col">{selected ? selected.name : "Selected model"}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ACTIONS.map(([code, text]) => (
                      <tr key={code}>
                        <th scope="row">{text}</th>
                        <td>{percent(find(baseline.metrics, code)?.value)}</td>
                        <td>{selected ? percent(find(selected.metrics, code)?.value) : "n/a"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <h3>Other review budgets</h3>
              <div className="tablewrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Budget</th>
                      <th scope="col">Rule precision / recall</th>
                      <th scope="col">Model precision / recall</th>
                    </tr>
                  </thead>
                  <tbody>
                    {BUDGETS.map(([budget, text]) => {
                      const value = (id: string, code: string) => pick(experiment.sensitivity_metrics, `budget:${budget}`, code, id)?.value;
                      return (
                        <tr key={budget}>
                          <th scope="row">Top {text}</th>
                          <td>
                            {percent(value(RULE, "precision"))} / {percent(value(RULE, "recall"))}
                          </td>
                          <td>{selected ? `${percent(value(selected.id, "precision"))} / ${percent(value(selected.id, "recall"))}` : "n/a"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Panel>
            <Panel title="World by world">
              <div className="tablewrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Simulated world</th>
                      <th scope="col">Rule precision</th>
                      <th scope="col">Model precision</th>
                    </tr>
                  </thead>
                  <tbody>
                    {worlds.map((world) => (
                      <tr key={world}>
                        <th scope="row">{world.slice("world:".length)}</th>
                        <td>{percent(pick(experiment.per_world_metrics, world, "precision", RULE)?.value)}</td>
                        <td>{selected ? percent(pick(experiment.per_world_metrics, world, "precision", selected.id)?.value) : "n/a"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <h3>Final test</h3>
              {testMetrics.length === 0 ? (
                <p className="muted">The final test has not been run. A model is promoted only after it passes.</p>
              ) : (
                <MetricList
                  metrics={testMetrics.map((m) => ({ ...m, name: `${NAMES[m.ranking ?? ""] ?? m.ranking ?? ""}: ${TEST_MEASURES[m.code ?? ""]}` }))}
                />
              )}
            </Panel>
          </div>
          <Panel title="Where the model is wrong, and how it differs from the rule">
            <div className="grid even">
              <div>
                <MetricList metrics={experiment.error_account.filter((m) => m.slice === "validation")} />
              </div>
              <div>
                {experiment.error_account.some((m) => m.slice === "test") && <MetricList metrics={experiment.error_account.filter((m) => m.slice === "test")} />}
                <Callout>
                  Groups overlap and are not added up. Most false positives are honest customers with repeated genuine delivery failures. Most
                  missed abusers acted only once.
                </Callout>
              </div>
            </div>
          </Panel>
          <div className="grid">
            <Panel title="Honest customers sent for review">
              <p className="muted">
                Share of each honest group that would be sent for review at the 5% budget, on training worlds. Groups overlap.
              </p>
              <HonestGroups experiment={experiment} />
              <Callout>
                Honest customers whose parcels genuinely went missing or arrived wrong more than once have a record that looks like repeated
                deceptive claims, so they are the group a claim-driven model is most likely to send for review wrongly. Rows marked gate group
                are checked by the gate. Treat a claim-driven selection as a reason to look at the deliveries, not as a finding.
              </Callout>
            </Panel>
            <Panel title="Stress worlds: one setting changed per world">
              <p className="muted">The frozen models on worlds that took no part in training. Diagnostic only; nothing is selected from them.</p>
              <StressWorlds experiment={experiment} selectedId={selected?.id ?? null} />
              <Callout>
                The level moves with how often simulated abusers act; the ordering of rule and model does not. The gap is the result, not the
                percentage.
              </Callout>
            </Panel>
          </div>
          <div className="grid">
            <Panel title="Difficulty and what the result depends on">
              <p className="muted">
                The difficulty of the simulation is a design setting with stated targets. These checks were made on training worlds before any
                validation world existed.
              </p>
              <MetricList
                metrics={references
                  .filter((m) => m.slice === "calibration" || m.slice === "ablation")
                  .map((m) =>
                    m.slice === "calibration" && m.value !== null && m.lower_95 !== null && m.upper_95 !== null
                      ? {
                          ...m,
                          name: `${m.name}: target ${percent(m.lower_95, 0)} to ${percent(m.upper_95, 0)}, ${
                            m.value < m.lower_95 ? "NOT MET (below)" : m.value > m.upper_95 ? "NOT MET (above)" : "met"
                          }`,
                          lower_95: null,
                          upper_95: null,
                        }
                      : m,
                  )}
              />
              <Row name="Calibration levers changed">{experiment.difficulty_calibration.calibrated ? experiment.difficulty_calibration.levers.join(", ") : "None"}</Row>
              <Callout>
                The model leans on two things this simulation makes sharp: abusers claim far more often than deliveries really fail, and honest
                customers rarely return in the last quarter of the window. Real customers blur both, so on real data both signals would be
                weaker. The figure without either family is the floor to keep in mind. Record:{" "}
                {experiment.difficulty_calibration.record_ref ?? "n/a"}.
              </Callout>
            </Panel>
            <Panel title="Style signals and wardrobing indicator (report only)">
              <MetricList metrics={[...experiment.style_metrics, ...experiment.wardrobing_metrics]} />
              <Callout>These are reported, never gated. They are shown to an analyst as evidence and are not part of the model score.</Callout>
            </Panel>
          </div>
          <div className="grid">
            <Panel title="Limits">
              <ul>
                {experiment.coverage_limitations.map((text) => (
                  <li key={text}>{text}</li>
                ))}
              </ul>
            </Panel>
            <TruthReveal experimentId={experimentId} />
          </div>
          <Manifest summary={summary} />
        </>
      )}
    </>
  );
}
