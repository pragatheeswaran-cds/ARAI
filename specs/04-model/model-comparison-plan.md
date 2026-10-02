# Supervised and unsupervised model comparison

Status: comparison direction, overall-risk output and frozen-artifact inference approved by the user on 2026-09-25 (option C, Q14 and Q15). Candidate families, exact action/window targets and thresholds remain to be specified. No models have been trained or selected by this document.

## Approved scope

Compare supervised and unsupervised candidates before selecting a model for the customer return-abuse detection demonstration. Isolation Forest is a reference candidate, not mandatory. The previous rules/forest/graph design remains a reference system comparison if implemented; it does not constrain the chosen algorithm. Neither approach may define abuse solely from high return volume.

Produce overall customer abuse risk with separate supporting evidence signals, not trained predictions for each abuse type in the first version. Train and select during development; publish a frozen model and preprocessing bundle for inference. Retraining is a separate explicit operation, never an implicit upload step.

This changes the prior specifications that allowed only Isolation Forest/config variants and prohibited all training-label use. Training labels are now permitted for supervised development data only. Hidden evaluation labels remain unavailable to either candidate during fitting, preprocessing or scoring.

## Data boundaries

- Generate operational events and independent, explicit simulated abusive actions, plus legitimate heavy returners, defective-product buyers and benign shared households.
- Derive operational features without reading private intent, defect truth, persona, ring membership or future outcomes.
- Supervised training receives the approved training features and corresponding target labels through a dedicated training path.
- Unsupervised fitting receives only permitted features. Labels may inform declared development-set model selection but are not fitting inputs.
- Use the same permitted evidence universe and held-out customer evaluation population for both approaches. Record any candidate-specific feature differences.
- Separate training, validation/selection and final test roles. Preserve complete synthetic worlds and identity groups when splitting; the exact seeds and protocol remain unresolved.
- Use validation results for model selection; access final test labels only after candidates, transforms, thresholds and selected model are frozen. Do not tune on final results.

## Proposed comparison procedure

Q16 approved selection direction: primary investigation yield is precision at the top 5% of eligible customers, with 1% and 10% sensitivity checks. Report recall and each legitimate segment's false-positive count/rate alongside it. This replaces the historical fixed k=625 primary budget. Budget fractions are workload choices, not abuse prevalence. Numeric acceptance and segment limits, tie handling and rounding remain pending.

Q17 approved relative acceptance gate: at the primary budget, a candidate must have strictly greater precision than the raw-return-rate baseline and no greater false-positive rate in each of the legitimate-heavy-returner, defective-product-buyer and benign-household segments. Rank only passing candidates by the agreed selection metric. If none pass, report no acceptable model. Select on validation data and freeze before final testing; a final-test failure is a failed result, not permission to select a replacement on test data. The aggregation and uncertainty protocol must be specified before evaluation. No absolute accuracy promise or additional numeric improvement margin has been approved.

1. Freeze operational features, target definitions, split protocol and candidate configurations.
2. Train a bounded set of supervised and unsupervised candidates.
3. Compare standalone model rankings on identical validation cases and review budgets.
4. Separately assess the existing rules/graph combination. Do not attribute a full system's advantage to its ML model alone.
5. Report overall precision/recall at equal review capacity, per-abuse-type recovery and false-positive counts/rates for each legitimate segment.
6. Include raw-return-rate ranking as a simple baseline. Compare ambiguous, low-history and mixed product/customer cases.
7. Select using a declared metric and legitimate-segment constraints; record rejected candidates and reasons. Numeric thresholds are pending.
8. Freeze the selected artifact and evaluate once under the sealed test protocol. Report failure if neither candidate meets the agreed criteria.

High synthetic accuracy may result from generator shortcuts. Evaluate variation across worlds and overlapping behaviours; do not claim real-world validation. Candidate-specific metrics must respect score semantics: anomaly scores and percentile ranks are not fraud probabilities.

## Unresolved product/model decisions

- Exact overall-risk score semantics and evidence fields; overall risk with separate signals is approved. Per-type recall is not equivalent to predicting a type.
- Target window and meaning: defined abusive actions within the observation window, not a permanent customer identity or a volume-only persona label.
- Supervised and unsupervised algorithm families; precise binary abuse-action target and handling of overlapping behaviours in private evaluation metadata.
- Frozen artifact schema and separation of fitted preprocessing from batch-derived operational features. Q15 rules out per-upload model or preprocessing refitting.
- Whether rules/graph evidence form shared inputs, post-model logic or separately reported system baselines.
- Exact seed roles, aggregation/uncertainty protocol and final tie-breaking/rounding policy. Review budgets and relative acceptance/benign-segment gates are approved in Q16/Q17; no absolute performance floor or improvement margin is assumed.

## Existing specifications affected

Training, selection, evaluation, artifact, inference and leakage contracts must follow this approved comparison direction when their detailed revisions are settled. Older Isolation-Forest-only fields and the `serial_returner` positive population list are historical drafts, not authorization to retain volume-only abuse labels or exclude the approved supervised comparison.
