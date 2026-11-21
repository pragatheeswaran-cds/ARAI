// Typed client for the ARAI API. Types are generated from final-spec/contracts/openapi.yaml (npm run api-types).
import type { components } from "./api-types";

type S = components["schemas"];
export type Dataset = S["Dataset"];
export type Run = S["Run"];
export type Customer = S["Customer"];
export type Case = S["Case"];
export type Review = S["Review"];
export type Signal = S["Signal"];
export type Style = S["Style"];
export type StyleDetail = S["StyleDetail"];
export type Experiment = S["Experiment"];
export type ExperimentSummary = S["ExperimentSummary"];
export type Metric = S["Metric"];
export type Candidate = S["Candidate"];
export type Health = S["Health"];
export type TruthExample = S["TruthExample"];
export type ScoreDistribution = S["ScoreDistribution"];
export type Curves = S["Curves"];
export type CommunityMember = S["CommunityMember"];
export type CommunityEdge = S["CommunityEdge"];
export type Community = NonNullable<Case["community"]>;
export type ScoreBreakdown = NonNullable<Case["score_breakdown"]>;
export type Memo = Case["memo"];
export type Workflow = Customer["workflow"];
export type WorkflowState = Workflow["state"];
export type PrimarySignal = Customer["primary_signals"][number];
export type Tier = NonNullable<Customer["tier"]>;
export type GateOutcome = NonNullable<Customer["gate_outcome"]>;
export type ReviewKind = Review["kind"];
export type Returner = StyleDetail["returners"][number];
export type ApiErrorBody = S["Error"];
export type Page<T> = { items: T[]; next_cursor: string | null };
export type Disposition = Review["disposition"];
export type Me = S["Me"];
export type DevUsers = S["DevUsers"];
export type AdminUser = S["AdminUser"];
export type AuthEvent = S["AuthEvent"];
export type AuthEventKind = AuthEvent["kind"];

export const API = "/api/v1";

export class ApiError extends Error {
  constructor(public status: number, public body: ApiErrorBody | null) {
    super(body?.message ?? `Request failed (${status})`);
  }
  get code(): string {
    return this.body?.error_code ?? "http_" + this.status;
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

// the session's CSRF token (contract 1.16.0, AM-69): kept in memory only, sent on every POST and DELETE
let csrfToken: string | null = null;
export const setCsrfToken = (token: string | null) => {
  csrfToken = token;
};
/** Fired when the API answers 401 outside the sign-in routes: the session has ended and the app shows the sign-in page. */
export const SIGNED_OUT_EVENT = "arai:signed-out";

async function request<T>(path: string, init?: RequestInit, query?: Query): Promise<T> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== null && value !== undefined && value !== "") params.set(key, String(value));
  }
  const url = API + path + (params.size ? "?" + params : "");
  let response: Response;
  const headers = new Headers(init?.headers);
  if ((init?.method ?? "GET").toUpperCase() !== "GET" && csrfToken) headers.set("X-CSRF-Token", csrfToken);
  try {
    response = await fetch(url, { ...init, headers, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, { error_code: "network", message: "The API could not be reached.", request_id: "", details: [] });
  }
  const text = await response.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  if (response.status === 401 && !path.startsWith("/auth/") && path !== "/me") window.dispatchEvent(new Event(SIGNED_OUT_EVENT));
  if (!response.ok) throw new ApiError(response.status, body as ApiErrorBody | null);
  return body as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});

export type CustomerFilters = {
  review_only: boolean;
  eligibility: "all" | "eligible" | "insufficient_history";
  search: string;
  evidence: string;
  disposition: "all" | "unreviewed" | Disposition;
  comparison: "all" | "model_only" | "baseline_only" | "both";
  // contract 1.6.0 and later; every filter changes what is shown and never a score or a selection
  wardrobing: "all" | Customer["wardrobing_status"];
  community: "all" | "ring" | "household" | "none";
  community_id: string;
  tier: "all" | Tier;
  gate: "all" | GateOutcome;
  state: "all" | WorkflowState;
  // contract 1.16.0: the cases the signed-in user did not open, by user id
  exclude_mine?: boolean;
  // contract 1.13.0: the cleared heavy returners view, filtered by the server rather than page by page in the browser
  cleared_heavy?: boolean;
  // contract 1.15.0: the customer against earlier snapshots of its world
  history?: "all" | "new_in_queue" | "repeat_in_queue" | "decided_before";
};

