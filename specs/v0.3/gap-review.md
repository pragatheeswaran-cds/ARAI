# v0.2 specification gap review

Date: 2026-09-25. Reviewed: `specs/v0.2/*`, `docs/agreed-project-scope.md`, `docs/returns-analysis-scope-discussion.md`, `docs/ml-development-workflow.md`, `specs/00-governance/{open-questions,gap-analysis,v02-resolution-map}.md`, `specs/02-data/{schema.yaml,retail-simulation-policy.yaml,customer-and-inspection-demo-data.md}`, `specs/04-model/model-comparison-plan.md`, `specs/06-api/openapi.yaml`, `specs/07-ui/ui-requirements.md`, team `code/synthetic-data/customer-master/config/*.yaml`, `customer_master.csv` and `sku_master.csv`.

Severity: **BLOCKING** means the dependent slice cannot be implemented without a decision. **IMPORTANT** means it must be settled before that slice is accepted. **MINOR** covers editorial issues and engineering defaults the implementer can propose. Each gap links to a decision-log item (D-xxx = decided, Q-xxx = open). A gap marked "decided" is closed on paper only; it is not verified until the check in the decision log passes.

## Summary

| ID | Severity | Slice | Gap | Decision item | State |
|---|---|---|---|---|---|
| G-01 | BLOCKING | all | v0.2 engineering defaults are assistant-authored and have no approval or freeze record | D-006, V02-DEF-* | decided (process); sign-off pending |
| G-02 | BLOCKING | 1, 2 | Non-receipt action contradicts the delivery contract | D-005 | decided |
| G-03 | BLOCKING | 1, 2 | Reason-code membership of features and SKU signals is undefined | D-018 to D-021, D-041 | decided |
| G-04 | BLOCKING | 1 | Coordinated-abuse and household generation is unspecified | D-013 to D-017, D-033 | decided |
| G-05 | BLOCKING | 1 | Profile source and persona-to-overlay mapping | D-003, D-009 to D-012, D-032 | decided |
| G-06 | BLOCKING | 3 | Legitimate-segment membership used by the gate is undefined | D-022 to D-025 | decided |
| G-07 | BLOCKING | 5, 6 | No demo behaviour when no model is selected or the final test fails | D-001 | decided |
| G-08 | BLOCKING | all | No MVP cut line against a 5-6 week window | D-002 | decided (all must-have); risk remains |
| G-09 | BLOCKING | 1, 5 | Stale v0.1 machine contracts conflict with v0.2 prose | D-008 | decided; schema drafted, API pending wireframes |
| G-10 | BLOCKING | 5 | UI technology unspecified in v0.2 | D-004 | decided |
| G-11 | IMPORTANT | 1, 2 | Date vs timestamp granularity and timezone of derived day counts | D-026 | decided |
| G-12 | IMPORTANT | 1, 2 | Out-of-window return requests are not specified | D-029 | decided |
| G-13 | IMPORTANT | 1, 3 | Label scope "included transaction" is undefined | D-027 | decided |
| G-14 | IMPORTANT | 1, 2 | Return status exists only at header level; no withdrawn/cancelled request state | D-028 | decided |
| G-15 | IMPORTANT | 3, 4 | Risk-percentile reference built from in-sample supervised scores | D-034 | decided |
| G-16 | IMPORTANT | 1, 2 | Defects are assigned per style but SKU expectations and the queue are per SKU | D-030 | decided |
| G-17 | IMPORTANT | 1, 3 | SKU queue and wardrobing indicator have no evaluation criteria; SKU targeting generation is undefined | D-015, D-031 | decided |
| G-18 | IMPORTANT | 1, 3 | Seeds for fixtures and stress worlds are unallocated; demo "curation" method is undefined | D-035 | decided |
| G-19 | IMPORTANT | 3 | Eligibility threshold may exclude about half the population | D-036 | decided (check on fixture) |
| G-20 | IMPORTANT | 5 | Review-note lifecycle and reviewer identity | D-037 | decided |
| G-21 | IMPORTANT | 5 | Dataset manifest schema for `POST /datasets` is undefined | D-008 (schema.yaml `manifest`) | drafted |
| G-22 | IMPORTANT | 3 | Gate feasibility risk in the household segment | R-01 | risk only |
| G-23 | MINOR | 5 | Identifier hashing/privacy at ingestion dropped silently from v0.1 | D-038 | decided |
| G-24 | MINOR | 5 | Optional LLM narrative scope for November | D-039 | decided |
| G-25 | MINOR | 1 | Generator parameters missing (delivery lead time, basket size, discounts, shipping) | D-042 | decided |
| G-26 | MINOR | 2 | Wardrobing latency-z aggregation is ambiguous | D-040 | decided |
| G-27 | MINOR | 3 | Whole-world bootstrap on 5 worlds is coarse | R-02 | risk only |
| G-28 | MINOR | docs | Text corruption in v0.2 and specs README | R-03 | editorial |

