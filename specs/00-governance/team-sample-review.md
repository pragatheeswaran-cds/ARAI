# Team customer-master and SKU sample conformance review

Date: 2026-09-25. Status: DRAFT ? NOT APPROVED.

**Verdict: partially reusable; not ready for integration or synthetic-data generation approval.** This review specifies corrections and decisions, not implementation. No generator or notebook cell was executed, no model was fitted, and no application code was changed. The assistant-generated `datasets/wardrobing-reference-20250901` dataset and its ZIP are excluded from evidence. The team's existing committed CSV was inspected only as evidence of its sample contract, not accepted as the future dataset.

## Evidence and reproducibility of this review

Repository: `code/synthetic-data`. Reviewed local `origin/dev`, pinned to commit `e5505d87574ceeca3f94defac375b387f06266de`. The working branch `main` contains only `.gitignore`; files were read using Git object access without checking out a branch or fetching. Notebook cell numbers below are one-based positions including Markdown cells. Paths below are Git paths at that commit, not files presumed present in the working tree.

Reviewed artifacts:

- `customer-master/config/cluster_rules.yaml` and `festive_windows.yaml`.
- `customer-master/notebooks/customer_master_eda.ipynb`, `dbscan_clustering.ipynb`, and `kmeans_clustering.ipynb`.
- `sku-master/sku_master_synthetic_generation_spec_v2.md`, `sku_master_generation.ipynb`, and `sku_master_eda.ipynb`.
- Existing customer CSV variants and text outputs. Parquet is present but was not independently decoded; binary/CSV equivalence is unverified.

Design comparison uses the Architecture & Execution Plan, HLD, LLD ?3.1/data and module definitions, and their draft contracts: [schema](../02-data/schema.yaml), [synthetic-data specification](../02-data/synthetic-data-spec.md), [features](../03-features/feature-spec.yaml), [leakage prevention](../03-features/leakage-prevention.md), [training](../04-model/training-spec.yaml), and [split policy](../02-data/data-split-spec.yaml). Existing specifications remain unapproved. Team sample choices do not override those sources automatically.

## What fits and can be reused

| Area | Assessment |
|---|---|
| SKU style-first construction | Fits the need for linked size/colour variants and bracketing evidence. Configured variant capacity is sufficient for every style. |
| SKU scale | 300 SKUs is within the architecture's 200?400 range. Five brands is compatible. The team's 37-style layout still needs review against the reference layout and coverage needs. |
| Explicit SKU rules | Unique variants, style-level invariants, explicit prices and reported soft-target misses are useful specification patterns. Runtime enforcement cannot be confirmed without helper modules. |
| Customer overlap | Legitimate high-return behaviour, household sharing and persona overlap are useful realism intentions. Their actual transaction-level effects remain unverified. |
| Signup/tenure checks | Existing 10,000-row output has unique customer IDs and tenure matching the team's 2026-09-09 as-of date. |
| Exploratory clustering | Useful development diagnostics when labelled as exploratory. It does not replace the architecture's Isolation Forest, rules, or identity graph. |

## Findings

### TEAM-001 ? BLOCKING: generator sources and reproducibility package are missing

`sku_master_generation.ipynb` cell 2 imports `sku_config_v2` and `sku_generator_v2`; neither module is in the reviewed Git tree. `customer_master_eda.ipynb` cell 35 refers to `src/generate_customer_master.py`, also absent. SKU output CSV, dependency lock/requirements, and executable test suite are absent. Notebook output is not proof that this checkout reproduces it.

Required evidence before implementation approval: versioned generator/helper sources, dependency versions, entry point, config reference and output manifest. No source retrieval or generation is requested by this review. Supplying missing source permits static review first; a reproducibility run belongs after spec approval.

### TEAM-002 ? BLOCKING: customer master is a different contract

The team's ten columns omit required `loyalty_tier` and `marketing_channel`. Statuses are `ACTIVE`, `FLAGGED`, `SUSPENDED`, `CLOSED`; the draft source-derived enum is `active`, `suspended`, `closed`. Case normalization alone cannot resolve `FLAGGED`.

