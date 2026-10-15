# Frontend data plan — closing the gaps in `frontend-data-gaps.md`

Written 2026-10-14 against branch `frontend` (commit c53ce9e), after reading the contract
(`final-spec/contracts/openapi.yaml`), the pipeline (`src/arai/features.py`, `scoring.py`, `publishing.py`),
the store (`src/arai/service/store.py`, `migrations/`), the read models (`views.py`), the API (`api.py`) and the
data contracts (`data-schema.yaml`, `features.yaml`, `reason-groups.yaml`, `experiment.yaml`).

**Short version.** The gaps document is right about the big absences (memo, counterfactuals, review workflow,
communities) but wrong or too pessimistic on about a third of its rows: a lot of what it marks *Missing* is
already computed by the pipeline and either stored but not served, or folded into free text. The genuinely
missing pieces trace to one cause: the design was drawn from the original product scope (rules + Isolation
Forest + Louvain graph + community-aware second pass + LLM memo, see `specs/01-product/scope.md`), while the
system that shipped is one supervised ranking plus measured evidence. Everything below is evidence and
read-model work; **nothing in this plan changes a score, a rank or a selection, so no new experiment is needed.**

---

## 1. Corrections to the gaps document

Rows whose status changes after checking the code. Rows not listed stand as written.

