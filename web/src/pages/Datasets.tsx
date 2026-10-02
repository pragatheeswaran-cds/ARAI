import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ApiError, allPages, api, newKey, type Dataset, type Run } from "../api";
import { useWorkspace } from "../App";
import { Badge, Callout, ErrorBox, LoadState, PageTitle, Panel, Row, ist, label, number, shortId, useLoad } from "../components/ui";

const TABLES = ["customer_master", "sku_master", "reason_code", "sales_order", "sales_order_line", "return_order", "return_order_line"];
const REQUIRED = ["manifest.json", ...TABLES.map((name) => name + ".csv")];
const POLL_MS = 2000;

function Upload({ onRegistered }: { onRegistered: () => void }) {
  const input = useRef<HTMLInputElement>(null);
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
      setMessage(`World ${dataset.world_id} is registered (${number(dataset.customer_count)} customers). Its content can no longer change.`);
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
        <input ref={input} type="file" multiple accept=".csv,.json" />
      </label>
      <p className="small">
        The files are validated on the server (columns, keys, references, money, chronology, hashes against the manifest). A snapshot that fails is
        rejected whole; nothing is repaired or stored.
      </p>
      <button className="primary" type="submit" disabled={busy}>
        {busy ? "Validating..." : "Validate and register"}
      </button>
      <p role="status">{message}</p>
      {error && <ErrorBox error={error} />}
    </form>
  );
}

function RunRow({ run, onRetry }: { run: Run; onRetry: (run: Run) => void }) {
  const tone = run.status === "succeeded" ? "green" : run.status === "failed" || run.status === "interrupted" ? "amber" : "gray";
  return (
    <tr>
      <td>
        {shortId(run.run_id, 14)}
        <small>
          {run.world_id} / submitted {ist(run.created_at)}
        </small>
      </td>
      <td>
        <Badge text={run.status} tone={tone} />
        <small>
          {run.status === "running" || run.status === "queued" ? (
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
      </td>
      <td>
        {run.model_kind === "baseline_fallback" ? "Return-rate baseline" : label(run.model_kind) + " model"}
        <small title={run.model_id}>bundle {shortId(run.model_id, 16)}</small>
      </td>
      <td>
        {run.status === "succeeded" ? (
          <>
            {number(run.eligible_count)} eligible / {number(run.selected_count)} selected
            <small>{number(run.excluded_count)} with insufficient history</small>
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
        {(run.status === "failed" || run.status === "interrupted") && (
          <button type="button" onClick={() => onRetry(run)}>
            Retry with the same dataset and bundle
          </button>
        )}
      </td>
    </tr>
  );
}

export function Datasets() {
  const { health, runs, reload } = useWorkspace();
  const datasets = useLoad(() => allPages<Dataset>((cursor) => api.datasets(cursor)), []);
  const [error, setError] = useState<ApiError | null>(null);
  const active = runs.some((run) => run.status === "queued" || run.status === "running");
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(reload, POLL_MS);
    return () => clearInterval(timer);
  }, [active, reload]);

  const submit = async (datasetId: string, modelId?: string) => {
    setError(null);
    try {
      await api.submitRun(datasetId, newKey(), modelId);
      reload();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure : new ApiError(0, null));
    }
  };
  const ready = !!health?.scoring_ready;

  return (
    <>
      <PageTitle title="Datasets & runs">
        Register an operational snapshot, then score it with the active bundle. Scoring uses frozen artifacts; nothing is trained here.
      </PageTitle>
      <div className="grid">
        <Panel title="Register a snapshot">
          <Upload onRegistered={datasets.reload} />
        </Panel>
        <Panel title="Scoring readiness">
          <Row name="Service">{health ? "Reachable" : "Not reachable"}</Row>
          <Row name="Scoring bundle" note="A run binds this bundle when it is submitted">
            {!health ? "unknown" : !ready ? "None valid: scoring blocked" : health.model_kind === "baseline_fallback" ? "Return-rate baseline" : `Promoted ${label(health.model_kind ?? "")} model`}
          </Row>
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
                  <th scope="col">World</th>
                  <th scope="col">Customers</th>
                  <th scope="col">History / cutoff</th>
                  <th scope="col">Validation</th>
                  <th scope="col">Manifest hash</th>
                  <th scope="col">Score</th>
                </tr>
              </thead>
              <tbody>
                {datasets.data.map((dataset) => (
                  <tr key={dataset.dataset_id}>
                    <td>
                      {dataset.world_id}
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
                      <button type="button" className="primary" disabled={!ready} onClick={() => submit(dataset.dataset_id)}>
                        Score with the active bundle
                      </button>
                      {!ready && <small>Blocked: no valid scoring bundle.</small>}
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
                  <RunRow key={run.run_id} run={run} onRetry={(failed) => submit(failed.dataset_id, failed.model_id)} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