`customer_segment` is a planted persona label embedded alongside behavioural columns. The current notebooks exclude it from feature inputs, which is good, but the production ingestion boundary must prevent it entering detector features or explanations as observed fact. `actual_orders`, `return_rate`, festive ratio and device counts describe simulated behaviour, not the architecture's five-column account reference.

Proposed disposition: preserve a canonical customer master, keep latent persona/subtype truth in an evaluation-only companion, and derive observed behaviour from transactions. Any alternative schema or status semantics require an explicit contract decision. Do not fabricate loyalty/channel values or map FLAGGED to a status without approval. Relates to Q-001/Q-002/Q-021.

### TEAM-003 ? BLOCKING: SKU schema, taxonomy and commercial rules diverge

| Contract | Existing design/draft | Team SKU v2 |
|---|---|---|
| Identifier and colour | `sku`, `colour` | `sku_id`, `color`, extra `color_id` |
| Category domain | dresses_occasion, footwear, jeans_trousers, tops_knitwear, outerwear, accessories | T-shirt, Shirt, Jeans, Jacket, Dress |
| Price bands | value, mid, premium | Budget, Mid, Premium, Luxury |
| Currency context | GBP transaction reference | Explicit INR prices |
| Return windows | Style-level assignment, variation within category | Fixed by category: 30/45/60 days |

Renaming two fields is insufficient. Footwear and accessories have no coverage; the existing category-coverage gate would fail. Currency changes must propagate to order amounts, refunds, thresholds and examples; relabelling INR amounts as GBP is invalid. Fixed category windows change the variation used to evaluate near-window returns. Mapping categories/bands, keeping six categories, or adopting a new taxonomy requires review of baselines and tests. No change is approved here.

### TEAM-004 ? BLOCKING: wardrober persona does not specify wardrobing events

`cluster_rules.yaml` assigns Fraud_Proxy probability 0.02 and wardrober subtype probability 0.27 within that group. That implies an expected 54 wardrober assignments per 10,000 customers, not an observed count or acceptance target. The exported customer CSV does not retain the subtype, so wardrober-specific evaluation cannot be recovered from that file alone.

The subtype config specifies tenure, order counts, festive ratio, return rate and device count. It does not specify the five design signals together: category-normalised latency, near-window returns against historical return windows, occasion-wear purchases, discretionary reasons, and absence of bracketing. SKU occasion flags alone cannot create those observations.

Before generation approval, define transaction-level conditional behaviour, valid order/return timing, reasons, quantities, historical windows and retained evaluation-only subtype truth. Include benign late returns, legitimate occasion purchases and bracketing counterexamples; do not make the label a deterministic copy of the detector threshold. Preserve the separate wardrobe indicator and existing unresolved multi-return aggregation question (Q-004). Do not blend it into the general abuse score.

### TEAM-005 ? BLOCKING for end-to-end fit: counts cannot establish graph or transactional evidence

`shared_device_count` cannot identify which customers actually share a device, address or payment instrument. It does not establish collusion rings, multi-identity edge corroboration, degree caps or benign household topology. Similarly, standalone customer totals cannot establish SKU defect clusters, order/return joins, refund amounts or late-return timelines.

This is a boundary limitation of the sample, not a requirement for a standalone master generator to implement the whole application. The later transactional specification must connect these modules to all seven operational tables and separate customer/SKU truth. Customer personas in this sample also differ from the design's eight abuse/benign populations. Define an explicit mapping or approve a revised population design; do not interpret all Fraud Proxy rows as equivalent to all four abuse types. Relates to Q-005/Q-021.

### TEAM-006 ? IMPORTANT: sampled ratios and frequency have ambiguous meanings

`customer_master_eda.ipynb` cell 11 defines `avg_days_between_orders = tenure_days / actual_orders`. This is account-age-per-order, not the mean interval between consecutive order timestamps. In particular, one order has no inter-order interval. Rename the propensity/proxy if retained, or define a future timestamp-derived feature with explicit behaviour for fewer than two orders.

