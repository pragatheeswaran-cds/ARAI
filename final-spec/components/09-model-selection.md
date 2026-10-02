# Model selection and promotion gate

Version 1.0 | Implementation baseline | Component SEL

## Requirements and boundary

At5%, candidate must strictly exceed raw-return-rate baseline precision and have no higher FPR in each of three benign groups, with valid coverage. Select by descending precision, then smallest worst-group FPR, then registered ordinal. Report every rejection. No pass -> no_selected_model.

Freeze selection/training bundle before test. Evaluate chosen model once on five untouched worlds with same gate and sensitivity budgets. Test failure blocks promotion; do not switch to runner-up using test results. New model/config/generator work prompted by test requires new experiment and untouched test worlds; retain failures. Selected model is never refit on validation.

Test segment1-199 is a reported coverage limitation; zero prevents verified pass. Synthetic pass is not production readiness. Baseline fallback is not a passing trained model. A valid existing active model is not replaced automatically after another experiment fails. Presentation simplification cannot weaken the gate.

## Inputs, outputs and dependencies

- Inputs: Validation metrics and frozen bundles; later sealed test.
- Outputs: Selection/rejection record and promotion eligibility.
- Dependencies: Evaluation.

## Acceptance criteria

| ID | Pass condition and required evidence |
|---|---|
| SEL-AC-01 | Higher precision/worse household FPR fails; equal precision fails. |
| SEL-AC-02 | Passing ties follow worst FPR then ordinal. |
| SEL-AC-03 | No winner produces fallback without fabricated promotion. |
| SEL-AC-04 | Selection record precedes test; test failure prevents runner-up switching. |
| SEL-AC-05 | Test-informed iteration retains failure and uses untouched test worlds. |

Acceptance status: **NOT_RUN**. Record executed results and artifact hashes; prose requirements are not implementation evidence.