## Details

### G-01 No approval record for v0.2 defaults (BLOCKING)
`v0.2/README.md` and `00-governance/v02-resolution-map.md` state that engineering choices are "assistant-authored specifications ... not additional user approvals". Business scope was confirmed ("we have same understanding now"), but no one approved the concrete numbers: dates, eligibility, k=20 shrinkage, SKU and wardrobing thresholds, candidates, seeds and API limits. Implementing unapproved numbers risks rework, and the specs themselves prohibit treating unapproved proposals as behaviour. **Decision D-006:** the user signs the v0.3 decision log. Each default is listed as V02-DEF-nn.

### G-02 Non-receipt vs delivery contract (BLOCKING)
- `v0.2/data.md`: `deceptive_nonreceipt_claim` requires the customer "actually receiving the item" and says "observed delivery records can be incomplete".
- `02-data/schema.yaml`: `delivered_date` is nullable only for cancelled orders; `order_status` is only `delivered|cancelled`.
- `v0.2/features.md`: maturity, exposure and latency all need `delivery_date`.

If delivery can be missing on received lines, nonreceipt claims (one of three action types) drop out of exposure and latency. No state exists for lines that are in transit at the cutoff or lost by the carrier. **Decision D-005:** every delivered line carries a carrier-scan `delivered_date`, including lines later claimed not received. Genuine carrier loss becomes `lost_in_transit` (no delivery, no exposure). Lines in transit at the cutoff become `shipped`. Applied in [schema.yaml](schema.yaml).

### G-03 Reason-code membership undefined (BLOCKING)
`v0.2/features.md` uses "transaction-claim", "damage/defect-reason", "discretionary-reason" and "occasion-wear" groups without listing codes. The v0.1 codebook makes this ambiguous:
- `late_delivery` has `claim_class=transaction_claim` and `intent_class=discretionary`, so it counts in both `claim_share` and `discretionary_share`. It is not a deceptive-claim reason.
- "Damage/defect" could mean `damaged` (carrier fault), `defective`, `poor_quality` and/or `not_as_described`. `damage_share` drives the SKU `quality_signal` predicate, so this choice changes SKU verdicts.
- The generator has no rule for which codes temporary-use returns, genuine fulfilment failures and deceptive contents claims use.

**Q-301:** an explicit mapping is proposed in [reason-code-mapping.yaml](reason-code-mapping.yaml).

### G-04 Coordination and household generation (BLOCKING)
`v0.2/data.md` says "within those accounts randomly form coordinated groups of 3-6" and "5% household members", but leaves these unspecified:
- the fraction of abusive accounts that are coordinated
- household size distribution
- which identifier types each group shares. The graph needs at least 2 shared types for an edge, so this decides detectability.
- what a coordinated abusive action looks like.

`coordinated_claim_share` looks for the same SKU within ±7 days. If the generator plants exactly that pattern, the detector's own rule defines truth, which `customer-and-inspection-demo-data.md` prohibits. **Q-302**, decided 2026-09-25 as D-013 to D-017: 40% of abusers are in groups of 3–6; households and groups have overlapping identifier sharing; coordination means shared target styles plus loose campaign timing, not the ±7-day rule; only claims can be coordinated; large shared addresses are added. Per-order usage rate is still open (Q-320).

### G-05 Profile source and persona mapping (BLOCKING)
v0.2 requires "10,000 independently generated customer profiles per world" (21 worlds). The team has one 10k profile file (seed 42, `cluster_rules.yaml`) and no generator source. Issues found in that file:

| Issue | Evidence |
|---|---|
| One seed, so it cannot supply 21 independent worlds | `cluster_rules.yaml` `seed: 42`; single `customer_master.csv` |
| Scalar `shared_device_count` with no real identity relationships | CSV header; REUSE-004 |
| Persona-conditioned `account_status`, including `FLAGGED` (308 rows), not in schema enum | CSV value counts; TEAM-D02 |
| `Fraud_Proxy` (2.1%) defined by high return rate and shared devices, which is a volume-defined label | `cluster_rules.yaml` subtypes |
| 5,810 rows with infeasible festive targets | `v0.2/data.md` |
| `avg_days_between_orders` is tenure/orders, not an observed gap | REUSE-006 |

