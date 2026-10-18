# The acceptance register, explained

`final-spec/acceptance-register.csv` lists the 113 acceptance criteria of the specification, one per row, each with its
status and the evidence for it. This page explains every criterion in plain words, groups them by the component of
the specification they belong to, and for each one that is not fully met says what is missing, how to close it and
who it waits on. It is generated from the register as of 17 Oct 2026; the register stays the source of record.

**Statuses.** PASS: the evidence shows the criterion met. PARTIAL: met in part; the missing part is named. NOT_RUN:
not exercised yet, with the reason. Every row also waits for the owner's sign-off (the reviewer column reads
"owner sign-off pending").

**Where it stands:** 105 PASS, 7 PARTIAL, 1 NOT_RUN.

## The open items at a glance

| Criterion | Status | What is missing | Waits on |
|---|---|---|---|
| [GEN-AC-08](#gen-ac-08) | PARTIAL | The small-world reports (coverage, eligibility, excluded abuse, segment support, blocked campaigns) were produced for the fixture world, but for the current generator revision the fixtures and the training worlds were generated in one batch, so the reports did not strictly come first. | Claude Code, on request. Small; offline. |
| [VAL-AC-01](#val-ac-01) | PARTIAL | Every implemented validation rule class has a failing example and a nonzero exit, but file encoding (a non-UTF-8 file) and the size limit have no fixture of their own. | Claude Code, on request. Small; tests only. |
| [FEAT-AC-04](#feat-ac-04) | PARTIAL | The graph rules are tested (one shared type makes no link, two make a link, a value shared by more than 25 accounts is dropped), but graph construction has no failure path that is told apart from a genuinely empty graph. | Owner decision: next experiment. |
| [API-AC-02](#api-ac-02) | PARTIAL | Upload parts, hashes, counts, ownership and path traversal are tested; the size limit is tested only with the limit lowered, not at the real limits of 500,000,000 bytes or 2,000,000 rows. | Claude Code, on request. Small to medium; tests only. |
| [OPS-AC-05](#ops-ac-05) | NOT_RUN | No VM has been deployed, so the smoke checks have never run. | Owner: needs a VM. |
| [OPS-AC-06](#ops-ac-06) | PARTIAL | The local rehearsal runs without cloud credentials and moving the artifacts is tested, but it has not been rehearsed on the presentation machine. | Owner: needs the presentation machine. |
| [TEST-AC-03](#test-ac-03) | PARTIAL | The integration cases are covered except one: a model-mismatch upload at the size limit. | Claude Code, on request, together with API-AC-02. |
| [TEST-AC-04](#test-ac-04) | PARTIAL | Scoring time is measured on the development machine (about 12 seconds for 10,000 customers) and the fallback is tested, but not on the presentation machine. | Owner: needs the presentation machine. |

Three of them (VAL-AC-01, API-AC-02, TEST-AC-03) can be closed with tests alone, and GEN-AC-08 with a rerun of the
small-world reports. Three need a machine (OPS-AC-05 a VM; OPS-AC-06 and TEST-AC-04 the presentation machine). FEAT-AC-04
changes hash-locked scoring code, so it belongs to the next experiment. `pendings.md` tracks them with the other open items.

## Contents

- [01. Goals, scope and domain language](#01-goals-scope-and-domain-language): 5 criteria, all PASS
- [02. Synthetic data generation](#02-synthetic-data-generation): 10 criteria, 1 open
- [03. Data contracts](#03-data-contracts): 6 criteria, all PASS
- [04. Data validation and cleaning](#04-data-validation-and-cleaning): 5 criteria, 1 open
- [05. Data exploration](#05-data-exploration): 6 criteria, all PASS
- [06. Feature engineering](#06-feature-engineering): 9 criteria, 1 open
- [07. Training and validation](#07-training-and-validation): 6 criteria, all PASS
- [08. Model evaluation](#08-model-evaluation): 9 criteria, all PASS
- [09. Model selection](#09-model-selection): 8 criteria, all PASS
- [10. Artifacts and versioning](#10-artifacts-and-versioning): 6 criteria, all PASS
- [11. Inference service](#11-inference-service): 7 criteria, all PASS
- [12. FastAPI and the API contract](#12-fastapi-and-the-api-contract): 8 criteria, 1 open
- [13. React/Vite UI](#13-reactvite-ui): 9 criteria, all PASS
- [14. Storage and audit](#14-storage-and-audit): 7 criteria, all PASS
- [15. Security, deployment and portability](#15-security-deployment-and-portability): 7 criteria, 2 open
- [16. Testing, traceability and delivery](#16-testing-traceability-and-delivery): 5 criteria, 2 open

## 01. Goals, scope and domain language

What the product is for and what it must never do: support a human returns reviewer with evidence, never act on a customer, and always be clear that the data is simulated. Specification: [`final-spec/components/01-goals-and-scope.md`](../final-spec/components/01-goals-and-scope.md).

### GOAL-AC-01

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The demonstration walkthrough shows every kind of customer the product must handle: honest heavy returners, buyers of defective products, families sharing an address or card, false claims, coordinated groups, people who wear and return, and mixed cases. Case pages never reveal the simulated truth.
- **Criterion as written:** Walkthrough covers legitimate heavy returns, defective buyers, benign sharing, deceptive claims, coordination, temporary use and mixed cases without revealing truth on cases.
- **Evidence:** records/2026-10-02-demo-walkthrough.md (one named case per situation in demonstration world W2401); reports/ui/2026-10-02/walkthrough-result.json
- **Gap:** none.

### GOAL-AC-02

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Nothing in the UI or API can suspend an account, refund an order, issue an AI verdict or route an inspection. The product supports a human reviewer; it does not act on customers.
- **Criterion as written:** No UI/API can suspend accounts, refund orders, generate LLM verdicts or route inspections.
- **Evidence:** tests/test_service.py::test_the_served_contract_is_the_bundled_one_and_every_route_is_in_it; tests/test_service.py::test_errors_are_distinguished_and_safe; tests/e2e/walkthrough.py (no training, refund, block or delete control)
- **Gap:** none.

### GOAL-AC-03

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The review queue is 5% of the customers who can be ranked. The customers left out for too little history, and the fallback to the return-rate rule when no model qualifies, are both shown.
- **Criterion as written:** Review budget is 5% of eligible customers; excluded-history counts and fallback are visible.
- **Evidence:** tests/test_service.py::test_population_counts_and_nullable_fields_reconcile; tests/test_service.py::test_baseline_fallback_ranks_equal_the_rule_and_is_labelled; reports/ui/2026-10-02/01-overview.png
- **Gap:** none.

### GOAL-AC-04

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Synthetic and prototype data are labelled as such everywhere, and illustrative numbers are never presented as measured results.
- **Criterion as written:** Synthetic and prototype data are clearly labelled; mock values are not evaluated results.
- **Evidence:** tests/e2e/walkthrough.py (synthetic-data strip on every page); web/src/App.tsx; the wireframe keeps its own illustrative-data banner
- **Gap:** none.

### GOAL-AC-05

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The walkthrough explains, with one case each, the four ways a plain return-rate rule goes wrong: honest heavy returners flagged, abuse hidden inside a normal return rate, customers with too little history, and linked accounts. Again without showing truth on case pages.
- **Criterion as written:** Walkthrough explains, with one case each and no truth on case pages, four reasons the return-rate rule misranks: honest heavy returns, abuse inside an ordinary return rate, thin history and linked accounts.
- **Evidence:** records/2026-10-02-demo-walkthrough.md (four reasons, one case each; truth only on the evaluation page); reports/ui/2026-10-02/walkthrough-result.json
- **Gap:** none.

## 02. Synthetic data generation

The simulator that creates the worlds: customers, orders, returns and the abuse inside them, reproducibly from a seed, with the truth kept separately and privately. Specification: [`final-spec/components/02-synthetic-data-generation.md`](../final-spec/components/02-synthetic-data-generation.md).

### GEN-AC-01

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The same seed, configuration and dependency lock regenerate exactly the same data. Different seeds give different worlds, and the CSV and Parquet copies hold the same values.
- **Criterion as written:** Pinned seed/config/lock reproduces canonical sorted tables; different seeds vary; CSV/Parquet values match.
- **Evidence:** tests/test_generator.py::test_same_seed_reproduces_every_table; tests/test_generator.py::test_different_seeds_differ; tests/test_generator.py::test_csv_and_parquet_hold_the_same_values
- **Gap:** none.

### GEN-AC-02

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The product catalogue adapter keeps all 300 SKUs and 37 styles with their prices, return windows, variants and launch dates, and records the source file's hash.
- **Criterion as written:** Adapter preserves 300 SKUs/37 styles, prices/windows/variants/launch dates and source hash.
- **Evidence:** tests/test_generator.py::test_catalog_adapter_preserves_the_source; tests/test_validation.py::test_catalog_hash_and_adapter_transforms_are_recorded
- **Gap:** none.

### GEN-AC-03

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Switching abuse off keeps ordinary shopping and honest returns as they were and removes every abusive order. A three-unit order with one honest and one abusive request yields two requested units.
- **Criterion as written:** Abuse-off preserves base sales and honest request content and removes every campaign order (return header identifiers and line numbers may differ); quantity-three fixture with one honest/one abusive request yields two requested units.
- **Evidence:** tests/test_generator.py::test_abuse_off_preserves_base_and_honest_events; tests/test_boundaries.py::test_quantity_three_line_with_one_honest_and_one_abusive_request_yields_two_units
- **Gap:** none.

### GEN-AC-04

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Every sale line is in one of its five states (awaiting dispatch, cancelled, shipped, delivered, lost in transit) with dates in a possible order before the cutoff, and nothing planned after the cutoff leaks into the export.
- **Criterion as written:** Five sale states and all cutoff chronology pass; future plans do not enter snapshot.
- **Evidence:** tests/test_generator.py::test_all_five_sale_states_occur; tests/test_validation.py::test_request_after_cutoff_is_rejected; twenty validated worlds in reports/eda/2026-10-02/summary.json
- **Gap:** none.

### GEN-AC-05

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Across the population, the expected share of accounts inclined to false claims (4%), to wear-and-return (3%) and to both (0.5%) matches the configuration, without forcing exact counts; impossible probabilities are refused.
- **Criterion as written:** Population-average probabilities equal .04/.03/.005; invalid allocation fails; no forced realized quotas.
- **Evidence:** tests/test_generator.py::test_expected_overlay_rates_are_four_three_and_half_percent; tests/test_generator.py::test_invalid_overlay_probability_fails_instead_of_clipping; reports/eda/2026-10-02/targets_vs_realised.csv
- **Gap:** none.

### GEN-AC-06

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Who counts as an abuser is rebuilt from what actually happened (actions, requests, units), not from plans. A group member who never acted is not counted, and a style counts as targeted only when one group has three or more accounts with completed coordinated claims.
- **Criterion as written:** Labels reconstruct from action/request/unit joins; nonacting group members and planned-only targets are not positive; a style is targeted iff one group has >=3 accounts with completed coordinated claims.
- **Evidence:** tests/test_generator.py::test_labels_reconstruct_from_actions_and_return_lines; tests/test_generator.py::test_style_is_targeted_only_with_three_accounts_from_one_group
- **Gap:** none.

### GEN-AC-07

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Households can share identifiers (address, card, device) by assignment without every shared identifier showing up in the data. One-off usage may legitimately be 0% or 100%.
- **Criterion as written:** Assigned sharing and realized links differ legitimately; one-order usage may be 0%/100%.
- **Evidence:** tests/test_eda.py::test_assigned_sharing_differs_from_realised_usage; notebooks/02_exploratory_data_analysis.ipynb section 12
- **Gap:** none.

### GEN-AC-08

**Status: PARTIAL** (checked 2026-10-02)

- **What it checks:** Before full-size data is generated, small-world reports on coverage, eligibility, excluded abuse, segment sizes and blocked campaigns are produced and checked.
- **Criterion as written:** Coverage, eligibility, excluded abuse, segment support and blocked-campaign reports precede full generation.
- **Evidence:** records/2026-10-02-generator-implementation.md; fixture reports were produced, but the current generator revision ran fixtures and training worlds in one batch
- **Gap:** The small-world reports (coverage, eligibility, excluded abuse, segment support, blocked campaigns) were produced for the fixture world, but for the current generator revision the fixtures and the training worlds were generated in one batch, so the reports did not strictly come first.
- **How to close it:** Rerun the small-world diagnostics for the current generator revision on their own and record them with a date. The generator itself does not change.
- **Waits on:** Claude Code, on request. Small; offline.

### GEN-AC-09

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Abusive orders respect signup, launch and cutoff dates; they are marked only in the private truth; coordinated claims happen only on that world's hot-list styles; an attempt that did not complete keeps its reason.
- **Criterion as written:** Campaign orders obey signup/launch/cutoff chronology and are marked only in private order_truth; coordinated claims occur only on world hot-list styles; uncompleted attempts keep a reason.
- **Evidence:** tests/test_generator.py::test_campaign_orders_are_private_and_only_hit_hot_list_styles; tests/test_boundaries.py::test_campaigns_start_only_after_the_ring_has_formed
- **Gap:** none.

### GEN-AC-10

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Each account's abuse rate and each address's genuine-failure rate come from reproducible random streams, and the achieved rates are reported. Claim timing, basket shape, line order and same-day orders do not by themselves give away which requests are abusive.
- **Criterion as written:** Per-account action rates and per-address genuine-failure multipliers reproduce from keyed streams; realized means versus .20 and the configured claim rates are reported; the temporary-use occasion weighting matches a fixture; claim timing, basket shape, header line order and same-day orders do not separate honest from abusive requests.
- **Evidence:** tests/test_generator.py::test_same_seed_reproduces_every_table; tests/test_generator.py::test_temporary_use_prefers_orders_with_occasion_wear; reports/eda/2026-10-02/targets_vs_realised.csv; tests/test_generator.py::test_every_transaction_claim_follows_one_timing_law; tests/test_generator.py::test_return_lines_are_numbered_in_time_order; tests/test_generator.py::test_no_account_places_two_orders_on_one_day; tests/test_generator.py::test_campaign_orders_have_ordinary_baskets; notebooks/02_exploratory_data_analysis.ipynb section 4b; tests/test_generator.py::test_campaign_claims_are_not_tied_to_the_first_line; tests/test_generator.py::test_deceptive_claims_share_the_honest_code_mix_and_can_cover_a_parcel; tests/test_generator.py::test_signups_are_flat_across_the_history_window
- **Gap:** none.

## 03. Data contracts

The shape of an upload: seven operational files and a manifest, their keys, dates, amounts and hashes, and the rule that truth never appears in them. Specification: [`final-spec/components/03-data-contracts.md`](../final-spec/components/03-data-contracts.md).

### DATA-AC-01

**Status: PASS** (checked 2026-10-02)

- **What it checks:** An upload with duplicate or missing keys, rows owned by the wrong customer, impossible quantities or impossible dates is refused as a whole, with the table and key of each problem.
- **Criterion as written:** Duplicate/missing keys, bad ownership, excess quantities and impossible chronology reject complete upload with table/key diagnostics.
- **Evidence:** tests/test_validation.py::test_duplicate_key_is_rejected; tests/test_validation.py::test_unknown_customer_is_rejected; tests/test_validation.py::test_cross_customer_return_is_rejected; tests/test_validation.py::test_excess_return_quantity_is_rejected; tests/test_validation.py::test_future_delivery_is_rejected
- **Gap:** none.

### DATA-AC-02

**Status: PASS** (checked 2026-10-02)

- **What it checks:** An upload is exactly the seven operational files, checked against the hashes and row counts in its manifest. Unknown columns or private truth files are refused.
- **Criterion as written:** Exactly seven file hashes/counts validate; unknown columns/private files reject.
- **Evidence:** tests/test_validation.py::test_changed_file_without_manifest_update_is_rejected; tests/test_validation.py::test_extra_or_private_file_is_rejected; tests/test_validation.py::test_private_column_is_rejected
- **Gap:** none.

### DATA-AC-03

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Two return requests made on different dates under one return order each keep their own timing.
- **Criterion as written:** Two request dates under one header retain separate latency.
- **Evidence:** tests/test_generator.py::test_two_request_dates_under_one_header_keep_their_own_times
- **Gap:** none.

### DATA-AC-04

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Evidence dated after the cutoff never survives into features; India-time dates and amounts in paise round-trip exactly.
- **Criterion as written:** Future evidence never survives; IST dates and paise values round-trip.
- **Evidence:** tests/test_validation.py::test_request_after_cutoff_is_rejected; tests/test_generator.py::test_csv_and_parquet_hold_the_same_values
- **Gap:** none.

### DATA-AC-05

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Registering the same snapshot twice gives the same dataset; different content for the same snapshot is refused.
- **Criterion as written:** Same world+content registration is stable; changed world content conflicts.
- **Evidence:** tests/test_service.py::test_dataset_registration_is_validated_idempotent_and_immutable; tests/test_service.py::test_a_world_cannot_be_registered_twice_with_different_content
- **Gap:** none.

### DATA-AC-06

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Every customer's and style's true label can be rebuilt from the private truth, and no truth column appears in the operational files.
- **Criterion as written:** Every customer/style label reconstructs privately; no truth columns occur operationally.
- **Evidence:** tests/test_generator.py::test_labels_reconstruct_from_actions_and_return_lines; tests/test_generator.py::test_operational_tables_carry_only_contract_columns; tests/test_generator.py::test_style_is_targeted_only_with_three_accounts_from_one_group
- **Gap:** none.

## 04. Data validation and cleaning

Checking an upload before it is accepted, and reporting every problem precisely instead of repairing data silently. Specification: [`final-spec/components/04-data-validation-cleaning.md`](../final-spec/components/04-data-validation-cleaning.md).

### VAL-AC-01

**Status: PARTIAL** (checked 2026-10-02)

- **What it checks:** Every class of validation rule has a passing and a failing example, and a failing upload makes the command exit with an error without publishing anything.
- **Criterion as written:** Each rule class has valid/invalid fixtures; invalid command exits nonzero without accepted publication.
- **Evidence:** tests/test_validation.py (one rejection per implemented rule class and a nonzero command exit); file encoding and the size limit have no fixture yet
- **Gap:** Every implemented validation rule class has a failing example and a nonzero exit, but file encoding (a non-UTF-8 file) and the size limit have no fixture of their own.
- **How to close it:** Add two fixtures to tests/test_validation.py: a file in another encoding and an over-limit file, each refused with a nonzero exit.
- **Waits on:** Claude Code, on request. Small; tests only.

### VAL-AC-02

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Returns are summed before they are joined to sales, so a sale is never counted twice.
- **Criterion as written:** Return aggregation before sales joins prevents duplicated exposure.
- **Evidence:** tests/test_generator.py::test_return_lines_are_aggregated_before_joining_sales
- **Gap:** none.

### VAL-AC-03

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Negative values, future dates, unknown categories and rows that cross customers are reported with the right keys.
- **Criterion as written:** Negative values/future availability/unknown category/cross-customer fixtures report correct keys.
- **Evidence:** tests/test_validation.py::test_negative_money_is_rejected; tests/test_validation.py::test_future_delivery_is_rejected; tests/test_validation.py::test_unknown_category_and_changed_catalog_are_rejected_with_the_sku_key; tests/test_validation.py::test_violations_name_the_offending_key
- **Gap:** none.

### VAL-AC-04

**Status: PASS** (checked 2026-10-02)

- **What it checks:** A customer missing optional evidence is kept, not dropped.
- **Criterion as written:** Optional missing evidence does not remove customers.
- **Evidence:** tests/test_validation.py::test_optional_evidence_may_be_empty_without_losing_customers
- **Gap:** none.

### VAL-AC-05

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The original file hashes and every allowed adapter transformation are recorded.
- **Criterion as written:** Original hashes and all allowed adapter transforms are recorded.
- **Evidence:** tests/test_validation.py::test_catalog_hash_and_adapter_transforms_are_recorded
- **Gap:** none.

## 05. Data exploration

Understanding the data before modelling: who can be ranked, what overlaps, and a calibration of the simulator recorded before any validation data exists. Specification: [`final-spec/components/05-data-exploration.md`](../final-spec/components/05-data-exploration.md).

### EDA-AC-01

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The exploration reports, world by world, how many customers can be ranked, how much abuse falls outside the ranked set, and the denominators of every rate.
- **Criterion as written:** Reports include eligibility/excluded abuse and denominators per world.
- **Evidence:** reports/eda/2026-10-02/eligibility.csv; tests/test_eda.py::test_eligibility_report_reconciles_with_its_denominators
- **Gap:** none.

### EDA-AC-02

**Status: PASS** (checked 2026-10-02)

- **What it checks:** A small hand-built example gives the expected enrichment figures (0.667 and 0.20), and a rate with no denominator is shown as empty, not zero.
- **Criterion as written:** Enrichment fixture yields .667/.20; undefined metrics are null.
- **Evidence:** tests/test_eda.py::test_enrichment_fixture_and_null_on_zero_denominator
- **Gap:** none.

### EDA-AC-03

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The exploration shows where features have no overlap between groups, and where genuine and false claims use the same reason codes.
- **Criterion as written:** Reports identify disjoint feature support and genuine/deceptive code overlap.
- **Evidence:** reports/eda/2026-10-02/code_overlap.csv; notebooks/02_exploratory_data_analysis.ipynb section 10; tests/test_eda.py::test_every_code_used_deceptively_also_has_honest_use
- **Gap:** none.

### EDA-AC-04

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Two groups can have the same propensity to abuse but different completed abuse, without that being flagged as an error.
- **Criterion as written:** Equal propensity may coexist with unequal completed prevalence without false failure.
- **Evidence:** reports/eda/2026-10-02/shortcut_auc.csv; notebooks/02_exploratory_data_analysis.ipynb sections 8 and 15
- **Gap:** none.

### EDA-AC-05

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Any change to the simulator's configuration is justified on development data before the validation worlds exist.
- **Criterion as written:** Configuration changes are justified on development data before validation manifests.
- **Evidence:** records/2026-10-02-eda.md; DECISIONS.md amendment 1.2; no validation manifest exists
- **Gap:** none.

### EDA-AC-06

**Status: PASS** (checked 2026-10-02)

- **What it checks:** A dated calibration record, written before the validation worlds, changes only the permitted settings and reports the baseline's and the best candidate's precision against the targets.
- **Criterion as written:** Dated calibration record precedes validation manifests, changes only permitted levers and reports achieved baseline and best-candidate precision against the targets.
- **Evidence:** records/2026-10-02-gate-dry-run.md (no lever changed; baseline .237 in band, best candidate .694 below band); DECISIONS.md AM-30
- **Gap:** none.

## 06. Feature engineering

Turning the raw tables into the model's 43 features, the linked-account graph and the evidence indicators, each checked against hand calculations. Specification: [`final-spec/components/06-feature-engineering.md`](../final-spec/components/06-feature-engineering.md).

### FEAT-AC-01

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Hand-calculated examples match the feature code: partial quantities, two-level shrinkage, a sole buyer, a style with a single SKU or no peers, and a zero-volume case.
- **Criterion as written:** Hand-calculated partial quantity, two-level shrinkage, sole buyer, single-SKU style/no peers and V=0 fixtures match.
- **Evidence:** tests/test_features.py::test_two_level_expectation_matches_hand_calculation; tests/test_features.py::test_a_category_without_peers_needs_the_frozen_reference
- **Gap:** none.

### FEAT-AC-02

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The model reads exactly 43 features in a fixed order, the first 17 unchanged since contract 1.4, with the two link measures kept out of the model. Renaming identifiers consistently changes nothing.
- **Criterion as written:** Ordered 43-feature schema enforced, its first 17 being contract 1.4 unchanged, with the two link measures kept out of the model matrix; identity renaming preserving equality leaves features unchanged.
- **Evidence:** tests/test_features.py::test_feature_schema_is_the_ordered_contract; tests/test_features.py::test_renaming_identifiers_changes_no_feature
- **Gap:** none.

### FEAT-AC-03

**Status: PASS** (checked 2026-10-02)

- **What it checks:** A customer is ranked only with at least three mature sale lines; recent requests change the mix of evidence but not the mature return rate.
- **Criterion as written:** Eligibility threshold exactly three mature lines; recent requests affect composition but not mature rate.
- **Evidence:** tests/test_features.py::test_eligibility_is_exactly_three_mature_lines_and_recent_requests_do_not_move_the_mature_rate
- **Gap:** none.

### FEAT-AC-04

**Status: PARTIAL** (checked 2026-10-02)

- **What it checks:** The linked-account graph: one shared identifier type makes no link, two make a link, an identifier shared by more than 25 accounts is dropped, and a graph that failed to build is told apart from one that is genuinely empty.
- **Criterion as written:** One shared type no edge; two edge; fanout26 value removed; empty vs failed graph distinguished.
- **Evidence:** tests/test_features.py::test_an_edge_needs_two_shared_identifier_types; tests/test_features.py::test_a_value_shared_by_more_than_25_accounts_is_dropped; graph construction has no failure path distinct from an empty graph
- **Gap:** The graph rules are tested (one shared type makes no link, two make a link, a value shared by more than 25 accounts is dropped), but graph construction has no failure path that is told apart from a genuinely empty graph.
- **How to close it:** Give graph construction an explicit failure state, distinct from an empty graph, and test both. The graph code is in features.py, one of the five hash-locked scoring files, so the change changes the scoring-code hash and belongs to a new experiment.
- **Waits on:** Owner decision: next experiment.

### FEAT-AC-05

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The six style states and their boundaries are right: claims 7 days apart link and 8 days apart do not, different SKUs of one style link, unsupported neighbours never link, and missed low-link cases are reported.
- **Criterion as written:** All six style states and signal boundaries correct; claims 7 days apart link and 8 do not; different SKUs of one style link; unsupported neighbors never link; low-link misses reported.
- **Evidence:** tests/test_features.py::test_style_states; tests/test_features.py::test_style_signal_boundaries; tests/test_features.py::test_linked_claims_need_a_supported_neighbour_on_the_same_style_within_seven_days; tests/test_features.py::test_style_without_support_or_returns_has_its_own_state; reports/eda/2026-10-02/detector_thresholds.csv
- **Gap:** none.

### FEAT-AC-06

**Status: PASS** (checked 2026-10-05)

- **What it checks:** The wardrobing (wear-and-return) indicator gets every boundary right on hand-built examples: the 70 and 100 point bands, a late occasion return alone, supporting evidence without a late return, single items, window boundaries, a claim that is not an item return, and no returns at all. It never feeds the model's risk score.
- **Criterion as written:** Wardrobing integer boundaries 70/100, a late occasion return alone (40 points, no band), supporting evidence without a late return (0 points), one returned occasion item (never an excess), a hand-calculated occasion excess and clean-style complaint, the incomplete status below the peer minimum, the 75%/100% window boundaries of a late return, a claim that is not an item return, and no-return fixtures match without mixing into model risk.
- **Evidence:** tests/test_features.py::test_wardrobing_bands_need_a_late_occasion_return_and_support_for_it_with_integer_points; tests/test_features.py::test_wardrobing_evidence_compares_occasion_returns_with_the_customers_other_returns_and_finds_clean_style_complaints; tests/test_features.py::test_a_late_return_is_an_item_return_in_the_last_quarter_of_its_window
- **Gap:** none.

### FEAT-AC-07

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Changing or removing the private truth while keeping the operational data changes no feature and no prediction: the model cannot see the answers.
- **Criterion as written:** Changing private labels with operational inputs fixed, or removing private truth altogether, changes no features or predictions.
- **Evidence:** tests/test_features.py::test_features_are_built_without_private_truth_and_ignore_it; tests/test_features.py::test_features_never_read_private_truth
- **Gap:** none.

### FEAT-AC-08

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The share of a customer's claims matched by a linked account follows the style-level rule on a hand-built example, counting each of the customer's own lines once.
- **Criterion as written:** coordinated_claim_share matches the style-grain linked-claim rule on a hand-built fixture and counts each own line once.
- **Evidence:** tests/test_features.py::test_coordinated_claim_share_counts_each_own_line_once
- **Gap:** none.

### FEAT-AC-09

**Status: PASS** (checked 2026-10-05)

- **What it checks:** The claim and timing features match a hand-calculated example, are zero or empty for a customer with no claims or returns, and leave the original 17 features unchanged.
- **Criterion as written:** The claim-context and timing-grain features match a hand-calculated fixture (rates, whole-order and two-reason orders, the densest fortnight, self-excluded peer and style rates, window ratios), give zeros and nulls for a customer or a snapshot without claims or returns, and leave the first 17 features of a first-experiment world unchanged value for value.
- **Evidence:** tests/test_features.py::test_claims_are_measured_against_what_was_bought_and_how_orders_were_claimed; tests/test_features.py::test_timing_is_read_in_finer_grain_than_late_or_not; tests/test_features.py::test_new_features_survive_a_snapshot_without_any_return; first 17 features of W2103 unchanged value for value (records/2026-10-05-experiment-2.md)
- **Gap:** none.

## 07. Training and validation

Fitting the candidate models without letting any held-out world leak into training. Specification: [`final-spec/components/07-training-and-validation.md`](../final-spec/components/07-training-and-validation.md).

### TRAIN-AC-01

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Training, validation, test and demonstration seeds never overlap; linked customers never span worlds; demo and fixture identifiers are refused in scorecards.
- **Criterion as written:** Seed sets disjoint; linked customers never cross worlds; scorecard rejects demo/fixture IDs.
- **Evidence:** tests/test_modeling.py::test_seed_sets_are_disjoint_and_identifiers_are_world_namespaced; tests/test_modeling.py::test_scorecards_refuse_fixture_worlds
- **Gap:** none.

### TRAIN-AC-02

**Status: PASS** (checked 2026-10-05)

- **What it checks:** Nothing is learned from held-out data; training fails if a training world needed the all-worlds category fallback; labels are joined only from the truth written with each world.
- **Criterion as written:** Held-out data fit no learned transform; training fails if a training world uses the all-worlds category fallback; assembly audits world IDs and joins labels only with the truth written with the world.
- **Evidence:** tests/test_modeling.py::test_learned_transforms_are_fitted_on_training_rows_only; tests/test_modeling.py::test_training_assembly_audits_world_ids; tests/test_pipeline.py::test_the_offline_pipeline_runs_end_to_end_under_the_roots_it_is_given (training refuses a world that uses the all-worlds fallback; labels refuse a truth file not written with the world)
- **Gap:** none.

### TRAIN-AC-03

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Every out-of-fold score comes from a model that never saw that world, and serving holds one final model.
- **Criterion as written:** Each OOF row scored by a pipeline excluding its world; serving contains one final estimator.
- **Evidence:** tests/test_modeling.py::test_each_out_of_fold_row_is_scored_without_its_world; tests/test_modeling.py::test_candidate_record_and_single_serving_estimator
- **Gap:** none.

### TRAIN-AC-04

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Every candidate's record includes its full parameters, training weights, hashes, durations, warnings and any rejection.
- **Criterion as written:** Every candidate record includes expanded params, training weights, hashes, durations, warnings and rejections.
- **Evidence:** tests/test_modeling.py::test_candidate_record_and_single_serving_estimator; tests/test_modeling.py::test_a_candidate_that_does_not_converge_is_rejected; records/2026-10-02-gate-dry-run.md
- **Gap:** none.

### TRAIN-AC-05

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The unsupervised reference cannot read the customer labels.
- **Criterion as written:** Unsupervised fit cannot read customer labels.
- **Evidence:** tests/test_modeling.py::test_unsupervised_fit_never_reads_a_label
- **Gap:** none.

### TRAIN-AC-06

**Status: PASS** (checked 2026-10-05)

- **What it checks:** A weighted candidate gives extra weight exactly to the honest members of its protected group, which changes the fitted model without adding a model input; training refuses a frame without that group flag, or with the flag among the features.
- **Criterion as written:** A weighted candidate weights exactly the honest members of its gate segment, changes the fitted model, adds no model input, and refuses a training frame without the segment flag or with the flag among its features.
- **Evidence:** tests/test_modeling.py::test_weighted_candidates_count_honest_gate_members_more_in_training_and_never_as_a_feature
- **Gap:** none.

## 08. Model evaluation

Measuring candidates honestly: precision at the review budget, false-positive rates for each protected honest group, references and an error account. Specification: [`final-spec/components/08-model-evaluation.md`](../final-spec/components/08-model-evaluation.md).

### EVAL-AC-01

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Hand-labelled examples give the right precision, recall and false-positive rate at review budgets of 1%, 5% and 10%, including rounding up, ties and pooled worlds.
- **Criterion as written:** Hand-labelled ceil/tie/pooled fixtures give correct precision/recall/FPR at1/5/10%.
- **Evidence:** tests/test_evaluation.py::test_review_budget_is_a_ceiling_per_world_then_pooled; tests/test_evaluation.py::test_ties_are_broken_by_the_public_hash_never_by_row_order
- **Gap:** none.

### EVAL-AC-02

**Status: PASS** (checked 2026-10-02)

- **What it checks:** A protected group smaller than 200 fails the coverage check, and a zero denominator is never reported as a 0% false-positive rate.
- **Criterion as written:** Segment<200 fails validation coverage; zero denominator never becomes0% FPR.
- **Evidence:** tests/test_evaluation.py::test_gate_refuses_thin_or_empty_segments; tests/test_evaluation.py::test_segment_rates_keep_their_denominators_and_a_zero_denominator_is_null
- **Gap:** none.

### EVAL-AC-03

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Group membership is right in awkward cases: ties at a quantile, a kept defective unit, an unused household identifier, overlapping groups.
- **Criterion as written:** Quantile ties/kept defective unit/unused household identifier/overlap fixtures have correct segment membership.
- **Evidence:** tests/test_evaluation.py::test_benign_segments_follow_the_definitions; tests/test_evaluation.py::test_segments_may_overlap_and_are_counted_separately
- **Gap:** none.

### EVAL-AC-04

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Reports give paired whole-world intervals and per-world results, without claiming statistical significance.
- **Criterion as written:** Reports include paired whole-world intervals and per-world results without significance claims.
- **Evidence:** tests/test_evaluation.py::test_bootstrap_is_paired_seeded_and_reports_intervals_not_significance; data/artifacts/experiments/EXP-20261002-01/reports/validation.json; records/2026-10-02-validation-and-selection.md
- **Gap:** none.

### EVAL-AC-05

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Missed style and wardrobing cases, the no-return state, coverage and empty metrics are all reported.
- **Criterion as written:** Style/wardrobing misses, no-return state, coverage and null metrics are present.
- **Evidence:** data/artifacts/experiments/EXP-20261002-01/reports/validation.json and test.json (evidence_report_only, coverage); records/2026-10-02-validation-and-selection.md; records/2026-10-02-final-test.md
- **Gap:** none.

### EVAL-AC-06

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Truth is joined only after scores are frozen, and no inference route ever returns truth.
- **Criterion as written:** Private evaluation joins happen after score freeze; no truth on inference routes.
- **Evidence:** tests/test_service.py::test_serving_does_not_import_offline_modules_or_need_private_truth; tests/test_service.py::test_case_shows_evidence_with_denominators_and_no_truth; records/2026-10-02-evaluation-critic-review.md
- **Gap:** none.

### EVAL-AC-07

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The rulebook and volume-only references use the same population, budget and ties as the model with thresholds from training only; they are marked report-only and can never be selected.
- **Criterion as written:** Rulebook and volume-only references use the identical population/k/ties and training-only thresholds, are flagged report-only and cannot be selected.
- **Evidence:** tests/test_evaluation.py::test_references_share_population_and_ties_and_can_never_be_selected; tests/test_evaluation.py::test_rulebook_thresholds_come_from_training_folds_only
- **Gap:** none.

### EVAL-AC-08

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The error account splits false positives and false negatives with their denominators, shows where model and baseline select differently, and discloses the calibration.
- **Criterion as written:** Error account gives false-positive and false-negative splits with denominators plus model-versus-baseline selection differences; the calibration disclosure is present.
- **Evidence:** tests/test_evaluation.py::test_error_account_splits_false_positives_and_false_negatives_with_denominators; data/artifacts/experiments/EXP-20261002-01/published/experiment.json; records/2026-10-02-gate-dry-run.md (calibration and timing ablation)
- **Gap:** none.

### EVAL-AC-09

**Status: PASS** (checked 2026-10-05)

- **What it checks:** The report shows what the result depends on (removing claim or timing features), how often each honest group is reviewed by model and rule, and the stress-world table, each produced by a pipeline command and reproducible.
- **Criterion as written:** The report carries the feature-family ablation (all, without claims, without timing, without both), the review rate of each honest group under model and rule including repeat genuine claimants, and the stress table; each is produced by a pipeline command and reproduces.
- **Evidence:** tests/test_pipeline.py::test_the_offline_pipeline_runs_end_to_end_under_the_roots_it_is_given; data/artifacts/experiments/EXP-20261002-01/reports/ablation.json and stress.json (arai ablation, arai stress)
- **Gap:** none.

## 09. Model selection

The gate a model must pass to replace the return-rate rule, decided before the test, with the test run once. Specification: [`final-spec/components/09-model-selection.md`](../final-spec/components/09-model-selection.md).

### SEL-AC-01

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The gate refuses a candidate with higher precision but a worse false-positive rate for households, and refuses one that only equals the rule's precision.
- **Criterion as written:** Higher precision/worse household FPR fails; equal precision fails.
- **Evidence:** tests/test_evaluation.py::test_gate_needs_strictly_higher_precision_and_no_worse_segment_rate
- **Gap:** none.

### SEL-AC-02

**Status: PASS** (checked 2026-10-02)

- **What it checks:** When several candidates pass, the tie is broken by the worst false-positive rate, then by a fixed order.
- **Criterion as written:** Passing ties follow worst FPR then ordinal.
- **Evidence:** tests/test_evaluation.py::test_choice_is_precision_then_worst_segment_rate_then_ordinal
- **Gap:** none.

### SEL-AC-03

**Status: PASS** (checked 2026-10-02)

- **What it checks:** When no candidate passes, the product falls back to the return-rate rule and says so, without pretending a model was promoted.
- **Criterion as written:** No winner produces fallback without fabricated promotion.
- **Evidence:** tests/test_evaluation.py::test_choice_is_precision_then_worst_segment_rate_then_ordinal; tests/test_evaluation.py::test_validation_needs_a_recorded_dry_run_and_the_test_needs_a_frozen_selection; tests/test_service.py::test_baseline_fallback_ranks_equal_the_rule_and_is_labelled
- **Gap:** none.

### SEL-AC-04

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The selection is recorded before the test, and a failed test cannot be rescued by switching to the runner-up.
- **Criterion as written:** Selection record precedes test; test failure prevents runner-up switching.
- **Evidence:** tests/test_evaluation.py::test_the_final_test_runs_once_and_survives_a_crash_between_its_two_records; data/artifacts/experiments/EXP-20261002-01/selection.json (frozen 16:49:15Z, tested 17:06:34Z); records/2026-10-02-final-test.md
- **Gap:** none.

### SEL-AC-05

**Status: PASS** (checked 2026-10-16)

- **What it checks:** When test results inform a new attempt, the earlier result is kept on record and the new attempt is tested on worlds nobody has seen.
- **Criterion as written:** Test-informed iteration retains failure and uses untouched test worlds.
- **Evidence:** Two test-informed iterations, each a new experiment on new worlds after the previous final test was recorded: experiment 2's test (records/2026-10-05-experiment-2.md, commit 52ab751) preceded experiment 3's contract (c78dcda), and experiment 3's test (68f4843) preceded experiment 4's contract (0b0bf29); test worlds W3301-W3305, W4301-W4305 and W5301-W5305 are disjoint, and src/arai/contract.py retired_seed_owner with tests/test_contract.py refuses a world of an earlier experiment. Earlier results are kept, not overwritten: experiment 2 stayed the published result, experiment 3 (a weaker 0.548) was set aside with its data untouched, and experiment 4's record keeps the selected candidate's failed repeat leg on training worlds. No final test has failed so far, so a failed test has not had to be retained.
- **Gap:** none. Note: No final test has ever failed, so keeping a failed test on record has not had to happen. The owner may prefer PARTIAL until it has (pendings.md, decision 2.3).

### SEL-AC-06

**Status: PASS** (checked 2026-10-02)

- **What it checks:** A dated dry run of the gate on training scores comes before the validation worlds and selects nothing; the gate and group definitions do not change afterwards.
- **Criterion as written:** Dated gate dry run on out-of-fold training scores precedes validation manifests and selects nothing; gate rule and segment definitions are unchanged afterwards.
- **Evidence:** records/2026-10-02-gate-dry-run.md; tests/test_evaluation.py::test_validation_needs_a_recorded_dry_run_and_the_test_needs_a_frozen_selection
- **Gap:** none.

### SEL-AC-07

**Status: PASS** (checked 2026-10-05)

- **What it checks:** A candidate that reviews honest repeat genuine claimants more often than the rule fails the gate whatever its precision.
- **Criterion as written:** A candidate that reviews honest repeat genuine claimants more often than the rule fails the gate whatever its precision; an equal or lower rate passes that leg.
- **Evidence:** tests/test_evaluation.py::test_gate_needs_strictly_higher_precision_and_no_worse_segment_rate; EXP-20261005-02 validation: hgb_leaf15 and hgb_leaf15_w4 rejected on the leg, hgb_leaf15_w6 selected (records/2026-10-05-experiment-2.md)
- **Gap:** none.

### SEL-AC-08

**Status: PASS** (checked 2026-10-05)

- **What it checks:** A candidate that reviews honest customers with exactly one genuine delivery failure more often than the rule fails the gate, even if it reviews repeat claimants less often.
- **Criterion as written:** A candidate that reviews honest customers with exactly one genuine failure more often than the rule fails the gate even when it reviews repeat claimants less often.
- **Evidence:** tests/test_evaluation.py::test_gate_needs_strictly_higher_precision_and_no_worse_segment_rate; EXP-20261005-04 validation and final test: the fifth leg met at 1.3% against 4.8% and 1.5% against 4.6% (records/2026-10-05-experiment-4.md)
- **Gap:** none.

## 10. Artifacts and versioning

Model bundles that are immutable, verified before use and tied to the code that produced them. Specification: [`final-spec/components/10-artifacts-and-versioning.md`](../final-spec/components/10-artifacts-and-versioning.md).

### ART-AC-01

**Status: PASS** (checked 2026-10-02)

- **What it checks:** A saved model, loaded again, gives the same scores within 1e-10 absolute and 1e-8 relative, and exactly the same ranked selection.
- **Criterion as written:** Save/load score tolerance1e-10 absolute/1e-8 relative and exact ranked selection pass fixed fixtures.
- **Evidence:** tests/test_bundles.py::test_saved_bundle_reproduces_training_scores_and_the_ranked_selection
- **Gap:** none.

### ART-AC-02

**Status: PASS** (checked 2026-10-02)

- **What it checks:** A bundle of unknown type, wrong hash, wrong schema or mismatched library version is refused before use.
- **Criterion as written:** Unknown type/hash/schema/library mismatch fails before use.
- **Evidence:** tests/test_bundles.py::test_any_mismatch_is_refused_before_use; tests/test_bundles.py::test_path_like_identifiers_are_refused; tests/test_bundles.py::test_a_rejected_candidate_cannot_be_bundled
- **Gap:** none.

### ART-AC-03

**Status: PASS** (checked 2026-10-02)

- **What it checks:** A run keeps the model it was submitted with, even if another model is promoted or the server restarts.
- **Criterion as written:** Run preserves bound model through promotion/restart.
- **Evidence:** tests/test_service.py::test_a_run_keeps_its_bound_model_through_promotion; tests/test_service.py::test_a_crash_publishes_nothing_and_restart_keeps_notes_and_bindings
- **Gap:** none.

### ART-AC-04

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The baseline works with no model at all, and serving can never train.
- **Criterion as written:** Baseline works without any candidate estimator; inference fits are blocked.
- **Evidence:** tests/test_bundles.py::test_baseline_needs_no_candidate_and_nothing_is_fitted_at_scoring; tests/test_bundles.py::test_scoring_never_calls_fit
- **Gap:** none.

### ART-AC-05

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Bundle hashes do not depend on their own metadata, and earlier bundles are never changed.
- **Criterion as written:** Hashes have no circular metadata; prior bundles remain immutable.
- **Evidence:** tests/test_bundles.py::test_the_identifier_is_a_content_hash_and_bundles_are_never_rewritten; tests/test_bundles.py::test_activation_is_atomic_versioned_and_never_falls_back_silently
- **Gap:** none.

### ART-AC-06

**Status: PASS** (checked 2026-10-05)

- **What it checks:** Publishing fails and changes nothing (active model, published report) if the feature code no longer reproduces the training features or the report cannot be built; a published bundle carries the training code hash, the cutoff and that check.
- **Criterion as written:** Publication fails, leaving the active pointer and the published report unchanged, when the feature code no longer reproduces the frozen training features or the report cannot be built; a published bundle carries the training-time code hash, the cutoff and the feature check.
- **Evidence:** tests/test_pipeline.py::test_the_offline_pipeline_runs_end_to_end_under_the_roots_it_is_given
- **Gap:** none.

## 11. Inference service

Scoring an uploaded snapshot as a background run that either completes fully or publishes nothing. Specification: [`final-spec/components/11-inference-service.md`](../final-spec/components/11-inference-service.md).

### INF-AC-01

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Submitting a scoring run is acknowledged before scoring finishes, and the run's stages are recorded.
- **Criterion as written:** Submission acknowledgement precedes scoring completion and stages persist.
- **Evidence:** tests/test_service.py::test_submission_is_acknowledged_before_scoring_and_is_idempotent
- **Gap:** none.

### INF-AC-02

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Repeating a request with the same idempotency key returns the same resource; the same key with a different body is refused (409).
- **Criterion as written:** Duplicate scoped key/body returns same resource; changed body409.
- **Evidence:** tests/test_service.py::test_submission_is_acknowledged_before_scoring_and_is_idempotent; tests/test_service.py::test_notes_are_append_only_idempotent_and_cross_runs
- **Gap:** none.

### INF-AC-03

**Status: PASS** (checked 2026-10-02)

- **What it checks:** A crash can never publish half a run, and a restart keeps notes and the run's model binding.
- **Criterion as written:** Crash cannot publish partial success; restart preserves notes/bindings.
- **Evidence:** tests/test_service.py::test_a_crash_publishes_nothing_and_restart_keeps_notes_and_bindings; tests/test_service.py::test_a_failed_stage_fails_the_run_with_a_safe_error
- **Gap:** none.

### INF-AC-04

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Population counts add up, and the fields of eligible and ineligible customers are filled or empty consistently.
- **Criterion as written:** Population counts and eligible/ineligible nullable fields reconcile.
- **Evidence:** tests/test_service.py::test_population_counts_and_nullable_fields_reconcile; tests/test_service.py::test_no_eligible_customer_is_a_valid_empty_ranking
- **Gap:** none.

### INF-AC-05

**Status: PASS** (checked 2026-10-02)

- **What it checks:** With no qualifying model the baseline gives complete, clearly labelled evidence; a corrupt active model fails loudly.
- **Criterion as written:** No-winner path yields complete labelled baseline evidence; corrupt active model fails.
- **Evidence:** tests/test_service.py::test_baseline_fallback_ranks_equal_the_rule_and_is_labelled; tests/test_service.py::test_corrupt_or_missing_or_rejected_models_block_scoring
- **Gap:** none.

### INF-AC-06

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The rule's rank and selection use the same budget and ties as the model's, equal them under fallback, and match the comparison filters' counts.
- **Criterion as written:** baseline_rank/baseline_selected use the same k and ties as the model, equal rank/selection under fallback, and the run counts match the comparison filters.
- **Evidence:** tests/test_service.py::test_population_counts_and_nullable_fields_reconcile; tests/test_service.py::test_comparison_filter_partitions_the_selected_customers; tests/test_service.py::test_baseline_fallback_ranks_equal_the_rule_and_is_labelled
- **Gap:** none.

### INF-AC-07

**Status: PASS** (checked 2026-10-05)

- **What it checks:** Each run records a drift report; shifted scores or inputs and changed scoring code each raise a warning, and a snapshot like the training data raises none.
- **Criterion as written:** A run records its drift report; shifted scores or inputs and a changed scoring code each raise a warning, and a snapshot like training raises none.
- **Evidence:** tests/test_service.py::test_a_run_says_when_its_scores_or_inputs_sit_outside_training; tests/test_service.py::test_a_scored_run_records_its_drift_report_and_a_changed_scoring_code
- **Gap:** none.

## 12. FastAPI and the API contract

The HTTP API: matches its OpenAPI contract exactly, pages correctly and refuses what it must. Specification: [`final-spec/components/12-fastapi-and-api-contract.md`](../final-spec/components/12-fastapi-and-api-contract.md).

### API-AC-01

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Every real request and response validates against the OpenAPI contract, including 201 and 202 answers and the documented errors.
- **Criterion as written:** All actual requests/responses validate against OpenAPI including201/202 and documented errors.
- **Evidence:** tests/test_service.py (every response body validated against contracts/openapi.yaml 1.2.0 with an OpenAPI 3.0 validator: Dataset, Run, CustomerPage, Case, Review, StylePage, StyleDetail, Health, Error)
- **Gap:** none.

### API-AC-02

**Status: PARTIAL** (checked 2026-10-02)

- **What it checks:** Uploads enforce allowed parts, size limits, hashes, row counts, ownership and refuse path traversal.
- **Criterion as written:** Upload parts/limits/hash/count/ownership/path-traversal fixtures enforced.
- **Evidence:** tests/test_service.py::test_upload_rejects_unknown_parts_missing_parts_paths_and_bad_manifests; tests/test_service.py::test_dataset_registration_is_validated_idempotent_and_immutable; tests/test_service.py::test_upload_over_the_size_limit_is_refused_with_413 (limit lowered for the test; no fixture at the real 500,000,000-byte or 2,000,000-row limit)
- **Gap:** Upload parts, hashes, counts, ownership and path traversal are tested; the size limit is tested only with the limit lowered, not at the real limits of 500,000,000 bytes or 2,000,000 rows.
- **How to close it:** Add a test that streams an upload just over the real byte limit (and one over the row limit) without keeping it in memory, and expects 413.
- **Waits on:** Claude Code, on request. Small to medium; tests only.

### API-AC-03

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Paging returns no duplicates or gaps, and a page cursor cannot be reused for another run or filter.
- **Criterion as written:** Cursors return no duplicates/gaps and cannot cross run/filter.
- **Evidence:** tests/test_service.py::test_cursors_are_stable_and_bound_to_their_list; tests/test_service.py::test_population_counts_and_nullable_fields_reconcile
- **Gap:** none.

### API-AC-04

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Every UI action has an endpoint, and there is no endpoint to train, refund, block or delete a note.
- **Criterion as written:** Every UI action has an endpoint, with no training/refund/block/delete-note operation.
- **Evidence:** tests/test_service.py::test_the_served_contract_is_the_bundled_one_and_every_route_is_in_it; tests/test_service.py::test_notes_are_append_only_idempotent_and_cross_runs
- **Gap:** none.

### API-AC-05

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Unknown (404), unfinished (409), conflict (409) and invalid (422) answers are told apart.
- **Criterion as written:** Unknown404, unfinished409, conflict409 and validation422 are distinguished.
- **Evidence:** tests/test_service.py::test_errors_are_distinguished_and_safe; tests/test_service.py::test_submission_is_acknowledged_before_scoring_and_is_idempotent
- **Gap:** none.

### API-AC-06

**Status: PASS** (checked 2026-10-02)

- **What it checks:** A browser origin that is not allowed is refused, and on the VM an unauthenticated API call is refused.
- **Criterion as written:** Unlisted CORS origin denied; VM API unauthenticated denied.
- **Evidence:** tests/test_service.py::test_cors_allows_only_listed_origins; tests/test_service.py::test_vm_profile_requires_the_shared_login
- **Gap:** none.

### API-AC-07

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The comparison filter (model only, rule only, both) splits the ranked customers consistently with the run's counts and stable paging; unranked customers appear only under All.
- **Criterion as written:** comparison filter values partition eligible customers consistently with the run counts and stable cursors; ineligible customers appear only under all.
- **Evidence:** tests/test_service.py::test_comparison_filter_partitions_the_selected_customers
- **Gap:** none.

### API-AC-08

**Status: PASS** (checked 2026-10-05)

- **What it checks:** Every published metric has a stable code; health reports the queue depth and the worker heartbeat; a login header that is not ASCII is refused with 401.
- **Criterion as written:** Every published metric has a code; Health reports the queue depth and the worker heartbeat; a login header that is not ASCII is refused with 401.
- **Evidence:** tests/test_pipeline.py::test_the_offline_pipeline_runs_end_to_end_under_the_roots_it_is_given; tests/test_service.py::test_health_reports_the_queue_and_when_a_worker_was_last_seen; tests/test_service.py::test_a_login_header_that_is_not_ascii_is_refused_not_crashed
- **Gap:** none.

## 13. React/Vite UI

The analyst workbench: every screen truthful about its state, usable by keyboard, never presenting simulation as a measured result. Specification: [`final-spec/components/13-react-vite-ui.md`](../final-spec/components/13-react-vite-ui.md).

### UI-AC-01

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The walkthrough moves through datasets, runs, queue, case, style, SKU, notes and evaluation, keeping its context and working Back.
- **Criterion as written:** Walkthrough traverses dataset/run/queue/case/style/SKU/notes/evaluation with stable context and back.
- **Evidence:** tests/e2e/walkthrough.py; reports/ui/2026-10-02/walkthrough-result.json (dataset, run, queue, case, style, SKU, notes, evaluation, back)
- **Gap:** none.

### UI-AC-02

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The clickable prototype opens offline from a file; the production UI takes its figures from the API, not from inline values.
- **Criterion as written:** Prototype opens offline via file://; production consumes API instead of inline metrics.
- **Evidence:** verification/wireframe-walkthrough (wireframe over file://, recorded under amendment 1.1); web/src/api.ts with types generated from the contract; no inline metric in web/src
- **Gap:** none.

### UI-AC-03

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Fallback, loading, failed, empty and insufficient-history states each tell the truth and look different.
- **Criterion as written:** Fallback/loading/failed/empty/insufficient-history states truthful and distinct.
- **Evidence:** tests/e2e/fallback_check.py with reports/ui/2026-10-02/fallback-result.json (baseline fallback in a browser: banner, relabelled score, comparison hidden); tests/e2e/walkthrough.py (error, empty, insufficient history); web/src/App.test.tsx
- **Gap:** none.

### UI-AC-04

**Status: PASS** (checked 2026-10-02)

- **What it checks:** No AI confidence, US dollars, non-apparel content, calibrated bands or loss-prevented claims remain.
- **Criterion as written:** No AI confidence/USD/non-apparel/calibrated bands/loss-prevented claims remain.
- **Evidence:** tests/e2e/walkthrough.py (no fraud, confidence or verdict wording on case pages); web/src/App.test.tsx; records/2026-10-02-frontend-critic-review.md
- **Gap:** none.

### UI-AC-05

**Status: PASS** (checked 2026-10-02)

- **What it checks:** A keyboard-only user can filter, open cases, move between tabs, add a note and come back.
- **Criterion as written:** Keyboard user filters, opens cases, navigates tabs, appends note and returns.
- **Evidence:** tests/e2e/walkthrough.py (keyboard: filter, open case, tabs, append note, back); reports/ui/2026-10-02/walkthrough-result.json
- **Gap:** none.

### UI-AC-06

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Notes persist across runs in the product; the prototype says its notes live in memory only.
- **Criterion as written:** Implemented notes persist cross-run; prototype labels memory-only behavior.
- **Evidence:** tests/test_service.py::test_notes_are_append_only_idempotent_and_cross_runs; tests/e2e/walkthrough.py (note persists after reload)
- **Gap:** none.

### UI-AC-07

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Simulated truth is revealed only on the evaluation page, and examples are never presented as measured results.
- **Criterion as written:** Truth reveal isolated to evaluation; examples never presented as measured results.
- **Evidence:** tests/e2e/walkthrough.py (truth hidden until asked for, absent from overview, queue and case); records/2026-10-02-frontend-critic-review.md
- **Gap:** none.

### UI-AC-08

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The model-versus-rule comparison appears on overview, queue and case in neutral wording and is hidden under fallback; evaluation shows the references, the error account and the calibration disclosure.
- **Criterion as written:** Rank comparison appears on overview/queue/case with neutral wording and is hidden under fallback; evaluation shows references, error account and calibration disclosure.
- **Evidence:** web/src/App.test.tsx (comparison shown with neutral wording, hidden under fallback); tests/e2e/walkthrough.py; reports/ui/2026-10-02/10-evaluation.png
- **Gap:** none.

### UI-AC-09

**Status: PASS** (checked 2026-10-05)

- **What it checks:** Evaluation finds each figure by its code, ranking and slice; it leads with what the result depends on, the repeat-claimant review rates and the stress range; the datasets page shows the worker state and the queue.
- **Criterion as written:** Evaluation finds every figure by code, ranking and slice with reworded names; it leads with the claim and timing dependence, the repeat-claimant review rates and the stress range; the datasets page shows the worker state and the queue.
- **Evidence:** web/src/pages/Evaluation.test.tsx; reports/ui/2026-10-05/walkthrough-result.json (46 of 46 browser checks)
- **Gap:** none.

## 14. Storage and audit

PostgreSQL as the one source of results and notes, safe under concurrency and crashes, with notes kept across runs. Specification: [`final-spec/components/14-storage-and-audit.md`](../final-spec/components/14-storage-and-audit.md).

### STORE-AC-01

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Two identical requests at the same moment create one resource.
- **Criterion as written:** Concurrent duplicate requests yield one resource.
- **Evidence:** tests/test_service.py::test_two_workers_cannot_claim_the_same_run_and_duplicate_submissions_make_one_run
- **Gap:** none.

### STORE-AC-02

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Two workers can never both claim the same job.
- **Criterion as written:** Two worker claims cannot both own same job.
- **Evidence:** tests/test_service.py::test_two_workers_cannot_claim_the_same_run_and_duplicate_submissions_make_one_run
- **Gap:** none.

### STORE-AC-03

**Status: PASS** (checked 2026-10-05)

- **What it checks:** A crash or a failure while writing results never shows a succeeded run without its complete results, nor results of a run that did not succeed.
- **Criterion as written:** A crash, or a failure while results are written, never exposes a succeeded run without its complete results, nor results of a run that did not succeed.
- **Evidence:** tests/test_service.py::test_results_and_success_are_one_transaction; tests/test_service.py::test_a_crash_publishes_nothing_and_restart_keeps_notes_and_bindings
- **Gap:** none.

### STORE-AC-04

**Status: PASS** (checked 2026-10-02)

- **What it checks:** A note written on one run appears on another run of the same world and customer, with its original author and run.
- **Criterion as written:** RunA note appears in runB same world/customer with original attribution.
- **Evidence:** tests/test_service.py::test_notes_are_append_only_idempotent_and_cross_runs
- **Gap:** none.

### STORE-AC-05

**Status: PASS** (checked 2026-10-05)

- **What it checks:** A backup restores to another folder without depending on paths of the original laptop.
- **Criterion as written:** Backup restores to relocated root without laptop path dependencies.
- **Evidence:** tests/test_service.py::test_a_database_dump_restores_to_another_database_and_artifact_root; tests/test_service.py::test_artifacts_move_to_another_root_without_stored_paths
- **Gap:** none.

### STORE-AC-06

**Status: PASS** (checked 2026-10-05)

- **What it checks:** Every API read of run results, the experiment report and the truth export comes from PostgreSQL; no result file is written or opened.
- **Criterion as written:** Every API read of run results, the experiment report and the truth export is answered from PostgreSQL; no result file is written or opened.
- **Evidence:** tests/test_service.py::test_the_api_answers_from_postgres_and_opens_no_result_file
- **Gap:** none.

### STORE-AC-07

**Status: PASS** (checked 2026-10-05)

- **What it checks:** Runs scored before version 1.7 are imported once from their files and answer identically; a run whose files are gone is marked failed, not shown empty.
- **Criterion as written:** Results of runs scored before version 1.7 are imported once from their files and answer identically; a run whose files are gone is failed, not empty.
- **Evidence:** tests/test_service.py::test_results_of_earlier_runs_are_imported_once_from_their_files
- **Gap:** none.

## 15. Security, deployment and portability

Running it on another machine or a VM: portable folders, no access to truth from serving, and the VM's security checks. Specification: [`final-spec/components/15-security-deployment-portability.md`](../final-spec/components/15-security-deployment-portability.md).

### OPS-AC-01

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The specification folder, extracted into a path with spaces and without the rest of the repository, passes its own verification tool.
- **Criterion as written:** Extracted folder in a path with spaces passes tools/verify_package.py without repo siblings.
- **Evidence:** ARAI-final-spec-v1.6.zip extracted to a directory whose path contains spaces, outside the repository; tools/verify_package.py reports PASS (46 files, 45 links, 101 criteria)
- **Gap:** none.

### OPS-AC-02

**Status: PASS** (checked 2026-10-16)

- **What it checks:** The wireframe opens offline on another machine and browser without installing anything.
- **Criterion as written:** Wireframe opens offline on another machine/browser without dependency installation.
- **Evidence:** tests/e2e/wireframe_offline_check.py: final-spec copied alone into a path with spaces on a second machine (Linux container) and opened from disk in a second browser (Chromium 141; the original checks used Edge on Windows) with the network off and every non-file request refused; 14 of 14 checks passed, no request left the machine, no console error, nothing installed for the wireframe. reports/ops-ac-02/2026-10-16/result.json, overview.png, case.png
- **Gap:** none.

### OPS-AC-03

**Status: PASS** (checked 2026-10-02)

- **What it checks:** A fresh second environment builds from the locks and migrations and reproduces small-world data and score ranks.
- **Criterion as written:** Fresh supported second environment bootstraps from locks/migrations and reproduces small-world canonical data/score ranks.
- **Evidence:** records/2026-10-02-serving-and-ui.md: the Linux container built from uv.lock regenerates fixture world 2001 with byte-identical CSV files and scores the demonstration world with identical scores and ranks to the Windows environment
- **Gap:** none.

### OPS-AC-04

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Serving cannot read truth, and an upload cannot write outside its folder.
- **Criterion as written:** Serving cannot read truth; upload cannot escape root.
- **Evidence:** tests/test_service.py::test_serving_does_not_import_offline_modules_or_need_private_truth; tests/test_service.py::test_upload_rejects_unknown_parts_missing_parts_paths_and_bad_manifests; docker-compose.yml mounts only data/artifacts (verified in the running container)
- **Gap:** none.

### OPS-AC-05

**Status: NOT_RUN**

- **What it checks:** On the VM: HTTPS works, the shared login answers 401 without credentials, the IP block holds, and the database is not reachable from the internet.
- **Criterion as written:** VM HTTPS/shared-login401/IP block/closed public DB smoke checks pass.
- **Evidence:** Not run: no VM has been deployed. When run it also covers a Keycloak sign-in, a role refusal and session expiry (component 15, AM-70).
- **Gap:** No VM has been deployed, so the smoke checks have never run.
- **How to close it:** Deploy to a VM (RUNBOOK 3.1 and 2.6, docker-compose.yml with APP_PROFILE=vm behind a TLS proxy) and run: HTTPS, the shared login's 401, the IP block, the closed database port, a Keycloak sign-in, a role refusal and session expiry.
- **Waits on:** Owner: needs a VM.

### OPS-AC-06

**Status: PARTIAL** (checked 2026-10-02)

- **What it checks:** The local rehearsal works without any cloud credential, and restores after its data folder moves.
- **Criterion as written:** Local rehearsal works without cloud credentials and restores at relocated root.
- **Evidence:** `arai local` rehearsed on the development machine with no cloud credential (reports/ui/2026-10-02/walkthrough-result.json); tests/test_service.py::test_artifacts_move_to_another_root_without_stored_paths. Not rehearsed on the presentation machine
- **Gap:** The local rehearsal runs without cloud credentials and moving the artifacts is tested, but it has not been rehearsed on the presentation machine.
- **How to close it:** Run RUNBOOK section 5 on the presentation machine, including a restore after moving the data folder, and record the result.
- **Waits on:** Owner: needs the presentation machine.

### OPS-AC-07

**Status: PASS** (checked 2026-10-05)

- **What it checks:** Health reports queue depth and worker heartbeat, each run reports drift against training, and two instances migrating the database at startup is safe.
- **Criterion as written:** Health reports queue depth and worker heartbeat; a run reports drift against training; concurrent migration at startup is safe.
- **Evidence:** tests/test_service.py::test_health_reports_the_queue_and_when_a_worker_was_last_seen; tests/test_service.py::test_a_run_says_when_its_scores_or_inputs_sit_outside_training
- **Gap:** none.

## 16. Testing, traceability and delivery

The register itself: evidence for every criterion, the experiment's order of events, and a release another developer can pick up. Specification: [`final-spec/components/16-testing-and-delivery.md`](../final-spec/components/16-testing-and-delivery.md).

### TEST-AC-01

**Status: PASS** (checked 2026-10-16)

- **What it checks:** Every criterion has evidence or an explicit NOT_RUN; passing a syntax check never counts as passing at runtime.
- **Criterion as written:** Every AC has evidence or explicit NOT_RUN; syntax success never stands in for runtime acceptance.
- **Evidence:** This register, re-checked 2026-10-16: every one of 113 criteria has evidence, PARTIAL with the gap named, or NOT_RUN with the reason
- **Gap:** none.

### TEST-AC-02

**Status: PASS** (checked 2026-10-02)

- **What it checks:** Small worlds are checked before full generation; calibration and the gate dry run come before validation worlds; the selection is frozen before the test.
- **Criterion as written:** Small-world gate precedes full generation; calibration and gate dry run precede validation generation; selection freezes before test exposure.
- **Evidence:** records/2026-10-02-gate-dry-run.md; records/2026-10-02-validation-and-selection.md; records/2026-10-02-final-test.md; the order is enforced in src/arai/experiment.py and tested in tests/test_evaluation.py
- **Gap:** none.

### TEST-AC-03

**Status: PARTIAL** (checked 2026-10-02)

- **What it checks:** The integration cases run, their outputs are kept, and no truth leaks.
- **Criterion as written:** Integration cases execute with retained output and no truth leakage.
- **Evidence:** tests/test_service.py, tests/test_bundles.py, tests/test_evaluation.py, tests/test_validation.py cover the listed integration cases except a model-mismatch upload at the size limit; outputs are retained under reports/ and the experiment directory
- **Gap:** The integration cases are covered except one: a model-mismatch upload at the size limit.
- **How to close it:** Add that case to the size-limit test of API-AC-02.
- **Waits on:** Claude Code, on request, together with API-AC-02.

### TEST-AC-04

**Status: PARTIAL** (checked 2026-10-02)

- **What it checks:** On the machine the demonstration runs on, scoring time is measured and the baseline fallback works.
- **Criterion as written:** Target-machine rehearsal has measured runtime and working baseline fallback.
- **Evidence:** Scoring a 10,000-customer world takes about 12 seconds on the development machine; the baseline fallback is tested. Not measured on the presentation machine
- **Gap:** Scoring time is measured on the development machine (about 12 seconds for 10,000 customers) and the fallback is tested, but not on the presentation machine.
- **How to close it:** On the presentation machine: time a scoring run and run the baseline rehearsal (tests/e2e/fallback_check.py).
- **Waits on:** Owner: needs the presentation machine.

### TEST-AC-05

**Status: PASS** (checked 2026-10-02)

- **What it checks:** The release states its failures, limitations and hashes, with enough reference material for another developer.
- **Criterion as written:** Release includes failures/limitations/hashes and enough reference material for another developer.
- **Evidence:** README.md; records/ (seven independent reviews with dispositions, validation, final test, limits); final-spec/DECISIONS.md AM-01..AM-34; hashes in selection.json and the bundle manifests
- **Gap:** none.
