# Artifacts, reproducibility and baseline bundle

Version 1.8 (amended 2026-10-05) | Implementation baseline | Component ART

## Requirements and boundary

Bundle includes estimator/preprocessing, ordered feature schema, category return fallbacks, sorted score reference, adapter, full params, training/code/config/lock hashes and cutoff. The code hashes are two: the scoring code that fitted the model, as training recorded it, and the code that built the bundle. A hash only says that a file changed, so publication also proves the change is harmless: it recomputes the features of a training world with the current code and compares them, value for value, with the frozen ones; the bundle records that check and the training feature quantiles used by the drift report (component 11). Separate immutable selection/test reports reference model hash; do not mutate fitted artifact or create circular hashes.

Use skops only after compatibility check in pinned environment. JSON/Parquet for metadata/reference. Explicit allow-list of serialized types, as an exact set of type names and never a name prefix (numpy and scikit-learn both contain callables that execute code); locally produced verified hashes only. Hashes give integrity, not authenticity: the artifact root must be writable only by the operator. API cannot upload model binaries. Reject signature/type/schema/library mismatch before use.

Baseline bundle is trained-statistics-only, before comparison, no candidate dependency: category fallbacks, sorted eligible training raw_return_rate. Score=raw_return_rate; reference percentile=100*(count_less+.5*count_equal)/reference_count. Supervised raw adapter decision_function; IF negative score_samples. Percentile not probability; label baseline score as Return-rate reference percentile. Every run also ranks eligible customers by raw_return_rate so model and baseline selections can be compared (component 11). Rulebook percentiles and volume-only coefficients live in a separate offline evaluation-reference artifact that serving never loads.

Validate new immutable directory, write the report, then atomic active pointer update as the last step: a publication that fails leaves serving untouched. Jobs bind dataset/model at submission, unaffected by promotion/restart. No fit/fit_transform in inference. Corrupt active model fails readiness, not silent fallback. Missing both model/baseline gives409; explicit rejected model gives409. No prior selection means baseline only/selection not completed, not gate FAIL.

Record canonical logical and physical file hashes. Compression bytes need not match unpinned libraries. Exact runtime locks required for reproduction.

## Inputs, outputs and dependencies

- Inputs: Training pipeline or baseline training statistics.
- Outputs: Immutable content-addressed bundle and activation record.
- Dependencies: Features/training/selection.

## Acceptance criteria

| ID | Pass condition and required evidence |
|---|---|
| ART-AC-01 | Save/load score tolerance1e-10 absolute/1e-8 relative and exact ranked selection pass fixed fixtures. |
| ART-AC-02 | Unknown type/hash/schema/library mismatch fails before use. |
| ART-AC-03 | Run preserves bound model through promotion/restart. |
| ART-AC-04 | Baseline works without any candidate estimator; inference fits are blocked. |
| ART-AC-05 | Hashes have no circular metadata; prior bundles remain immutable. |
| ART-AC-06 | Publication fails, leaving the active pointer and the published report unchanged, when the feature code no longer reproduces the frozen training features or the report cannot be built; a published bundle carries the training-time code hash, the cutoff and the feature check. |

Acceptance status is recorded per criterion in acceptance-register.csv (status, evidence, date, reviewer). Prose requirements are not implementation evidence.
