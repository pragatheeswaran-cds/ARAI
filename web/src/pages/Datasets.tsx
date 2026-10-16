import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ApiError, allPages, api, newKey, type Dataset, type Run } from "../api";
import { useSession, useWorkspace } from "../App";
import { Badge, Callout, ErrorBox, LoadState, PageTitle, Panel, Row, ist, label, number, shortId, useLoad } from "../components/ui";
import { seconds, snapshotDate, stepper } from "../derive";

const TABLES = ["customer_master", "sku_master", "reason_code", "sales_order", "sales_order_line", "return_order", "return_order_line"];
const REQUIRED = ["manifest.json", ...TABLES.map((name) => name + ".csv")];
const POLL_MS = 2000;
const WORKER_QUIET_SECONDS = 60;

/** The worker may be a separate process; it reports in every couple of seconds and at each stage of a run. */
export function workerState(secondsSinceSeen: number | null): string {
  if (secondsSinceSeen === null) return "No worker has reported: submitted runs will wait";
  if (secondsSinceSeen > WORKER_QUIET_SECONDS) return `Not seen for ${number(Math.round(secondsSinceSeen))} seconds: runs may be waiting`;
  return "Running";
}

function Upload({ onRegistered }: { onRegistered: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [chosen, setChosen] = useState<string[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setMessage(null);
    const files = Array.from(input.current?.files ?? []);
    const names = files.map((file) => file.name);
    const missing = REQUIRED.filter((name) => !names.includes(name));
    const extra = names.filter((name) => !REQUIRED.includes(name));
    if (missing.length || extra.length || files.length !== REQUIRED.length) {
      setMessage(
        `Choose exactly these eight files. Missing: ${missing.join(", ") || "none"}. Not expected: ${extra.join(", ") || "none"}. Nothing was uploaded.`,
      );
      return;
    }
    const form = new FormData();
    form.set("manifest", await files.find((file) => file.name === "manifest.json")!.text());
    for (const table of TABLES) form.set(table, files.find((file) => file.name === table + ".csv")!, table + ".csv");
    setBusy(true);
    try {
      const dataset = await api.registerDataset(form);
      setMessage(
        `World ${dataset.world_id}, snapshot of ${snapshotDate(dataset.cutoff)}, is registered (${number(dataset.customer_count)} customers). Its content can no longer change; a later export of the same customers registers as a new snapshot of the same world.`,
      );
      if (input.current) input.current.value = "";
      onRegistered();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure : new ApiError(0, null));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit}>
      <label>
        Snapshot files: manifest.json and the seven operational CSV files
        <input ref={input} type="file" multiple accept=".csv,.json" onChange={() => setChosen(Array.from(input.current?.files ?? []).map((f) => f.name))} />
      </label>
      <ul className="checklist" aria-label="Required files">
        {REQUIRED.map((name) => {
          const present = chosen.includes(name) && !(error?.body?.details ?? []).some((d) => d.rule_id === "upload.missing_part" && d.table && name.startsWith(d.table));
          return (
            <li key={name} className={present ? "present" : "missing"}>
              {name} {present ? "" : <span className="muted">{chosen.length ? "missing" : ""}</span>}
            </li>
          );
        })}
      </ul>
      <p className="small">
        The files are validated on the server (columns, keys, references, money, chronology, hashes against the manifest). A snapshot that fails is
        rejected whole with its reasons grouped by rule; nothing is repaired, quarantined or stored.
      </p>
      <button className="primary" type="submit" disabled={busy}>
        {busy ? "Validating..." : "Validate and register"}
      </button>
      <p role="status">{message}</p>
      {error && <ErrorBox error={error} />}
    </form>
  );
}

function Stepper({ run }: { run: Run }) {
  return (
    <div className="stepper" aria-label="Stages">
      {stepper(run).map((step) => (
        <div key={step.name} className={"step " + step.status} title={step.detail}>
          <strong>{step.title}</strong>
          {step.status === "done" ? `done ${seconds(step.seconds)}` : step.status === "active" ? `running ${seconds(step.seconds)}` : step.status === "stopped" ? "stopped" : "waiting"}
        </div>
      ))}
    </div>
  );
}

