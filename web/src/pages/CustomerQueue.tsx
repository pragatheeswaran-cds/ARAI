import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { ApiError, api, type Customer, type CustomerFilters } from "../api";
import { useWorkspace } from "../App";
import { CustomerTable, SCORE_HELP, TAGS, tagLabel } from "../components/CustomerTable";
import { Callout, ErrorBox, PageTitle, Panel, number } from "../components/ui";

const COMPARISONS: Record<CustomerFilters["comparison"], string> = {
  all: "All",
  model_only: "Selected by the model, not by the rule",
  baseline_only: "Selected by the rule, not by the model",
  both: "Selected by both",
};

export function CustomerQueue() {
  const { runId = "" } = useParams();
  const { run, fallback } = useWorkspace();
  const [params, setParams] = useSearchParams();
  const comparison = (params.get("comparison") ?? "all") as CustomerFilters["comparison"];
  // the queue opens on the review set; a comparison view needs every customer, so it switches to all
  const show = params.get("show") ?? (comparison === "all" ? "review" : "all");
  const filters: CustomerFilters = {
    review_only: show === "review",
    eligibility: show === "insufficient" ? "insufficient_history" : show === "eligible" ? "eligible" : "all",
    search: params.get("search") ?? "",
    evidence: params.get("evidence") ?? "",
    disposition: (params.get("disposition") ?? "all") as CustomerFilters["disposition"],
    comparison: fallback ? "all" : comparison,
  };
  const key = JSON.stringify([runId, filters]);
  const [items, setItems] = useState<Customer[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [searchText, setSearchText] = useState(filters.search);

  const load = (after: string | null) => {
    setLoading(true);
    setError(null);
    let cancelled = false;
    api.customers(runId, filters, after).then(
      (page) => {
        if (cancelled) return;
        setItems((previous) => (after ? [...previous, ...page.items] : page.items));
        setCursor(page.next_cursor);
        setLoading(false);
      },
      (failure) => {
        if (cancelled) return;
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
    if (value && value !== "all" && !(name === "show" && value === "review")) next.set(name, value);
    else next.delete(name);
    if (name === "show" && value === "review") next.delete("comparison");
    setParams(next, { replace: true });
  };

  return (
    <>
      <PageTitle title="Customer queue">Filters change what is shown. They never change a score or the run's review selection.</PageTitle>
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
            <select value={show} onChange={(e) => set("show", e.target.value)}>
              <option value="review">Selected for review</option>
              <option value="all">All customers</option>
              <option value="eligible">Eligible (ranked)</option>
              <option value="insufficient">Insufficient history</option>
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
                  setParams(next, { replace: true });
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
        </form>
        <p className="small" role="status">
          {loading && items.length === 0 ? "Loading..." : `${number(items.length)} customer(s) shown${cursor ? ", more available" : ""}`}
          {run ? ` / ${number(run.selected_count)} selected of ${number(run.eligible_count)} eligible in this run` : ""}
        </p>
        {error && <ErrorBox error={error} retry={() => load(null)} />}
        {!error && !loading && items.length === 0 && <div className="empty">No customer matches. Clear the search or change a filter.</div>}
        {items.length > 0 && <CustomerTable runId={runId} customers={items} fallback={fallback} />}
        {cursor && (
          <p>
            <button type="button" onClick={() => load(cursor)} disabled={loading}>
              {loading ? "Loading..." : "Load more"}
            </button>
          </p>
        )}
      </Panel>
      <Callout>
        {SCORE_HELP} Rank is the position in this batch. Customers with fewer than three mature sale lines are not ranked; their evidence can still
        be opened.
      </Callout>
    </>
  );
}
