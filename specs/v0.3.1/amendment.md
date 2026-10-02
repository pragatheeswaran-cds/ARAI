# Proposed corrections and decisions

Date: 2026-09-25. All A-* and P-* entries below are PROPOSED, not approved.
Sources: [v0.3 decisions](../v0.3/decision-log.md), [v0.2 data](../v0.2/data.md), [features](../v0.2/features.md), [modeling](../v0.2/modeling.md), and [serving](../v0.2/serving.md).

The existing customer top-5% precision/benign-FPR gate, held-out protocol, truth separation, no automatic retailer action, and synthetic-performance limitations remain unchanged.

## A-01: Correct the shortcut probe

Amends D-009/D-032 verification, not the action-defined customer label.

Equal propensity assignment does not imply equal completed-action labels: customers with different numbers of opportunities have different chances of acting. For an enabled customer with independent opportunities at probability 0.2, the chance of at least one action is 1 - 0.8^n. It is 0.2 for one opportunity and about 0.893 for ten, before further eligibility/collision/timing constraints.

For stress world 2507, validate equal allocation probabilities among accounts with positive target order count, with all such persona multipliers set to 1. Zero-target accounts are excluded from allocation. Do not require a persona-only classifier of completed y_abuse to have a 95% interval containing 0.5; even a valid null experiment does not guarantee that outcome.

Report overlay assignment rates by persona with denominators, completed-action prevalence, and persona-only and opportunity-count-only prediction diagnostics. Any predictive probe must use held-out customers/worlds rather than training accuracy. Examine completed-action rates within opportunity-count strata; sparse strata are descriptive only. In normal worlds retain the >0.60 persona-only AUC flag as a diagnostic, not an automatic generation failure or instruction to tune seeds.

Acceptance evidence: exact allocation probabilities agree with A-04; zero-target accounts have no overlay; test fixtures demonstrate that equal propensity can coexist with unequal completed-action rates. No requirement to manufacture AUC near 0.5.

## A-02: Represent orders awaiting dispatch

Amends D-005/D-042 and sales_order_line.

Add awaiting_dispatch. At cutoff:
- awaiting_dispatch: order placed, neither cancelled nor dispatched; shipped_date and delivered_date are null.
- cancelled: cancellation occurred before dispatch and by cutoff; both dates null.
- shipped: dispatch observed by cutoff, neither delivery nor confirmed loss observed; shipped_date present and <= cutoff date, delivered_date null.
- delivered: carrier scan observed by cutoff; both dates present, order_date <= shipped_date <= delivered_date <= cutoff date.
- lost_in_transit: dispatch and carrier loss confirmation observed by cutoff; shipped_date present, delivered_date null.

Only delivered lines contribute delivered exposure; maturity remains delivered_date + sale-captured window <= cutoff date. Future planned dispatch/delivery/loss/cancellation events stay private. A future cancellation must not make the current snapshot cancelled. Do not eliminate cutoff-day orders to work around the missing state.

Acceptance fixtures: cutoff-day order awaiting dispatch; dispatch next day; in-transit line; genuine loss; scanned genuine nonreceipt; scanned deceptive nonreceipt. Pending dispatch contributes no mature or delivered units. Add these states to the D-005 development coverage check.

## A-03: Allocate purchased units before adding abuse

Amends D-012 and clarifies D-027/D-028.

Use private unit keys (order_id, order_line_no, unit_index), unit_index in 1..quantity. They are generator bookkeeping, not additional operational model inputs.