| § | Element | Doc says | Verified | Why |
|---|---|---|---|---|
| 1 | Alert budget | Missing | **Stored, not served** | `summary.review_budget_k` is written into `runs.summary` (`scoring.py` summary dict) and never put in `run_body`. Also derivable: `min(N, ceil(0.05 × eligible_count))` (`ranking.budget`). |
| 1 | Queue threshold score | Missing | **Derivable server-side** | `risk_score` of the customer at `rank = review_budget_k`. One SQL. |
| 2 | Case id is a hash | Confirm | **It is not a hash** | Ids are `W5401-C00042` (world prefix + sequence, `docs/experiment-4-data-guide.md` §2). An 8-char truncation shows `W5401-C0`. Show the full 12-char id; drop the hash affordance. |
| 2 | Risk score 0–100 | Confirm | **Confirmed, but it is a percentile** | `bundles.reference_percentile`: position of the raw score in the frozen training distribution. Design tiers at 45/75 would put 25% of customers in HIGH while the queue is 5%. See decision D1. |
| 2 | Filters | Missing | **Partial** | `GET /customers` already filters on `review_only`, `eligibility`, `search`, `evidence` (tag), `disposition`, `comparison`. Not on tier, gate, ring, wardrobing or workflow state. Wardrobing is a stored column; trivial to add. |
| 2 | Layer marks | Missing | **No layers exist** | The model is one boosted-tree candidate over 43 features. There is no rules layer, anomaly layer or graph layer in scoring. The "layers" can only be *presented* families of evidence (§3.2). |
| 3 | Expected vs actual returns | Missing, "nothing today carries it" | **Present except the band** | `Case.signals` carries `mature_requested_units` (actual), `expected_requested_units` (expected, two-level self-excluded baseline), `raw_return_rate`, `expected_return_rate` and `residual_z`. Only the standard deviation behind the band is not published. |
| 3 | "Why expected is high" facts | Missing | **Partly stored** | `bracketing_share` is a model feature and sits in `run_customers.measures`. Per-bracket kept counts and median return day are derivable once the timeline carries order id, size and day (next row). |
| 3 | Reason code per return | Missing | **Computed, folded into text** | `scoring._timeline` builds `description` from `reason_code`, units, `day N of a W-day window`, `line_status`, and a linked-claim flag. `reason_text` (customer free text) is never read. Exposing structured columns is a column add, not pipeline work. |
| 3 | Order id, size, kept lines | Missing | **Computed, folded into text** | Purchases are already timeline events (`event_type = purchase`) with order id in `source_ref` and size in the description. |
| 3 | Item received | Partial | **In the raw table, not carried** | `return_order_line.return_received_flag` (null when the reason needs no item back). |
| 3 | Node scores for neighbours | Missing | **Trivial join** | `run_customers` has `risk_score` per neighbour in the same run. |
| 3 | Household vs ring | Partial | **Derivable by rule** | See §3.1; `coordinated_claim_matches` on edges is the observable differentiator. |
| 4 | Threshold slider | Missing | **Derivable from stored rows** | Every eligible customer has `risk_score`, `rank` and `baseline_rank` in `run_customers`. Histogram and queue size at any threshold are one query. |
| 4 | Legitimate heavy returners at a threshold | Partial | **Derivable for the demo world** | `experiment_truth` (y_abuse per customer of W5401) joined to `run_customers` of a W5401 run, with "heavy" = raw rate ≥ 90th percentile of eligible customers (the gate's own definition, `evaluation.benign_segments`). |
| 7 | Hero curve | Partial, "check how many budget slices" | **Three points (1%, 5%, 10%)** | `experiment.yaml budgets`. A full curve for both rankings is derivable from the same join as the slider: cumulative abusers over rank, and over baseline rank. |
| 7 | Eight populations | Partial | **All eight published** | Per ranking and slice: `recall.deceptive_nonreceipt_claim`, `recall.deceptive_contents_claim`, `recall.temporary_use_return` (abuser populations) and `review_rate.{legit_heavy_returner, defective_product_buyer, benign_household, repeat_genuine_claimant, one_genuine_failure}` (honest populations). |
| 7 | Ablation table | Present, "confirm three rows" | **Six rows, different cut** | Slice `ablation` has `all`, `first_contract`, `without_late_return_lines`, `without_timing`, `without_claims`, `without_claims_and_timing` plus `ablation.rule`. The honest table is "what claims add / what timing adds", not rules/anomaly/graph. |
| 7 | Git SHA, seeds | Partial | **Seeds in config, SHA nowhere** | `experiment.yaml` lists seeds; `config.json` records code and feature hashes, not a git SHA. Add at train time. |
| 8 | Upload seven files | Missing, "no file upload" | **Present** | `POST /datasets` is multipart: `manifest` + seven table files, each exactly once. Missing or unknown parts come back as 422 details with `upload.missing_part` / `upload.unknown_part`. The checklist is servable from that, or client-side before submit. |
| 8 | Quarantine | Partial | **All-or-nothing by design** | `datasets.register` raises `Rejected` on any violation; there is no non-blocking outcome. "Continue with N quarantined" is a contract change (`data-schema.yaml` requires every row valid). Decision D5. |
| 8 | Stepper stages | Partial | **Eight real stages, no timings** | `store.STAGES`: queued, validate, features, eligibility, scoring, evidence, publish, done. Only `started_at` and `completed_at` exist on the run. No "second pass" exists. |
| 9 | Free text never shown | Rule | **Already true** | `reason_text` is `evidence_only` in the schema and no code path reads it. |
| 9 | Scores are not probabilities | Rule | **Already true** | Bundle `score_label` is "Training reference percentile". |

Confirmed **Missing** with nothing to build on: investigation memo and its gate, counterfactuals, score
attribution, first/second pass, community id/kind/size, review workflow and the second-person refusal, style
names, reason-code distribution per style, flagged-returner share, per-stage timings, cancel run, achievable
separation ceiling.

---

## 2. Constraints every addition must respect

These are not preferences; they are what keeps the published model valid.

1. **Do not touch `features.py`, `dataset.py`, `modeling.py`, `bundles.py` or `ranking.py`.** They are the
   `CODE_FILES` hashed into every bundle (`bundles.code_sha256`). A change makes every later run carry the
   warning "the scoring code differs from the code this bundle was published with", and `publishing.verify_feature_code`
   compares the feature frame to the frozen training frame **exactly**, so adding a column there breaks
   republishing. New per-customer evidence goes in `service/scoring.py` (not hashed) using `FeatureResult.lines`,
   `.requests`, `.graph` which `compute_features` already returns.
2. **Results are written once, in the transaction that marks a run succeeded** (`store.finish_run`). New evidence is
   a new result table or new columns, written in the same transaction; no recompute on read.
3. **Serving never sees truth.** The only truth in the database is the demo world export (`experiment_truth`:
   `y_abuse`, `action_types`). Anything built from it is evaluation-page material, labelled synthetic.
4. **Reviews are append-only** and the API "has no route that edits or deletes a note" (`api.py` docstring). The
   workflow is modelled as more kinds of append, with state derived on read.
5. **Every rate ships with its counts.** New fields follow the `Signal {value, denominator}` shape or carry
   numerator and denominator explicitly.
6. Adding a result table means: migration SQL, a column spec in `service/results.py`, a reader in `store.py`,
   a shaper in `views.py`, the schema in `openapi.yaml`, and regenerated `web/src/api-types.ts`. Each work
   package below lists which of these it touches.

---

## 3. Work packages

Ordered so that each unblocks the next screen in the demo path. Sizes are for the backend; the frontend work
per package is the screen that consumes it.

### WP0 — Serve what is already computed (half a day)

No pipeline change; `store.py`, `views.py`, `api.py`, `openapi.yaml`, one migration.

**Status: done on branch `frontend-implementation` (contract 1.4.0, schema version 4, AM-55).** Two names differ from the table below: the pooled rate ships with its counts as `eligible_requested_units` and `eligible_purchased_units`, and the `Neighbor` fields are `risk_score`, `rank`, `selected_for_review`, `evidence_tags`. The new timeline columns are null for runs scored before the upgrade; submit a new run on the demo world to see them.

| Field | Where it comes from |
|---|---|
| `Run.review_budget` | `runs.summary->>'review_budget_k'` |
| `Run.threshold_score` | `risk_score` where `rank = review_budget_k` |
| `Run.mean_return_rate`, `Run.median_score` | aggregates over `run_customers` (eligible) |
| `Run.graph_edges` | already in summary |
| `TimelineEvent`: `order_id`, `order_line_no`, `quantity`, `size`, `reason_code`, `reason_group`, `day_in_window`, `window_days`, `line_status`, `item_received`, `linked_claim` | the same frames `scoring._timeline` already reads; add columns to `run_timeline` and keep `description` for compatibility |
| `Neighbor.risk_score`, `Neighbor.rank`, `Neighbor.selected_for_review`, `Neighbor.evidence_tags` | join to `run_customers` |
| `GET /customers?wardrobing=elevated` | stored column |
| `GET /runs/{id}/score-distribution` | bins of `risk_score` over eligible customers, plus `selected_at_or_above` per bin; serves the slider and the histogram |

### WP1 — Communities: the clustering the design assumes (1 day)

`scoring.py` + new table `run_communities` + `Customer.community` + `Case.community`.

**Status: done on branch `ccr-488644ae-esclgi` (contract 1.6.0, AM-57).** `Customer.community {id, kind, size}` (null without a supported edge), `Case.community` with `method`, the member sums, `members[]` carrying each member's own result and `edges[] {a, b, types, coordinated_claim_matches}`; `Run.community_count` and `Run.ring_count`; queue filters `community=ring|household|none` and `community_id`. Table `run_communities` and `run_customers.community_id` (schema version 5). The kind rule is checked offline by `scripts/community_check.py`; the confusion against `relationship_truth` is in `records/2026-10-15-community-kind-check.md`.

- Input: `result.graph.edges` (`customer_a`, `customer_b`, `shared_types`, `shared_value_count`,
  `max_value_fanout`, `weight`). An edge already needs two shared identifier types and values shared by more
  than 25 accounts are already dropped, so components are small and clean.
- Algorithm: **connected components** over supported edges is enough for this graph and is deterministic.
  Louvain on `weight` only matters if a component is large enough to split; cap: if a component has more
  than, say, 12 members, run Louvain inside it (networkx `louvain_communities`, fixed seed). Record which
  method produced each community.
- Output per community: `community_id` (world-scoped, sha of sorted member ids), `size`, `members[]` with
  each member's `risk_score`, `rank`, `selected_for_review`, `mature_requested_units`,
  `mature_purchased_units`, and `edges[] {a, b, types[], coordinated_claim_matches}` (the `_neighbors`
  function already computes matches per directed edge).
- **Kind rule (§3.1).** Observable only; truth is never used at scoring time.
  - `ring` if any edge in the community has `coordinated_claim_matches ≥ 1`, or two or more members are
    selected for review, or a member's `coordinated_claim_share > 0`.
  - `household` otherwise when `size ≥ 2`.
  - `none` for a customer with no supported edge.
  - Why this separates them: the generator gives households a shared address with probability 1.0 and a
    shared payment 0.3, coordination groups a shared device 0.8 and payment 0.7 with an address only 0.4
    (`generator/relationships.py`), and only coordination groups claim on the same style within seven days.
    The rule can be checked offline on any training world against `relationship_truth.group_type` before the
    demo; record the confusion in `records/`.
- Derived captions: ring "71% of lines across the ring" = sum of member requested over sum of member
  purchased; household "returns at the run average" = member rate against `Run.mean_return_rate`.
- `Run.community_count` and `Run.ring_count` go into the summary.
- Queue grouping by ring and the `ring` filter follow from `Customer.community.id`.

### WP2 — Attribution, counterfactuals, gate outcome, tiers (1.5 days)

`scoring.py`, a new `service/attribution.py`, new table `run_attributions`, new fields on `Customer`/`Case`.

**Status: done on branch `ccr-488644ae-esclgi` (contract 1.7.0, AM-58).** `Customer.tier`, `Customer.gate_outcome` and `Customer.primary_signals[]`; `Case.score_breakdown` (five families, `typical_from`, `threshold_raw_score`, each row with `in_queue_without` and `tier_without`, so it serves the counterfactual panel too) and `Case.rules_fired[]`; queue filters `tier` and `gate` as the same rules in SQL. Table `run_attributions` (schema version 6). Computed for every eligible customer, so the cleared case has its breakdown too. The first/second pass panel is dropped: nothing exists to publish.

- **Method: family re-scoring with the frozen pipeline, predict-side only.** For each selected customer and
  each feature family, set the family's features to the training median (the bundle manifest carries
  `feature_quantiles[name] = [p10, p50, p90]`), call `bundles.raw_scores`, map through
  `reference_percentile`, and compare with the threshold raw score at rank k. That gives in one pass:
  - `score_breakdown[] {family, score_without, delta_points, in_queue_without}` — honest wording is "score with
    this family at typical values", **not** contributions that sum to the score. Boosted trees do not decompose
    additively; the design's "+14 +12 +8 summing to 58" cannot be produced truthfully. If an additive
    decomposition is wanted, SHAP (`shap.TreeExplainer` supports `HistGradientBoostingClassifier`) is the
    alternative at the cost of a dependency and a skops allow-list change; recommend the re-scoring method.
  - `counterfactuals[]` — the same rows; the design's "signal removed" is a family removed.
