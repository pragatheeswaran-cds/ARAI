# Frontend data gaps — Returns Analyst Workbench design vs the current API

**Purpose.** The design canvas (Returns Analyst Workbench, 9 artboards, 14 Oct 2026) was built from the
UI/UX spec without regard to what the system serves today. This document lists every data element the
screens show, says whether the current API contract (`web/src/api-types.ts`, generated from
`final-spec/contracts/openapi.yaml`) provides it, and what is needed if it does not.

**Status (15 Oct 2026).** Every row below is now served by API contract 1.12.0 or derived in `web/src/derive.ts`; the screens are built. `docs/frontend-data-plan.md` records what was decided and where each item landed. This document stays as the record of the gap analysis.

**How to use it.** For each row marked *Missing* or *Derivable*, decide one of: (a) add it to the API
response, (b) derive it in the frontend from fields that exist, (c) compute it in the ML pipeline and
publish it with the run, or (d) serve it from a synthetic fixture until (a)–(c) land. The last column
is a first guess at which of those applies; it is not a decision.

**Status key**

| Status | Meaning |
|---|---|
| Present | The contract has it under the name given |
| Derivable | Can be computed in the frontend from fields that exist, given an agreed rule |
| Partial | Something similar exists but the shape or granularity differs |
| Missing | Nothing in the contract produces it |

**Endpoint mapping.** The spec names `GET /flagged`, `GET /case/{id}`, `GET /skus`, `POST /jobs`. The
contract's equivalents are `GET /runs/{run_id}/customers`, `GET /runs/{run_id}/customers/{customer_id}`,
`GET /runs/{run_id}/styles` and `/styles/{style_id}`, `POST /runs`, `GET /experiments/{id}`. Everything
is scoped by `run_id`.

---

## 1. Shared chrome (sidebar, run strip)

| Element in design | Current contract | Status | Likely source |
|---|---|---|---|
| Active run id | `Run.run_id` | Present | — |
| Dataset name ("W5401 · operational") | `Run.dataset_id`, `Run.world_id`, `Dataset.purpose` | Present | Compose in UI |
| Customers scored | `Run.eligible_count` (+ `excluded_count`) | Present | — |
| Alerts in queue | `Run.selected_count` | Present | — |
| Alert budget ("of 625 budget") | — | Missing | API: add `review_budget` to `Run` (comes from `experiment.yaml` / model config) |
| Queue threshold score (62) | — | Missing | ML/API: the score at the budget cut; publish with the run |
| Time of run | `Run.completed_at` | Present | — |
| Reviewer selector list | — | Missing | UI constant for the hackathon; no login |
| Online / offline indicator | `Health.alive`, `scoring_ready` | Present | — |
| "New run in progress" note | `Run.status`, `Run.stage`, `Run.progress` | Present | — |
| Config hash (audit footer) | `ExperimentSummary.config_hash` | Present | Needs the run → experiment link |

## 2. Case Queue

