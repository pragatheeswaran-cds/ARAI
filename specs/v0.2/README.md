# Return-abuse ML pipeline - implementation specification v0.2

Business scope confirmed by the user on 2026-09-25: "we have same understanding now". [Approved scope](../../docs/agreed-project-scope.md). This package translates that scope into concrete engineering choices; those choices are documented defaults, not fabricated user decisions. No dataset, fitted model or application is certified by this package.

## Read in order

1. [Data generation and contracts](data.md)
2. [Feature engineering](features.md)
3. [Training, evaluation and selection](modeling.md)
4. [Artifact, inference, API and UI](serving.md)
5. [Delivery and acceptance](delivery.md)
6. [Machine-readable experiment defaults](experiment.yaml)
7. [Existing generator reuse and required repairs](existing-generator-disposition.md)

Structural checks and their limits are recorded in [verification](verification.md).

## Authority and migration

Confirmed business decisions govern this package. For the specified ML pipeline, these v0.2 engineering contracts supersede contradictory v0.1 draft fields: fixed 625-review budgets, volume-only fraud labels, mandated Isolation Forest, per-upload fitting, old apparel categories/currency and universal prohibition of training labels. Existing HLD/LLD/source archives remain historical evidence. Do not combine incompatible defaults from both versions.

The seven operational tables remain the integration boundary. v0.2 adds explicit line request time and availability semantics, separates generator profiles/private truth from inputs, and defines a frozen model bundle. The existing team CSVs require adapters; they are not asserted to be ready-to-train data. Missing generator modules are an evidence gap: either recover them or implement the documented generation contract, never claim the old outputs were reproduced without doing so.

## Scope boundary

Primary: customer investigations, linked SKU context and image-free wardrobing evidence. No inspection-routing expansion, live point-of-return decisions or automated customer penalties. The UI offers evidence and analyst notes, not confirmed-fraud adjudication. A separately displayed wardrobing indicator is not added mechanically to the risk score; a selected model may learn from permitted timing/product features.

## Defaults versus unknowns

This package chooses dates, seeds, candidate configurations, rounding, formulas, local persistence and a bounded API for implementation. Performance, generator fidelity, library compatibility and timings must be measured. Exact dependency versions are locked after an environment compatibility check and before producing accepted artifacts. No arbitrary metric is reported as achieved.

Historic advanced two-pass score blending is not silently mandatory: v0.2 selects a frozen model using context-aware features. The original multi-component/two-pass design can be evaluated as a separately named system candidate if implemented with frozen fitted state; it cannot change the published candidate set after final-test access. The main interface and evaluation must identify whether the ranked output is a standalone model or a combined system.