Generation order:
1. Generate profiles, purchased baskets, delivery facts, defects, and honest request events independently of enabling abuse.
2. Reserve every unit referenced by any honest request, including a later-withdrawn request. This conservative simulation rule avoids rewriting honest event history. It is stricter than the operational non-withdrawn quantity cap.
3. Draw abuse opportunities at the existing per-relevant-order probability 0.20. Select only unreserved delivered units with facts compatible with the intended action. Genuine nonreceipt cannot also be deceptive nonreceipt for that same unit. Temporary use requires actual receipt; it may coexist with a defective item.
4. If both enabled action families select the same unit, use a keyed random tie-break independent of persona and detector scores. Reserve the winning unit. Do not force a replacement or resample until success. Mark the other opportunity uncompleted with a private reason.
5. Emit at most one abusive request per unit. Failed or future opportunities never make y_abuse positive. A submitted rejected request still counts; an abusive request is never withdrawn under D-027.

Disabling abuse must preserve all base sales and honest return-line event fields and IDs, including timestamps, reasons, quantities and statuses. Derived aggregates such as header refund totals may change when abusive lines are added. Use separate purpose-labelled random streams keyed by seed, entity key and event purpose; adding one stream must not advance another. Record the RNG algorithm/version and stream-key algorithm in generator metadata.

Do not invent new purchases to make a campaign succeed. For D-015, generate campaign plans in a separate stream, then match only compatible existing delivered purchases in the target styles to campaign request times. Reject impossible matches (before delivery, beyond cutoff, or unavailable quantities); record planned, eligible, submitted and blocked opportunity counts. The configured late-request policy still applies; no repair may move a date solely to improve detection.

Private action truth must link completed actions to the emitted return line and allocated unit keys, with campaign_id and group_id where applicable. This permits an independent reconstruction of y_abuse.

Acceptance fixtures: one unit already honestly returned; quantity three with one honest and one abusive requested unit; competing action types; withdrawn honest request; rejected abuse; unmatched campaign; toggling abuse preserves the canonical base tables and honest events. Every active requested unit is unique.

## A-04: Specify joint propensity allocation

Amends D-009/D-032 and V02-DEF-08 interpretation.

The 4% claim, 3% temporary-use, and 0.5% overlap rates are expected shares of the entire world, not exact quotas and not completed-action prevalence. The shared denominator includes zero-target accounts; those accounts receive zero probability. This denominator is an explicit proposed choice.

For account i, let m_i be its accepted persona multiplier if target_order_count > 0, else 0. Let M be the mean m_i over all accounts, including zeros, and w_i = m_i/M.

Draw exactly one categorical state per account:
- claim_only: 0.035 * w_i
- temporary_use_only: 0.025 * w_i
- both: 0.005 * w_i
- neither: 1 - 0.065 * w_i

This preserves expected full-world marginals 0.04 and 0.03 and overlap 0.005 without independent Bernoulli draws. Existing multipliers remain Occasional/Seasonal/Loyalist 1.0, New_Growth 1.5, High_Intensity 2.0. Stress 2507 sets all actionable multipliers to 1.0.

Fail configuration validation if M=0 or any category probability is outside [0,1]; do not clip or silently change totals. A deliberately all-dormant fixture may disable overlays explicitly and has no prevalence claim. Report expected and realized counts, allocation population, blocked opportunities and completed labels separately. Never regenerate a world to hit exact shares.

Acceptance: probabilities sum to one per account; their population averages yield the three target rates within numeric tolerance; sample variation is not structural failure.

## A-05 / P-02: Evaluate useful style and wardrobing behavior

Amends D-031 reporting/acceptance. Recommended P-02: sealed performance remains report-only; development behavior checks are mandatory.

Keep the accepted style thresholds until development evidence supports a separately recorded change before validation generation. D-030 moves aggregation to style level; it does not establish that the old thresholds work well there. Six connected returners among 36 have component_share=1/6 and cannot meet 0.50.

