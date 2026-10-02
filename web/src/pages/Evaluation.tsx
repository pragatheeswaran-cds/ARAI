import { useState } from "react";
import { useParams } from "react-router-dom";
import { allPages, api, type Candidate, type Experiment, type Metric, type TruthExample } from "../api";
import { useWorkspace } from "../App";
import { Badge, Callout, LoadState, PageTitle, Panel, Row, Stat, label, number, percent, useLoad } from "../components/ui";

const SEGMENTS = [
  ["review rate, honest heavy returners", "Heavy returners"],
  ["review rate, honest defective-product buyers", "Defective-product buyers"],
  ["review rate, honest household members", "Household members"],
] as const;
const ACTIONS = [
  ["recall, deceptive nonreceipt claim", "Deceptive non-receipt claims"],
  ["recall, deceptive contents claim", "Deceptive contents claims"],
  ["recall, temporary use return", "Temporary-use returns"],
  ["recall, coordinated action", "Coordinated (ring) claims"],
] as const;
const NAMES: Record<string, string> = {
  raw_return_rate: "Return-rate rule (baseline)",
  logreg_c1: "Logistic regression",
  hgb_leaf15: "Boosted trees, 15 leaves",
  hgb_leaf31: "Boosted trees, 31 leaves",
  iforest_256: "Isolation forest, 256 samples",
  iforest_1024: "Isolation forest, 1,024 samples",
  analyst_rulebook: "Analyst rulebook",
  volume_only_logreg: "Volume-only model",
};
const ROLE_COLOR = { baseline: "#eb6834", reference: "#1baf7a", candidate: "#2a78d6" } as const;
const ROLE_LABEL = { baseline: "Return-rate rule", reference: "Report-only reference", candidate: "Candidate model" } as const;

type RowData = { id: string; name: string; role: keyof typeof ROLE_COLOR; metrics: Metric[]; status: string; reasons: string[] };

const find = (metrics: Metric[], name: string) => metrics.find((m) => m.name === name) ?? null;
const fraction = (m: Metric | null) => (m && m.numerator !== null && m.denominator !== null ? `${number(m.numerator)} / ${number(m.denominator)}` : "");