| Element in design | Current contract | Status | Likely source |
|---|---|---|---|
| Rank | `Customer.rank` | Present | — |
| Case id | `Customer.customer_id` | Present | Design shows a short "C10482" plus an 8-char hash; the contract has one id. Confirm it is hashed |
| Risk score 0–100 | `Customer.risk_score` | Present | Confirm the scale is 0–100, or rescale in UI |
| Tier LOW / MEDIUM / HIGH | — | Derivable | Agree band cutoffs (design uses 0–44, 45–74, 75–100). Return `tier` from the API or derive in UI |
| Recommendation LOW / WARNING / HOLD / ESCALATE (gate outcome) | — | Missing | ML/API: a gate rule over score, tier, ring membership, wardrobing status. `Review.disposition` is a reviewer's opinion, not the gate |
| Up to three primary signal chips (plain language, < 40 chars) | `Customer.evidence_tags[]` (strings), `Case.signals[].label` | Partial | Need an ordered top-3 with plain-language phrasing and a tooltip value + rule id. Either rename tags or add `primary_signals[] {label, rule_id, value, denominator}` |
| Layer marks: rules / anomaly / graph fired | — | Missing | ML: tag each signal with its layer, or add `layers_fired: {rules, anomaly, graph}` |
| Ring: community id and size | `Case.neighbors[]` (per customer, no grouping) | Missing | ML: community detection output. Add `community {id, kind: ring\|household\|none, size}` to `Customer` |
| "Household" vs ring distinction | `Neighbor.supported`, `coordinated_claim_matches`, `max_value_fanout` | Partial | A benign/ring classification rule exists in spirit (supported edges, claim matches) but no field says which. Needs an explicit `kind` |
| Status: New / In review / Awaiting approval / Approved / Rejected / Auto-logged | `Customer.latest_disposition` (needs_investigation / likely_legitimate / unresolved) | Missing | API: review workflow state; see §5 |
| Awaiting-second-approval band (cases with a first reviewer needing a second) | — | Missing | API: query by workflow state; see §5 |
| "You opened this — needs another reviewer" | — | Missing | API: `opened_by` on the case |
| Show cleared heavy returners: high raw return rate but not selected | `Customer.selected_for_review`, `support_counts.mature_requested_units / mature_purchased_units` | Derivable | Raw rate from support counts; "heavy" cutoff (design: > 40%) to agree |
| One-line cleared reason ("size bracketing · consistent with basket") | — | Missing | ML/LLM: short template from the strongest explanatory feature |
| Ring grouping of rows (expandable) | — | Missing | Follows from community id |
| Pagination | `CustomerPage.next_cursor` | Present | Cursor-based; design shows page numbers. Use cursor and drop "page x of y" |
| Filters: tier, gate, layer, ring, wardrobing, status | query params: none beyond cursor/limit | Missing | API: add filters, or load the whole queue (several hundred rows) and filter client-side |

## 3. Case Detail — evidence (left column)

| Element in design | Current contract | Status | Likely source |
|---|---|---|---|
| Header: tier, score, recommendation, status, ring, run | see §2 | Partial | Same gaps as the queue |
| Cleared header sentence | — | Derivable | Template when `selected_for_review = false` and raw rate above cutoff |
| **Score breakdown**: contribution of rules / anomaly / graph summing to the blended score | `Customer.raw_score`, `risk_score` | Missing | ML: per-layer contributions (or SHAP-style attributions grouped by layer). Add `score_breakdown {rules, anomaly, graph}` |
| Fired rule ids with plain names and contribution (+14, +12, +8) | `Case.signals[] {code, label, value, denominator, unit, source_refs}` | Partial | `code` and `label` exist; contribution to score does not. Add `contribution` per signal |
| **Expected vs actual returns**: actual returned lines, expected lines for this basket, normal band (low–high), z residual | — | Missing | ML: leave-one-out basket baseline. Add `basket_expectation {actual_lines, total_lines, expected_lines, band_low, band_high, z}`. This is the product's central claim; nothing today carries it |
| "Why expected is high" facts (share of multi-size orders, kept per bracket, median return day) | — | Missing | Derivable from order lines if the timeline carries order id and size (see return behaviour row) |
| **First pass vs second pass** scores and delta | — | Missing | ML: publish both scores when a second pass runs. Add `first_pass_score`, `second_pass_score` |
| **Linked accounts graph**: nodes, edges by identifier type | `Case.neighbors[] {customer_id, shared_types[], shared_value_count, supported, ...}` | Partial | Only edges from this customer. To draw a ring as a cluster, need edges between neighbours too: `community.edges[] {a, b, types[]}` |
| Node scores for member cases, "+ N more" | `Neighbor` has no score | Missing | Join to `Customer` per neighbour, or include `risk_score` on `Neighbor` |
| Ring caption stats ("71% of lines across the ring") | — | Derivable | From member support counts once members are listed |
| Household caption ("linked accounts return at the run average") | — | Derivable | Member rates + run-wide average (run-wide average not exposed; add `Run.mean_return_rate`) |
| **Return behaviour table**: SKU, category | `TimelineEvent.sku`, `style_id`; category via `Style.category` | Present | — |
| Reason code per return | `TimelineEvent.description` (free text), `event_type` | Missing | Data: `reason-groups.yaml` exists in contracts; expose `reason_code` on the event. Free text must not be shown |
| Day returned / window length | `TimelineEvent.observed_at` only | Derivable | Need the matching order/delivery event and the policy window. Add `return_day`, `window_days` or pair events by `order_id` |
| Item received yes/no (claim) | `event_type` may encode it | Partial | Confirm event types; add `item_received: bool` |
| Order id and size, to group "3 sizes of one style, 1 kept" | — | Missing | Add `order_id`, `size` to `TimelineEvent`; kept lines need purchase events in the timeline too |
| Value in ₹ | `TimelineEvent.amount_inr` | Present | — |
| **Wardrobing panel**: status, signal checklist, fixed limitation text | `Case.wardrobing {status, indicator_score, signals[], limitation}` | Present | Design shows only when `status = elevated` |

