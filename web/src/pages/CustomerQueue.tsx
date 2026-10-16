import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ApiError, api, queueExportUrl, type Customer, type CustomerFilters } from "../api";
import { useReviewer, useWorkspace } from "../App";
import { CustomerTable, SCORE_HELP, TAGS, tagLabel } from "../components/CustomerTable";
import { Callout, ErrorBox, PageTitle, Panel, number, percent, useLoad } from "../components/ui";
import { GATE_HELP, GATE_LABEL, STATE_LABEL, TIER_HELP, TIER_LABEL } from "../derive";

const COMPARISONS: Record<CustomerFilters["comparison"], string> = {
  all: "All",
  model_only: "Selected by the model, not by the rule",
  baseline_only: "Selected by the rule, not by the model",
  both: "Selected by both",
};
const EMPTY: CustomerFilters = {
  review_only: true, eligibility: "all", search: "", evidence: "", disposition: "all", comparison: "all", wardrobing: "all", community: "all",
  community_id: "", tier: "all", gate: "all", state: "all", exclude_reviewer: "",
};

/** Cases a second person must decide, without the ones this reviewer opened. */
function ApprovalBand({ runId }: { runId: string }) {
  const { name } = useReviewer();
  const { fallback } = useWorkspace();
  const band = useLoad(() => api.customers(runId, { ...EMPTY, review_only: false, state: "awaiting_approval", exclude_reviewer: name.trim() }, null, 20), [runId, name]);
  const items = band.data?.items ?? [];
  if (!items.length) return null;
  return (
    <div className="band" role="region" aria-label="Awaiting a second reviewer">
      <h3>
        Awaiting your approval: {number(items.length)}
        {band.data?.next_cursor ? "+" : ""} case(s) another reviewer opened
      </h3>
      <p className="small">A case is decided by someone other than the person who opened it. {name.trim() ? `Cases ${name.trim()} opened are not listed.` : "Enter your name in the run strip to hide the cases you opened."}</p>
      <CustomerTable runId={runId} customers={items} fallback={fallback} compact />
    </div>
  );
}

