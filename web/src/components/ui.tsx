import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ApiError } from "../api";

// ---------------------------------------------------------------- formatting
export const label = (text: string) => text.replaceAll("_", " ");

export function percent(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? "n/a" : (value * 100).toFixed(digits) + "%";
}

export function number(value: number | null | undefined, digits = 0): string {
  return value === null || value === undefined ? "n/a" : value.toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function rupees(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : "INR " + value.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

/** Timestamps are stored in UTC and shown in India Standard Time. */
export function ist(value: string | null | undefined, withTime = true): string {
  if (!value) return "n/a";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const options: Intl.DateTimeFormatOptions = { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "numeric" };
  if (withTime) Object.assign(options, { hour: "2-digit", minute: "2-digit", hour12: false });
  return date.toLocaleString("en-GB", options) + (withTime ? " IST" : "");
}

export const shortId = (id: string, keep = 10) => (id.length > keep + 4 ? id.slice(0, keep) + "..." : id);

// ---------------------------------------------------------------- data loading
export type Loaded<T> = { data: T | null; error: ApiError | null; loading: boolean; reload: () => void };

/** Runs an async loader when its dependencies change. A stale response never overwrites a newer one. */
export function useLoad<T>(loader: () => Promise<T>, deps: unknown[]): Loaded<T> {
  const [state, setState] = useState<{ data: T | null; error: ApiError | null; loading: boolean }>({ data: null, error: null, loading: true });
  const [tick, setTick] = useState(0);
  const latest = useRef(0);
  const lastTick = useRef(0);
  useEffect(() => {
    const call = ++latest.current;
    const refresh = lastTick.current !== tick; // reload() keeps what is shown; a new question clears it
    lastTick.current = tick;
    setState((previous) => ({ data: refresh ? previous.data : null, loading: true, error: null }));
    loader().then(
      (data) => call === latest.current && setState({ data, error: null, loading: false }),
      (error) =>
        call === latest.current &&
        setState({ data: null, loading: false, error: error instanceof ApiError ? error : new ApiError(0, null) }),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  const reload = useCallback(() => setTick((value) => value + 1), []);
  return { ...state, reload };
}

// ---------------------------------------------------------------- building blocks
export function PageTitle({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="heading">
      <div>
        <div className="eyebrow">ARAI / {title.toUpperCase()}</div>
        <h1>{title}</h1>
        {children && <p className="muted">{children}</p>}
      </div>
    </div>
  );
}

export function Stat({ name, value, note }: { name: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="stat">
      <div className="small">{name}</div>
      <div className="value">{value}</div>
      {note && <small className="muted">{note}</small>}
    </div>
  );
}

export function Badge({ text, tone = "plain" }: { text: string; tone?: "plain" | "amber" | "gray" | "green" }) {
  return <span className={"badge " + tone}>{label(text)}</span>;
}

export function Panel({ title, children, aside }: { title?: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="panel">
      {(title || aside) && (
        <div className="panel-head">
          {title && <h2>{title}</h2>}
          {aside}
        </div>
      )}
      {children}
    </section>
  );
}

export function Callout({ children }: { children: ReactNode }) {
  return <div className="callout">{children}</div>;
}

export function Row({ name, note, children }: { name: ReactNode; note?: ReactNode; children: ReactNode }) {
  return (
    <div className="signal">
      <span>
        {name}
        {note && <small>{note}</small>}
      </span>
      <strong>{children}</strong>
    </div>
  );
}

/** Loading, failed and empty are different states and say so. */
export function LoadState({ state, empty, children }: { state: Loaded<unknown>; empty?: boolean; children?: ReactNode }) {
  if (state.loading && state.data === null) {
    return (
      <div className="empty" role="status">
        Loading...
      </div>
    );
  }
  if (state.error) return <ErrorBox error={state.error} retry={state.reload} />;
  if (empty) return <div className="empty">{children ?? "Nothing to show."}</div>;
  return null;
}

export function ErrorBox({ error, retry }: { error: ApiError; retry?: () => void }) {
  const meaning: Record<string, string> = {
    run_not_ready: "This run has not finished, so it has no results yet.",
    run_output_missing: "The results of this run are no longer available. Submit a retry from Datasets and runs.",
    not_found: "This item does not exist in the selected run.",
    network: "The API could not be reached. Check that the service is running.",
  };
  return (
    <div className="error" role="alert">
      <strong>{meaning[error.code] ?? error.message}</strong>
      <div className="small">
        Error code {error.code}
        {error.body?.request_id ? ` / request ${error.body.request_id}` : ""}
      </div>
      {error.body?.details?.length ? (
        <ul>
          {error.body.details.slice(0, 12).map((d, i) => (
            <li key={i}>
              {d.rule_id}
              {d.table ? ` / ${d.table}` : ""}
              {d.row_key ? ` / ${d.row_key}` : ""} ({d.count})
            </li>
          ))}
        </ul>
      ) : null}
      {retry && (
        <button type="button" onClick={retry}>
          Try again
        </button>
      )}
    </div>
  );
}