function RunRow({ run, onRetry, onCancel, manage }: { run: Run; onRetry: (run: Run) => void; onCancel: (run: Run) => void; manage: boolean }) {
  const cancelled = run.status === "interrupted" && run.error?.error_code === "cancelled"; // stopped on purpose, not a failure
  const tone = run.status === "succeeded" ? "green" : cancelled ? "gray" : run.status === "failed" || run.status === "interrupted" ? "amber" : "gray";
  const active = run.status === "running" || run.status === "queued";
  return (
    <tr>
      <td>
        {shortId(run.run_id, 14)}
        <small>
          {run.world_id} snapshot {snapshotDate(run.cutoff)} / submitted {ist(run.created_at)}
        </small>
      </td>
      <td>
        <Badge text={cancelled ? "cancelled" : run.status} tone={tone} />
        <small>
          {active ? (
            <>
              stage: {label(run.stage)}
              <progress value={run.progress} max={1} aria-label="Scoring progress" />
            </>
          ) : run.completed_at ? (
            "finished " + ist(run.completed_at)
          ) : (
            ""
          )}
        </small>
        {(active || run.stage_log.length > 0) && <Stepper run={run} />}
      </td>
      <td>
        {run.model_kind === "baseline_fallback" ? "Return-rate baseline" : label(run.model_kind) + " model"}
        <small title={run.model_id}>bundle {shortId(run.model_id, 16)}</small>
      </td>
      <td>
        {run.status === "succeeded" ? (
          <>
            {number(run.eligible_count)} scored / {number(run.selected_count)} alerts
            <small>
              {number(run.excluded_count)} unranked / {run.ring_count ?? 0} ring(s) in {run.community_count ?? 0} linked group(s) / {run.styles_with_verdict ?? 0} style(s) with a
              verdict
            </small>
            {run.memos && (
              <small>
                memos: {run.memos.complete ? `${run.memos.ok} drafted, ${run.memos.unavailable} unavailable` : `${run.memos.ok + run.memos.unavailable} of ${run.memos.selected} decided`}
              </small>
            )}
          </>
        ) : run.error ? (
          <>
            {run.error.message}
            <small>
              {run.error.error_code} / request {shortId(run.error.request_id, 12)}
            </small>
          </>
        ) : (
          <span className="muted">no results until the run succeeds</span>
        )}
      </td>
      <td>
        {run.status === "succeeded" && (
          <Link className="button" to={`/runs/${run.run_id}/customers`}>
            View results
          </Link>
        )}
        {manage && (run.status === "failed" || run.status === "interrupted") && !cancelled && (
          <button type="button" onClick={() => onRetry(run)}>
            Retry with the same dataset and bundle
          </button>
        )}
        {manage && active && (
          <button type="button" onClick={() => onCancel(run)}>
            {run.status === "queued" ? "Cancel" : "Stop at the next stage"}
          </button>
        )}
      </td>
    </tr>
  );
}

