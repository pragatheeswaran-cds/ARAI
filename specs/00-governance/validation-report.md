# Specification validation and readiness report

Reviewed 2026-09-25. **NOT READY FOR IMPLEMENTATION.** This report records specification checks and data inspection, not application acceptance tests. Drafts require explicit approval/freeze in the next phase.

## Existing artifacts discovered

26 original files: four DOCX design/build documents with four companion PDFs; HLD/LLD Markdown and HTML summaries; data-dictionary HTML; two presentation HTML files and two slide decks; seven figures; three current synthetic-data Python files; one ZIP containing six input CSV/Parquet pairs, two ground-truth CSVs, a manifest and older copies of data documentation/source. The referenced submission proposal, approval/decision log, runtime config, dependency lock, application source, notebooks, API/UI definitions and application tests were not found. The synthetic validator exists but is not an application test suite.

DOCX paragraphs/tables, HTML/slide text, current source, archived source differences, manifest and every CSV were inspected. Companion PDFs were inventoried but their text parity with DOCX was not independently verified; no PDF parser was installed. Parquet members were inventoried but CSV/Parquet value parity could not be checked without an installed engine. No source file was regenerated to conceal the mismatch.

## Specifications created and derivation

61 artifacts under specs/: all 56 requested paths, plus source inventory, preserved design config, observed data profile, source test catalog and this validation report. The set covers governance, product, data, features, model/evaluation/selection/policy, inference, API, UI, MLOps, security and testing. Ten FRs, eight NFRs, six use cases and ten acceptance criteria retain explicit design traceability. The feature dictionary covers 31 named features/signals plus derived output contracts. All 48 LLD module test cases are preserved alongside future test specifications.

Direct HLD/LLD derivations include the seven-table contract, two-pass shrinkage/residual design, Isolation Forest and its eight inputs, rule thresholds, weighted/capped graph, separate wardrobing band, SKU verdict predicates, three-part blend, run-relative percentiles, packet caps, one-retry provider fallback, six job/review API operations, five UI screens, local deployment and sealed-seed/matched-budget evaluation intent. This does not imply the source formulas are complete or mutually consistent.

Ten explicit review assumptions cover draft versioning, local demonstration boundary, API validation/error completions, null/empty conventions, local artifact lifecycle, UI states/accessibility, full hashes, complete segment reporting, proposed nested wire shapes and numeric fixture tolerance. Business thresholds, graph formulas, selection priorities and gate mappings were not invented.

## Structural checks performed

- All 56 requested paths exist with substantive content; total 61 specification artifacts. All 16 YAML artifacts parse with duplicate-key rejection; observed-data-profile.json parses. All 68 Markdown file links resolve, and all question references resolve to the 22 registered questions.
- OpenAPI contains exactly the six LLD operations, unique operation IDs and complete declared path parameters; all 44 internal references resolve. A dedicated OpenAPI conformance validator is not installed; these are structural checks, not a certification of external tooling compatibility.
- The ordered eight-feature forest allow-list matches the preserved LLD config. Blend weights sum to one; separate wardrobe weights and rule boundaries remain source-derived.
- All 26 original file hashes match the pre-edit inventory. Changes are confined to specs/. No root configuration, source, dataset, notebook, application or trained artifact was added or changed.
- Source test extraction contains 16 modules and 48 source cases. Test catalogs are planned verification, not test executions. Traceability contains 64 rows, including every FR/NFR and each feature.

## Observed data checks

Six CSV manifest hash prefixes match actual bytes. Inspected keys are unique and no sales line is returned twice. Checked sales-header, SKU, return-header, reason and returned-sales-line references resolve; returned SKU/customer match sales; quantity bounds, pro-rata refund bounds using a one-penny observation tolerance, non-refunded zero amounts, no returns on cancelled orders and return-after-delivery checks have zero observed violations. These read-only checks do not certify the full proposed DQ contract or approve its unresolved rounding/eligibility policy.