## 4. Case Detail — memo and decision (right column)

| Element in design | Current contract | Status | Likely source |
|---|---|---|---|
| **Investigation memo** with sections: summary, key evidence, alternative explanations, recommended action | — | Missing | LLM: generate per selected customer at run time; validate; store. Add `memo {status: ok\|unavailable, sections{...}, generated_at, model, attempts}` |
| Evidence statements anchored to panels | — | Missing | Memo generator emits `anchors[]` naming the panel id (`expected`, `returns`, `linked`) |
| "Memo unavailable" state after retry / failed validation | — | Missing | Part of the memo object (`status`, `attempts`) |
| **Counterfactual**: score, tier and in/out of queue with each signal removed | — | Missing | ML: re-score with each layer or signal zeroed. Add `counterfactuals[] {signal, score, tier, in_queue}` |
| **Threshold slider**: queue size at any threshold | — | Missing | Derivable client-side from a score histogram of all eligible customers; add `Run.score_histogram` (bins) or load all scores once |
| Slider: "legitimate heavy returners caught at this threshold" | `GET /experiments/{id}/truth` (synthetic, evaluation-only) | Partial | Only for synthetic worlds via truth; for the demo, precompute per-threshold counts and publish with the experiment |
| **Decision panel** state | see §5 | Missing | — |
| Agree / Disagree feedback on LOW / cleared cases with optional reason | `POST .../reviews {reviewer_name, disposition, note}` | Partial | Can be stored as a review; needs a `kind` to separate feedback from approvals |
| Audit footer: memo time, queue log row link | — | Missing | `memo.generated_at`; queue log row id per selected customer |

## 5. Review workflow and the second-person rule

The contract's reviews are an append-only list of `{reviewer_name, disposition, note}`. The design needs
a small state machine and a server-side rule. All of this is missing.

| Needed | Notes |
|---|---|
| Review kinds: `open`, `approve`, `reject`, `feedback` | Or separate endpoints `POST .../open`, `POST .../approve`, `POST .../reject` |
| Case workflow state: new, in_review, awaiting_approval, approved, rejected, auto_logged | Derived server-side from the review list and the gate outcome |
| `opened_by`, `opened_at`, `decided_by`, `decided_at` on the case | Read-only record state in the design |
| Server refusal when approver = opener | 409 with a verbatim reason the UI shows unchanged. This is demonstrated on stage |
| Required note on open / approve / reject | Validation 4xx |
| Query: cases awaiting a second reviewer, excluding those the current reviewer opened | For the approval band |
| Auto-log for LOW / WARNING | No reviewer needed; still written to the queue log |

## 6. SKU Intelligence