export function Datasets() {
  const { health, runs, reload } = useWorkspace();
  const manage = useSession().can("manage"); // datasets and runs are the admin's (contract 1.16.0)
  const datasets = useLoad(() => allPages<Dataset>((cursor) => api.datasets(cursor)), []);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const keys = useRef(new Map<string, string>()); // one idempotency key per intended submission, reused if it is retried
  const active = runs.some((run) => run.status === "queued" || run.status === "running");
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(reload, POLL_MS);
    return () => clearInterval(timer);
  }, [active, reload]);

  const submit = async (datasetId: string, modelId?: string) => {
    if (busy) return; // a double click is one submission
    const slot = `${datasetId}|${modelId ?? "active"}`;
    if (!keys.current.has(slot)) keys.current.set(slot, newKey());
    setBusy(true);
    setError(null);
    try {
      await api.submitRun(datasetId, keys.current.get(slot)!, modelId);
      keys.current.delete(slot); // accepted: the next click is a new submission
      reload();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure : new ApiError(0, null));
    } finally {
      setBusy(false);
    }
  };
  const ready = !!health?.scoring_ready;
  const scored = new Set(runs.map((run) => run.dataset_id)); // a dataset with a run is kept; the server refuses otherwise too
  const remove = async (dataset: Dataset) => {
    if (!window.confirm(`Remove the registered snapshot of world ${dataset.world_id}? Its files are deleted; nothing was scored on it.`)) return;
    setError(null);
    try {
      await api.deleteDataset(dataset.dataset_id);
      datasets.reload();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure : new ApiError(0, null));
    }
  };
  const cancel = async (run: Run) => {
    setError(null);
    try {
      await api.cancelRun(run.run_id);
      reload();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure : new ApiError(0, null));
    }
  };

  return (
    <>
      <PageTitle title="Upload & score">
        Register an operational snapshot, then score it with the active bundle. Scoring uses frozen artifacts; nothing is trained here.
      </PageTitle>
      <div className="grid">
        <Panel title="Register a snapshot">
          {manage ? <Upload onRegistered={datasets.reload} /> : <p className="muted">Registering and scoring snapshots need the admin role.</p>}
        </Panel>
        <Panel title="Scoring readiness">
          <Row name="Service">{health ? "Reachable" : "Not reachable"}</Row>
          <Row name="Scoring bundle" note="A run binds this bundle when it is submitted">
            {!health ? "unknown" : !ready ? "None valid: scoring blocked" : health.model_kind === "baseline_fallback" ? "Return-rate baseline" : `Promoted ${label(health.model_kind ?? "")} model`}
          </Row>
          <Row name="Scoring worker" note="Runs wait in the queue until a worker takes them">
            {!health ? "unknown" : workerState(health.worker_seconds_since_seen)}
          </Row>
          <Row name="Runs waiting or being scored">{health ? number(health.queue_depth) : "unknown"}</Row>
          <Callout>
            A run keeps the dataset and the bundle it was submitted with, whatever is promoted later. A failed or interrupted run publishes nothing;
            retry creates a new run with the same bindings.
          </Callout>
        </Panel>
      </div>
      {error && <ErrorBox error={error} />}
      <Panel title="Registered datasets">
        <LoadState state={datasets} empty={!!datasets.data && datasets.data.length === 0}>
          No dataset is registered yet.
        </LoadState>
        {datasets.data && datasets.data.length > 0 && (
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">World / snapshot</th>
                  <th scope="col">Customers</th>
                  <th scope="col">History / cutoff</th>
                  <th scope="col">Validation</th>
                  <th scope="col">Manifest hash</th>
                  <th scope="col">Score</th>
                </tr>
              </thead>
              <tbody>
                {/* the snapshots of one world together, latest cutoff first (AM-68) */}
                {[...datasets.data]
                  .sort((a, b) => a.world_id.localeCompare(b.world_id) || new Date(b.cutoff).getTime() - new Date(a.cutoff).getTime())
                  .map((dataset) => (
                  <tr key={dataset.dataset_id}>
                    <td>
                      {dataset.world_id} <strong>{snapshotDate(dataset.cutoff)}</strong>
                      <small>
                        {label(dataset.purpose)} / schema {dataset.schema_version} / INR
                      </small>
                    </td>
                    <td>{number(dataset.customer_count)}</td>
                    <td>
                      {ist(dataset.history_start, false)} to {ist(dataset.cutoff)}
                    </td>
                    <td>
                      <Badge text={dataset.validation_status} tone="green" />
                    </td>
                    <td title={dataset.manifest_hash}>{shortId(dataset.manifest_hash, 16)}</td>
                    <td>
                      {manage ? (
                        <button type="button" className="primary" disabled={!ready || busy} onClick={() => submit(dataset.dataset_id)}>
                          Score with the active bundle
                        </button>
                      ) : (
                        <small>Scoring needs the admin role.</small>
                      )}
                      {manage && !ready && <small>Blocked: no valid scoring bundle.</small>}
                      {manage && !scored.has(dataset.dataset_id) && (
                        <button type="button" className="quiet" onClick={() => remove(dataset)} title="Only a dataset nothing was scored on can be removed">
                          Remove
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <Panel title="Runs">
        {runs.length === 0 ? (
          <div className="empty">No run has been submitted.</div>
        ) : (
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Run</th>
                  <th scope="col">Status</th>
                  <th scope="col">Bound bundle</th>
                  <th scope="col">Result</th>
                  <th scope="col">Action</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <RunRow key={run.run_id} run={run} onRetry={(failed) => submit(failed.dataset_id, failed.model_id)} onCancel={cancel} manage={manage} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