- Families (from `ablation.py` plus the remaining features): `claims` (20 features), `timing` (10),
  `expected_vs_actual` (raw rate, expected rate, residual z, refund ratio, trend), `composition` (damage,
  bracketing, occasion, discretionary, open-window shares), `volume` (mature lines, order count, units per
  order). Links are evidence-only except `coordinated_claim_share`, which belongs to `claims`.
- Cost: about 300 selected customers × 5 families = 1,500 predictions, under a second.
- **Rules "layer":** the analyst rulebook (`selection.RULEBOOK_RULES`, five rules) is a report-only reference
  today. Its two thresholds are the training p90 of `raw_return_rate` and `requested_refund_ratio`, which are
  in the bundle's `feature_quantiles`, so `rules_fired[] {rule_id, label, fired}` can be computed per customer
  at scoring time with no new artefact. Present as "rules that would have fired", not as part of the score.
- **Primary signals (top 3 chips):** order the existing `evidence_tags` by the family deltas above; label
  table in `views.py` (tag → plain phrase under 40 characters, tooltip from the matching `Signal`). No new
  pipeline output.
- **Gate outcome** (decision D2): a stated rule in `views.py`, versioned in the contract, for example
  `ESCALATE` = selected and (ring or wardrobing elevated); `HOLD` = selected otherwise; `WARNING` = not
  selected and (tier MEDIUM or raw rate above the heavy cutoff); `LOW` = rest.