| Element in design | Current contract | Status | Likely source |
|---|---|---|---|
| Style id, category, variant count | `Style.style_id`, `category`; `StyleDetail.skus[]` | Present | — |
| Human style name ("Aerin quilted jacket") | — | Missing | Data: add a `name` to the SKU master, or show style id only |
| Return rate with counts | `Style.raw_return_rate`, `requested_units`, `purchased_units` | Present | — |
| Expected rate ("shrunk baseline") | `Style.shrunk_return_rate` | Present | — |
| "Low volume — estimate leans on category" | `Style.state = insufficient_support`, `mature_sale_lines` | Derivable | — |
| Verdict: Quality issue / Abuse target / Normal / Not enough data | `Style.state` (quality, targeting, mixed_or_uncertain, no_elevated_signal, insufficient_support, no_return_evidence) | Present | Map `mixed_or_uncertain` to a fifth label or to "Normal" with a caution — decide |
| Returner concentration (share of returns from flagged customers or rings) | `Style.linked_claim_share`, `linked_claimers` | Partial | Linked-claim share is close but not the same as "from flagged customers". Add `flagged_returner_share` |
| Top reason codes per style | `Style.damage_share`, `claim_share` | Missing | Data: reason-code distribution per style |
| Suggested owner | — | Derivable | From verdict: quality → Merchandising; targeting → Returns policy |
| Headline pair (highest-contrast quality vs targeting) | — | Derivable | Client-side over the styles list: max rate among `quality`, paired with a `targeting` style of lower rate |
| Drawer 1 — who is returning it (share flagged, ring members) | `StyleDetail.customer_ids[]` | Partial | Needs a join to customers for score, tier, ring; better to return `returners[] {customer_id, risk_score, tier, community, lines_returned, lines_bought, last_reason_code}` |
| Drawer 2 — reasons given | — | Missing | Same as top reason codes |
| Drawer 3 — when in the window (median day, share in last five days) | — | Missing | Derivable from return events if `return_day` exists |
| Drawer 4 — how risky the returners are (median score vs run median) | — | Missing | Join plus `Run.median_score` |
| Verdict sentence ("an ordinary product returned by an unusual set of buyers") | — | Derivable | Template per state |
| Filters by verdict, pagination | `StylePage.next_cursor` | Partial | Cursor only; no verdict filter param |

## 7. Evaluation Scorecard

| Element in design | Current contract | Status | Likely source |
|---|---|---|---|
| Limitation banner | `Experiment.synthetic_only`, `coverage_limitations[]` | Present | — |
| Hero curve: abusers caught vs alerts used, for the raw-rate ranking and the selected model | `Metric {ranking, slice: "budget:<fraction>", value, numerator, denominator}` | Partial | Exists only at the published budget fractions. A curve needs 10–20 points per ranking; check how many `budget:` slices are published, or add a `curves` block |
| Marker at the alert budget | `Run.review_budget` (missing, §1) | Missing | — |
| Two statements at the budget (abusers caught, alerts spent on legitimate heavy returners) | `Metric.code` such as `review_rate.benign_household`, `precision` | Partial | Confirm codes for "legitimate heavy returners reviewed" and "abusers caught" exist for both rankings |
| Headline metrics with Wilson interval and n | `Metric.lower_95`, `upper_95`, `denominator` | Present | — |
| Development vs sealed seeds | `Metric.slice = validation` / `test` | Present | Gap computed in UI |
| Ablation table (what each layer adds) | `Metric.slice = ablation` | Present | Confirm the three rows exist as separate rankings or codes |
| Per-population breakdown, eight populations | `Metric.slice = honest_groups`, `error_account[]` | Partial | Need a code per planted population, and "left alone" phrasing for the benign ones. Confirm all eight are published |
| Achievable-separation ceiling | — | Missing | On the buy-back list; show only if published |
| Run manifest: git SHA, seeds, config hash, dataset hash | `config_hash`, `Dataset.manifest_hash` | Partial | Git SHA and seeds not exposed; add to `ExperimentSummary` |

## 8. Upload & Score

