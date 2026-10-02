# Training, evaluation and model selection

## Candidate comparison

[experiment.yaml](experiment.yaml) defines five bounded candidates: logistic regression, two histogram gradient-boosting configurations, and two Isolation Forest configurations. These are engineering selections for a modest tabular-data comparison, not a claim of optimal algorithms. Isolation Forest remains replaceable by a versioned development decision; it is not mandated by the business scope. No automated unbounded hyperparameter search.

Each candidate uses the same operational feature allow-list and eligible customer population. Supervised fits see training targets; unsupervised fits see the mixed unlabelled training population, not a secretly filtered benign-only dataset. Imputation, scaling, category fallbacks and score normalization are fitted on training worlds only. No validation/test-world model refitting. Complete world-level grouping prevents linked customers from crossing splits.

World-derived SKU and identity statistics are calculated within each available snapshot using the deterministic feature contract, without labels. This is a whole-population input requirement, not a fitted transformation. Frozen fallback statistics are learned only from training worlds. Feature code is identical during training and inference.

Training output is one fitted bundle per candidate plus candidate ID, fully expanded estimator parameters, feature schema/hash, training-world hashes, fit durations, lockfile/code hashes and errors/warnings. A convergence failure or nonfinite output rejects the candidate; do not silently increase its iteration budget after final-test inspection.

## Split and selection protocol

Use the configured ten training worlds, five validation worlds and five final-test worlds. World IDs namespace every customer/relationship. Existing reference seed20250901 is development evidence, never sealed. The demo world is separate and may be curated; it never supplies selection metrics.

For every world and fraction f, N=eligible customers and k=ceil(f*N), capped at N. N=0 invalidates evaluation. Rank descending raw candidate score; break ties by ascending SHA-256("review-tie-v02|world_id|customer_id"). Apply the same tie rule to raw-return-rate baseline. Do not round displayed scores before ranking. Report realized k/N when rounding changes the fraction.

Primary validation results pool TP/FP/FN/TN across worlds after selecting k separately in each world. precision=sumTP/sumk; recall=sumTP/sumpositive; each benign FPR=sumselected_benign_segment/sumbenign_segment. Per-world results and denominators accompany pooled values. Abusive-type recall uses overlapping private action tags; benign groups use y=0. Zero segment denominator makes the gate unverifiable and fails validation coverage rather than returning0.

Gate at5%: precision strictly exceeds baseline and each benign group's FPR is <= baseline. Select passing candidate by descending precision, then smallest worst benign-group FPR, then registered candidate ordinal. Report every rejection. If none passes, emit no_selected_model; the UI can show a failed experiment but not a production-ready winner.

Freeze the selected existing training bundle without refitting on validation data. Run one final evaluation on held-out worlds under the same gate and report sensitivity at1%/10%. A final-test gate failure prevents promotion; do not switch to a runner-up using those test results. Further development requires a new version and untouched test worlds; retain failed results and explain why a new experiment exists.

Report percentile bootstrap intervals from1000 resamples of whole worlds (not independent customer rows), plus all five individual world results. Five worlds give limited uncertainty evidence. The approved gate uses point estimates; do not present it as a statistically significant improvement. Raw accuracy is supplementary; report PR-AUC as a diagnostic if implemented, never substitute it for the approved gate.

## Overall risk and type evidence

Raw score orientation must be higher=suspicious. Supervised candidates use decision_function; Isolation Forest uses -score_samples. Register score adapter by candidate type, not by guessing score ranges. Risk display=100*training-score empirical CDF with midrank treatment of ties, clamped to[0,100]. Store the sorted training reference in the bundle. It is a reference percentile, not fraud probability. Batch rank and selected_for_review are separate values. A new batch does not refit the CDF.

Supporting signals explain observed return, claim, SKU and relationship patterns; they do not claim the selected classifier predicts the specific abuse type. Evaluate per-action recovery independently. Wardrobing indicator is displayed separately; no forced score blend with it.

## Robustness and valid claims

Before sealed testing, evaluate development stress worlds: ordinary return propensity +/-20%, defect incidence doubled, household sharing doubled, and action rates halved/doubled, with valid probability clipping. Vary one mechanism at a time and preserve the core action definitions. Record performance degradation; do not declare same-generator seed changes to be a real-world generalization test.

Required shortcut probes: shuffle opaque IDs without changing equality; remove persona/status fields; test identical claim codes in genuine and deceptive cases; verify target label never used in features; inspect benign/abusive distributions for implausible disjoint support. Publish generator assumptions alongside metrics.

## Technical references

- scikit-learn documents [Isolation Forest scores](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html); lower score_samples values are more anomalous, so our adapter reverses the sign.
- The [histogram gradient-boosting classifier](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html) provides classification scores and the candidate controls used here.
- The [common pitfalls guide](https://scikit-learn.org/stable/common_pitfalls.html) supports fitting preprocessing on training data and applying the same fitted transformations to later data. Our world/snapshot protocol is an additional project-specific design.

Sources checked2026-09-25. They support API and preprocessing behaviour, not our synthetic distributions, chosen hyperparameters or performance expectations.
