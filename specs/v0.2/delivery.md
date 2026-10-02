# Delivery slices and acceptance

Roles below are suggested ownership for the three-person team, not assignments already communicated to anyone. Astra can assist every slice; acceptance depends on executable evidence, not generated code volume.

| Slice | Suggested owner | Concrete deliverable | Exit evidence |
|---|---|---|---|
|1 Data contract | Data lead | Catalog/profile adapters, action definitions, generator, private truth separation | Reproducible small world; all structural checks pass; required scenario matrix present |
|2 Features | ML lead with data lead | Frozen feature schema, deterministic snapshot builder, matched unit/line counts | Hand-computed quantity/timing/SKU tests; no truth reads |
|3 Training and selection | ML lead | Registered five-candidate experiment, split artifacts, comparison report | No held-out fitting; candidate gates enforced; no-winner handled |
|4 Artifact and inference | App lead with ML lead | Immutable bundle loader and batch scorer | Save/load parity; zero fit calls; model hash stable during a run |
|5 API and UI | App lead | Job API, customer/SKU views, evaluation page | End-to-end valid/error cases and analyst walkthrough |
|6 Integration and demo | All three | Untouched final evaluation, documented limitations, repeatable demo | Test results retained; scorecard honest; rehearsal completes on target machine |

Build a small deterministic world first to verify the entire pipeline; then run full worlds. UI fixtures may be used before training completes but must be labelled fixtures and excluded from scorecards. Do not generate all full-scale data before validating generation semantics.

## Required meaningful checks

The [generator reuse requirements](existing-generator-disposition.md) add REUSE-001 through REUSE-012 to slice1 acceptance. Reasons and verified reproductions are in the [generator assessment](../../docs/generator-reuse-assessment.md). Recover/reconstruct only missing components; the existing SKU catalog is retained.

### Data and features

- Same pinned seed/config produces logically identical tables; different seeds vary while preserving contract.
- Customer signup/SKU launch precede orders; snapshot visibility never includes future fields.
- Partial return: purchase3 units, request1 -> volume numerator1, denominator3; additional request cannot push cumulative quantity above3.
- Consolidated header with two different line requested_at values yields independently correct latency.
- Open window: recent delivered/unreturned sale does not enter mature return-rate denominator.
- SKU peers exclude own quantity before shrinkage; no peers uses frozen training fallback. Duplicated return joins cannot inflate sales.
- Benign household sharing changes relationship evidence, not truth labels. Defect exposure does not erase independent action truth.
- Replacing any private label or propensity file while holding operational data fixed leaves features/inference unchanged.

### Training and evaluation

- Models and fitted transforms see only training-world IDs; supervised targets cannot reach unsupervised fit.
- Identical feature order and fixed score orientation for all candidates; missing columns fail instead of silently reordering.
- k=ceil(.05*N) implemented once for candidates and baseline; ties use the same deterministic hash rule.
- Fixtures prove a candidate with higher precision but worse household FPR is rejected.
- Fixtures prove no passing candidate produces no_selected_model, not a default artifact.
- Final test cannot change selected candidate/config. Model selection record precedes test result publication.
- Empty legitimate-segment denominator is unverifiable, not0% FPR. Overlapping benign groups do not inflate aggregate totals.
- Insufficient-history abuse is reported separately so eligible-only recall is not misrepresented.

### Serving and UI

- Saved/reloaded artifact preserves raw scores within declared floating-point tolerance and exactly preserves ranked selection on a fixed fixture.
- Instrument fit/fit_transform to fail if called by inference; incoming data still score using the frozen pipeline.
- Wrong hash/schema/library compatibility fails readiness; a job uses its originally bound model after promotion.
- Duplicate request returns the same job; conflicting idempotency payload returns409.
- Failure/crash cannot expose a succeeded run with partial predictions. Restart preserves audit records.
- Customer page never displays private synthetic truth. Evaluation page clearly labels truth and synthetic limitations.
- SKU issue never automatically clears unrelated customer evidence. No API can suspend an account or issue a refund.

## Evidence package

Publish generator/config/dependency hashes, dataset manifests, validation reports, selected feature schema, all candidate settings/results, baseline and group scorecards, chosen model hash, final-test gate, machine/runtime measurements and known failures. No fabricated run numbers. Source document claims without reproducible outputs remain historical, not verified.

## Dates and milestones

Business target is November1-14,2026. Plan slices1-2 first, then a thin training-to-UI integration before broad tuning. Reserve the final week before the chosen demo date for frozen evaluation, integration fixes and rehearsal. Exact work dates depend on team availability; no person-hour commitment has been inferred from headcount.

## Specification verification vs implementation verification

Parsing YAML and checking cross-document links validates this package's structure only. The acceptance checks above must be executed once implementations exist. Missing original generator source, dependency lock, actual run durations and measured model performance are unresolved implementation evidence, not reasons to invent successful results or restart business questioning.