Add:
- Style state cross-tab including quality, targeting, mixed_or_uncertain, insufficient_support, and no_return_evidence, against defect/targeted/both/neither truth.
- Targeting precision and recall using the targeting predicate, including mixed cases where that predicate fired. Retain predicate booleans independently of the displayed state.
- Defect-detection precision/recall using the quality predicate; disclose that the existing mutually restrictive component predicates can miss mixed cases.
- Style support coverage, unique-returner counts, completed coordinated-claim counts, and number of distinct acting groups per style.
- Report full-population style recall as well as supported-style recall. Undefined metrics are null with counts, never perfect or zero performance by convention.
- Retain both wardrobing bands' precision/recall and false-alert rates for honest late returners and size bracketers. Define late-return controls as y=0 with >=1 non-withdrawn request having window_ratio>=0.75; size-bracketer controls as y=0 with >=1 mature order/style containing >=2 distinct sizes. Report overlap and eligibility coverage.

Development acceptance checks are behavioral, not claims of accuracy: hand-computed positive/negative predicate fixtures; multi-group and diluted targeting cases; no-return and low-support cases; mixed defect/abuse; honest late-return and bracketing examples. Their measured output must match the formula, even when that output is a miss.

A feature owner must review development recall/coverage and record "usable with stated limitations" or "needs revision" before the demo capability is declared ready. A detector with no true positive on any supported development targeting case is not accepted as a demonstrated targeting capability; revise on development data or explicitly renegotiate scope. Do not inject sealed evaluation cases or tune thresholds against sealed results. Injected demo examples are illustrations only.

Alternative P-02: adopt numerical minimum recall/precision thresholds now. No such threshold is proposed without development evidence; do not invent an apparent performance guarantee.

## A-06 / P-03: Separate targeting intent from completed activity

Amends D-015 product truth and D-031 style evaluation.

Recommended P-03:
- planned_targeted_by: groups whose campaign plans include the style.
- completed_targeted_by: groups with >=1 completed coordinated claim on a delivered unit of that style, with request and operational availability <= cutoff.
- targeted: completed_targeted_by is nonempty.

Use targeted for the style evaluation cross-tab. Defect state remains independently generated. Planned-only targets remain private diagnostics and are not detectable-abuse positives. A group member who never acts remains non-positive unless they complete some other abusive action. Retain solo claims separately; this target definition is coordinated targeting, not all possible abuse against a product.

Truth follows the action definition, never the graph threshold, a reason-share threshold, or +/-7-day feature capture. Low-link actions remain genuine positives; report their detectability separately.

Customer y_abuse retains D-027's submitted-by-cutoff meaning. For this generator, each emitted return line has available_at equal to requested_at. A consolidated header uses the latest included line request time for return_created_at and available_at; header time is never substituted for line latency. All included lines and their header must be visible by cutoff, so completed visible action truth and operational visibility agree. Supporting delayed ingestion later requires an explicit label/observability contract.

Alternative P-03: evaluate planned targeting intent. If chosen, label the task as campaign-intent prediction and separately report styles with zero observed completed actions; do not present it as detection of observed abuse.

## A-07: Make baseline fallback independent of model promotion

Completes D-001 and amends the model-required branches of v0.2/serving.md.

Create a content-addressed baseline bundle from training worlds only, before candidate evaluation. It contains schema/feature hashes, training category fallback rates, category latency median/IQR, configuration and source hashes, and a sorted eligible training raw-return-rate reference. It has no estimator, no candidate preprocessing dependency, and no private truth files.

Runtime contract:
- No active promoted model plus a valid baseline bundle: run with model_kind=baseline_fallback.
- Bind model_id to the baseline bundle hash at submission; expose the kind so it cannot be mistaken for a promoted classifier.
- raw_score is mature raw_return_rate; risk_score is its frozen training-reference ECDF percentile with the existing midrank tie rule. Display "Return-rate reference percentile", not abuse probability.
- Rank and select using the existing eligibility, top-5% budget and common hash tie-break.
- Compute graph/style/wardrobing evidence with the same deterministic feature code and baseline training statistics.
- Retain the failed selection/final-test result and an explicit fallback banner. Fallback never counts as passing the candidate gate.
- Missing/invalid baseline dependencies still return a readiness failure/409; never fit during inference or silently invent zero statistics.
- An explicitly requested rejected/unregistered model remains a 409, not silent fallback.
- Automatic fallback must not mask a corrupt active model; fail readiness and require an explicit activation change.
- Health reports scoring_ready, promoted_model_ready, and model_kind separately. Exact endpoint schemas await D-007.

