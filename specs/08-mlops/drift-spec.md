# Drift specification and applicability

OPS-006. DRAFT. HLD ?10 explicitly places automated drift monitoring in production, outside the current MVP. The meaningful MVP obligation is to retain comparable run distributions and provenance in monitoring-spec.md; no service or automatic retraining trigger is added.

Feature drift: compare approved numeric/categorical summaries only across compatible schema, observation/maturity policy and feature versions. Prediction drift: compare raw component/blended scores and graph health, not fixed percentile tier proportions alone. Different batch composition can legitimately alter ranks; do not claim rank changes prove model deterioration.

Concept/performance drift requires delayed independently adjudicated outcomes and stable cohort windows. Those labels do not exist; planted labels across seeds do not establish concept drift. Reviewer actions are selected observations, not ground truth.

Future metric choices (for example distribution-distance measures), baseline window, sample-size gates, statistical tests, thresholds, alert ownership and retraining approval all remain TBD Q-020. No arbitrary PSI/KS threshold is introduced. Verification now: stored raw distributions and version references; future alert tests only after scope approval.