**Decision D-003:** reconstruct the profile generator under v0.3 and reuse `cluster_rules.yaml` ranges as input configuration. **Still open (Q-303):** how personas relate to the abuse and benign overlays (4% claim abuse, 3% temporary use, 8% heavy shoppers, 5% households). The user first deferred this, then decided it later in the same session (2026-09-25) as D-009 to D-012: overlays are independent of persona with multipliers of at most 2×, Fraud_Proxy becomes the label-neutral `High_Intensity` persona with its subtypes kept as action templates, benign rates come from the team config (6% heavy returners, 12% households), and the persona return rate is an honest baseline that abuse adds to. Multiplier values remain open (Q-319).

### G-06 Legitimate-segment membership (BLOCKING)
The approved gate compares FPR in three benign segments, but v0.2 defines them only as `y_abuse=0 AND heavy_return_profile | defective_product_exposure | shared_household`. Undefined:
- whether `heavy_return_profile` is the 8% heavy-shopper overlay, the team's `high_return_legit_prob` accounts, or an observed-volume rule
- whether `defective_product_exposure` means buying from a defect-prone style or receiving a latent-defective unit
- whether membership requires eligibility (at least 3 mature lines)
- whether a household-overlay member with no shared identifiers counts

Each choice changes gate denominators and therefore the selected model. **Q-304.**

### G-07 No demo behaviour for no winner (BLOCKING)
`v0.2/modeling.md` allows `no_selected_model` and blocks promotion after a final-test failure. `serving.md` returns 409 when there is no promoted model, so the demo could have no customer queue. **Decision D-001:** the raw-return-rate baseline serves as a clearly labelled fallback ranker, and the evaluation page shows the failed gate.

### G-08 Timeline vs scope (BLOCKING)
Target is 1-14 Nov 2026, about 5-6 weeks from 2026-09-25. Person-hours are unknown and there is no MVP cut. **Decision D-002:** all of these are must-have: SKU queue, wardrobing indicator, graph/coordination evidence and the full 21-world protocol. **Risk R-04:** the plan has no stretch buffer. v0.2's "small world first, thin end-to-end slice" sequencing becomes mandatory, not advisory.

### G-09 Stale machine contracts (BLOCKING for AI-assisted implementation)
The v0.1 files `06-api/openapi.yaml` (`/jobs`, `/flagged`, `/case/{id}/approve`) and `02-data/schema.yaml` conflict with the v0.2 prose. In the v0.1 schema, `account_status`, `disposition`, `reason_text`, `days_to_return` and `within_window_flag` are required, and `requested_at`, `available_at` and the sale-captured window are absent. The v0.2 README says only that "contradictory fields" are superseded; it gives no per-file list. Astra-assisted implementation will pick up whichever file it finds. **Decision D-008:** a consolidated [schema.yaml](schema.yaml) now; a v0.3 OpenAPI after the wireframes.

### G-10 UI technology (BLOCKING)
v0.2 is silent. v0.1 (`07-ui/ui-requirements.md`, `01-product/scope.md`) says Streamlit. **Decision D-004:** React/Vite SPA over FastAPI. The user will share wireframes; the frontend spec and API contract follow from them.

### G-11 Time granularity (IMPORTANT)
`order_date` and `delivered_date` are dates, while `requested_at` is a timestamp. "Calendar days" does not name a timezone. `mean_inter_order_gap_days` is defined "from consecutive actual order timestamps", but orders carry only dates. Sales rows have no `available_at`. **Q-305.** Proposed: all day arithmetic uses Asia/Kolkata local dates, the order gap uses `order_date`, and sale availability equals `order_date`.

### G-12 Out-of-window requests (IMPORTANT)
It is unspecified whether requests after the return window are generated, accepted or rejected, and whether `median_window_ratio` and `late_window_share` may exceed 1. **Q-306.**

### G-13 Label scope (IMPORTANT)
The rule `y_abuse=1 iff completed abusive action ... on an included transaction` never defines "included". Open cases: actions on unmatured lines (the request is visible but excluded from rate denominators), actions on lines later cancelled, and actions by ineligible customers. **Q-307.**

### G-14 Line-level return state (IMPORTANT)
`return_status` exists only on the header, but v0.2 counts rejected and pending requests separately and says "after removing cancelled requests". No cancelled or withdrawn request state exists. **Q-308.** Proposed in schema: `return_order_line.line_status`.