- **Tier** (decision D1): recommend anchoring to the queue, not to fixed percentiles: `HIGH` = selected;
  `MEDIUM` = `risk_score ≥ 90` and not selected; `LOW` otherwise. Serve `tier` from the API so the UI and
  the memo agree.
- **First pass / second pass:** nothing to publish; the system has one pass. Remove the panel or relabel it
  "model score / return-rate rule score" using `rank` against `baseline_rank`, which exist for every customer.

### WP3 — Basket expectation band and the cleared reason (half a day)

`scoring.py` only (uses `result.lines` which carries `p_expected` per mature line).

**Status: done on branch `frontend-implementation` (contract 1.5.0, AM-56).** `Customer.basket_expectation` carries `actual_units`, `purchased_units`, `expected_units`, `sd`, `band_low`, `band_high`, `z`; `Customer.cleared_reason` is the template key; `Run.heavy_returner_cutoff` is the 90th percentile. The bracketing facts and the median return day are signals on the case (`bracketing_units`, `bracketing_kept_units`, `median_return_day`).

- `basket_expectation {actual_units, purchased_units, expected_units, sd, band_low, band_high, z}` with
  `sd = sqrt(d × Σ q·p·(1−p))` recomputed from `result.lines` exactly as `compute_features` does, and
  `band = expected ± 2·sd`. Serve as a `Signal` group on `Case` and as three numbers on `Customer` for the
  queue's cleared rows.
