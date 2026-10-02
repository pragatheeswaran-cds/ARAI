import { createContext, useContext, useEffect, useMemo, type ReactNode } from "react";
import { NavLink, Navigate, Route, Routes, useLocation, useMatch } from "react-router-dom";
import { allPages, api, type ExperimentSummary, type Health, type Run } from "./api";
import { ist, shortId, useLoad } from "./components/ui";
import { CustomerCase } from "./pages/CustomerCase";
import { CustomerQueue } from "./pages/CustomerQueue";
import { Datasets } from "./pages/Datasets";
import { Evaluation } from "./pages/Evaluation";
import { Overview } from "./pages/Overview";
import { StyleDetailPage, StyleQueue } from "./pages/Styles";

type Workspace = {
  health: Health | null;
  runs: Run[];
  run: Run | null; // the run in the address bar, otherwise the latest succeeded run
  experiment: ExperimentSummary | null;
  fallback: boolean;
  reload: () => void;
};

const WorkspaceContext = createContext<Workspace>({ health: null, runs: [], run: null, experiment: null, fallback: false, reload: () => {} });
export const useWorkspace = () => useContext(WorkspaceContext);

/** Why the return-rate ranking is active, in the words the situation calls for. */
export function fallbackReason(health: Health | null, experiment: ExperimentSummary | null): string | null {
  if (!health || health.promoted_model_ready) return null;
  if (!health.scoring_ready) return "No valid scoring bundle is available. Scoring is blocked until a model or the baseline is activated.";
  const tail = " The return-rate ranking is active. Evidence remains available; no trained-model result is claimed.";
  if (!experiment || experiment.selection_status === "not_completed") return "Baseline only: model selection has not been completed." + tail;
  if (experiment.selection_status === "no_selected_model") return "No candidate passed the validation gate." + tail;
  if (experiment.final_test_status === "failed") return "The selected model failed its final test and was not promoted." + tail;
  if (experiment.final_test_status === "unverifiable") return "The final test could not be verified, so no model was promoted." + tail;
  return "A model was selected on validation but its final test has not been run, so it is not promoted." + tail;
}

function Shell({ children }: { children: ReactNode }) {
  const { run, health, experiment } = useWorkspace();
  const location = useLocation();
  useEffect(() => {
    document.getElementById("main")?.focus();
  }, [location.pathname]);
  const reason = fallbackReason(health, experiment);
  const runLink = (suffix: string) => (run ? `/runs/${run.run_id}/${suffix}` : "/datasets");
  const modelLabel = !run ? "No scored run" : run.model_kind === "baseline_fallback" ? "Return-rate baseline" : `Model (${run.model_kind})`;
  return (
    <>
      <div className="strip">SYNTHETIC DATA ONLY / Simulated customers and returns / No real person or production accuracy claim</div>
      <div className="shell">
        <aside>
          <div className="brand">ARAI.</div>
          <div className="tag">
            ADAPTIVE RETURN ABUSE
            <br />
            INTELLIGENCE
          </div>
          <nav aria-label="Main">
            <NavLink to="/overview">Overview</NavLink>
            <NavLink to="/datasets">Datasets &amp; runs</NavLink>
            <NavLink to={runLink("customers")}>Customer queue</NavLink>
            <NavLink to={runLink("styles")}>Style investigation</NavLink>
            <NavLink to={experiment ? `/experiments/${experiment.experiment_id}` : "/experiments/none"}>Evaluation</NavLink>
          </nav>
          <div className="footnote">
            Indian apparel / INR
            <br />
            Human investigation support
            <br />
            Signals are not proof of misconduct
          </div>
        </aside>
        <div className="workspace">
          <header>
            <div>
              <div className="small">Returns analyst workspace</div>
              <strong>{run ? `World ${run.world_id}` : "No scored run selected"}</strong>
            </div>
            <div className="small context" aria-label="Run context">
              {run ? (
                <>
                  <strong>
                    Run {shortId(run.run_id, 12)} / {modelLabel}
                  </strong>
                  <br />
                  Bundle {shortId(run.model_id, 14)} / Cutoff {ist(run.cutoff)}
                </>
              ) : (
                <strong>Register a dataset and score it to begin</strong>
              )}
            </div>
          </header>
          {reason && (
            <div className="banner" role="status">
              {reason}
            </div>
          )}
          <main id="main" tabIndex={-1}>
            {children}
          </main>
          <footer className="bottom">
            Investigation signals are not proof of misconduct. Synthetic data only; no production accuracy claim.
            <br />
            Local profile: reviewer names are free text, not an authenticated identity.
          </footer>
        </div>
      </div>
    </>
  );
}

export default function App() {
  const match = useMatch("/runs/:runId/*");
  const loaded = useLoad(async () => {
    const [health, runs, experiments] = await Promise.all([
      api.health().catch(() => null),
      allPages((cursor) => api.runs(undefined, cursor), 5).catch(() => [] as Run[]),
      api.experiments().catch(() => ({ items: [] as ExperimentSummary[], next_cursor: null })),
    ]);
    return { health, runs, experiment: experiments.items.at(-1) ?? null };
  }, []);
  const workspace = useMemo<Workspace>(() => {
    const runs = loaded.data?.runs ?? [];
    const fromUrl = match?.params.runId ? runs.find((r) => r.run_id === match.params.runId) : undefined;
    const run = fromUrl ?? runs.find((r) => r.status === "succeeded") ?? null;
    const health = loaded.data?.health ?? null;
    return {
      health,
      runs,
      run,
      experiment: loaded.data?.experiment ?? null,
      fallback: run ? run.model_kind === "baseline_fallback" : !!health && !health.promoted_model_ready,
      reload: loaded.reload,
    };
  }, [loaded.data, loaded.reload, match?.params.runId]);

  return (
    <WorkspaceContext.Provider value={workspace}>
      <Shell>
        <Routes>
          <Route path="/" element={<Navigate to="/overview" replace />} />
          <Route path="/overview" element={<Overview />} />
          <Route path="/datasets" element={<Datasets />} />
          <Route path="/runs/:runId/customers" element={<CustomerQueue />} />
          <Route path="/runs/:runId/customers/:customerId" element={<CustomerCase />} />
          <Route path="/runs/:runId/styles" element={<StyleQueue />} />
          <Route path="/runs/:runId/styles/:styleId" element={<StyleDetailPage />} />
          <Route path="/experiments/:experimentId" element={<Evaluation />} />
          <Route path="*" element={<div className="empty">Unknown page. <NavLink to="/overview">Go to the overview</NavLink></div>} />
        </Routes>
      </Shell>
    </WorkspaceContext.Provider>
  );
}
