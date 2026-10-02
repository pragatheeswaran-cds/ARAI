# Existing generator and master-data reuse assessment

Review date: 2026-09-25. Scope: existing team SKU/customer-master artifacts against the user-confirmed v0.2 ML pipeline. This is a source/data review, not execution of the full generators or model training.

## Decision

**Retain the SKU catalog. Adapt the customer profile design. Recover the missing generator sources before judging their implementation; rebuild only the missing generation layer if recovery is not possible.** The evidence does not justify discarding all existing work or calling unavailable code unfixable.

| Artifact | Decision | Reason |
|---|---|---|
| Current 300-row SKU CSV and 37-style specification | Retain as the approved catalog baseline | Checked structural, commercial, category-window and lifecycle invariants pass. |
| SKU generation notebook | Retain as orchestration/reference; not currently a self-contained generator | It imports two local modules absent from the supplied repository and searched archives. |
| Customer profile configuration and 10,000-row CSV | Adapt; retain as development profile/reference material | Useful variation and legitimate overlap, but planned ratios, persona labels and scalar device counts are not observed transactions or action-based truth. |
| Customer generator implementation | Recover, or reconstruct the missing layer | No generation source/entry point was found; only configuration, output and analysis notebooks. Its code quality cannot be assessed from outputs alone. |
| EDA/K-means/DBSCAN notebooks | Retain for exploratory profile analysis; repair diagnostic/validation integration | Persona exploration is valid, but the saved results are not independent fraud-detection evaluation. |
| Existing CSV/Parquet outputs as final ML dataset | Do not promote as-is | Transactions, event-derived features, action truth, independent worlds and required subgroup evidence must be generated/validated first. This is a scope/readiness limitation, not a claim that every row is corrupt. |

The implementation obligations and conditional replacement rule are in [generator disposition specification](../specs/v0.2/existing-generator-disposition.md).

## Evidence and limits

- Team repository HEAD: `e5505d87574ceeca3f94defac375b387f06266de`; current SKU CSV is untracked. No tracked working-tree edits were reported by the read-only status check.
- Reviewed current working files, not just old assessment summaries. Enumerated the local repository and checked root ZIP inventories for missing helper names. No source was fetched from a remote repository.
- SKU CSV SHA-256: `0a558c72b1c4e108d4d114ec72f3480bc72597d05282979ded4087cbcdb53a3e`.
- Customer CSV SHA-256: `86890ee1dee1c8e536ec98991a26c2bd8447554d598190dc89ee01c10da8b8ff`.
- Parsed 57 code cells across five notebooks. All parsed as Python; no saved error output was found. This is not a successful notebook run.
- Independently executed a CSV audit and two small notebook-code reproductions on in-memory fixtures. Original notebooks, CSVs and generators were not changed.
- Did not execute complete notebooks, generate new data, train models or confirm same-seed generation. The current review Python environment lacks scikit-learn/Faker/pyarrow; this is an environment limitation, not evidence those libraries were absent from the author's environment. Parquet parity is unverified.
- Reproducible support: [audit script](reviews/generator-review/audit_data.py), [data evidence](reviews/generator-review/data-audit.json), [notebook inventory](reviews/generator-review/source-inventory.json). Notebook cell references below are zero-based JSON cell indexes.

## What is already good

SKU checks: 300 unique SKU IDs; 37 styles; no duplicate style/colour/size variants; no missing cells; configured style counts, allowed variants, prices and bands match the supplied specification. Style-level price, band, occasion, launch and activity invariants pass. Brand/category price ladders, colour-ID mapping and category return windows pass. There are45 occasion-wear SKUs.

The41 inactive SKUs are not a defect: the specification retires whole styles in oldest-first order nearest to45. Prefix totals41 and49 are equally close, and the output uses the valid41-SKU prefix. Do not force45 by splitting a style.