- "Why expected is high": from the same frame, `multi_size_order_share` (= `bracketing_share`, already
  stored), `kept_per_bracket {sizes_ordered, kept}` per order/style, and `median_return_day` from the
  requests frame.
- **Cleared reason, one line, templated, not generated:** choose the strongest of `bracketing_share ≥ 0.5`
  ("size bracketing · consistent with basket"), `expected_return_rate ≥ 0.35` ("buys high-return styles"),
  `residual_z < 1` ("returns at the rate the basket predicts"), else "below the review threshold". Store the
  template key, render text in the UI.
- Heavy-returner cutoff for "cleared heavy returners": use the gate's own definition, the 90th percentile of
  eligible raw rates in this run, stored as `Run.heavy_returner_cutoff`, rather than the design's fixed 40%.

### WP4 — SKU Intelligence extras (1 day)

`scoring.py` (from `result.requests`, `customer_styles`), `run_styles` columns, new `run_style_reasons`.

**Status: done on branch `ccr-488644ae-esclgi` (contract 1.9.0, AM-60).** `Style.name`, `median_return_day`, `share_in_last_five_days`, `flagged_returner_share {numerator, denominator, share}`, `ring_returners`, `median_returner_score`, `reason_codes[]`; `StyleDetail.returners[]` beside `customer_ids` (same ids, same order, so the UI keeps working). Schema version 8.