function rows(experiment: Experiment): RowData[] {
  const reference = (prefix: string): Metric[] =>
    experiment.reference_metrics.filter((m) => m.name.startsWith(prefix + ": ")).map((m) => ({ ...m, name: m.name.slice(prefix.length + 2) }));
  return [
    { id: "raw_return_rate", name: NAMES.raw_return_rate, role: "baseline", metrics: experiment.baseline_metrics, status: "comparison", reasons: [] },
    { id: "analyst_rulebook", name: NAMES.analyst_rulebook, role: "reference", metrics: reference("analyst rulebook"), status: "report only", reasons: [] },
    { id: "volume_only_logreg", name: NAMES.volume_only_logreg, role: "reference", metrics: reference("volume-only model"), status: "report only", reasons: [] },
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
  return (
    <div className="tablewrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Ranking</th>
            <th scope="col">Precision at 5%</th>
            <th scope="col">Recall</th>
            {SEGMENTS.map(([, text]) => (
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
                {SEGMENTS.map(([name]) => {
                  const m = find(row.metrics, name);
                  return (
                    <td key={name}>
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
        const isCount = m.name.endsWith("(count)");
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

function TruthReveal({ experimentId }: { experimentId: string }) {
  const { run } = useWorkspace();
  const [shown, setShown] = useState(false);
  const truth = useLoad(async () => {
    if (!shown) return null;
    // the export lists abusers first, so paging stops at the first page that reaches honest customers
    const examples: TruthExample[] = [];
    let cursor: string | null = null;
    for (let page = 0; page < 200; page++) {
      const result = await api.truth(experimentId, cursor);
      examples.push(...result.items);
      cursor = result.next_cursor;
      if (!cursor || result.items.some((item) => item.y_abuse === 0)) break;
    }
    const world = examples[0]?.customer_id.split("-")[0];
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
  const state = useLoad(() => api.experiment(experimentId), [experimentId]);
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
  const byScope = (metrics: Metric[], text: string) => metrics.filter((m) => m.scope.includes(text));
  const budgets = ["1% review budget", "5% review budget", "10% review budget"];
  const testMetrics = experiment ? byScope(experiment.sensitivity_metrics, "final test worlds") : [];
  const worlds = experiment ? Array.from(new Set(experiment.per_world_metrics.map((m) => m.scope.split(",")[0]))) : [];
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
            <Stat name="World protocol" value="10 / 5 / 5" note="Training / validation / test worlds" />
          </div>
          <Panel title="How often each ranking is right">
            <p className="muted">Measured on: {scope}.</p>
            <PrecisionChart data={data} />
            <Scorecard data={data} />
            <Callout>
              The gate: strictly higher precision than the return-rate rule and no higher review rate in each honest group, at the 5% budget. The
              heavy-returner group is defined on return rate itself, so the rule always does worst there; the household and defective-buyer groups
              are the informative checks. The rulebook and the volume-only model are references and can never be selected. Spreads come from
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
                    {ACTIONS.map(([name, text]) => (
                      <tr key={name}>
                        <th scope="row">{text}</th>
                        <td>{percent(find(baseline.metrics, name)?.value)}</td>
                        <td>{selected ? percent(find(selected.metrics, name)?.value) : "n/a"}</td>
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
                    {budgets.map((budget) => {
                      const pick = (id: string, kind: string) =>
                        experiment.sensitivity_metrics.find((m) => m.scope === budget && m.name === `${id}: ${kind}`)?.value;
                      return (
                        <tr key={budget}>
                          <th scope="row">Top {budget.split(" ")[0]}</th>
                          <td>
                            {percent(pick("raw_return_rate", "precision"))} / {percent(pick("raw_return_rate", "recall"))}
                          </td>
                          <td>{selected ? `${percent(pick(selected.id, "precision"))} / ${percent(pick(selected.id, "recall"))}` : "n/a"}</td>
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
                    {worlds.map((world) => {
                      const pick = (id: string) => experiment.per_world_metrics.find((m) => m.scope.startsWith(world + ",") && m.name === `${id}: precision`);
                      return (
                        <tr key={world}>
                          <th scope="row">{world.replace("world ", "")}</th>
                          <td>{percent(pick("raw_return_rate")?.value)}</td>
                          <td>{selected ? percent(pick(selected.id)?.value) : "n/a"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <h3>Final test</h3>
              {testMetrics.length === 0 ? (
                <p className="muted">The final test has not been run. A model is promoted only after it passes.</p>
              ) : (
                <MetricList metrics={testMetrics.filter((m) => /: (precision|recall|review rate, .*)$/.test(m.name)).map((m) => ({ ...m, name: m.name.replace(/^[a-z0-9_]+: /, (id) => (NAMES[id.slice(0, -2)] ?? id.slice(0, -2)) + ": ") }))} />
              )}
            </Panel>
          </div>
          <Panel title="Where the model is wrong, and how it differs from the rule">
            <div className="grid even">
              <div>
                <MetricList metrics={experiment.error_account.filter((m) => m.scope.includes("validation"))} />
              </div>
              <div>
                {byScope(experiment.error_account, "final test").length > 0 && <MetricList metrics={byScope(experiment.error_account, "final test")} />}
                <Callout>
                  Groups overlap and are not added up. Most false positives are honest customers with repeated genuine delivery failures. Most
                  missed abusers acted only once.
                </Callout>
              </div>
            </div>
          </Panel>
          <div className="grid">
            <Panel title="Difficulty and what the result depends on">
              <p className="muted">
                The difficulty of the simulation is a design setting with stated targets. These checks were made on training worlds before any
                validation world existed.
              </p>
              <MetricList
                metrics={experiment.reference_metrics
                  .filter((m) => m.scope.startsWith("difficulty calibration") || m.scope.startsWith("timing-feature ablation"))
                  .map((m) => (m.scope.startsWith("difficulty") ? { ...m, name: `${m.name} (target ${percent(m.lower_95, 0)} to ${percent(m.upper_95, 0)})`, lower_95: null, upper_95: null } : m))}
              />
              <Row name="Calibration levers changed">{experiment.difficulty_calibration.calibrated ? experiment.difficulty_calibration.levers.join(", ") : "None"}</Row>
              <Callout>
                The model's precision leans on when in the return window items come back. In this simulation honest customers rarely return in the
                last quarter of the window; real customers do so more often, so on real data that signal would be weaker. The figure without any
                timing feature is the one to quote as robust. Record: {experiment.difficulty_calibration.record_ref ?? "n/a"}.
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
        </>
      )}
    </>
  );
}
