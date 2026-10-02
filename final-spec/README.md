# ARAI - portable development specification

Version **1.2** - Consolidated 2026-09-26, amended 2026-10-02 - **Implementation baseline**

Each component has its own specification and acceptance criteria. This folder is the authoritative development package; no previous version, original laptop path or sibling archive is required.

The user requested the final agreed component specs after reviewing v0.3.1 and authorized this work. This package carries forward the recorded v0.3 decisions and reviewed corrections, plus API/UI details now that the initial wireframe is supplied. [Decision provenance](DECISIONS.md) distinguishes consolidation defaults from historical decisions. No new historical signature or measured implementation success is asserted.

Amendment 1.1 (2026-10-02) records the changes agreed in the user's review of version 1.0: ring purchases and graded style-targeting truth, linked-claim style evidence, calibrated and disclosed difficulty, report-only reference rankings, the rule-versus-model comparison in the API and UI, a gate dry run, integer wardrobing points and a lower quality threshold. [Decision provenance](DECISIONS.md) lists each change, what it supersedes and which values are still unmeasured engineering defaults. Components 04, 14 and 15 are unchanged from 1.0. The seven operational tables and manifest schema_version stay 1.0.

Amendment 1.2 (2026-10-02) follows the first generator run and the exploration of the development worlds: longer tenures for established personas, ring campaigns that start at ring formation, three scope clarifications, the confirmed style-targeting threshold and the first evidence in the acceptance register. See the amendment 1.2 section of the decision provenance.

## Start on any system

1. Copy/extract the **whole final-spec folder**.
2. Open [the clickable wireframe](wireframe/index.html) in a browser. No install, server or Internet required.
3. Read components below and implement dependencies first.
4. From this folder run: python tools/verify_package.py (Python3.10+, standard library only).
5. Track actual implementation evidence in [acceptance-register.csv](acceptance-register.csv). All runtime ACs start NOT_RUN.

Production architecture: Python/FastAPI + React/Vite + PostgreSQL, Parquet artifacts and offline model fitting. Standalone HTML is for portable wireframe review, not a replacement for React/Vite.

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