- `reason_codes[] {code, group, lines, units}` per style (top reasons drawer and the queue column).
- `median_return_day`, `share_in_last_five_days` per style from request timing.
- `flagged_returner_share {numerator, denominator}` = returners selected for review / unique returners;
  `ring_returners` from WP1.
- `returners[]` for the drawer: `run_customer_styles` joined to `run_customers` (score, tier, community,
  lines returned, lines bought, last reason code), replacing bare `customer_ids`.
- `median_returner_score` against `Run.median_score`.
- **Style name:** `sku_master` has `brand` and `category` but no name. Compose `"{brand} {category}"` and
  append the style id when the pair is not unique in the run. A real name column is a data-schema change the
  team's adapter would have to supply; not worth it for the hackathon.
- Verdict filter: `state` is already a query parameter on `GET /styles`.

### WP5 — Evaluation page data (half a day)

`publishing.py` (offline, re-run `arai publish`, no training) and one endpoint.

**Status: done on branch `ccr-488644ae-esclgi` (contract 1.10.0, AM-61).** `GET /experiments/{id}/curves?run_id=&max_points=` (every k, thinned to 200 by default, budget and last k always kept; 409 `world_mismatch` for a run on another world); `ExperimentSummary.git_sha` and the five seed lists. The SHA is recorded at publish time, not train time: `modeling.py` is a hashed scoring file and stays untouched. Experiment 4 needs a verification-only republish to carry the fields; until then they read null and empty.

- `GET /experiments/{id}/curves?run_id=` : from `experiment_truth` × `run_customers` of a run on the truth
  world, cumulative `abusers_caught` and `legitimate_heavy_returners_reviewed` over `rank` and over
  `baseline_rank`, every k from 1 to eligible. Fifteen points is the design's choice; the endpoint can return
  all. Labelled `synthetic_only: true` like the truth page. This also answers the slider's second line.
- `ExperimentSummary.git_sha`, `train_seeds`, `validation_seeds`, `test_seeds`, `demo_seed`: seeds from
  `experiment.yaml`; the SHA recorded by `train_experiment` into `config.json` (`git rev-parse HEAD`,
  "unknown" when not a repository). Requires a republish to appear for experiment 4; a republish is
  verification-only and does not refit.
- Marker at the budget: `Run.review_budget` from WP0.
- Ablation rows: present as claims / timing / both, per the real slice.
- Ceiling: stays unpublished; the page shows it only if a metric with code `ceiling.*` exists.

### WP6 — Review workflow and the second-person rule (1 day)

`store.py`, `api.py`, `openapi.yaml`, one migration on `reviews`.

**Status: done on branch `ccr-488644ae-esclgi` (contract 1.8.0, AM-59).** Kinds `note | open | request_approval | approve | reject | feedback` (`request_approval` instead of a second `open`, so the state is never ambiguous); `Customer.workflow {state, opened_by, opened_at, decided_by, decided_at}` derived on read; 409 `case_not_open` and 409 `second_reviewer_required` with the fixed message; queue filters `state` and `exclude_reviewer`. Schema version 7 adds `reviews.kind`.

- Add `kind` to reviews: `open | approve | reject | feedback | note`, existing rows become `note`. The
  table stays append-only.
- State derived on read in SQL, per `(world_id, customer_id)`: `auto_logged` when gate is LOW or WARNING
  and no review; `new` when nothing; `in_review` after `open`; `awaiting_approval` after a second `open`
  or an explicit `request_approval` kind if the design needs it; `approved` / `rejected` after the kind.
  Expose `workflow {state, opened_by, opened_at, decided_by, decided_at}` on `Customer`.
- Server rule: `approve` or `reject` by the same `reviewer_name` as the latest `open` returns
  `409 second_reviewer_required` with a fixed message the UI shows verbatim. A note is required on open,
  approve and reject (422 otherwise).
- Queue filter `state=awaiting_approval&exclude_reviewer=<name>` for the approval band.
- `feedback` kind carries `disposition` for LOW and cleared cases without changing state.

