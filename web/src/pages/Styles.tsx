import { Link, useParams, useSearchParams } from "react-router-dom";
import { allPages, api, type Returner, type Style } from "../api";
import { useWorkspace } from "../App";
import { TierBadge } from "../components/CustomerTable";
import { Badge, Callout, LoadState, PageTitle, Panel, Row, Stat, label, number, percent, rupees, useLoad } from "../components/ui";
import { VERDICT, headlinePair, lowVolume } from "../derive";

const STATES = ["all", "quality", "targeting", "mixed_or_uncertain", "no_elevated_signal", "insufficient_support", "no_return_evidence"] as const;
const tone = (state: Style["state"]) => (state === "targeting" || state === "mixed_or_uncertain" ? "amber" : state === "quality" ? "green" : "gray");

export function Verdict({ state }: { state: Style["state"] }) {
  return <Badge text={VERDICT[state].label} tone={tone(state)} title={VERDICT[state].sentence} />;
}

function TopReason({ style }: { style: Style }) {
  const top = style.reason_codes[0];
  if (!top) return <span className="muted">no return</span>;
  return (
    <>
      {label(top.code)}
      <small>
        {label(top.group)} / {number(top.units)} of {number(style.requested_units)} units
      </small>
    </>
  );
}

function Headline({ styles, runId }: { styles: Style[]; runId: string }) {
  const pair = headlinePair(styles);
  if (!pair) return null;
  const line = (s: Style) => `${percent(s.raw_return_rate)} returned (${number(s.requested_units)} of ${number(s.purchased_units)} units)`;
  return (
    <Panel title="Two styles with similar return rates and different stories">
      <div className="grid even">
        <div>
          <h3>
            <Link to={`/runs/${runId}/styles/${pair.quality.style_id}`}>{pair.quality.name}</Link> <Verdict state="quality" />
          </h3>
          <p className="muted">
            {line(pair.quality)}. {VERDICT.quality.sentence} Flagged returners: {percent(pair.quality.flagged_returner_share?.share, 0)}. Owner: {VERDICT.quality.owner}.
          </p>
        </div>
        <div>
          <h3>
            <Link to={`/runs/${runId}/styles/${pair.targeting.style_id}`}>{pair.targeting.name}</Link> <Verdict state="targeting" />
          </h3>
          <p className="muted">
            {line(pair.targeting)}. {VERDICT.targeting.sentence} Flagged returners: {percent(pair.targeting.flagged_returner_share?.share, 0)}. Owner: {VERDICT.targeting.owner}.
          </p>
        </div>
      </div>
    </Panel>
  );
}