In the existing team CSV, 8,244 positive-order rows have a non-integer product `festive_order_ratio * actual_orders`; all 1,413 one-order rows have a festive ratio strictly between zero and one. Those values cannot be exact realised fractions of festive orders. They could be valid latent generation propensities, but that interpretation must be declared and distinguished from observed features. For rounded observed ratios, define precision/tolerance and derive them from counts. Return-rate denominators (orders, lines or units) require their own decision; this review does not assume they are identical. Relates to Q-002/Q-004.

### TEAM-007 ? IMPORTANT: labels guide DBSCAN selection despite held-out wording

`dbscan_clustering.ipynb` cell 8 selects eligible runs by descending `ARI_segment`, then silhouette. `customer_master_eda.ipynb` cell 30 repeats this approach. The same population's persona labels therefore influence epsilon selection; they are not untouched evaluation evidence. Excluding label columns from X does not remove this selection leakage.

Treat these results as development diagnostics and make that status explicit. Follow the draft independent-seed/freeze protocol before any final performance claim. K-means silhouette exploration is also not sealed evaluation. The architecture retains Isolation Forest's eight specified features; the six customer EDA inputs, including raw return rate, are not an approved replacement feature set. Relates to Q-009/Q-010.

### TEAM-008 ? IMPORTANT: enrichment diagnostic computes recall

`dbscan_clustering.ipynb` cell 14 prints that Fraud Proxy is enriched when `fraud_noise / fraud_n >= 0.2`. This ratio is capture/recall. Enrichment instead compares `fraud_noise / n_noise` with `fraud_n / N`, with explicit zero-denominator handling; lift is their ratio when defined.

Counterexample: N=10,000, fraud=200, noise=3,000, fraud-in-noise=60 passes the notebook's 30% recall condition, but noise fraud prevalence is 2%, exactly the population prevalence (lift 1). This is an algebraic counterexample, not generated project data. Any acceptance threshold for lift or recall remains TBD; the diagnostic does not prove synthetic realism.

### TEAM-009 ? IMPORTANT: diagnostic validation does not gate invalid data

Customer EDA cells 5, 8 and 11 print validation results instead of raising on failed checks. SKU EDA cell 24 catches assertion failures and prints them; the actual validation helpers are missing. Hardcoded fallback paths to a developer's machine further limit portability. Stored notebook results can continue to look complete after a failed diagnostic.

Specify a future validation gate that exits unsuccessfully on hard-contract violations and prevents export/acceptance, with separate advisory realism diagnostics. Require a run manifest binding generator commit, dependencies, config, seed, as-of date and hashes. The team's seed 42/as-of 2026-09-09/calendar differs from the existing reference; this is a proposal needing coordinated approval, not intrinsically an error. Specify deterministic allocation tie-breaking and resolve SKU spec sections 4/15 wording about what the seed may change. Relates to Q-010/Q-021.

## Checks actually performed

- Parsed all five notebooks as JSON and syntax-parsed all 57 Python code cells: no syntax errors. Imports, runtime behaviour and model results were not validated.
- Independently summed SKU v2's 37 style rows: 300 SKUs; Budget/Mid/Premium/Luxury counts 24/155/90/31; no style requests more variants than its colour-by-size Cartesian capacity. These are specification arithmetic checks, not output verification or proof that allocation meets every soft target.
- Inspected the team's committed 10,000-row customer CSV: zero duplicate IDs, zero tenure mismatches at its configured date, 1,581 null average-gap values and no nulls in the other nine fields. Status counts: ACTIVE 9,282; FLAGGED 308; SUSPENDED 237; CLOSED 173. These observations do not establish contract compliance.
- Verified missing modules against the complete 15-file Git tree. No dependency installation, model execution, branch change or synthetic generation was performed.

## Decisions to resolve in the spec review

These additional decisions supplement, and do not close, the original [open questions](open-questions.md). Proposed owners are roles, not assigned people. All remain OPEN; no assumption below constitutes approval.