If no promotion has been attempted, show "baseline only - selection not completed", not a fabricated gate FAIL. If an earlier valid model exists, continue its bound version unless explicitly switched; do not silently replace it following another experiment's failure.

Acceptance: no model promoted, valid baseline -> complete run and evidence; no model and no baseline -> 409; failed candidate never deserialized; stable hash across restart; no fit calls; insufficient-history fields remain null.

## A-08: Correct stochastic relationship checks

Amends D-014/D-033 verification, keeping the selected sharing probabilities.

Validate sampled member probability p against its configured interval. A one-order member legitimately realizes 0% or 100%; do not require realized per-member usage to lie in the interval.

For each member/type, report n eligible orders, k shared-value uses, and p; n=0 yields a null realized proportion. Across independent draws report expected usage sum(p_j), observed sum(x_j), and variance sum(p_j*(1-p_j)). Diagnostic deviations trigger investigation, not seed resampling. If draws are coupled across types or members, declare that dependence and do not apply the independent-draw variance across those draws.

D-014's approximately 79%/71% figures concern assignment of at least two shared types assuming independent group-level type draws. They are not promises of observed graph connectivity. Report assigned type patterns, observed sharing, and surviving graph edges separately, including fan-out exclusions.

Fixture invariants cover edge rules, shared identifier equality, no private role prefixes, and high-fan-out suppression. Coverage requirements for deterministic development fixtures are satisfied by explicit fixtures, not by rejecting sealed random worlds.

## A-09 / P-01: Delivery scope and first implementation slice

Recommended P-01: preserve customer investigation, style investigation, wardrobing and graph evidence, and the full 10/5/5/1 world protocol. Treat presentation depth as the adjustable scope.

Minimum demo: one dataset/run flow, customer queue/case, compact style table with SKU drill-down, graph evidence table, wardrobing explanation, evaluation report/page, and an honest baseline fallback. Interactive graph visualization, advanced filtering, extensive styling and cloud deployment are stretch work. PostgreSQL remains the local metadata store. No inspection-routing expansion or LLM narrative.

By 2026-10-09 review data-slice acceptance and an initial runtime estimate. If data is not accepted, or the full evaluation/rehearsal does not fit the remaining schedule, ask for an explicit dated replan. Simplify presentation first; never silently reduce held-out worlds, remove benign controls, or claim a trained-model success from fallback. Freeze evaluation and reserve the final week before the actual demo date for integration/rehearsal.

Alternative P-01: keep D-002 unchanged with no scope flexibility; record actual owner availability and a credible schedule before committing to the full presentation.

After package acceptance:
1. Use fixture seeds 2001-2003, 1,000 customers each, plus hand-authored boundary cases in a separately marked test fixture. Keep random-world coverage reports distinct from injected boundary fixtures.
2. Implement schema validation, deterministic generator, private truth joins and diagnostics first. No full train/validation/test generation yet.
3. Verify A-01 through A-04/A-06/A-08 data invariants; report eligibility, action/overlay counts, style support, benign-segment sizes and blocked campaigns.
4. Exercise features and the baseline path with hand-computed examples, including A-05/A-07.
5. Fix generator defects only on development fixtures/stress worlds. Record config changes before generating validation worlds. Preserve sealed-test rules.
6. Accept this slice only with actual outputs, hashes and test results. Then proceed to full training worlds and a thin end-to-end run before UI expansion.

The reference to all scenarios in D-035 excludes the superseded pending-item inspection scenario, consistent with the latest steering in customer-and-inspection-demo-data.md.
