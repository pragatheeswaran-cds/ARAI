// Customer Intelligence (Penpot board 4): one customer's behaviour in this snapshot, read from the same case the
// investigation page shows. Nothing here is a new computation of a score; the charts count the customer's own events.
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type Case, type Customer } from "../api";
import { useWorkspace } from "../App";
import { BLUE, Donut, HBars, LineChart, SLATE } from "../components/charts";
import { Chips, StateBadge, TierBadge } from "../components/CustomerTable";
import { Callout, LoadState, PageTitle, Panel, Row, Stat, ist, label, number, percent, rupees, useLoad } from "../components/ui";
import { caseId, rawRate } from "../derive";

type Event = Case["timeline"][number];
const isReturn = (event: Event) => event.event_type !== "purchase";

/** Purchases and returns by calendar month, every month between the first and the last event present. */
export function monthly(events: Event[]): { month: string; purchases: number; returns: number }[] {
  const counts = new Map<string, { purchases: number; returns: number }>();
  for (const event of events) {
    const month = event.observed_at.slice(0, 7);
    const entry = counts.get(month) ?? { purchases: 0, returns: 0 };
    if (isReturn(event)) entry.returns += 1;
    else entry.purchases += 1;
    counts.set(month, entry);
  }
  const months = [...counts.keys()].sort();
  if (!months.length) return [];
  const out = [];
  const [endYear, endMonth] = months[months.length - 1].split("-").map(Number);
  let [year, month] = months[0].split("-").map(Number);
  while (year < endYear || (year === endYear && month <= endMonth)) {
    const key = `${year}-${String(month).padStart(2, "0")}`;
    out.push({ month: key, ...(counts.get(key) ?? { purchases: 0, returns: 0 }) });
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
  }
  return out;
}