| Decision | Priority | Proposed owner | Required outcome |
|---|---|---|---|
| TEAM-D01 | BLOCKING | Data lead | Complete source inventory for TEAM-001 and confirm which output/config version belongs to it. |
| TEAM-D02 | BLOCKING | Data/product leads | Canonical customer fields; FLAGGED meaning; evaluation-only persona/subtype contract. |
| TEAM-D03 | BLOCKING | Product/data leads | Taxonomy, currency, bands, window variation and occasion semantics; explicit mapping or approved design amendment. |
| TEAM-D04 | BLOCKING | ML/data leads | Wardrobing event-generation rules, benign controls, populations and identity-sharing topology. |
| TEAM-D05 | IMPORTANT | ML lead | Declare ratio/frequency semantics, diagnostic-only clustering, metric correction, held-out seed and freeze policy. |
| TEAM-D06 | IMPORTANT | Engineering/data leads | Validation failure contract, dependencies, deterministic ties, calendar/as-of and provenance manifest. |

User clarification (2026-09-25): the customer behaviour fields and labels are intended to assess synthetic customer clusters, then drive sales and return generation. The notebooks therefore have an exploratory generator-design role; this intent is no longer an assumption. This clarification does not approve their label definitions, change the production model, or resolve label-guided evaluation concerns. See the staged workflow below.

## Verification to specify before later implementation

| Proposed check ID | Findings/contract | Future verification | Current status |
|---|---|---|---|
| TEAM-TEST-001 | TEAM-001/009; reproducibility | All imported project modules supplied; manifest binds code/config/dependencies; same approved seed yields identical normalised output. | Specified only; execution deferred |
| TEAM-TEST-002 | TEAM-002; DATA-001 | Exact approved fields/enums, unique IDs, signup/as-of/order chronology; planted truth excluded from detector input. | Blocked on contract decision |
| TEAM-TEST-003 | TEAM-003; DATA-001 | SKU/transaction FK compatibility, category coverage, currency consistency, variants, prices and historical window rules. | Blocked on contract decision |
| TEAM-TEST-004 | TEAM-004/005; feature/leakage specs | Wardrobing signals derive from joined events; benign counterexamples; subtype truth isolated; graph uses actual identity links. | Blocked on event specification |
| TEAM-TEST-005 | TEAM-006 | Derived rates reconcile with approved denominators/timestamps, rounding and sparse-history rules. | Blocked on semantic decision |
| TEAM-TEST-006 | TEAM-007/008; split/evaluation specs | Sealed labels never select epsilon/config; recall and lift reported separately; zero denominators and the counterexample covered. | Specified only; not implemented |
| TEAM-TEST-007 | TEAM-009; data quality | Deliberately invalid fixture causes validation failure and blocks export; warnings do not count as successful gates. | Specified only; not implemented |

Review order: agree master contracts and scenario semantics, reconcile this report with the existing SDD questions, then freeze the relevant specifications. Only a subsequent explicitly authorised phase should repair generators or produce new datasets.

**SPECIFICATION READINESS: NOT READY FOR IMPLEMENTATION.**


## Clarified customer-profile-first workflow

Source: user clarification on 2026-09-25. Intent confirmed; detailed contracts remain DRAFT and require review before generation.

The extra customer fields are purposeful simulation inputs. Their presence is not itself a defect. TEAM-002 concerns exporting them as the operational customer master; TEAM-005 concerns the evidence required at the later transactional boundary, not a demand that this first-stage sample already contain sales and returns. TEAM-006 distinguishes intended propensities from realised measurements. This clarification narrows those findings without approving incompatible schemas.

### Stages and boundaries

