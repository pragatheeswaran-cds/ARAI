# Training dataset, model fitting and validation

Version 1.1 (amended 2026-10-02) | Implementation baseline | Component TRAIN

## Requirements and boundary

World seeds: train2101-2110, validation2201-2205, test2301-2305, demo2401. Fixtures2001-2003 have1000 customers; stress2501-2507 are ordinary propensity x1.2/x.8, defect x2, household share x2, per-account action rate x.5/x2, all-1 actionable multipliers. Sets disjoint. Scalar stress probabilities clip to valid range; invalid joint overlay fails. Demo normally generated plus documented injected cases; never selection/scorecard input.

Candidates share eligible rows and ordered features. Labels join supervised assembly only after features freeze. Isolation Forest uses mixed unlabeled training, not truth-filtered benign rows. All learned medians/scalers/fallbacks fit training only.

Exact params in experiment.yaml: logistic C1/lbfgs/max_iter1000; two HGB learning_rate .05/max_iter200/min_samples_leaf50/l2=1/leaves15 or31/no early stop; two IF300 trees/max_samples256 or1024/contamination auto/max_features1/no bootstrap/one job. No unbounded search.

Supervised reference uses 5 folds grouped by world (two held out per fold). Each fold fits complete preprocessing/fallbacks on eight worlds, scores two. Pool sorted OOF scores; final estimator fits all10 once. Fold models excluded from serving bundle. IF reference uses in-sample training scores. OOF display reference is approximate for final estimator, not calibrated or selection input.

Report-only references are fitted beside the candidates and are never candidates: volume_only_logreg (the logreg_c1 settings with only mature_sale_lines and log_order_count as inputs) and analyst_rulebook (component 08). Both take coefficients or thresholds from training worlds only and use the same fold-local fitting for out-of-fold scores. Out-of-fold training scores also feed difficulty calibration (component 05) and the gate dry run (component 09).

Freeze expanded parameters/dependency versions. Convergence/nonfinite output rejects candidate. Training, selection/promotion offline only; no inference refitting. Selected artifact remains original training fit, never refit on validation.

## Inputs, outputs and dependencies

- Inputs: Frozen features, training labels, experiment.yaml.
- Outputs: Five candidate bundles and fitting reports.
- Dependencies: Generation, features and experiment contract.

## Acceptance criteria

| ID | Pass condition and required evidence |
|---|---|
| TRAIN-AC-01 | Seed sets disjoint; linked customers never cross worlds; scorecard rejects demo/fixture IDs. |
| TRAIN-AC-02 | Held-out data fit no learned transform or fallback; assembly audits world IDs. |
| TRAIN-AC-03 | Each OOF row scored by a pipeline excluding its world; serving contains one final estimator. |
| TRAIN-AC-04 | Five candidate records include expanded params/hashes/durations/warnings/rejections. |
| TRAIN-AC-05 | Unsupervised fit cannot read customer labels. |

Acceptance status: **NOT_RUN**. Record executed results and artifact hashes; prose requirements are not implementation evidence.