export function CustomerQueue() {
  const { runId = "" } = useParams();
  const { run, fallback } = useWorkspace();
  const [params, setParams] = useSearchParams();
  const comparison = (params.get("comparison") ?? "all") as CustomerFilters["comparison"];
  // the queue opens on the review set; a comparison view, a community, a cleared view or a state filter needs every customer
  const view = params.get("show") ?? (comparison !== "all" || params.get("community_id") || params.get("state") ? "all" : "review");
  const filters: CustomerFilters = {
    ...EMPTY,
    review_only: view === "review",
    eligibility: view === "insufficient" ? "insufficient_history" : view === "eligible" || view === "cleared" ? "eligible" : "all",
    cleared_heavy: view === "cleared",
    search: params.get("search") ?? "",
    evidence: params.get("evidence") ?? "",
    disposition: (params.get("disposition") ?? "all") as CustomerFilters["disposition"],
    comparison: fallback ? "all" : comparison,
    wardrobing: (params.get("wardrobing") ?? "all") as CustomerFilters["wardrobing"],
    community: (params.get("community") ?? "all") as CustomerFilters["community"],
    community_id: params.get("community_id") ?? "",
    tier: (params.get("tier") ?? "all") as CustomerFilters["tier"],
    gate: (params.get("gate") ?? "all") as CustomerFilters["gate"],
    state: (params.get("state") ?? "all") as CustomerFilters["state"],
  };
  const grouped = params.get("group") === "ring";
  const key = JSON.stringify([runId, filters]);
  const [items, setItems] = useState<Customer[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [searchText, setSearchText] = useState(filters.search);

  const current = useRef(key);
  current.current = key;
  const load = (after: string | null) => {
    setLoading(true);
    setError(null);
    let cancelled = false;
    const issuedFor = key; // a page that arrives after the filters changed belongs to the old list and is dropped
    api.customers(runId, filters, after, 50).then(
      (page) => {
        if (cancelled || issuedFor !== current.current) return;
        setItems((previous) => (after ? [...previous, ...page.items] : page.items));
        setCursor(page.next_cursor);
        setLoading(false);
      },
      (failure) => {
        if (cancelled || issuedFor !== current.current) return;
        setError(failure instanceof ApiError ? failure : new ApiError(0, null));
        setLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => load(null), [key]);

  const set = (name: string, value: string) => {
    const next = new URLSearchParams(params);
    // each filter has its own "no filter" value: the review set for Show, "all" or empty for the others
    const isDefault = name === "show" ? value === "review" : !value || value === "all";
    if (isDefault) next.delete(name);
    else next.set(name, value);
    if (name === "show" && value !== "all") {
      next.delete("comparison"); // a comparison view needs every customer
      next.delete("community_id");
    }
    setParams(next); // every filter change is a history entry, so Back returns to the previous view
  };
  const shown = items; // the cleared view is filtered by the server (cleared_heavy), so every page is full

  return (
    <>
      <PageTitle title="Case queue">Filters change what is shown. They never change a score or the run's review selection.</PageTitle>
      <ApprovalBand runId={runId} />
      <Panel>
        <form
          className="filters"
          onSubmit={(event) => {
            event.preventDefault();
            set("search", searchText.trim());
          }}
        >
          <label>
            Search customer ID
            <input value={searchText} onChange={(e) => setSearchText(e.target.value)} placeholder="e.g. C00219" />
          </label>
          <button type="submit">Search</button>
          <label>
            Show
            <select value={view} onChange={(e) => set("show", e.target.value)}>
              <option value="review">Selected for review</option>
              <option value="cleared">Cleared heavy returners</option>
              <option value="all">All customers</option>
              <option value="eligible">Eligible (ranked)</option>
              <option value="insufficient">Insufficient history</option>
            </select>
          </label>
          <label title={TIER_HELP}>
            Tier
            <select value={filters.tier} onChange={(e) => set("tier", e.target.value)}>
              <option value="all">Any</option>
              {(Object.keys(TIER_LABEL) as (keyof typeof TIER_LABEL)[]).map((tier) => (
                <option key={tier} value={tier}>
                  {TIER_LABEL[tier]}
                </option>
              ))}
            </select>
          </label>
          <label title={GATE_HELP}>
            Recommendation
            <select value={filters.gate} onChange={(e) => set("gate", e.target.value)}>
              <option value="all">Any</option>
              {(Object.keys(GATE_LABEL) as (keyof typeof GATE_LABEL)[]).map((gate) => (
                <option key={gate} value={gate}>
                  {GATE_LABEL[gate]}
                </option>
              ))}
            </select>
          </label>
          <label>
            Linked accounts
            <select value={filters.community} onChange={(e) => set("community", e.target.value)}>
              <option value="all">Any</option>
              <option value="ring">In a ring</option>
              <option value="household">In a household</option>
              <option value="none">No supported link</option>
            </select>
          </label>
          <label>
            Status
            <select value={filters.state} onChange={(e) => set("state", e.target.value)}>
              <option value="all">Any</option>
              {(Object.keys(STATE_LABEL) as (keyof typeof STATE_LABEL)[]).map((state) => (
                <option key={state} value={state}>
                  {STATE_LABEL[state]}
                </option>
              ))}
            </select>
          </label>
          <label>
            Wardrobing indicator
            <select value={filters.wardrobing} onChange={(e) => set("wardrobing", e.target.value)}>
              <option value="all">Any</option>
              <option value="elevated">Elevated</option>
              <option value="possible">Possible</option>
              <option value="no_elevated_signal">No elevated signal</option>
              <option value="insufficient_evidence">Insufficient evidence</option>
              <option value="incomplete">Incomplete</option>
            </select>
          </label>
          <label>
            Measured evidence
            <select value={filters.evidence} onChange={(e) => set("evidence", e.target.value)}>
              <option value="">Any</option>
              {TAGS.map((tag) => (
                <option key={tag} value={tag}>
                  {tagLabel(tag)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Review note
            <select value={filters.disposition} onChange={(e) => set("disposition", e.target.value)}>
              <option value="all">Any</option>
              <option value="unreviewed">No note yet</option>
              <option value="needs_investigation">Needs investigation</option>
              <option value="likely_legitimate">Likely legitimate</option>
              <option value="unresolved">Unresolved</option>
            </select>
          </label>
          {!fallback && (
            <label>
              Model and return-rate rule
              <select
                value={comparison}
                onChange={(e) => {
                  const next = new URLSearchParams(params);
                  if (e.target.value === "all") next.delete("comparison");
                  else {
                    next.set("comparison", e.target.value);
                    next.set("show", "all");
                  }
                  setParams(next);
                }}
              >
                {Object.entries(COMPARISONS).map(([value, text]) => (
                  <option key={value} value={value}>
                    {text}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            Group rows
            <select value={grouped ? "ring" : "none"} onChange={(e) => set("group", e.target.value === "ring" ? "ring" : "")}>
              <option value="none">By rank</option>
              <option value="ring">By linked-account group</option>
            </select>
          </label>
        </form>
        {filters.community_id && (
          <p className="small">
            Showing the members of linked-account group {filters.community_id}.{" "}
            <Link to={`/runs/${runId}/customers`}>Back to the queue</Link>
          </p>
        )}
        <p className="small" role="status">
          {loading && items.length === 0 ? "Loading..." : error ? "Nothing to show." : `${number(shown.length)} customer(s) shown${cursor ? ", more available" : ""}`}
          {run && !error && run.run_id === runId ? ` / ${number(run.selected_count)} selected of ${number(run.eligible_count)} eligible in this run` : ""}
          {view === "cleared" && run && run.heavy_returner_cutoff !== null
            ? ` / heavy means a raw return rate at or above ${percent(run.heavy_returner_cutoff, 0)}, this run's 90th percentile`
            : ""}
        </p>
        {!error && run && run.run_id === runId && (
          <p className="actions">
            <a className="button" href={queueExportUrl(runId, filters)} download>
              Export this view as CSV
            </a>{" "}
            <span className="small muted">every row of the current filters, for the returns-policy or service team; no note text is exported</span>
          </p>
        )}
        {error && <ErrorBox error={error} retry={() => load(null)} />}
        {!error && !loading && shown.length === 0 && (
          <div className="empty">{view === "cleared" ? "No heavy returner outside the queue in this run." : "No customer matches. Clear the search or change a filter."}</div>
        )}
        {shown.length > 0 && <CustomerTable runId={runId} customers={shown} fallback={fallback} run={run} grouped={grouped} />}
        {cursor && (
          <p>
            <button type="button" onClick={() => load(cursor)} disabled={loading}>
              {loading ? "Loading..." : "Load more"}
            </button>
          </p>
        )}
      </Panel>
      <Callout>
        {SCORE_HELP} Rank is the position in this batch. Tier is anchored to the queue and the recommendation is a stated rule over the run's
        results, not a model output. Customers with fewer than three mature sale lines are not ranked; their evidence can still be opened.
      </Callout>
    </>
  );
}
