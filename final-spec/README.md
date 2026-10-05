# ARAI - portable development specification

Version **3.0** - Consolidated 2026-09-26, amended 2026-10-05 - **Implementation baseline**

Each component has its own specification and acceptance criteria. This folder is the authoritative development package; no previous version, original laptop path or sibling archive is required.

The user requested the final agreed component specs after reviewing v0.3.1 and authorized this work. This package carries forward the recorded v0.3 decisions and reviewed corrections, plus API/UI details now that the initial wireframe is supplied. [Decision provenance](DECISIONS.md) distinguishes consolidation defaults from historical decisions. No new historical signature or measured implementation success is asserted.

Amendment 1.1 (2026-10-02) records the changes agreed in the user's review of version 1.0: ring purchases and graded style-targeting truth, linked-claim style evidence, calibrated and disclosed difficulty, report-only reference rankings, the rule-versus-model comparison in the API and UI, a gate dry run, integer wardrobing points and a lower quality threshold. [Decision provenance](DECISIONS.md) lists each change, what it supersedes and which values are still unmeasured engineering defaults. Components 04, 14 and 15 are unchanged from 1.0. The seven operational tables and manifest schema_version stay 1.0.

Amendment 1.2 (2026-10-02) follows the first generator run and the exploration of the development worlds: longer tenures for established personas, ring campaigns that start at ring formation, three scope clarifications, the confirmed style-targeting threshold and the first evidence in the acceptance register. See the amendment 1.2 section of the decision provenance.

Amendment 1.3 (2026-10-02) follows an independent review of that exploration: one timing law for every claim, ordinary baskets for ring orders, return lines numbered by time, annual order targets, ring activity spread over the window and correlated honest claims. Worlds generated under 1.2 are void.

Amendment 1.4 (2026-10-02) follows a second review of the data, the first gate dry run and a review of the features: raw link measures are evidence only, a count of late item returns is the 17th feature, the wardrobing indicator is rebuilt on late returns, deceptive claims match honest ones in reason code, line and extent, and difficulty calibration is closed with its outcome disclosed. Worlds generated under 1.3 are void.

Amendment 1.5 (2026-10-02) follows a third review, made before any validation world existed: the dependence of the result on the simulated return-timing law is disclosed with an ablation, the experiment order is enforced in code with provenance in every record, and the API contract moves to 1.2.0. No world or model changed.

Amendment 1.6 (2026-10-02) records the outcome (selection on validation, the final test passed once) and the decisions from the reviews of the serving side and the front end: an exact allow-list for serialised types, safer startup reconciliation, and caveats shown first on the evaluation page.

Amendment 1.7 (2026-10-05) records the project owner's decision after a review of the code: the API reads from PostgreSQL only. Run results, the published experiment report and the truth export are stored there; no result file is written. The API contract is unchanged.

Amendment 1.8 (2026-10-05) follows a principal-ML review of the specification and the code: the report now states what the result depends on and which honest group the model reviews more often than the rule, the development target is closed as a property of the simulation, the API contract moves to 1.3.0 (stable metric codes, worker heartbeat), and provenance, publication and monitoring gaps are closed. A version label on a component or contract names the amendment in which that file last changed in substance.

Amendment 1.9 (2026-10-05) records two owner decisions: the 0.75-0.85 development target stays open until it is reached (the closure in 1.8 is withdrawn), and a new experiment on fresh seeds will add a gate leg for honest repeat claimants.

Amendment 2.0 (2026-10-05) is the contract of that experiment, EXP-20261005-02: fresh seeds, 43 features (the first 17 unchanged), six candidates of which three weight honest repeat claimants in training, and a four-leg gate. The simulator is unchanged.

Amendment 3.0 (2026-10-05) records that experiment 2 passed its final test and sets up experiment 3, EXP-20261005-03: the same features, candidates and gate on a less generous simulator (honest customers return late more often, abusers act less often), to test how much of the result survives. Earlier worlds are never overwritten.

## Start on any system

