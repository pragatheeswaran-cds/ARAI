# Team customer-master and SKU assessment

Follow-up: the [generator reuse assessment](generator-reuse-assessment.md) rechecks the current artifacts against v0.2, verifies additional SKU invariants, reproduces notebook diagnostic/validation issues and identifies calendar-infeasible profile targets. Use it with the [current repair requirements](../specs/v0.2/existing-generator-disposition.md); the historical observations below are preserved.

Review date: 2026-09-25. Status: specification review; not implementation approval.

The team samples are useful foundations for a customer-profile-first simulation. The added SKU CSV confirms the previously saved SKU summaries and resolves the missing-output limitation. Missing generator sources, profile semantics, evaluation issues and differences from the existing project contracts remain open. No new synthetic data was generated, no notebook or model was executed, and no application code was changed.

N/A in the tables means no issue identified within the checks performed. It does not imply complete runtime validation.

## Evidence and scope

- Team repository: `code/synthetic-data`; source/configuration/notebooks read from local `origin/dev`, pinned to `e5505d87574ceeca3f94defac375b387f06266de`.
- Customer data inspected directly from that commit: `customer-master/output/customer_master.csv` and `customer_master_v1_1000.csv`. Parquet was not independently decoded.
- Newly added SKU data inspected directly: [sku_master.csv](../code/synthetic-data/sku-master/sku_master.csv). This file is currently untracked in the team working tree; no matching generator run manifest is supplied.
- SKU CSV SHA-256: `0a558c72b1c4e108d4d114ec72f3480bc72597d05282979ded4087cbcdb53a3e`.
- Design comparisons use the existing Architecture/HLD/LLD and [draft schema](../specs/02-data/schema.yaml), not an assumption that the team samples supersede them.
- The assistant-generated `datasets/wardrobing-reference-20250901` dataset and its ZIP are excluded. This assessment concerns team artifacts only.
- Detailed earlier findings and decision IDs are retained in the [specification review](../specs/00-governance/team-sample-review.md). This document supersedes its historical statement that the SKU CSV is unavailable; missing helper modules remain unresolved.

## Intended workflow

The user clarified that customer age, order counts and other behavioural fields are simulation profiles used to explore clusters and then generate sales and returns. Extra fields are therefore purposeful, not inherently defective.

Customer profiles -> simulated labels -> exploratory clustering -> sales/return generation after specification approval -> features recomputed from transactions -> detector evaluation.

Keep operational account status, simulated behaviour truth, cluster IDs and detector outputs distinct. An active account can also have a simulated fraud persona. Planned rates/counts must be distinguished from observations. Clusters matching labels constructed from the same fields demonstrate encoded structure, not independent fraud-detection validity.

## Available data

| Dataset | Evidence | Size and scope |
|---|---|---|
| Current customer master | Actual committed CSV | 10,000 customers, 10 columns |
| Earlier customer master | Actual committed CSV | 1,000 customers, 10 columns; five personas, no zero-order rows |
| SKU master | Added CSV, independently inspected | 300 SKUs, 13 source columns, 37 styles, five brands and five categories |

Customer columns: `customer_id`, `signup_date`, `tenure_days`, `customer_segment`, `actual_orders`, `avg_days_between_orders`, `festive_order_ratio`, `return_rate`, `shared_device_count`, `account_status`.

SKU columns: `sku_id`, `style_id`, `brand`, `category`, `size`, `color`, `color_id`, `unit_price`, `price_band`, `return_window_days`, `is_occasion_wear`, `launch_date`, `active_flag`. The notebook adds `derived_band` for checking; its 14-column summary is not a 14-column source contract.

### Current customer distribution

| Segment | Count | Share |
|---|---:|---:|
| Occasional | 3,832 | 38.32% |
| Seasonal | 1,847 | 18.47% |
| Loyalist | 1,573 | 15.73% |
| New Growth | 1,453 | 14.53% |
| Dormant | 1,088 | 10.88% |
| Fraud Proxy | 207 | 2.07% |

Account statuses: ACTIVE 9,282; FLAGGED 308; SUSPENDED 237; CLOSED 173. These are separate from persona labels.

## Customer-master assessment

