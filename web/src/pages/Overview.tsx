import { Link } from "react-router-dom";
import { api } from "../api";
import { useWorkspace } from "../App";
import { CustomerTable } from "../components/CustomerTable";
import { Callout, LoadState, PageTitle, Panel, Row, Stat, ist, label, number, percent, useLoad } from "../components/ui";
import { inrLakh, snapshotDate } from "../derive";

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

  if (!run) {
    const waiting = runs.filter((r) => r.status === "queued" || r.status === "running").length;
    return (
      <>
        <PageTitle title="Overview">No scored run is available yet.</PageTitle>
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
  return (
    <>
      <PageTitle title="Overview">
        One scored snapshot of world {run.world_id}. Counts describe this run; they are not accuracy figures.
      </PageTitle>
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
              name="Decided on an earlier snapshot"
              value={number(run.previous_snapshot.approved_before + run.previous_snapshot.rejected_before)}
              note={
                <Link to={`/runs/${run.run_id}/customers?history=decided_before`}>
                  {number(run.previous_snapshot.rejected_before)} rejected, {number(run.previous_snapshot.approved_before)} approved
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
            <CustomerTable runId={run.run_id} customers={lists.data.modelOnly} fallback={false} />
          ) : (
            <p className="muted">None in this run.</p>
          )}
          <p>
            <Link to={`/runs/${run.run_id}/customers?comparison=model_only&show=all`}>See all {number(run.model_only_count)}</Link>
          </p>
          <h3>Selected by the return-rate rule, not by the model ({number(run.baseline_only_count)})</h3>
          {lists.data.baselineOnly.length ? (
            <CustomerTable runId={run.run_id} customers={lists.data.baselineOnly} fallback={false} />
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
