# Testing, traceability and delivery

Version 1.0 | Implementation baseline | Component TEST

## Requirements and boundary

acceptance-register.csv contains stable AC IDs initially NOT_RUN. Update only with actual command/result/artifact/date/reviewer. Package syntax checks are not runtime acceptance.

Slices:1 portable bootstrap/catalog adapter/schema validation/1000-customer fixtures;2 generator/private diagnostics/feature hand calculations;3 baseline and thin inference/API/UI;4 full training and five candidates;5 validation selection then untouched test;6 rehearsal and optional VM. No full generation before small-world correctness. UI fixtures never enter scorecards.

Retain reuse requirements: source/catalog provenance, real identities, feasible festive dates, observed gaps, correct enrichment, executable validation, independent evaluation, historical chronology, seed/format parity and honest reconstruction. Their ACs live in GEN/VAL/EDA/TRAIN.

Integration scenarios: valid/malformed/private/missing upload, partial/consolidated returns, cutoff boundaries, no graph vs graph failure, no eligible, no selected model, model mismatch, idempotency conflict, crash/restart, notes cross-run, test failure, low-support/no-return style, UI/API empty/loading/error and baseline evidence.

Weekly checkpoints; by2026-10-09 check data acceptance/runtime estimates. Simplify presentation first, preserve four capabilities/21 worlds unless explicit new scope decision. Reserve final week before selected November date for evaluation freeze/integration/rehearsal.

Release hashes/spec/config/locks/code, manifests, validation/EDA, features, every candidate/rejection/final test, model/baseline hash,target runtime,walkthrough,limitations. Document injected demo IDs; exclude from scorecards. Test-informed changes require new experiment/untouched worlds. Output-affecting fixes version artifacts and rerun affected ACs.

## Inputs, outputs and dependencies

- Inputs: Component acceptance criteria and immutable fixtures.
- Outputs: Executed acceptance register and release evidence.
- Dependencies: All components.

## Acceptance criteria

| ID | Pass condition and required evidence |
|---|---|
| TEST-AC-01 | Every AC has evidence or explicit NOT_RUN; syntax success never stands in for runtime acceptance. |
| TEST-AC-02 | Small-world gate precedes full generation; selection freezes before test exposure. |
| TEST-AC-03 | Integration cases execute with retained output and no truth leakage. |
| TEST-AC-04 | Target-machine rehearsal has measured runtime and working baseline fallback. |
| TEST-AC-05 | Release includes failures/limitations/hashes and enough reference material for another developer. |

Acceptance status: **NOT_RUN**. Record executed results and artifact hashes; prose requirements are not implementation evidence.