/** The address of the queue's CSV export for the same filters the list uses (contract 1.14.0). */
export function queueExportUrl(runId: string, filters: Partial<CustomerFilters>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== null && value !== undefined && value !== "" && value !== false) params.set(key, String(value));
  }
  if (filters.review_only === false) params.set("review_only", "false");
  return `${API}/runs/${encodeURIComponent(runId)}/customers/export${params.size ? "?" + params : ""}`;
}

export const api = {
  me: () => request<Me>("/me"),
  devUsers: () => request<DevUsers>("/auth/dev-users"),
  devLogin: (user: string) => request<Me>("/auth/dev-login", json({ user })),
  logout: () => request<null>("/auth/logout", { method: "POST" }),
  health: () => request<Health>("/health"),
  datasets: (cursor?: string | null) => request<Page<Dataset>>("/datasets", undefined, { cursor, limit: 100 }),
  registerDataset: (form: FormData) => request<Dataset>("/datasets", { method: "POST", body: form }),
  deleteDataset: (datasetId: string) => request<null>(`/datasets/${encodeURIComponent(datasetId)}`, { method: "DELETE" }),
  runs: (dataset_id?: string, cursor?: string | null) => request<Page<Run>>("/runs", undefined, { dataset_id, cursor, limit: 100 }),
  run: (runId: string) => request<Run>(`/runs/${encodeURIComponent(runId)}`),
  cancelRun: (runId: string) => request<Run>(`/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" }),
  scoreDistribution: (runId: string) => request<ScoreDistribution>(`/runs/${encodeURIComponent(runId)}/score-distribution`),
  submitRun: (dataset_id: string, idempotency_key: string, model_id?: string) =>
    request<Run>("/runs", json(model_id ? { dataset_id, idempotency_key, model_id } : { dataset_id, idempotency_key })),
  customers: (runId: string, filters: Partial<CustomerFilters>, cursor?: string | null, limit = 50) =>
    request<Page<Customer>>(`/runs/${encodeURIComponent(runId)}/customers`, undefined, { ...filters, cursor, limit }),
  customerCase: (runId: string, customerId: string) =>
    request<Case>(`/runs/${encodeURIComponent(runId)}/customers/${encodeURIComponent(customerId)}`),
  appendReview: (runId: string, customerId: string, body: S["ReviewRequest"]) =>
    request<Review>(`/runs/${encodeURIComponent(runId)}/customers/${encodeURIComponent(customerId)}/reviews`, json(body)),
  styles: (runId: string, state: string, cursor?: string | null) =>
    request<Page<Style>>(`/runs/${encodeURIComponent(runId)}/styles`, undefined, { state, cursor, limit: 100 }),
  style: (runId: string, styleId: string) =>
    request<StyleDetail>(`/runs/${encodeURIComponent(runId)}/styles/${encodeURIComponent(styleId)}`),
  experiments: () => request<Page<ExperimentSummary>>("/experiments", undefined, { limit: 100 }),
  experiment: (id: string) => request<Experiment>(`/experiments/${encodeURIComponent(id)}`),
  curves: (id: string, runId: string, maxPoints = 200) =>
    request<Curves>(`/experiments/${encodeURIComponent(id)}/curves`, undefined, { run_id: runId, max_points: maxPoints }),
  // people and access (contract 2.0.0, AM-71; admin only)
  adminUsers: () => request<{ items: AdminUser[] }>("/admin/users"),
  adminAction: (userId: string, action: "disable" | "enable" | "end-sessions", reason?: string) =>
    request<AdminUser>(`/admin/users/${encodeURIComponent(userId)}/${action}`, json(reason ? { reason } : {})),
  authEvents: (filters: { user_id?: string; kind?: string }, cursor?: string | null) =>
    request<Page<AuthEvent>>("/admin/auth-events", undefined, { ...filters, cursor, limit: 50 }),
  truth: (id: string, cursor?: string | null) =>
    request<{ synthetic_only: boolean; world_id: string | null } & Page<TruthExample>>(`/experiments/${encodeURIComponent(id)}/truth`, undefined, { cursor, limit: 100 }),
};

/** Every page of a cursor-paged list (bounded, so a mistake cannot loop forever). */
export async function allPages<T>(load: (cursor: string | null) => Promise<Page<T>>, maxPages = 50): Promise<T[]> {
  const items: T[] = [];
  let cursor: string | null = null;
  for (let page = 0; page < maxPages; page++) {
    const result: Page<T> = await load(cursor);
    items.push(...result.items);
    cursor = result.next_cursor;
    if (!cursor) break;
  }
  return items;
}

export function newKey(): string {
  return crypto.randomUUID();
}