The archive has 10,000 labelled customers, 338 SKUs, 52,232 orders, 115,299 sales lines, 24,661 submissions and 30,694 return lines. Abuse labels total 740 (7.4%). The essential customer_master table is absent. There are 5,140 stored latency/header-date disagreements, 2,389 delivered lines with unexpired return windows, 466 partial returns, 237 consolidated submissions and 25 injected reason-text rows. See observed-data-profile.json for reproducible evidence and explicit unverified Parquet parity.

## End-to-end consistency review

| Boundary | Review result | Governing question / fix |
|---|---|---|
| Architecture ? HLD | Batch design preserved; storage choices conflict; safety wording conflicts with low-tier clearing; source approval absent | Q-007/Q-011/Q-017 |
| HLD ? LLD | Seven files and module boundaries agree; all feature formulas, graph contribution and severe/clear authority are not complete | Q-004/Q-005/Q-007 |
| LLD ? specifications | Source thresholds and module IDs preserved; obsolete /score appendix not promoted into API; literal source test ambiguities annotated | Q-008/Q-018/Q-022 |
| Data ? features | Archive missing master; latency source inconsistent; statuses, quantities and exposure maturity undefined | Q-001/Q-002/Q-003 |
| Features ? training | Exact forest allow-list matches; unknown null/rank/category/trend transformations explicitly blocked | Q-004/Q-012 |
| Training ? evaluation | Unsupervised batch fitting and independent seed worlds retained; no invented supervised row split | Q-009/Q-010 |
| Evaluation ? selection | Primary criterion, minimum quality, deterministic candidate/tie order and ceiling unavailable; selection refuses incomplete policy | Q-009 |
| Selected bundle ? inference | Run-scoped fit/transform/graph/policy provenance defined; serialization and second-pass refit semantics unresolved | Q-006/Q-013 |
| Inference ? API | Job-shaped scoring retained, no probability response; nested shapes proposed; lifecycle/version access incomplete | Q-008/Q-012 |
| API ? UI | Six operations mapped to five screens; scorecard, upload registration, opener/outcomes remain explicit gaps | Q-008/Q-019 |
| Requirements ? tests | Stable IDs linked to future components and test specs; no claim of implemented tests | traceability-matrix.md |
| Security/operability ? release | Privacy exclusions and safe fallback retained; salt/encryption/retention, durable persistence and numeric SLOs unset | Q-011/Q-014/Q-015 |

Directly resolvable clarifications: percentile score is not probability; raw-z source fixtures require explicit deff; exclusion sets must use a union to avoid double subtraction; risk tier and memo tier remain separate; null/absence never implies zero risk; packet size is bytes; historic reference metrics are not new evaluation results. Meaningful unresolved policy choices remain in the question register.

## Remaining risks and approval decisions

12 BLOCKING: Q-001?Q-012 cover complete dataset, return/exposure semantics, latency source, feature formulas, graph scoring/fallback, second pass, decision authority, API lifecycle, ML acceptance/selection, seed freeze, persistence and ranking/flagging. Nine IMPORTANT questions cover explanation/artifact format, operational limits, privacy controls, SKU semantics, source authority, evidence quality, UI details, synthetic shortcuts and conflicting scope wording. Q-020 is OPTIONAL production MLOps.

Leakage risks: importing sealed labels or generator rates; parsing identity prefixes; using post-outcome account/status/receipt information as prospective input; cross-customer graph/transaction random splits; incomplete community exclusion in category priors; tuning on sealed worlds. The specs prohibit shortcuts and keep unresolved as-of choices blocked.

Synthetic concerns: population-conditioned reasons/timing/topology/status create easy proxies; static fixed-size rings and template text simplify recovery; repeated seeds share the same law; missing customer master and consolidated dates cause skew; open return windows bias rates. Known generator parameters do not automatically supply an achievable-separation estimator. Existing quoted precision figures lack scored-run artifacts and cannot satisfy release criteria.

Owners must explicitly approve the question resolutions and assumptions, then freeze the relevant versions. No additional architecture, production infrastructure, account action or model family was introduced. Implementation remains deferred.