### WP7 — Investigation memo with a deterministic gate (1.5 days)

New stage after `evidence`, table `run_memos`, `Case.memo`.

**Status: done on branch `ccr-488644ae-esclgi` (contract 1.11.0, AM-62).** `service/memo.py`: the case as served minus reviews, sentences and other customers' ids; `claude-opus-5-5` (`ARAI_MEMO_MODEL` overrides) with structured output and `fallbacks: "default"`; the deterministic gate; two attempts; a pool of four after `finish_run`. `Case.memo {status: ok | unavailable | pending | not_selected, ...}`; `Run.memos {selected, ok, unavailable, complete}` instead of a `Run.stage = investigation`, because a succeeded run's stage stays `done`. Without `ANTHROPIC_API_KEY` every memo is `unavailable` (`no_api_key`) and nothing is called. Table `run_memos` (schema version 9).

- **Input is the Case JSON only**: signals, basket expectation, attribution, community, timeline rows,
  wardrobing. No free text, no truth, no identifiers beyond the customer id.
- **Generation:** one call per selected customer with the Anthropic Python SDK, `claude-opus-5-5`,
  structured output (`output_config.format`) for `{summary, key_evidence[] {statement, panel, value,
  denominator}, alternative_explanations[], recommended_action}`. Streaming is not needed for a short
  JSON; keep `max_tokens` modest. Include the server-side `fallbacks` parameter so a declined request is
  retried on a fallback model inside the same call.
- **Gate (the "independent deterministic gate" of the original scope):** every number in
  `key_evidence` must equal a value or denominator present in the case; every `panel` must be one of
  `expected | returns | linked | wardrobing`; the action must be one of the gate outcomes; no customer id
  other than the case's may appear; length limits. Failing the gate twice gives `status = unavailable` with
  `attempts` and the reason. The UI never shows a memo without `status = ok`.
- **Operational facts to plan around:** the worker is one thread (`worker.py`), so 300 sequential calls add
  minutes to a run; run memos concurrently with a small pool after `finish_run` so results stay available
  while memos arrive, and let `Run.stage = investigation` report progress. The VM profile may have no
  outbound network or key; then every memo is `unavailable` by design and the screens must look right that way.
- `memo.generated_at`, `model`, `attempts` feed the audit footer.

### WP8 — Upload & Score polish (half a day, plus one decision)

**Status: done on branch `ccr-488644ae-esclgi` (contract 1.12.0, AM-63).** `Run.stage_log[] {stage, at}` (schema version 10), `Run.styles_with_verdict`, `POST /runs/{run_id}/cancel` (queued: interrupted at once; running: cooperative stop at the next stage, error code `cancelled`; finished: 409 `run_finished`). The checklist and the stage mapping are UI work from fields that exist; quarantine stays blocking (D5).

- Checklist of seven files: build client-side from `data-schema.yaml` table names; on 422 map
  `upload.missing_part` rows onto it.
- Stage mapping for the stepper: `validate → ingest`, `features + eligibility → features`,
  `scoring → detection`, `evidence → investigation` (memo stage joins it in WP7). Drop "second pass".
  Add `runs.stage_log JSONB` appended by `update_stage` for per-stage elapsed times.
- `stage_detail` is optional; the graph size is already in the summary.
- Done summary: `community_count`, `ring_count` (WP1) and `styles_with_verdict` (count of
  `state in (quality, targeting, mixed_or_uncertain)`) into the summary.
- Cancel: a queued run can flip to `interrupted` atomically; a running run needs a cooperative check in the
  stage callback. Low priority.
- Quarantine: decision D5. Recommend keeping validation blocking and showing grouped reasons from the 422
  details, which exist today.

---

## 4. What the frontend derives itself

Rules the UI applies with fields that exist after WP0. Keep each rule in one place (`web/src/derive.ts`)
and mirror the server rule where one exists.