### G-15 Risk-percentile reference (IMPORTANT)
The display risk is the empirical CDF of training scores. Supervised candidates (HGB in particular) score their own training rows optimistically, so new-data percentiles will sit systematically lower. It is also unstated whether the reference covers pooled eligible rows from all ten training worlds. **Q-309.** Proposed: pooled eligible training rows using out-of-fold scores (5-fold, grouped by world) for supervised candidates, and in-sample scores for Isolation Forest. Ranking is unaffected.

### G-16 Style vs SKU grain (IMPORTANT)
Defects are drawn "for 8% of styles", but `p_cs` and the SKU queue work per SKU, and each style has 6-10 SKUs (mean 8.1). Per-SKU peer support is diluted, and a style-level defect appears as several weak SKU signals. **Q-310.**

### G-17 SKU and wardrobing evaluation (IMPORTANT)
`customer-and-inspection-demo-data.md` proposes evaluating SKU verdicts and the wardrobing indicator against private truth, but `v0.2/modeling.md` defines metrics only for customer ranking. How abusers choose targeted SKUs (the "suspected abuse targeting" truth) is not specified. Both features are now must-have (D-002), so they need at least reported metrics. **Q-311.**

### G-18 Seeds and demo curation (IMPORTANT)
`experiment.yaml` allocates train, validation, test and demo seeds, but none for the "small deterministic world" or the development stress worlds. The demo world "may be curated" without saying whether that means post-hoc case selection or injected scenarios. **Q-312.**

### G-19 Eligibility coverage (IMPORTANT)
In the team profiles, 42.3% of customers have fewer than 3 target orders and 15.8% have none. With a maturity requirement, roughly half of customers may be `insufficient_history`. That shrinks N, and therefore k, and hides abuse by low-volume accounts. v0.2 explicitly wants low-volume abusers. **Q-313:** confirm after the first small world is measured. Do not change the threshold before that.

### G-20 Review notes (IMPORTANT)
Notes are attached per `run_id`. Unspecified: whether they carry across runs for the same customer, whether `reviewer_name` is free text with no authentication, and whether notes can be edited or deleted. **Q-314.**

### G-21 Dataset manifest (IMPORTANT)
`POST /datasets` takes a "JSON manifest" with no field list, and `world_id` and the cutoff must come from it. Drafted as `manifest` in [schema.yaml](schema.yaml).

### G-22 Household gate risk (risk R-01)
The raw-return-rate baseline ignores identity links, so its household-segment FPR can be low. A candidate using graph features that is at all sensitive to benign sharing can fail the strict "no higher" household condition. The gate is user-approved and is not reopened here. Mitigation: measure baseline segment FPRs on the first development worlds and report early. Do not tune the gate.

### G-23 Identifier privacy (MINOR)
v0.1 required salted hashing of address, device and payment IDs at ingestion. v0.2 says only "opaque identifiers". **Q-315.** Proposed: synthetic IDs are already opaque, so no hashing in v1; the demo is local only.

### G-24 LLM narrative (MINOR)
v0.2 says "if enabled later". **Q-316.** Proposed: out of scope for November.

### G-25 Generator parameters (MINOR)
Missing: delivery lead-time distribution, basket size and quantity distribution, discounts, shipping fee, refund timing and return channel mix. The implementer proposes values in the generator config and records them in the manifest. **Q-317.**

### G-26 Latency-z aggregation (MINOR)
"Aggregate customer/category latency z by valid return count" can be read as a return-count-weighted mean of per-line z, or as a per-category mean weighted by category count. **Q-318.** Proposed: the mean of per-return-line z, where z = (latency - category training median) / max(1, IQR).

### G-27 Bootstrap resolution (risk R-02)
Resampling 5 worlds with replacement gives only 126 distinct multisets, so intervals will be coarse and step-like. Report as-is with this caveat.

### G-28 Editorial (risk R-03)
The v0.2 files have lost spaces between numbers and words (`upload422`, `cap at25`, `on2026-09-25`), and `specs/README.md` shows `?` in place of dashes. This is readable, but AI-assisted readers may mis-tokenise it. Fix in the next version of those files; they were not edited under this review's constraint.

## What was checked and not checked
- Confirmed: 18 YAML files exist under `specs/` (matches `v0.2/verification.md`). The team SKU catalog has 300 SKUs in 37 styles with 6-10 SKUs per style, launched between 2024-01-20 and 2025-11-23. The team customer file has 10,000 rows with the segment mix and status counts cited above.
- Not checked: runtime behaviour, library compatibility, or any generated data. No code or data was produced.
