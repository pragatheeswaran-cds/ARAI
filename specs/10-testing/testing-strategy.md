# Testing strategy

TEST-STRATEGY-001. DRAFT. Sources: LLD ?9 and 48 source cases in lld-test-catalog.md. No application test was implemented or run by this specification task. Existing synthdata/validate.py is evidence of synthetic checks only and requires the missing customer_master in its current version.

Levels: unit arithmetic/decision boundaries; data and artifact contract checks; generated/upload and two-pass integration; leakage/privacy/reproducibility properties; ML evaluation and deterministic selection; API contract and failure behaviour; UI state/accessibility; complete offline end-to-end rehearsal. The adjacent seven test catalogs define IDs, fixtures and expected assertions.

Use independent hand-computed oracles, never capture implementation outputs as correctness targets. Exact rational formulas can be checked before a model exists; tolerances for floating-point comparisons must be pinned in test fixtures (proposed numerical tolerance 1e-6 for shown arithmetic only, A-010). Rank/decision outputs use exact equality. Business tolerances and latency limits are never inferred from numeric comparison tolerance.

All module source tests must be reviewed. M09 benign-heavy mean <= normal is an empirical desired property, not a mathematical guarantee. M10 edge contribution does not by itself create an edge. M11 tier counterfactual needs a reference population. M12 fixtures need n_sales>=20 and do not define customer suppression. M13 positive percentile delta for every ring member and household tolerance are not universally guaranteed. M16 graph ablation may show no significant gain and must report that honestly. These ambiguities remain in Q-005/Q-006/Q-009/Q-012/Q-016.

Future cadence per LLD: approved unit cases each commit; data/artifact/privacy contracts every run; full reproducibility integration at gates; dev-seed evaluations during tuning; sealed evaluation exactly once after freeze; adversarial and offline rehearsals before demo. No CI infrastructure is introduced here.

Release cannot pass by skipping blocked assertions. Publish passed/failed/not-run/blocked separately, with evidence and owner. Required unknown definitions prevent freezing the affected slice. Sealed test outcomes never tune thresholds. Specification validation performed in this task is documented separately in ../00-governance/validation-report.md.