| Element | Rule |
|---|---|
| Dataset name | `${world_id} · ${purpose}` |
| Config hash footer | `ExperimentSummary.config_hash` of the experiment whose `selected_model_id = Run.model_id` |
| Cleared heavy returners | `!selected_for_review && mature_requested_units / mature_purchased_units ≥ Run.heavy_returner_cutoff` |
| Low-volume caption on a style | `state === "insufficient_support"` or `mature_sale_lines < 20` |
| Suggested owner | `quality → Merchandising`, `targeting → Returns policy`, `mixed_or_uncertain → both` |
| Headline style pair | highest `raw_return_rate` among `state = quality` paired with a `targeting` style of lower rate |
| Verdict sentence | one template per `state`; `mixed_or_uncertain` gets its own ("elevated on both counts; read the evidence") |
| Dev vs sealed gap | `validation` minus `test` metric with the same `code` and `ranking` |
| Pagination | cursor only; show "more" rather than page numbers |
| Run-in-progress note | `Run.status in (queued, running)` with `stage` and `progress` |

---

## 5. Decisions

**All eight decided on 2026-10-15, each on the recommendation.** The table is kept as the record; the
work packages above build to these.

| # | Decision | Decided |
|---|---|---|
| D1 | Tier cutoffs on a training-percentile score | Anchor to the queue: HIGH = selected, MEDIUM = `risk_score ≥ 90` and not selected, LOW otherwise. The design's 45/75 would label a quarter of customers HIGH. |
| D2 | Gate outcome rule | The rule in WP2, versioned in `openapi.yaml` as an enum with its definition in the description. It is a presentation rule, not a model output, and the UI should say so. |
| D3 | Community kind rule | WP1's rule, validated offline against `relationship_truth` on two training worlds and recorded. |
| D4 | Customer id display | Full id, copy on click. No hashing in the demo; the data guide already says the ids are synthetic. |
| D5 | Non-blocking quarantine | Keep validation blocking. "Continue with N rows quarantined" is a contract change and not needed for the demo path. |
| D6 | Score breakdown wording | "Score with this family at typical values", never contributions summing to the score. |
| D7 | Memo model and runtime | `claude-opus-5-5` with structured output and the deterministic gate; memos generated after the run completes so results are never held back by the LLM. |
| D8 | `mixed_or_uncertain` label | Fifth verdict label, not folded into Normal. |

---

## 6. Order of work against the demo path

The gaps document's §11 list, re-ordered by what is already there:

1. **WP0** — budget, threshold, structured timeline, neighbour scores, histogram. Unblocks the queue header, the return behaviour table and the slider's first line.
2. **WP3** — basket expectation band and the cleared reason. Unblocks the C10482 and C20391 panels; most of it is already served.
3. **WP1** — communities. Unblocks ring grouping, the linked-accounts graph and the ring/household captions.
4. **WP2** — attribution, counterfactuals, tiers, gate. Unblocks the score panel, the chips and the queue columns.
5. **WP6** — workflow and the 409. The stage demonstration.
6. **WP4** — style extras. SKU pair screen.
7. **WP5** — curves and manifest. Scorecard.
8. **WP7** — memo. Last, because every screen must already look right with `memo.status = unavailable`.
9. **WP8** — stepper and upload polish.

Backend total: about eight working days for one person; WP0, WP3 and WP5 are independent and can run in
parallel with WP1 and WP2.

**Fixtures.** The `data/` folder is not present in this working tree (it is git-ignored and the runbook expects
`data\EXP-20261005-04`), so fixtures cannot be cut from a live run on this machine without restoring it or the
team package (`data/exports/EXP-20261005-04`). Once WP0 to WP4 land, every fixture in the gaps document's §10
except the memo can be a saved API response from a W5401 run, which is better than hand-written JSON because
the shapes cannot drift. Until then, hand-written fixtures should follow the field names in this plan.
