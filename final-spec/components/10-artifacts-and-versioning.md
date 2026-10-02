# Artifacts, reproducibility and baseline bundle

Version 1.6 (amended 2026-10-02) | Implementation baseline | Component ART

## Requirements and boundary

Bundle includes estimator/preprocessing, ordered feature schema, category return fallbacks, sorted score reference, adapter, full params, training/code/config/lock hashes and cutoff. Separate immutable selection/test reports reference model hash; do not mutate fitted artifact or create circular hashes.

Use skops only after compatibility check in pinned environment. JSON/Parquet for metadata/reference. Explicit allow-list of serialized types, as an exact set of type names and never a name prefix (numpy and scikit-learn both contain callables that execute code); locally produced verified hashes only. Hashes give integrity, not authenticity: the artifact root must be writable only by the operator. API cannot upload model binaries. Reject signature/type/schema/library mismatch before use.

Baseline bundle is trained-statistics-only, before comparison, no candidate dependency: category fallbacks, sorted eligible training raw_return_rate. Score=raw_return_rate; reference percentile=100*(count_less+.5*count_equal)/reference_count. Supervised raw adapter decision_function; IF negative score_samples. Percentile not probability; label baseline score as Return-rate reference percentile. Every run also ranks eligible customers by raw_return_rate so model and baseline selections can be compared (component 11). Rulebook percentiles and volume-only coefficients live in a separate offline evaluation-reference artifact that serving never loads.

Validate new immutable directory then atomic active pointer update. Jobs bind dataset/model at submission, unaffected by promotion/restart. No fit/fit_transform in inference. Corrupt active model fails readiness, not silent fallback. Missing both model/baseline gives409; explicit rejected model gives409. No prior selection means baseline only/selection not completed, not gate FAIL.

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

Acceptance status: **NOT_RUN**. Record executed results and artifact hashes; prose requirements are not implementation evidence.
