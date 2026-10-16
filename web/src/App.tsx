import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { NavLink, Navigate, Route, Routes, useLocation, useMatch } from "react-router-dom";
import { ApiError, SIGNED_OUT_EVENT, allPages, api, setCsrfToken, type Dataset, type ExperimentSummary, type Health, type Me, type Run } from "./api";
import { ErrorBox, PageTitle, ist, number, shortId, useLoad } from "./components/ui";
import { datasetName, latestSnapshotRun } from "./derive";
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
  dataset: Dataset | null; // the run's dataset, for its name
  experiment: ExperimentSummary | null;
  fallback: boolean;
  reload: () => void;
};

const WorkspaceContext = createContext<Workspace>({ health: null, runs: [], run: null, dataset: null, experiment: null, fallback: false, reload: () => {} });
export const useWorkspace = () => useContext(WorkspaceContext);

/** Who is signed in (contract 1.16.0, AM-69): from the session, never typed. `can` reads the user's permissions. */
type Session = { me: Me; can: (permission: string) => boolean; signOut: () => void };
const SessionContext = createContext<Session>({ me: null as unknown as Me, can: () => false, signOut: () => {} });
export const useSession = () => useContext(SessionContext);

/** The sign-in page: the development login's people (laptops and demos), or Keycloak single sign-on (step 2). */
function SignIn({ onSignedIn }: { onSignedIn: (me: Me) => void }) {
  const users = useLoad(() => api.devUsers(), []);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const sso = users.error instanceof ApiError && users.error.status === 404;
  const signIn = async (name: string) => {
    setBusy(name);
    setError(null);
    try {
      onSignedIn(await api.devLogin(name));
    } catch (failure) {
      setError(failure instanceof ApiError ? failure : new ApiError(0, null));
    } finally {
      setBusy(null);
    }
  };
  return (
    <>
      <div className="strip">SYNTHETIC DATA ONLY / Simulated customers and returns / No real person or production accuracy claim</div>
      <main id="main" className="signin">
        <div className="brand">ARAI.</div>
        <PageTitle title="Sign in">Every note and decision is recorded under the person who signed in.</PageTitle>
        {sso ? (
          <p>
            <a className="button primary" href="/api/v1/auth/login">
              Sign in with Keycloak
            </a>
          </p>
        ) : (
          <>
            <p className="small">Development login: choose who you are. Single sign-on through Keycloak replaces this list on a shared deployment.</p>
            <div className="signin-users">
              {(users.data?.users ?? []).map((user) => (
                <button key={user.display_name} type="button" className="primary" disabled={busy !== null} onClick={() => signIn(user.display_name)}>
                  {user.display_name}
                  <small>{user.roles.join(", ")}</small>
                </button>
              ))}
            </div>
          </>
        )}
        {error && <ErrorBox error={error} />}
      </main>
    </>
  );
}

/** The run strip: what the queue is cut from, the budget and its edge, when it was scored, and how far its memos are. */
function RunStrip({ run, dataset }: { run: Run; dataset: Dataset | null }) {
  const inProgress = run.status === "queued" || run.status === "running";
  return (
    <div className="runstrip" aria-label="Run strip">
      <span>
        Dataset <strong>{datasetName(run, dataset)}</strong>
      </span>
      <span>
        Customers scored <strong>{number(run.eligible_count)}</strong> <span className="muted">(+{number(run.excluded_count)} unranked)</span>
      </span>
      <span>
        Alerts in queue <strong>{number(run.selected_count)}</strong>
        {run.review_budget !== null && <span className="muted"> of {number(run.review_budget)} budget</span>}
      </span>
      {run.threshold_score !== null && (
        <span title="The reference percentile of the last customer inside the budget; the queue is everyone at or above it">
          Queue threshold <strong>{run.threshold_score.toFixed(1)}</strong>
        </span>
      )}
      <span>
        Scored <strong>{ist(run.completed_at)}</strong>
      </span>
      {run.memos && !run.memos.complete && (
        <span className="muted" role="status">
          Memos drafting: {number(run.memos.ok + run.memos.unavailable)} of {number(run.memos.selected)}
        </span>
      )}
      {inProgress && <span role="status">New run in progress: {run.stage}</span>}
    </div>
  );
}