export function StyleQueue() {
  const { runId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const state = (STATES as readonly string[]).includes(params.get("state") ?? "") ? (params.get("state") as string) : "all";
  const styles = useLoad(() => allPages<Style>((cursor) => api.styles(runId, state, cursor)), [runId, state]);
  const all = useLoad(() => (state === "all" ? Promise.resolve(null) : allPages<Style>((cursor) => api.styles(runId, "all", cursor))), [runId, state]);
  const forPair = state === "all" ? styles.data : all.data;
  return (
    <>
      <PageTitle title="SKU intelligence">Style-level evidence with SKU drill-down. A verdict describes the product evidence, never a customer.</PageTitle>
      {forPair && <Headline styles={forPair} runId={runId} />}
      <Panel>
        <div className="filters">
          <label>
            Verdict
            <select value={state} onChange={(e) => setParams(e.target.value === "all" ? {} : { state: e.target.value }, { replace: true })}>
              <option value="all">All</option>
              {STATES.filter((s) => s !== "all").map((value) => (
                <option key={value} value={value}>
                  {VERDICT[value as Style["state"]].label}
                </option>
              ))}
            </select>
          </label>
          {state !== "all" && <span className="small">{VERDICT[state as Style["state"]].sentence}</span>}
        </div>
        <LoadState state={styles} empty={!!styles.data && styles.data.length === 0}>
          No style has this verdict in this run.
        </LoadState>
        {styles.data && styles.data.length > 0 && (
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Style</th>
                  <th scope="col">Verdict</th>
                  <th scope="col">Return rate</th>
                  <th scope="col" title="Return rate shrunk towards the category rate; the expected rate for a style with this volume">
                    Expected rate
                  </th>
                  <th scope="col" title="Returners selected for review, over all customers who returned this style">
                    Flagged returners
                  </th>
                  <th scope="col">Top reason</th>
                  <th scope="col">Suggested owner</th>
                </tr>
              </thead>
              <tbody>
                {styles.data.map((s) => (
                  <tr key={s.style_id}>
                    <td>
                      <Link className="link" to={`/runs/${runId}/styles/${s.style_id}`}>
                        {s.name}
                      </Link>
                      <small>
                        {s.style_id} / {s.category}
                        {lowVolume(s) ? " / low volume: estimate leans on the category" : ""}
                      </small>
                    </td>
                    <td>
                      <Verdict state={s.state} />
                    </td>
                    <td>
                      {percent(s.raw_return_rate)}
                      <small>
                        {number(s.requested_units)} / {number(s.purchased_units)} units / {number(s.mature_sale_lines)} lines
                      </small>
                    </td>
                    <td>{percent(s.shrunk_return_rate)}</td>
                    <td>
                      {percent(s.flagged_returner_share?.share, 0)}
                      <small>
                        {s.flagged_returner_share ? `${s.flagged_returner_share.numerator} of ${s.flagged_returner_share.denominator} returners` : "n/a"}
                        {s.ring_returners ? ` / ${s.ring_returners} in a ring` : ""}
                      </small>
                    </td>
                    <td>
                      <TopReason style={s} />
                    </td>
                    <td>{VERDICT[s.state].owner}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <Callout>
        Quality issue: quality-reason share of 30% or more. Abuse target: at least three linked claimants and a linked-claim share of 7.5% or more. Mixed:
        both. Styles with fewer than 20 mature sale lines carry no verdict. Product evidence never clears a customer automatically.
      </Callout>
    </>
  );
}

function ReturnersTable({ returners, runId }: { returners: Returner[]; runId: string }) {
  if (!returners.length) return <p className="muted">No customer has a return request on this style.</p>;
  return (
    <div className="tablewrap small-table">
      <table>
        <thead>
          <tr>
            <th scope="col">Customer</th>
            <th scope="col">Score / tier</th>
            <th scope="col">Linked accounts</th>
            <th scope="col">Lines returned / bought</th>
            <th scope="col">Last reason</th>
          </tr>
        </thead>
        <tbody>
          {returners.map((r) => (
            <tr key={r.customer_id}>
              <td>
                <Link className="link" to={`/runs/${runId}/customers/${r.customer_id}`}>
                  {r.customer_id}
                </Link>
                <small>{r.selected_for_review ? "selected for review" : "not selected"}</small>
              </td>
              <td>
                {r.risk_score === null ? "unranked" : r.risk_score.toFixed(1)} <TierBadge tier={r.tier} />
              </td>
              <td>{r.community ? `${r.community.kind} of ${r.community.size}` : <span className="muted">none</span>}</td>
              <td>
                {r.return_lines ?? "?"} / {r.purchased_lines ?? "?"}
                <small>{r.requested_units} unit(s) requested{r.linked_claim_lines ? ` / ${r.linked_claim_lines} linked claim line(s)` : ""}</small>
              </td>
              <td>{r.last_reason_code ? label(r.last_reason_code) : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function StyleDetailPage() {
  const { runId = "", styleId = "" } = useParams();
  const { run } = useWorkspace();
  const state = useLoad(() => api.style(runId, styleId), [runId, styleId]);
  const detail = state.data;
  const s = detail?.style;
  const flagged = s?.flagged_returner_share ?? null;
  return (
    <>
      <Link className="button back" to={`/runs/${runId}/styles`}>
        Back to SKU intelligence
      </Link>
      <PageTitle title={s ? s.name : `Style ${styleId}`}>
        {s ? (
          <>
            {styleId} / {s.category} / {detail.skus.length} variant(s). <Verdict state={s.state} /> {VERDICT[s.state].sentence} Suggested owner: {VERDICT[s.state].owner}.
          </>
        ) : (
          ""
        )}
      </PageTitle>
      <LoadState state={state} />
      {detail && s && (
        <>
          <div className="stats">
            <Stat
              name="Return rate"
              value={percent(s.raw_return_rate)}
              note={`${number(s.requested_units)} of ${number(s.purchased_units)} units / expected ${percent(s.shrunk_return_rate)}${lowVolume(s) ? " / low volume: leans on the category" : ""}`}
            />
            <Stat name="Mature sale lines" value={number(s.mature_sale_lines)} note="At least 20 needed for a verdict" />
            <Stat name="Quality-reason share" value={percent(s.damage_share)} note="Carrier damage excluded / signal at 30%" />
            <Stat name="Linked-claim share" value={percent(s.linked_claim_share)} note={`${s.linked_claimers} linked claimant(s) / signal at 3 claimants and 7.5%`} />
          </div>
          <div className="grid even">
            <Panel title="Who is returning it">
              <Row name="Returners selected for review" note="A share of returners, not a statement about the product">
                {flagged ? `${flagged.numerator} of ${flagged.denominator} (${percent(flagged.share, 0)})` : "n/a"}
              </Row>
              <Row name="Returners in a ring">{s.ring_returners ?? "n/a"}</Row>
              <Row name="Distinct returners">{number(s.unique_returners)}</Row>
              <ReturnersTable returners={detail.returners} runId={runId} />
              <Callout>Product evidence never clears a customer automatically, and a customer on this list is not thereby suspected.</Callout>
            </Panel>
            <Panel title="Reasons given">
              {s.reason_codes.length === 0 ? (
                <p className="muted">No return request on mature lines.</p>
              ) : (
                s.reason_codes.map((r) => (
                  <Row key={r.code} name={label(r.code)} note={label(r.group)}>
                    {number(r.units)} unit(s) / {number(r.lines)} line(s) / {percent(s.requested_units ? r.units / s.requested_units : null, 0)}
                  </Row>
                ))
              )}
              <p className="muted">From the codebook; the customer's free text is never shown.</p>
            </Panel>
            <Panel title="When in the window">
              <Row name="Median return day" note="Days after delivery">
                {s.median_return_day === null ? "n/a" : number(s.median_return_day)}
              </Row>
              <Row name="Requests in the last five days of the window">{percent(s.share_in_last_five_days, 0)}</Row>
            </Panel>
            <Panel title="How risky the returners are">
              <Row name="Median score of the returners" note="Training reference percentile; not a probability">
                {s.median_returner_score === null ? "n/a" : s.median_returner_score.toFixed(1)}
              </Row>
              <Row name="Median score of the run's eligible customers">{run?.median_score === null || run?.median_score === undefined ? "n/a" : run.median_score.toFixed(1)}</Row>
              <p className="muted">
                {s.median_returner_score !== null && run?.median_score !== null && run?.median_score !== undefined
                  ? s.median_returner_score > run.median_score + 10
                    ? "The people returning this style score well above the run's median."
                    : "The people returning this style score about like everyone else."
                  : ""}
              </p>
            </Panel>
          </div>
          <Panel title="Evidence with denominators and SKU drill-down">
            {detail.signals.map((signal) => (
              <Row key={signal.code} name={signal.label}>
                {signal.value === null ? "n/a" : number(signal.value)}
                {signal.denominator !== null ? ` / ${number(signal.denominator)}` : ""} <span className="muted">{signal.unit.replace(/^units of /, "")}</span>
              </Row>
            ))}
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
        </>
      )}
    </>
  );
}