function countBy<T>(items: T[], key: (item: T) => string | null | undefined): [string, number][] {
  const counts = new Map<string, number>();
  for (const item of items) {
    const name = key(item);
    if (name) counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  return [...counts.entries()].sort((x, y) => y[1] - x[1]);
}

export function CustomerProfile() {
  const { runId = "", customerId = "" } = useParams();
  const { run } = useWorkspace();
  const state = useLoad(() => api.customerCase(runId, customerId), [runId, customerId]);
  const data = state.data;
  const c = data?.customer;
  const events = data?.timeline ?? [];
  const purchases = events.filter((e) => !isReturn(e));
  const returns = events.filter(isReturn);
  const timed = returns.filter((e) => e.day_in_window !== null && e.day_in_window !== undefined);
  const latency = timed.length ? timed.reduce((sum, e) => sum + (e.day_in_window as number), 0) / timed.length : null;
  const lastReturn = returns.length ? returns.map((e) => e.observed_at.slice(0, 10)).sort().at(-1) : null;
  const months = monthly(events);
  const reasons = countBy(returns, (e) => e.reason_code);
  const categoryOf = new Map((data?.styles ?? []).map((s) => [s.style_id, s.category]));
  const categories = countBy(returns, (e) => (e.style_id ? categoryOf.get(e.style_id) ?? "other" : null));
  const shared = countBy((data?.neighbors ?? []).flatMap((n) => n.shared_types), (type) => type);
  const rate = c ? rawRate(c) : null;
  const expected = c?.basket_expectation ?? null;
  return (
    <>
      <Link className="button back" to={`/runs/${runId}/profiles`}>
        Back to Customers
      </Link>
      <PageTitle title="Customer Intelligence">
        Customer behaviour, return trends and risk indicators for {customerId} in this snapshot. Observed evidence for a human reviewer; it is not a
        finding of misconduct.
      </PageTitle>
      <LoadState state={state} />
      {data && c && (
        <>
          <div className="grid">
            <Panel title="Customer">
              <Row name="Customer ID">{c.customer_id}</Row>
              <Row name="Email">{c.contact.email ?? "not in this snapshot"}</Row>
              <Row name="Phone">{c.contact.phone ?? "not in this snapshot"}</Row>
              <Row name="Region">{c.contact.region ? label(c.contact.region) : "not in this snapshot"}</Row>
              <Row name="Case" note="a case is this customer in this run">
                <Link to={`/runs/${runId}/customers/${c.customer_id}`}>{caseId(c.customer_id)}</Link>
              </Row>
              <Row name="Status">
                <StateBadge customer={c} compact />
              </Row>
              <Row name="Observed patterns">
                <Chips signals={c.primary_signals} />
              </Row>
            </Panel>
            <Panel title="Risk Score">
              <div className="value">
                {c.risk_score === null ? "n/a" : `${c.risk_score.toFixed(0)} / 100`} <TierBadge tier={c.tier} />
              </div>
              <p className="small muted">
                {c.rank ? `Rank ${number(c.rank)} of ${number(run?.eligible_count ?? 0)} ranked customers.` : "Not ranked: fewer than three mature sale lines."} A
                percentile against the training scores, not a probability.
              </p>
              <Link className="button primary" to={`/runs/${runId}/customers/${c.customer_id}`}>
                Open the investigation
              </Link>
            </Panel>
          </div>
          <div className="stats five">
            <Stat name="Total Orders" value={number(purchases.length)} note="order lines in the snapshot" />
            <Stat name="Total Returns" value={number(returns.length)} note={purchases.length ? `${percent(returns.length / purchases.length, 0)} of order lines` : "no order line"} />
            <Stat name="Refund Amount" value={c.refunded_inr === null || c.refunded_inr === undefined ? "n/a" : rupees(c.refunded_inr)} note="paid on refunded return lines" />
            <Stat name="Avg. Return Latency" value={latency === null ? "n/a" : `${latency.toFixed(1)} days`} note="after delivery, over timed requests" />
            <Stat name="Last Return" value={lastReturn ? ist(lastReturn + "T12:00:00Z", false) : "none"} note="date of the latest request" />
          </div>
          <div className="three">
            <Panel title="Return Trends">
              <LineChart
                label="Order lines and return requests of this customer by month"
                format={(value) => number(value)}
                series={[
                  { name: "Order lines", color: SLATE[0], points: months.map((m) => ({ x: m.month.slice(2), y: m.purchases })) },
                  { name: "Returns", color: BLUE[1], points: months.map((m) => ({ x: m.month.slice(2), y: m.returns })) },
                ]}
              />
            </Panel>
            <Panel title="Return Reason Mix">
              {reasons.length ? (
                <Donut
                  center={number(returns.length)}
                  sub="returns"
                  format={(value) => number(value)}
                  slices={[
                    ...reasons.slice(0, 4).map(([name, value], index) => ({ name: label(name), value, color: SLATE[index] })),
                    ...(reasons.length > 4 ? [{ name: "other", value: reasons.slice(4).reduce((sum, [, value]) => sum + value, 0), color: SLATE[4] }] : []),
                  ]}
                />
              ) : (
                <p className="muted">No return request with a reason code in this snapshot.</p>
              )}
            </Panel>
            <Panel title="Peer Comparison">
              <Row name="Return rate" note={`against ${percent(run?.mean_return_rate, 0)} across ranked customers`}>
                {percent(rate, 0)}
              </Row>
              <Row name="Units returned" note={expected ? `against ${expected.expected_units.toFixed(1)} expected for this basket` : "no basket expectation for this customer"}>
                {c.support_counts.mature_requested_units} of {c.support_counts.mature_purchased_units}
              </Row>
              <Row name="Heavy-returner line" note="the 90th percentile of return rates in this run">
                {percent(run?.heavy_returner_cutoff, 0)}
              </Row>
            </Panel>
          </div>
          <div className="three">
            <Panel title="Product Concentration">
              <p className="small muted">Categories by this customer's return requests</p>
              {categories.length ? (
                <HBars bars={categories.slice(0, 6).map(([name, value]) => ({ name, value: value / returns.length }))} format={(value) => percent(value, 0)} max={1} />
              ) : (
                <p className="muted">No return request.</p>
              )}
            </Panel>
            <Panel title="Linked Accounts">
              <Row name="Accounts sharing identifiers">{number(data.neighbors.length)}</Row>
              {shared.map(([type, value]) => (
                <Row key={type} name={`Share a ${type}`} note="accounts, among the links above">
                  {number(value)}
                </Row>
              ))}
              {c.community && (
                <Row name="Group" note="membership is evidence, not guilt">
                  {c.community.kind} of {c.community.size}
                </Row>
              )}
              {!data.neighbors.length && <p className="muted">No other account shares two identifier types with this one.</p>}
            </Panel>
            <Panel title="Summary">
              <p>
                {data.memo.summary ??
                  (c.selected_for_review
                    ? "Selected for review in this run; the investigation memo has not been drafted yet."
                    : "Not selected for review in this run. Its evidence can still be opened.")}
              </p>
              {c.community && (
                <Link className="button" to={`/runs/${runId}/network?group=${encodeURIComponent(c.community.id)}`}>
                  View Network Graph
                </Link>
              )}
            </Panel>
          </div>
          <Callout>
            {c.contact.email === null && c.contact.phone === null && c.contact.region === null
              ? "This snapshot was written before region, email and phone were part of the data, so none is shown. "
              : "Email and phone are synthetic: every address is at example.com and no number belongs to a real subscriber. "}
            Return history, the behaviour evidence and the notes are on the <Link to={`/runs/${runId}/customers/${c.customer_id}`}>investigation page</Link>.
          </Callout>
        </>
      )}
    </>
  );
}

/** Customers: find a customer of this run and open its profile. */
export function CustomerSearch() {
  const { runId = "" } = useParams();
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [search, setSearch] = useState("");
  const found = useLoad(() => api.customers(runId, { review_only: !search, search }, null, 50), [runId, search]);
  const items: Customer[] = found.data?.items ?? [];
  return (
    <>
      <PageTitle title="Customers">Find a customer of this run and open its profile. Without a search, the customers selected for review are listed.</PageTitle>
      <Panel>
        <form
          className="filters"
          onSubmit={(event: FormEvent) => {
            event.preventDefault();
            setSearch(text.trim());
          }}
        >
          <label>
            Search by Customer ID, Email, Phone
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. C00219" size={32} />
          </label>
          <button type="submit">Search</button>
        </form>
        <LoadState state={found} empty={!!found.data && items.length === 0}>
          No customer matches.
        </LoadState>
        {items.length > 0 && (
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Customer ID</th>
                  <th scope="col">Email / phone</th>
                  <th scope="col">Region</th>
                  <th scope="col">Risk Score</th>
                  <th scope="col">Risk Level</th>
                  <th scope="col">Return %</th>
                  <th scope="col">Pattern(s)</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {items.map((c) => (
                  <tr key={c.customer_id} onDoubleClick={() => navigate(`/runs/${runId}/profiles/${c.customer_id}`)}>
                    <td>
                      <Link className="link" to={`/runs/${runId}/profiles/${c.customer_id}`}>
                        {c.customer_id}
                      </Link>
                    </td>
                    <td>
                      {c.contact.email ?? <span className="muted">n/a</span>}
                      {c.contact.phone && <small>{c.contact.phone}</small>}
                    </td>
                    <td>{c.contact.region ? label(c.contact.region) : <span className="muted">n/a</span>}</td>
                    <td>{c.risk_score === null ? "n/a" : c.risk_score.toFixed(1)}</td>
                    <td>
                      <TierBadge tier={c.tier} />
                    </td>
                    <td>{percent(rawRate(c), 0)}</td>
                    <td>
                      <Chips signals={c.primary_signals} />
                    </td>
                    <td>
                      <StateBadge customer={c} compact />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {found.data?.next_cursor && <p className="small muted">Showing the first 50; search to narrow the list.</p>}
      </Panel>
    </>
  );
}
