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
export type ApiErrorBody = S["Error"];
export type Page<T> = { items: T[]; next_cursor: string | null };
export type Disposition = Review["disposition"];

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

async function request<T>(path: string, init?: RequestInit, query?: Query): Promise<T> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== null && value !== undefined && value !== "") params.set(key, String(value));
  }
  const url = API + path + (params.size ? "?" + params : "");
  let response: Response;
  try {
    response = await fetch(url, init);
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
};

export const api = {
  health: () => request<Health>("/health"),
  datasets: (cursor?: string | null) => request<Page<Dataset>>("/datasets", undefined, { cursor, limit: 100 }),
  registerDataset: (form: FormData) => request<Dataset>("/datasets", { method: "POST", body: form }),
  runs: (dataset_id?: string, cursor?: string | null) => request<Page<Run>>("/runs", undefined, { dataset_id, cursor, limit: 100 }),
  run: (runId: string) => request<Run>(`/runs/${encodeURIComponent(runId)}`),
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
  truth: (id: string, cursor?: string | null) =>
    request<{ synthetic_only: boolean } & Page<TruthExample>>(`/experiments/${encodeURIComponent(id)}/truth`, undefined, { cursor, limit: 100 }),
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
