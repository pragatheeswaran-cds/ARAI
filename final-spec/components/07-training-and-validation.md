# Training dataset, model fitting and validation

Version 3.0 (amended 2026-10-05) | Implementation baseline | Component TRAIN

## Requirements and boundary

World seeds of experiment 3 (EXP-20261005-03, generator-config 3.0): train4101-4110, validation4201-4205, test4301-4305, demo4401, stress4501-4507; fixtures 2001-2003 are regenerated in memory by the tests. Experiment 2 (EXP-20261005-02) used train3101-3110, validation3201-3205, test3301-3305, demo3401 and stress2501-2507; all are retired with those of the first experiment. The seeds of the first experiment (train2101-2110, validation2201-2205, test2301-2305, demo2401) are retired: their worlds stay on disk as the record of EXP-20261002-01 and are never generated, scored or reused for experiment 2. Fixtures2001-2003 have1000 customers; stress2501-2507 are ordinary propensity x1.2/x.8, defect x2, household share x2, per-account action rate x.5/x2, all-1 actionable multipliers. Sets disjoint. Scalar stress probabilities clip to valid range; invalid joint overlay fails. Demo normally generated plus documented injected cases; never selection/scorecard input.

Candidates share eligible rows and ordered features. Labels join supervised assembly only after features freeze. Isolation Forest uses mixed unlabeled training, not truth-filtered benign rows. All learned medians/scalers/fallbacks fit training only.

Exact params in experiment.yaml, six candidates: logistic C1/lbfgs/max_iter1000; four HGB learning_rate .05/max_iter200/min_samples_leaf50/l2=1/leaves15/no early stop, one unweighted and three with honest_group_weights 4, 6 and 8 on repeat_genuine_claimant; one IF300 trees/max_samples256/contamination auto/max_features1/no bootstrap/one job. No unbounded search. A weighted candidate is fitted with that weight on every honest training customer of the named gate segment and weight 1 on everyone else, fold-locally for out-of-fold scores (AM-48). The segment flag is private truth, joined for training exactly as the label is; it is never a feature and nothing of the kind is read when a snapshot is scored. The weights were chosen on the training worlds of the first experiment and are registered here before any world of experiment 2 exists.

Supervised reference uses 5 folds grouped by world (two held out per fold). Each fold fits its complete preprocessing on eight worlds and scores two. The category fallback is fitted once on all ten training worlds, and training fails if any training world uses it, so no held-out row is ever scored with a statistic that saw its world (AM-43; this supersedes the fold-local fallback wording in experiment.yaml until that contract is next revised). Pool sorted OOF scores; final estimator fits all10 once. Fold models excluded from serving bundle. IF reference uses in-sample training scores. OOF display reference is approximate for final estimator, not calibrated or selection input.

Report-only references are fitted beside the candidates and are never candidates: volume_only_logreg (the logreg_c1 settings with only mature_sale_lines and log_order_count as inputs) and analyst_rulebook (component 08). Both take coefficients or thresholds from training worlds only and use the same fold-local fitting for out-of-fold scores. Out-of-fold training scores also feed difficulty calibration (component 05) and the gate dry run (component 09).

Training and the gate dry run refuse to run once a validation or test world exists. Training records the hash of the scoring code that fitted the models, the training cutoff and the 10th, 50th and 90th percentile of every feature over eligible training rows. Freeze expanded parameters/dependency versions. Convergence/nonfinite output rejects candidate. Training, selection/promotion offline only; no inference refitting. Selected artifact remains original training fit, never refit on validation.

## Inputs, outputs and dependencies

- Inputs: Frozen features, training labels, experiment.yaml.
- Outputs: One bundle and fitting report per registered candidate.
- Dependencies: Generation, features and experiment contract.

## Acceptance criteria

| ID | Pass condition and required evidence |
|---|---|
| TRAIN-AC-01 | Seed sets disjoint; linked customers never cross worlds; scorecard rejects demo/fixture IDs. |
| TRAIN-AC-02 | Held-out data fit no learned transform; training fails if a training world uses the all-worlds category fallback; assembly audits world IDs and joins labels only with the truth written with the world. |
| TRAIN-AC-03 | Each OOF row scored by a pipeline excluding its world; serving contains one final estimator. |
| TRAIN-AC-04 | Every candidate record includes expanded params, training weights, hashes, durations, warnings and rejections. |
| TRAIN-AC-05 | Unsupervised fit cannot read customer labels. |
| TRAIN-AC-06 | A weighted candidate weights exactly the honest members of its gate segment, changes the fitted model, adds no model input, and refuses a training frame without the segment flag or with the flag among its features. |

Acceptance status is recorded per criterion in acceptance-register.csv (status, evidence, date, reviewer). Prose requirements are not implementation evidence.
