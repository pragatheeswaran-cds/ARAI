import { Link, useParams, useSearchParams } from "react-router-dom";
import { allPages, api, type Style } from "../api";
import { Badge, Callout, LoadState, PageTitle, Panel, Row, Stat, label, number, percent, rupees, useLoad } from "../components/ui";

const STATES = ["all", "quality", "targeting", "mixed_or_uncertain", "no_elevated_signal", "insufficient_support", "no_return_evidence"];
const MEANING: Record<string, string> = {
  quality: "Many returns of this style give a quality reason.",
  targeting: "Claims on this style come from linked accounts within days of each other.",
  mixed_or_uncertain: "Both signals fire; the evidence does not separate product quality from targeting.",
  no_elevated_signal: "Enough sales to judge, and neither signal fires.",
  insufficient_support: "Fewer than 20 mature sale lines: too little to judge.",
  no_return_evidence: "Enough sales and no return or claim at all.",
};
const tone = (state: string) => (state === "targeting" || state === "mixed_or_uncertain" ? "amber" : state === "quality" ? "green" : "gray");

export function StyleQueue() {
  const { runId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const state = STATES.includes(params.get("state") ?? "") ? (params.get("state") as string) : "all";
  const styles = useLoad(() => allPages<Style>((cursor) => api.styles(runId, state, cursor)), [runId, state]);
  return (
    <>
      <PageTitle title="Style investigation">Style-level evidence with SKU drill-down. A state describes the product evidence, never a customer.</PageTitle>
      <Panel>
        <div className="filters">
          <label>
            Evidence state
            <select value={state} onChange={(e) => setParams(e.target.value === "all" ? {} : { state: e.target.value }, { replace: true })}>
              {STATES.map((value) => (
                <option key={value} value={value}>
                  {label(value)}
                </option>
              ))}
            </select>
          </label>
          {state !== "all" && <span className="small">{MEANING[state]}</span>}
        </div>
        <LoadState state={styles} empty={!!styles.data && styles.data.length === 0}>
          No style is in this state in this run.
        </LoadState>
        {styles.data && styles.data.length > 0 && (
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Style / category</th>
                  <th scope="col">State</th>
                  <th scope="col">Mature sale lines</th>
                  <th scope="col">Return rate</th>
                  <th scope="col" title="Requested units with a quality reason (defective, poor quality, not as described)">
                    Quality-reason share
                  </th>
                  <th scope="col">Claim share</th>
                  <th scope="col" title="Claims matched by a linked account's claim on the same style within 7 days">
                    Linked-claim share
                  </th>
                </tr>
              </thead>
              <tbody>
                {styles.data.map((s) => (
                  <tr key={s.style_id}>
                    <td>
                      <Link className="link" to={`/runs/${runId}/styles/${s.style_id}`}>
                        {s.style_id}
                      </Link>
                      <small>{s.category}</small>
                    </td>
                    <td>
                      <Badge text={s.state} tone={tone(s.state)} />
                    </td>
                    <td>{number(s.mature_sale_lines)}</td>
                    <td>
                      {percent(s.raw_return_rate)}
                      <small>
                        {number(s.requested_units)} / {number(s.purchased_units)} units
                      </small>
                    </td>
                    <td>{percent(s.damage_share)}</td>
                    <td>{percent(s.claim_share)}</td>
                    <td>
                      {percent(s.linked_claim_share)}
                      <small>{s.linked_claimers ? `${s.linked_claimers} linked claimant(s)` : "no linked claimant"}</small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <Callout>
        Quality signal: quality-reason share of 30% or more. Targeting signal: at least three linked claimants and a linked-claim share of 7.5% or
        more. Styles with fewer than 20 mature sale lines show no shares.
      </Callout>
    </>
  );
}

export function StyleDetailPage() {
  const { runId = "", styleId = "" } = useParams();
  const state = useLoad(() => api.style(runId, styleId), [runId, styleId]);
  const detail = state.data;
  return (
    <>
      <Link className="button back" to={`/runs/${runId}/styles`}>
        Back to style queue
      </Link>
      <PageTitle title={`Style ${styleId}`}>{detail ? `${detail.style.category} / ${label(detail.style.state)}: ${MEANING[detail.style.state]}` : ""}</PageTitle>
      <LoadState state={state} />
      {detail && (
        <>
          <div className="stats">
            <Stat name="Mature sale lines" value={number(detail.style.mature_sale_lines)} note="At least 20 needed for evidence" />
            <Stat
              name="Requested units"
              value={`${number(detail.style.requested_units)} / ${number(detail.style.purchased_units)}`}
              note={`${percent(detail.style.raw_return_rate)} return rate / ${number(detail.style.unique_returners)} returning customers`}
            />
            <Stat name="Quality-reason share" value={percent(detail.style.damage_share)} note="Carrier damage excluded / signal at 30%" />
            <Stat
              name="Linked-claim share"
              value={percent(detail.style.linked_claim_share)}
              note={`${detail.style.linked_claimers} linked claimant(s) / signal at 3 claimants and 7.5%`}
            />
          </div>
          <div className="grid">
            <Panel title="Evidence with denominators">
              {detail.signals.map((signal) => (
                <Row key={signal.code} name={signal.label}>
                  {signal.value === null ? "n/a" : number(signal.value)}
                  {signal.denominator !== null ? ` / ${number(signal.denominator)}` : ""} <span className="muted">{signal.unit.replace(/^units of /, "")}</span>
                </Row>
              ))}
              <h3>SKU drill-down</h3>
              <div className="tablewrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">SKU</th>
                      <th scope="col">Size / colour</th>
                      <th scope="col">Catalog price</th>
                      <th scope="col">Requested / purchased units</th>
                      <th scope="col">Support</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.skus.map((sku) => (
                      <tr key={sku.sku}>
                        <td>{sku.sku}</td>
                        <td>
                          {sku.size} / {sku.colour}
                        </td>
                        <td>{rupees(sku.unit_price_inr)}</td>
                        <td>
                          {number(sku.requested_units)} / {number(sku.purchased_units)}
                          <small>{number(sku.mature_sale_lines)} mature sale lines</small>
                        </td>
                        <td>
                          <Badge text={sku.support_status} tone="gray" />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
            <Panel title="Customers with requests on this style">
              <p className="muted">Customers with linked claims come first, then by claims and requested units (up to 50).</p>
              {detail.customer_ids.length === 0 && <p className="muted">No customer has a return request on this style.</p>}
              <ul className="plain">
                {detail.customer_ids.map((id) => (
                  <li key={id}>
                    <Link to={`/runs/${runId}/customers/${id}`}>{id}</Link>
                  </li>
                ))}
              </ul>
              <Callout>Product evidence never clears a customer automatically, and a customer on this list is not thereby suspected.</Callout>
            </Panel>
          </div>
        </>
      )}
    </>
  );
}