| Category | What is good | What is bad / needs attention |
|---|---|---|
| Identifiers | All 10,000 IDs are unique; no duplicate rows. | N/A |
| Signup date and tenure | All ages match signup dates against 2026-09-09. Age range 3-365 days; signup dates 2025-09-09 through 2026-09-06. | Accounts older than one year are not covered. Whether needed is a scope decision. |
| Order counts | Range 0-140 represents inactive accounts and heavy shoppers. Useful for future generation targets. | `actual_orders` implies observations. Specify whether it is an exact planned count or a stochastic target before generating events. |
| Zero-order records | All 1,581 zero-order customers have null average gaps and zero return/festive ratios. No positive-order customer has a null gap. | N/A |
| Missing values | No nulls in the other nine columns; gap nulls correspond to zero orders. | N/A within the team's current profile semantics. |
| Persona diversity | Config includes household sharing, legitimate high returners, heavy buyers and overlap between personas. | These are explicit artificial assumptions, not evidence of real-world distributions. |
| Return and festive ratios | Valid inputs as generation propensities; both remain within 0-1. Observed ranges: return 0-0.83, festive 0-0.87. | They cannot yet be claimed as measured transactional rates. For 8,244 positive-order rows, festive ratio times order count is non-integer; all 1,413 one-order rows have fractional festive ratios. Define propensities versus rounded observed ratios. |
| Average order gap | A simple frequency proxy is available. | Formula is tenure/order count, not mean spacing between orders. Rename or later derive from order timestamps, with fewer-than-two-order handling specified. |
| Status and labels | Persona and status are separate columns. | Define FLAGGED and suspicion semantics. Fraud Proxy is artificial truth, not confirmed real fraud. Keep truth outside detector inputs. |
| Identity sharing | Device counts vary from 1-12; config acknowledges benign sharing. | Counts cannot establish shared-identity topology. Future transactions need actual device/address/payment links. |
| Wardrobing | A wardrober subtype exists in configuration. | Output does not retain the subtype, so its actual count cannot be established from this CSV. Event timing, reasons, occasion purchases and bracketing remain to be specified. |
| Project integration | IDs and signup dates support the account reference role. | Required loyalty_tier/marketing_channel are missing; status enum differs. A profile table is not automatically the canonical operational master. |
| Versions and reproducibility | Seed/config and current/earlier outputs are available. | Referenced generator source is missing. No manifest proves which source/config produced each version. |

## SKU distributions verified from the added CSV

| Dimension | Counts |
|---|---|
| Brand | Brand_A 80; Brand_B 70; Brand_C 62; Brand_D 56; Brand_E 32 |
| Category | T-shirt 78; Shirt 64; Jeans 62; Jacket 58; Dress 38 |
| Size | S 46; M 90; L 90; XL 60; XXL 14 |
| Colour | Black 77; White 60; Navy 47; Grey 46; Red 28; Beige 22; Green 20 |
| Price band | Budget 24; Mid 155; Premium 90; Luxury 31 |
| Return window | 30 days: 204; 45 days: 58; 60 days: 38 |
| Occasion wear | True 45; False 255 |
| Active | True 259; False 41 |

## SKU assessment

| Category | What is good | What is bad / needs attention |
|---|---|---|
| Output availability | Actual 300-row CSV is now present; key counts match saved EDA summaries. | File is untracked and lacks a run manifest. Full byte-for-byte provenance to the earlier notebook run is not established. |
| Scale | 300 SKUs is within the architecture's 200-400 range. | N/A |
| Identifiers and variants | Zero duplicate SKU IDs, full rows or style-colour-size variants. | N/A |
| Missing values | Zero missing values across all 13 columns. | N/A |
| Types and dates | Prices/windows parse as integers; flags as booleans; every launch date parses in YYYY-MM-DD format. | N/A |
| Style membership | Exactly the 37 configured styles; every style count, colour, size, price and band matches the v2 specification table. | N/A |
| Style consistency | Brand, category, price, band, window, occasion flag, launch date and active flag are constant within each style. | N/A |
| Colour coding | Colour-to-colour_id mapping is one-to-one in both directions. | N/A |
| Category coverage | Five categories provide differentiated products. | Existing contract requires six different category values; footwear/accessories are absent. Mapping or a design amendment is needed. |
| Prices | All positive, range 499-6,499; configured style prices match exactly. | Team spec declares INR but existing project reference uses GBP. Currency must be reconciled across sales/refunds and examples. CSV itself has no currency field. |
| Price bands | Verified 24/155/90/31 counts agree with configuration. | Budget/Mid/Premium/Luxury differs from existing value/mid/premium contract. |
| Return windows | Explicit 30/45/60-day values support future timing calculations. | Fixed category windows differ from the existing within-category variation design. Preserve the applicable historical window on return events. |
| Occasion wear | 45 flagged SKUs provide inputs for wardrobe scenarios. | Flag alone is insufficient: transactional behaviour must supply the other signals and benign counterexamples. |
| Launch and activity | Dates span 2024-01-20 through 2025-11-23; 259 active and 41 inactive SKUs. | Current activity does not define historical availability. Future sales must obey launch dates and an agreed retirement/availability policy. |
| Price outliers | The saved EDA's 18 high-price outliers are configured luxury dresses; prices are confirmed by the CSV. | N/A; global outlier status alone is not an error. |
| Schema names | Fields are consistent within the team CSV. | `sku_id`/`color` differ from `sku`/`colour`; extra color_id needs an explicit integration policy. |
| Generator reproducibility | Detailed v2 specification and generation notebook describe the intended construction. | Imported sku_config_v2 and sku_generator_v2 modules remain absent from the reviewed commit. Runtime correctness cannot be certified. |