Customer checks:10,000 unique IDs; valid signup/tenure agreement; no negative order counts or out-of-range return/festive ratios. All1,581 zero-order rows consistently have zero ratios and null average gaps. Overlap is already present:36 Fraud Proxy profiles have one device,644 other profiles have at least three,424 non-Fraud-Proxy profiles have return rates>=0.32, and57 Fraud Proxy profiles have rates<=0.32. These are useful overlap diagnostics, not proof of business realism or detection accuracy.

## Findings and reasons

### GEN-001 - Missing generator sources prevent reproducibility acceptance

**Evidence:** [SKU generation notebook](../code/synthetic-data/sku-master/sku_master_generation.ipynb), cells1/7/9, imports `sku_config_v2` and `sku_generator_v2` and calls their generation/validation functions. Neither module exists in the workspace search, local repository tree, `final_1.zip` or `return-abuse-synthetic-data.zip`. The customer folder has no generation entry point; its EDA reads pre-existing CSV output.

**Impact:** The existing output cannot establish generator correctness, deterministic reproduction or compatibility with revised world/snapshot contracts.

**Disposition:** Recover the original modules and customer entry point, then test. If unavailable, implement the missing layer against retained specifications and catalog fixtures, version it as a reconstruction and do not claim byte-for-byte reproduction of an unknown original algorithm. There is no evidence that the missing original code is inherently unfixable.

### GEN-002 - Customer profiles are not action truth or operational feature data

**Evidence:** [cluster_rules.yaml](../code/synthetic-data/customer-master/config/cluster_rules.yaml) assigns six profile segments and four Fraud Proxy subtypes. The current CSV has207 Fraud Proxy rows but stores no subtype/action events, actual orders/returns or identity-link records. The table contains target-like rates/counts. Account-status weights are persona-conditioned:64.73% of Fraud Proxy rows are FLAGGED/SUSPENDED versus4.20% of other profiles.

**Impact:** Treating `customer_segment == Fraud Proxy`, a cluster ID or account status as fraud truth would contradict Q11. Feeding profile targets/status into inference would introduce generator shortcuts. Scalar shared_device_count cannot identify which accounts share a device or distinguish a household from a ring. The table alone cannot measure the agreed legitimate-group gates.

**Disposition:** Keep profiles private; separate propensity from executed action truth; retain subtype/household/defect metadata privately; generate events and identity relationships, then recompute features. Preserve the status field only as optional excluded reference metadata. The existing profile concept is repairable; these missing capabilities must be added.

### GEN-003 - Festive targets are infeasible for many profiles at this snapshot

**Evidence:** [festive_windows.yaml](../code/synthetic-data/customer-master/config/festive_windows.yaml) covers Oct1-15, Oct20-Nov10, and Dec20-Jan5. In the approved12-month window ending2026-09-09, the latest festive day is2026-01-05. There are5,810 nonzero-order profiles with positive festive_order_ratio and no festive day on/after signup before the cutoff. Example `C_00001` signed up2026-05-04 with47 target orders and festive ratio0.26.

**Impact:** Those values cannot be exact realised festive ratios without inventing pre-signup orders or changing the configured calendar. As private preferences, they are not inherently corrupt; the problem arises when mapping them directly into dated events or calling them observed behaviour.

**Disposition:** Convert the ratio into an unconstrained preference/target, intersect eligible order dates with signup/history/calendar first, and compute the realised ratio from generated dates. If no eligible festive dates exist, realised festive share is0; record why the target was not met. Do not fabricate history to preserve the target. Calendar windows remain explicit simulation assumptions, not verified festival dates.

### GEN-004 - Average gap is a rate proxy, not an observed inter-order gap

**Evidence:** Customer EDA cell10 compares `avg_days_between_orders` to `tenure_days / actual_orders`. The CSV matches that expression within0.05 days.1,413 one-order profiles have non-null values even though a single order has no observed inter-order interval.