/** Who is signed in, their roles and Sign out, above the run strip. */
function SignedIn() {
  const { me, signOut } = useSession();
  return (
    <div className="signedin small" aria-label="Signed in">
      Signed in as <strong>{me.display_name}</strong> <span className="muted">({me.roles.join(", ")})</span>{" "}
      <button type="button" className="quiet" onClick={signOut}>
        Sign out
      </button>
    </div>
  );
}

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
  const { run, dataset, health, experiment } = useWorkspace();
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
          <SignedIn />
          {run && <RunStrip run={run} dataset={dataset} />}
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
            Every note and decision is recorded under the signed-in reviewer. This instance uses the development login.
          </footer>
        </div>
      </div>
    </>
  );
}

export default function App() {
  const [session, setSession] = useState<{ me: Me | null; checked: boolean }>({ me: null, checked: false });
  useEffect(() => {
    let live = true;
    api.me().then(
      (me) => {
        setCsrfToken(me.csrf_token);
        if (live) setSession({ me, checked: true });
      },
      () => live && setSession({ me: null, checked: true }),
    );
    const ended = () => {
      setCsrfToken(null);
      setSession({ me: null, checked: true });
    };
    window.addEventListener(SIGNED_OUT_EVENT, ended);
    return () => {
      live = false;
      window.removeEventListener(SIGNED_OUT_EVENT, ended);
    };
  }, []);
  if (!session.checked) return <p className="muted">Checking sign-in...</p>;
  if (!session.me) {
    return (
      <SignIn
        onSignedIn={(me) => {
          setCsrfToken(me.csrf_token);
          setSession({ me, checked: true });
        }}
      />
    );
  }
  const me = session.me;
  const signOut = () => {
    api.logout().finally(() => {
      setCsrfToken(null);
      setSession({ me: null, checked: true });
    });
  };
  return (
    <SessionContext.Provider value={{ me, can: (permission) => me.permissions.includes(permission as Me["permissions"][number]), signOut }}>
      <Workbench />
    </SessionContext.Provider>
  );
}

function Workbench() {
  const match = useMatch("/runs/:runId/*");
  const loaded = useLoad(async () => {
    const [health, runs, experiments, datasets] = await Promise.all([
      api.health().catch(() => null),
      allPages((cursor) => api.runs(undefined, cursor), 5).catch(() => [] as Run[]),
      api.experiments().catch(() => ({ items: [] as ExperimentSummary[], next_cursor: null })),
      allPages((cursor) => api.datasets(cursor), 5).catch(() => [] as Dataset[]),
    ]);
    return { health, runs, datasets, experiment: experiments.items.at(-1) ?? null };
  }, []);
  const workspace = useMemo<Workspace>(() => {
    const runs = loaded.data?.runs ?? [];
    const fromUrl = match?.params.runId ? runs.find((r) => r.run_id === match.params.runId) : undefined;
    const run = fromUrl ?? latestSnapshotRun(runs);
    const health = loaded.data?.health ?? null;
    return {
      health,
      runs,
      run,
      dataset: run ? (loaded.data?.datasets ?? []).find((d) => d.dataset_id === run.dataset_id) ?? null : null,
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
          <Route
            path="*"
            element={
              <>
                <PageTitle title="Unknown page">There is nothing at this address.</PageTitle>
                <div className="empty">
                  <NavLink to="/overview">Go to the overview</NavLink>
                </div>
              </>
            }
          />
        </Routes>
      </Shell>
    </WorkspaceContext.Provider>
  );
}