1. Copy/extract the **whole final-spec folder**.
2. Open [the clickable wireframe](wireframe/index.html) in a browser. No install, server or Internet required.
3. Read components below and implement dependencies first.
4. From this folder run: python tools/verify_package.py (Python3.10+, standard library only).
5. Track actual implementation evidence in [acceptance-register.csv](acceptance-register.csv). All runtime ACs start NOT_RUN.

Production architecture: Python/FastAPI + React/Vite + PostgreSQL (metadata and every served result), file artifacts for registered snapshots and model bundles, and offline model fitting. Standalone HTML is for portable wireframe review, not a replacement for React/Vite.

## Separate component specifications

| Order | Component | Acceptance prefix |
|---|---|---|
| 01 | [Goals, scope and domain language](components/01-goals-and-scope.md) | GOAL-AC |
| 02 | [Synthetic data generation](components/02-synthetic-data-generation.md) | GEN-AC |
| 03 | [Operational and private data contracts](components/03-data-contracts.md) | DATA-AC |
| 04 | [Data validation, cleaning and snapshot clearance](components/04-data-validation-cleaning.md) | VAL-AC |
| 05 | [Exploratory data analysis and diagnostics](components/05-data-exploration.md) | EDA-AC |
| 06 | [Feature engineering and explanatory evidence](components/06-feature-engineering.md) | FEAT-AC |
| 07 | [Training dataset, model fitting and validation](components/07-training-and-validation.md) | TRAIN-AC |
| 08 | [Model and evidence evaluation](components/08-model-evaluation.md) | EVAL-AC |
| 09 | [Model selection and promotion gate](components/09-model-selection.md) | SEL-AC |
| 10 | [Artifacts, reproducibility and baseline bundle](components/10-artifacts-and-versioning.md) | ART-AC |
| 11 | [Batch inference and job lifecycle](components/11-inference-service.md) | INF-AC |
| 12 | [FastAPI and API contract](components/12-fastapi-and-api-contract.md) | API-AC |
| 13 | [React/Vite frontend and analyst workflows](components/13-react-vite-ui.md) | UI-AC |
| 14 | [PostgreSQL, immutable storage and audit](components/14-storage-and-audit.md) | STORE-AC |
| 15 | [Security, deployment and portability](components/15-security-deployment-portability.md) | OPS-AC |
| 16 | [Testing, traceability and delivery](components/16-testing-and-delivery.md) | TEST-AC |

## Shared contracts and inputs

- [Operational tables](contracts/data-schema.yaml), [manifest JSON Schema](contracts/manifest.schema.json), [private truth](contracts/private-truth.yaml).
- [Generation settings](contracts/generator-config.yaml), [joint overlay policy](contracts/generator-policy.yaml), [reason groups](contracts/reason-groups.yaml).
- [Ordered features](contracts/features.yaml), [candidate/split settings](contracts/experiment.yaml), [OpenAPI](contracts/openapi.yaml).
- [Catalog](assets/sku_master_source.csv), [profile inputs](assets/profile-config.yaml), [festival calendar](assets/festive-windows.yaml), [16-code reference](assets/reason_codes.csv).
- [Original PDF](reference/ARAI-original.pdf), [PDF changes](wireframe/changes-from-pdf.md), [prototype walkthrough](wireframe/README.md).
- [Decision record](DECISIONS.md), [acceptance register](acceptance-register.csv), [verification](verification/REPORT.md).

## Contract ownership

Data schema/codebook own operational fields; features.yaml owns feature order; experiment.yaml owns seeds/candidates; OpenAPI owns routes/payloads. Components own semantics/invariants/acceptance. Contradictions are spec defects: record a dated correction, never silently fall back to older versions. Historical PDF informs layout; final UI requirements resolve outdated behavior. Prototype values are not performance targets.

## Implementation sequence

Small-world validation -> generator/truth diagnostics -> hand-checked features -> baseline end-to-end -> full training/comparison -> difficulty calibration and gate dry run on training worlds -> validation selection -> untouched final test -> analyst rehearsal. Local first, cloud optional.

This is not an implemented generator, model, API or production UI. Select and lock exact compatible runtime versions at implementation bootstrap. Consolidation numeric defaults may change only with a dated development record before validation generation, never in response to sealed tests.