| Element in design | Current contract | Status | Likely source |
|---|---|---|---|
| Select seven contract files with present / missing checklist | `POST /datasets` registers a path or id; no file upload | Missing | API: multipart upload or a server-side folder picker; the checklist comes from `data-schema.yaml` |
| Preloaded dataset option | `GET /datasets` | Present | — |
| Validation: rows accepted, rows quarantined, reasons grouped, blocking flag | `Dataset.validation_status = "accepted"` only; `Error.details[] {rule_id, table, row_key, count}` on failure | Partial | Success path has no counts. Add `validation {accepted_rows, quarantined_rows, reasons[] {rule_id, table, count, blocking}}` |
| "Continue with N rows quarantined" | — | Missing | Needs non-blocking validation outcomes |
| Downloadable quarantined list | — | Missing | Endpoint or file link |
| Stepper: stages ingest → features → detection → second pass → investigation | `Run.stage` (string), `Run.progress` | Partial | Agree the five stage names; add per-stage `started_at`, `completed_at` for elapsed times |
| Sub-stage detail ("graph: 7,120 of 10,214 nodes") | — | Missing | Optional; `Run.stage_detail` |
| Job failed: stage, message, retry | `Run.status = failed`, `Run.error`, `Run.stage` | Present | — |
| Done summary: customers scored, alerts, rings found, SKUs with a verdict | `eligible_count`, `selected_count`; rings and SKU-with-verdict counts missing | Partial | Add `community_count` and `styles_with_verdict` to `Run` |
| Cancel run | — | Missing | Optional |

## 9. Cross-cutting rules the data must respect

- Only hashed identifiers reach the UI. Confirm `customer_id` is a hash; the design truncates to 8 characters with copy-on-click for the full value.
- Free-text return reasons are never shown. `TimelineEvent.description` must not contain customer-written text, or the UI must ignore it in favour of `reason_code`.
- Every rate ships with its counts; every headline metric ships with its interval and n. The `Metric` shape already does this; the per-style and per-customer shapes need numerator and denominator too.
- Scores are rankings, not probabilities. No field should be named or documented as a probability of abuse.
- The memo is a draft. Memo status must be explicit so the UI never shows a partial or unvalidated memo.

## 10. Suggested synthetic fixture set (if the backend lands later)

One JSON bundle that matches the design exactly, usable by the frontend and as the target shape for the API:

| File | Contents |
|---|---|
| `run.json` | Run with budget, threshold, counts, stage timings |
| `queue.json` | 625 selected customers with tier, gate, primary signals, layers, community, workflow state; plus ~30 cleared heavy returners with a reason |
| `case-C10482.json` | Full flagged case: breakdown, basket expectation, first/second pass, community with edges, timeline with reason codes and order ids, wardrobing, memo, counterfactuals, workflow state (opened by someone else) |
| `case-C20391.json` | Full cleared case: same shape, household community, memo, counterfactuals, auto-logged |
| `score-histogram.json` | Score bins for all eligible customers, plus per-threshold counts of legitimate heavy returners (from truth) |
| `styles.json` | 300–400 styles with names, verdicts, reason codes, flagged-returner share |
| `style-SKU-JK-4821.json`, `style-SKU-SN-1190.json` | Drawer data: four questions and returner list |
| `experiment.json` | Metrics with intervals, two budget curves with 15 points each, ablation, eight populations, manifest |
| `job-running.json`, `job-failed.json` | Run objects for the stepper states |

## 11. Smallest set that unblocks the demo path

Queue → C10482 → C20391 with slider → SKU pair → Scorecard chart needs, in priority order:

1. Tier bands and gate outcome.
2. Basket expectation (actual, expected, band, z) on the case.
3. Score breakdown by layer and first/second pass scores.
4. Community id, kind and size with member edges.
5. Memo object with status.
6. Review workflow with the second-person refusal.
7. Score histogram for the slider.
8. Style names, reason codes and flagged-returner share.
9. Budget curve points for both rankings.

Everything else can start as a fixture or a placeholder without changing the screens.