**Impact:** Copying the value into observed features misstates its meaning and may double-count the information in tenure/order count. This is not an arithmetic failure under the existing profile formula.

**Disposition:** Rename the private field to `target_days_per_order` or document it as an intensity proxy. In generated data, compute actual mean gaps from consecutive order timestamps, null when fewer than two orders exist. Do not require the realised gap to equal tenure/order count.

### GEN-005 - Clustering results cannot be promoted to independent ML evaluation

**Evidence:** Customer EDA cell29 and DBSCAN notebook cell7 compute ARI against customer_segment while choosing epsilon on the same population. The scaler is fitted on that entire exploratory dataset. Direct persona/status columns are excluded from X, which is good, but labels still inform configuration selection. The authoring context explicitly describes profile exploration before transaction generation.

**Impact:** These are development/profile diagnostics, not sealed fraud detection scores. This is acceptable for their exploratory purpose and becomes a defect only if reused as independent model-selection/test evidence.

**Disposition:** Retain exploration, label outputs accordingly, and implement the separate action-label/world-split experiment in v0.2. Do not claim all EDA must be replaced or that whole-dataset exploratory scaling is itself a production bug.

### GEN-006 - Enrichment diagnostic uses the wrong denominator

**Evidence:** DBSCAN notebook cell13 prints that Fraud Proxy is enriched in noise when `fraud_noise / fraud_n >= 0.2`. That is a recall threshold, not enrichment. Executing the actual branch with N=1000, fraud_n=200, noise_n=300 and fraud_noise=40 prints "enriched" although fraud prevalence in noise is13.33%, below the population's20% (enrichment ratio0.667).

**Impact:** The diagnostic can give a false assurance about profile separation. This reproduction demonstrates the logic defect, not that the currently saved DBSCAN run is necessarily unenriched.

**Disposition:** Compare `fraud_noise/noise_n` with `fraud_n/N`, report recall separately, and handle zero denominators explicitly. A small repair is sufficient.

### GEN-007 - EDA failure reporting is not an automated acceptance gate

**Evidence:** Executed the actual customer date-validation cell7 with one negative tenure in an in-memory copy. It printed `RESULT: FAIL` but returned normally. The source notebooks are analysis tools, not standalone generation validators.

**Impact:** An automated pipeline that treats successful cell execution as validation success could continue with invalid data. Interactive printouts are useful but insufficient for export/acceptance.

**Disposition:** Extract/reuse checks in a validator that emits structured findings and exits nonzero/raises on hard violations. Keep EDA summaries. Add a regression fixture proving invalid input cannot produce an accepted manifest.

### GEN-008 - Reuse needs explicit adapters and historical availability

**Evidence:** Team SKU columns include sku_id/color and boolean flags; the canonical interface uses sku/colour and0/1 flags. Customer fields and enum casing differ.17 SKU rows launched after the new history start;41 are inactive at the final snapshot but have no retirement timestamp. Notebooks also contain a machine-specific fallback path to another user's project directory.

**Impact:** Blind file reuse can break schema joins, create sales before launch, misinterpret historical activity or read an unintended file. These are integration limitations, not reasons to discard the catalog.

**Disposition:** Named/versioned adapters, explicit input/output paths, sale-after-launch checks and declared historical-activity handling. Pin/hash the current CSV; do not silently relabel GBP data as INR or infer missing retirement dates.

## Repair versus replacement rule

Recover and repair first. Rebuild only a missing component when its source cannot be obtained, or a recovered component demonstrably cannot meet the approved contracts without redesign. Preserve working catalog rules, profile concepts and fixtures. A future rewrite proposal must identify the failed acceptance checks and why a localized repair is inadequate. No such whole-system impossibility was established in this review.

No additional business interview was required: the findings can be addressed within the already agreed scope. Supplying the missing original source would allow a deeper implementation review, but the current specification records the conditional recovery/reconstruction path without blocking this assessment.
