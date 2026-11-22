import { Link } from "react-router-dom";
import { api } from "../api";
import { useWorkspace } from "../App";
import { CustomerTable } from "../components/CustomerTable";
import { useState } from "react";
import { BLUE, Donut, LineChart, SLATE, VBars } from "../components/charts";
import { tagLabel } from "../components/CustomerTable";
import { Callout, LoadState, PageTitle, Panel, Row, Stat, ist, label, number, percent, useLoad } from "../components/ui";
import { TIER_LABEL, change, inrLakh, inrShort, periods, snapshotDate } from "../derive";

const RANGES: [number, string][] = [
  [30, "Last 30 days"],
  [90, "Last 90 days"],
  [180, "Last 180 days"],
  [365, "Last 365 days"],
  [0, "Whole history"],
];

export function Overview() {
  const { run, runs, experiment, fallback, health } = useWorkspace();
  const lists = useLoad(async () => {
    if (!run || run.status !== "succeeded") return null;
    const [next, modelOnly, baselineOnly] = await Promise.all([
      api.customers(run.run_id, { review_only: true }, null, 5),
      fallback ? null : api.customers(run.run_id, { review_only: false, comparison: "model_only" }, null, 5),
      fallback ? null : api.customers(run.run_id, { review_only: false, comparison: "baseline_only" }, null, 5),
    ]);
    return { next: next.items, modelOnly: modelOnly?.items ?? [], baselineOnly: baselineOnly?.items ?? [] };
  }, [run?.run_id, run?.status, fallback]);

  const [range, setRange] = useState(30);
  const dashboard = useLoad(async () => {
    if (!run || run.status !== "succeeded") return null;
    const [insights, curves] = await Promise.all([
      api.insights(run.run_id),
      experiment ? api.curves(experiment.experiment_id, run.run_id, 2000).catch(() => null) : null,
    ]);
    return { insights, curves };
  }, [run?.run_id, run?.status, experiment?.experiment_id]);

  if (!run) {
    const waiting = runs.filter((r) => r.status === "queued" || r.status === "running").length;
    return (
      <>
        <PageTitle title="Overview Dashboard">No scored run is available yet.</PageTitle>
        <Panel>
          <div className="empty">
            {waiting ? `${waiting} run(s) are still being scored.` : "Register a dataset and score it to see customers, styles and evidence."}
            <p>
              <Link className="button primary" to="/datasets">
                Open datasets &amp; runs
              </Link>
            </p>
            {health && !health.scoring_ready && <p>No valid scoring bundle is active, so scoring is blocked.</p>}
          </div>
        </Panel>
      </>
    );
  }

  const eligible = run.eligible_count ?? 0;
  const selected = run.selected_count ?? 0;
  const evaluation = !experiment
    ? "No experiment published"
    : `${label(experiment.selection_status)} / final test ${label(experiment.final_test_status)}`;
  const insights = dashboard.data?.insights ?? null;
  const curves = dashboard.data?.curves ?? null;
  const end = (insights?.daily.at(-1)?.date ?? run.cutoff.slice(0, 10)) as string;
  const period = insights ? periods(insights.daily, end, range) : null;
  const rate = (p: { return_lines: number; flagged_return_lines: number } | null) => (p && p.return_lines ? p.flagged_return_lines / p.return_lines : null);
  const points = (delta: number | null) => (delta === null ? null : (delta >= 0 ? "+" : "") + (delta * 100).toFixed(1) + " pp");
  const currentRate = rate(period?.current ?? null);
  const previousRate = rate(period?.previous ?? null);
  const outcomes = insights?.counts.outcomes;
  const closed = outcomes ? outcomes.cleared + outcomes.confirmed + outcomes.not_confirmed : 0;
  const atBudget = curves && curves.review_budget ? [...curves.points].filter((p) => p.k <= (curves.review_budget as number)).at(-1) ?? null : null;
  const versus = range ? `vs. previous ${range} days` : "";
  const short = (date: string) => new Date(date + "T00:00:00Z").toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: "UTC" });
  return (
    <>
      <PageTitle title="Overview Dashboard">
        Key numbers on return patterns, risk levels and the review queue for world {run.world_id}. Counts describe this snapshot; they are
        not accuracy figures.
      </PageTitle>
      <LoadState state={dashboard} />
      {insights && (
        <>
          <div className="filters">
            <label>
              Period
              <select value={range} onChange={(e) => setRange(Number(e.target.value))}>
                {RANGES.map(([days, text]) => (
                  <option key={days} value={days}>
                    {text}
                  </option>
                ))}
              </select>
            </label>
            <span className="small">
              Up to {ist(end + "T12:00:00Z", false)}, the snapshot's last day. Risk levels and the queue are as of the snapshot, whatever the period.
            </span>
          </div>
          {!insights.available && (
            <Callout>This run was scored before daily figures were stored. Score the snapshot again (Configuration) to see trends, channels and categories.</Callout>
          )}
          <div className="stats">
            <Stat
              name="Total Returns"
              value={number(period?.current.return_lines ?? 0)}
              note={[change(period?.current.return_lines ?? 0, period?.previous?.return_lines), versus].filter(Boolean).join(" ") || "return lines requested"}
            />
            <Stat
              name="Suspected Return Rate"
              value={percent(currentRate)}
              note={
                currentRate !== null && previousRate !== null
                  ? `${points(currentRate - previousRate)} ${versus}`
                  : "share of return lines from customers selected for review"
              }
            />
            <Stat name="Suspected Customers" value={number(selected)} note="selected for review in this snapshot" />
            <Stat
              name="False Positive Rate"
              value={closed ? percent((outcomes!.cleared + outcomes!.not_confirmed) / closed) : "n/a"}
              note={closed ? `${number(outcomes!.cleared + outcomes!.not_confirmed)} of ${number(closed)} closed cases were cleared or not confirmed` : "no case has been closed yet"}
            />
          </div>
          <Panel title="Suspected Loss Trend" aside={<span className="small muted">refunds paid to customers selected for review, by day</span>}>
            {period && (
              <LineChart
                label="Refunds paid to customers selected for review, by day"
                format={inrShort}
                series={[
                  { name: "Current period", color: BLUE[0], points: period.current.days.map((d) => ({ x: short(d.date), y: d.flagged_refunded_inr })) },
                  ...(period.previous
                    ? [{ name: "Previous period", color: SLATE[2], dashed: true, points: period.previous.days.map((d) => ({ x: short(d.date), y: d.flagged_refunded_inr })) }]
                    : []),
                ]}
              />
            )}
            <p className="small muted">
              {inrShort(period?.current.flagged_refunded_inr ?? 0)} of {inrShort(period?.current.refunded_inr ?? 0)} refunded in the period went to
              customers selected for review. A refund to a selected customer is not a confirmed loss.
            </p>
          </Panel>
          <div className="three">
            <Panel title="Risk Level Distribution">
              <Donut
                center={number(insights.counts.tiers.CRITICAL + insights.counts.tiers.HIGH)}
                sub="in the queue"
                format={(value) => number(value)}
                slices={(["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const).map((tier, index) => ({ name: TIER_LABEL[tier], value: insights.counts.tiers[tier] ?? 0, color: SLATE[index] }))}
              />
            </Panel>
            <Panel title="Pattern Distribution">
              <VBars
                label="Share of the customers selected for review with each observed pattern"
                format={(value) => percent(selected ? value / selected : null, 0)}
                bars={[
                  ...Object.entries(insights.counts.tags)
                    .sort((x, y) => y[1] - x[1])
                    .map(([tag, value]) => ({ name: tagLabel(tag), value })),
                  { name: "in a ring", value: insights.counts.in_ring },
                  { name: "wardrobing indicator elevated", value: insights.counts.wardrobing_elevated },
                ]}
              />
              <p className="small muted">Share of the {number(selected)} customers selected for review; a customer can show several patterns.</p>
            </Panel>
            <Panel title="Suspected Returns by Channel">
              <Donut
                center={number(insights.channels.reduce((sum, c) => sum + c.flagged_return_lines, 0))}
                sub="return lines"
                format={(value) => number(value)}
                slices={insights.channels.map((c, index) => ({ name: label(c.channel), value: c.flagged_return_lines, color: BLUE[Math.min(index, BLUE.length - 1)] }))}
              />
              <p className="small muted">Return lines of customers selected for review, whole history, by the channel of the return.</p>
            </Panel>
          </div>
          {curves && atBudget && (
            <Panel title="Measured against the synthetic truth of this world" aside={<span className="small muted">simulated data only</span>}>
              <div className="stats">
                <Stat name="True abuse rate" value={percent(curves.eligible_count ? curves.abusers / curves.eligible_count : null)} note={`${number(curves.abusers)} of ${number(curves.eligible_count)} ranked customers`} />
                <Stat name="Abusers in the queue" value={number(atBudget.model_abusers_caught)} note={`of the first ${number(atBudget.k)} customers by rank`} />
                <Stat name="True false positive rate" value={percent(atBudget.k ? 1 - atBudget.model_abusers_caught / atBudget.k : null)} note="queued customers who are not abusers in the truth" />
                <Stat name="Return-rate rule, same budget" value={number(atBudget.baseline_abusers_caught)} note="abusers the rule's queue would hold" />
              </div>
              <Callout>
                These four numbers exist only because this world is simulated and its truth was published with the experiment. A real snapshot has no
                truth; the numbers above this panel are what a live deployment would show.
              </Callout>
            </Panel>
          )}
        </>
      )}
      <div className="stats">
        <Stat name="Eligible customers" value={number(eligible)} note="At least 3 mature sale lines" />
        <Stat
          name="Selected for review"
          value={number(selected)}
          note={eligible ? `Top 5% of eligible, rounded up (${percent(selected / eligible)})` : "No eligible customer"}
        />
        <Stat name="Insufficient history" value={number(run.excluded_count)} note="Not ranked; never treated as low risk" />
        <Stat name="Scoring mode" value={fallback ? "Baseline" : "Model"} note={fallback ? "Return-rate ranking" : label(run.model_kind)} />
      </div>
      {run.warnings.length > 0 && (
        <div className="banner" role="status">
          {run.warnings.join(" ")}
        </div>
      )}
      <div className="grid">
        <Panel title="Next customers to investigate">
          <LoadState state={lists} empty={!!lists.data && lists.data.next.length === 0}>
            No customer was selected for review in this run.
          </LoadState>
          {lists.data && lists.data.next.length > 0 && <CustomerTable runId={run.run_id} customers={lists.data.next} fallback={fallback} compact />}
          <Callout>A high return volume alone is not abuse. Product context, timing and relationships support a human decision.</Callout>
          <Link className="button primary" to={`/runs/${run.run_id}/customers`}>
            Open customer queue
          </Link>
        </Panel>
        <Panel title="Workspace context">
          <Row name="Snapshot cutoff" note="Fixed for this run; evidence is never recomputed for another date">
            {ist(run.cutoff)}
          </Row>
          <Row name="Scope / currency">Apparel / INR</Row>
          <Row name="Scored">{ist(run.completed_at)}</Row>
          <Row name="Evaluation status" note="Measured offline on simulated worlds">
            {evaluation}
          </Row>
          <p>
            <Link to="/datasets">Dataset and run lifecycle</Link>
          </p>
          {experiment && (
            <p>
              <Link to={`/experiments/${experiment.experiment_id}`}>Model comparison and evaluation</Link>
            </p>
          )}
        </Panel>
      </div>
      {run.previous_snapshot && (
        <Panel title={`Since the previous snapshot of ${run.world_id} (${snapshotDate(run.previous_snapshot.cutoff)})`}>
          <div className="stats">
            <Stat
              name="Also in the previous queue"
              value={number(run.previous_snapshot.repeat)}
              note={<Link to={`/runs/${run.run_id}/customers?history=repeat_in_queue`}>open them</Link>}
            />
            <Stat
              name="New to the queue"
              value={number(run.previous_snapshot.new)}
              note={<Link to={`/runs/${run.run_id}/customers?history=new_in_queue`}>open them</Link>}
            />
            <Stat name="Left the queue" value={number(run.previous_snapshot.left)} note="selected then, not now" />
            <Stat
              name="Closed on an earlier snapshot"
              value={number(run.previous_snapshot.confirmed_before + run.previous_snapshot.cleared_before)}
              note={
                <Link to={`/runs/${run.run_id}/customers?history=decided_before`}>
                  {number(run.previous_snapshot.confirmed_before)} confirmed, {number(run.previous_snapshot.cleared_before)} cleared
                </Link>
              }
            />
          </div>
          <Callout>
            The same customers keep their identifiers from one snapshot to the next, so their notes and earlier decisions stay with them. Each snapshot
            is scored on its own; the review runs per snapshot, so a case decided last month comes back as a new case when it is selected again, with
            the earlier decision shown on it.
          </Callout>
        </Panel>
      )}
      {run.refunds && (
        <Panel title="Refunds paid to the customers in each queue">
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Queue</th>
                  <th scope="col">Customers</th>
                  <th scope="col">Refunds paid</th>
                  <th scope="col">Of which on transaction claims</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>{fallback ? "Review set (return-rate ranking)" : "Selected by the model"}</td>
                  <td>{number(run.refunds.review_set.customers)}</td>
                  <td>{inrLakh(run.refunds.review_set.refunded_inr)}</td>
                  <td>{inrLakh(run.refunds.review_set.claim_refunded_inr)}</td>
                </tr>
                {!fallback && (
                  <tr>
                    <td>Would be selected by the return-rate rule</td>
                    <td>{number(run.refunds.rule_set.customers)}</td>
                    <td>{inrLakh(run.refunds.rule_set.refunded_inr)}</td>
                    <td>{inrLakh(run.refunds.rule_set.claim_refunded_inr)}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <Callout>
            Observed refunds from the snapshot, not losses. A refund on a transaction claim (item not received, empty package, missing parts,
            wrong item sent) is money paid where no item came back to inspect; it is not proof of abuse.
          </Callout>
        </Panel>
      )}
      {!fallback && lists.data && (
        <Panel title="Model and return-rate rule compared">
          <p className="muted">
            Both rankings were given the same review budget of {number(selected)} customers. {number(run.model_only_count)} customers are selected
            by the model and not by the rule; {number(run.baseline_only_count)} are selected by the rule and not by the model.
          </p>
          <h3>Selected by the model, not by the return-rate rule ({number(run.model_only_count)})</h3>
          {lists.data.modelOnly.length ? (
            <CustomerTable runId={run.run_id} customers={lists.data.modelOnly} fallback={false} showRule />
          ) : (
            <p className="muted">None in this run.</p>
          )}
          <p>
            <Link to={`/runs/${run.run_id}/customers?comparison=model_only&show=all`}>See all {number(run.model_only_count)}</Link>
          </p>
          <h3>Selected by the return-rate rule, not by the model ({number(run.baseline_only_count)})</h3>
          {lists.data.baselineOnly.length ? (
            <CustomerTable runId={run.run_id} customers={lists.data.baselineOnly} fallback={false} showRule />
          ) : (
            <p className="muted">None in this run.</p>
          )}
          <p>
            <Link to={`/runs/${run.run_id}/customers?comparison=baseline_only&show=all`}>See all {number(run.baseline_only_count)}</Link>
          </p>
          <Callout>
            These lists compare two rankings of the same run. They say nothing about who actually abused returns; simulated truth appears only
            on the Evaluation page.
          </Callout>
        </Panel>
      )}
      <Panel title="Investigation paths">
        <div className="three">
          <div>
            <h3>Customer context</h3>
            <p className="muted">Observed against expected returns, claims, timing, linked accounts and append-only analyst notes.</p>
            <Link className="button" to={`/runs/${run.run_id}/customers`}>
              Investigate customers
            </Link>
          </div>
          <div>
            <h3>Product explanations</h3>
            <p className="muted">Style-level quality and targeting evidence with SKU support.</p>
            <Link className="button" to={`/runs/${run.run_id}/styles`}>
              Investigate styles
            </Link>
          </div>
          <div>
            <h3>Evaluation boundary</h3>
            <p className="muted">Simulated truth, error rates and model comparison live on a separate page.</p>
            {experiment ? (
              <Link className="button" to={`/experiments/${experiment.experiment_id}`}>
                Review evaluation
              </Link>
            ) : (
              <span className="muted">No experiment published.</span>
            )}
          </div>
        </div>
      </Panel>
    </>
  );
}