## Clustering and code assessment

The following model numbers are saved notebook results, not runs performed during this review.

| Category | What is good | What is bad / needs attention |
|---|---|---|
| K-means | Saved adjusted Rand index is 0.320 at six clusters and 0.333 at the silhouette-selected ten clusters. This shows partial persona correspondence. | This does not prove business realism or independent fraud-detection performance. Perfect separation need not be the objective. |
| DBSCAN results | Saved run places 142 of 207 Fraud Proxy customers among 213 noise points: 68.6% capture and 66.7% noise precision. | Same-data persona agreement selected epsilon; these are development results. Most customers form one large cluster, so this is not recovery of six personas. |
| Enrichment diagnostic | The saved run has greater fraud prevalence in noise than the overall population. | General code condition checks recall rather than enrichment. Correct formula: compare fraud_in_noise/noise_count with fraud_count/customer_count; handle zero denominators. |
| Feature isolation | Notebook feature lists exclude persona labels and account status. | Exclusion from X does not prevent label leakage through model selection. Sealed labels must not guide tuning. |
| Validation | Checks cover missingness, duplicates, ranges and consistency. | Several failures only print messages. A future hard-contract gate must fail and block export/acceptance. |
| Python syntax | All 57 notebook code cells passed static syntax parsing in the preceding review. | Imports, missing helpers, dependency compatibility and runtime behaviour are not validated by syntax checks. |
| Architecture fit | Clustering is appropriate as an exploratory generator-design activity. | It does not replace the specified production Isolation Forest/rules/graph approach without a design decision. |

## Checks performed and limitations

The added CSV was checked for shape, nulls, duplicates, ID uniqueness, variant uniqueness, types, date parsing, counts/distributions, positive prices, colour-code consistency and style invariants. Its 37 styles were compared directly with the v2 specification's counts, allowed colours/sizes, exact prices and price bands; no mismatch was found in those comparisons. Existing notebook summaries agree on the checked aggregate quantities.

These checks do not demonstrate that missing generator modules reproduce the CSV, that every soft distribution target or price-ladder rule has been independently verified, or that future sales/returns satisfy chronology and referential constraints. No new model fit or synthetic generation was run.

## Required specification decisions

| Priority | Decision | Related review IDs |
|---|---|---|
| BLOCKING | Supply and review missing generator/helper source and provenance. | TEAM-001 / TEAM-D01 |
| BLOCKING | Separate simulation profiles, truth labels and operational customer fields; define status/suspicion meaning. | TEAM-002 / TEAM-D02 |
| BLOCKING | Agree SKU taxonomy, currency, bands, field mappings and return-window variation. | TEAM-003 / TEAM-D03 |
| BLOCKING | Specify profile-to-event generation, wardrobing signals, benign controls and actual identity relationships. | TEAM-004/005 / TEAM-D04 |
| IMPORTANT | Define planned-versus-observed rates/counts, gap semantics, evaluation isolation and corrected metrics. | TEAM-006/007/008 / TEAM-D05 |
| IMPORTANT | Specify validation failure behaviour, seed/as-of/calendar policy, dependency versions and output manifests. | TEAM-009 / TEAM-D06 |

The missing SKU output concern is resolved. The remaining decisions should be reviewed before generation; no business thresholds, revised schemas or algorithms are approved by this assessment.

**SPECIFICATION READINESS: NOT READY FOR IMPLEMENTATION.**