1. Define customer simulation profiles: signup date/age, intended order volume, return propensity, festive preference and identity-sharing behaviour. Specify each field's meaning, units, reference date and whether it is an exact constraint or a stochastic target.
2. Define simulated labels and their provenance. If labels are assigned from profile fields, version the assignment rules; if profiles are sampled conditional on a persona, version those conditional distributions. Do not leave that direction implicit. Exact label rules, boundaries and mixtures remain unresolved.
3. Run development-only clustering diagnostics on approved profile inputs with labels excluded from X. Compare clusters with planted labels to assess structure and overlap. Label-guided tuning is development, not independent validation. Cluster identifiers have no intrinsic fraud meaning.
4. After specification approval, generate linked sales and returns conditional on those profiles, SKU definitions and temporal/business constraints. Profiles supply intended behaviour; events must realise it through actual dates, quantities, reasons, amounts and shared identities. A count of shared devices cannot replace explicit shared identifiers.
5. Derive observed customer features anew from the generated transactions using the canonical feature formulas. Compare achieved behaviour with profile targets using specified tolerances; do not overwrite observations with targets to force agreement. Tolerances remain TBD.
6. Evaluate the existing production detector on those transaction-derived features under the independent-seed/freeze protocol, with planted labels available only to evaluation. This is separate from stage 3's clustering diagnostic.

### Separate meanings of labels

| Concept | Meaning and boundary |
|---|---|
| Account status | Operational lifecycle such as active/suspended/closed. An active account may still have planted fraudulent behaviour. Existing enum remains unchanged pending TEAM-D02. |
| Simulated behaviour truth | Generator-assigned scenario/persona and abuse subtype, retained outside operational detector inputs. This is artificial truth, not proof of real fraud. |
| Suspicion label | Must specify whether it is a generator scenario, an ambiguous simulated case, or a detector/reviewer outcome. Its meaning and relationship to fraud are TBD. |
| Cluster ID | Exploratory grouping from profile features; not automatically an account status or fraud label. |
| Detector output | Risk/ranking and separate wardrobing indicator derived from observable evidence; never copied from planted truth. |

Do not use active, suspicious and fraud as one mutually exclusive enum without resolving these meanings. Generation-time profiles and truth may be used by the generator; they must not leak into production feature inputs or case evidence as if observed.

### Field semantics to approve

- Number of orders: distinguish planned order count from realised count. If exact, later sales must contain that many eligible orders; if a stochastic target, specify its distribution and acceptance tolerance.
- Signup age: derive from signup date and a fixed as-of date. Never sample age and date independently. All order dates must satisfy signup chronology.
- Return/festive ratio: a value such as 0.23 can be a propensity even for a customer with one planned order. The eventual observed ratio must be recomputed from actual eligible events and its approved denominator. The earlier arithmetic finding applies only if the value is represented as a realised ratio.
- Average order gap: tenure/order count is a profile proxy, not observed mean inter-order spacing. Keep names and sparse-history handling explicit.
- Wardrobing: retain the intended subtype and specify late/near-window returns, occasion wear, reasons and bracketing behaviour, with benign overlap. An elevated return propensity alone does not define wardrobing.

### Diagnostic limits and verification additions

High cluster agreement can show that the generator encoded distinct profiles. When labels were defined from the same profile features, that agreement can also be circular; it cannot establish real-world fraud performance. Low agreement is not automatically failure because benign and abusive behaviour may overlap. Do not tune for perfect separation or use label rules identical to the detector decision threshold as proof of detection quality.

Proposed TEAM-TEST-008: verify profile-target versus realised-event reconciliation, signup chronology, stochastic tolerances and exclusion of profile/truth fields from detector inputs. Status: specified only; tolerances and label contract unresolved; no test implemented.

TEAM-D02 still requires exact status/label contracts. TEAM-D04 still requires profile-to-event and wardrobing rules. TEAM-D05 now has confirmed diagnostic intent, but field semantics, metric correction and evaluation isolation remain open. No new data or implementation is authorised by this clarification.


## Added SKU CSV: follow-up evidence

The user subsequently supplied `code/synthetic-data/sku-master/sku_master.csv`. The [combined assessment in docs](../../docs/team-customer-master-sku-assessment.md) records its SHA-256 and independent checks: 300 rows, 13 columns, zero missing values/duplicate variants, and agreement with all 37 configured style counts, prices, bands and allowed sizes/colours. This resolves the missing-SKU-output limitation in the historical review above. Missing generator modules and remaining contract decisions are not resolved. No generation or model execution was performed.
