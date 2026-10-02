# Traceability matrix

All tests below are **planned specification IDs**, not existing executable test files. Paths refer to specs/ unless a source/implementation path is stated. Existing generator/validator do not establish application completion. Source abbreviations resolve via source-inventory.md. Every FR and NFR is individually mapped; feature IDs have individual rows; related cross-cutting rules use explicit ranges whose members are defined in canonical specs.

| Requirement | Source | Specification | Implementation | Test | Status |
|---|---|---|---|---|---|
| FR-001 | HLD ?3 F1 | 03-features/feature-spec.yaml | M04?M06/M08 ? planned, absent | FEATURE-001 / MODEL-002 | Draft; open dependencies |
| FR-002 | HLD ?3 F2 | 04-model/training-spec.yaml | M08/M09 ? planned, absent | MODEL-001 / MODEL-002 | Draft; open dependencies |
| FR-003 | HLD ?3 F3 | 03-features/feature-transformations.md | M10 ? planned, absent | FEATURE-003 | Draft; open dependencies |
| FR-004 | HLD ?3 F4 | 04-model/threshold-policy.yaml | M07/M18 ? planned, absent | FEATURE-002 / UI-002 | Draft; open dependencies |
| FR-005 | HLD ?3 F5 | 04-model/threshold-policy.yaml | M12 ? planned, absent | FEATURE-004 | Draft; open dependencies |
| FR-006 | HLD ?3 F6 | 03-features/feature-transformations.md | M05/M13 ? planned, absent | FEATURE-005 | Draft; open dependencies |
| FR-007 | HLD ?3 F7 | 05-inference/prediction-contract.yaml | M11/M14/M15 ? planned, absent | INF-002 / INF-003 | Draft; open dependencies |
| FR-008 | HLD ?3 F8 | 09-security/security-requirements.md | M15/M17 ? planned, absent | API-003 | Draft; open dependencies |
| FR-009 | HLD ?3 F9 | 06-api/openapi.yaml | M03/M17/M18 ? planned, absent | API-001 / DATA-TEST-001 | Draft; open dependencies |
| FR-010 | HLD ?3 F10 | 04-model/evaluation-spec.yaml | M16 ? planned, absent | MODEL-002 / MODEL-003 | Draft; open dependencies |
| NFR-001 | HLD ?3.1 N1 | 04-model/reproducibility-spec.md | cross-cutting ? planned, absent | E2E-002 | Draft; thresholds/decisions as noted |
| NFR-002 | HLD ?3.1 N2 | 05-inference/prediction-contract.yaml | cross-cutting ? planned, absent | INF-003 | Draft; thresholds/decisions as noted |
| NFR-003 | HLD ?3.1 N3 | 08-mlops/monitoring-spec.md | cross-cutting ? planned, absent | API-004 | Draft; thresholds/decisions as noted |
| NFR-004 | HLD ?3.1 N4 | 09-security/data-privacy.md | cross-cutting ? planned, absent | INF-002 | Draft; thresholds/decisions as noted |
| NFR-005 | HLD ?3.1 N5 | 04-model/threshold-policy.yaml | cross-cutting ? planned, absent | API-003 | Draft; thresholds/decisions as noted |
| NFR-006 | HLD ?3.1 N6 | 06-api/api-requirements.md | cross-cutting ? planned, absent | API-001 | Draft; thresholds/decisions as noted |
| NFR-007 | HLD ?3.1 N7 | 08-mlops/deployment-spec.md | cross-cutting ? planned, absent | E2E-003 | Draft; thresholds/decisions as noted |
| NFR-008 | HLD ?3.1 N8 | 04-model/evaluation-spec.yaml | cross-cutting ? planned, absent | MODEL-003 | Draft; thresholds/decisions as noted |
| FEAT-001 n_orders | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-002 |
| FEAT-002 n_lines | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-002 |
| FEAT-003 n_returns | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-002 |
| FEAT-004 spend | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-002 |
| FEAT-005 tenure_days | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Draft; eligibility Q-002 |
| FEAT-006 raw_rate | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-002 |
| FEAT-007 mu_cat | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-006 |
| FEAT-008 shrunk_rate | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Draft; eligibility Q-002 |
| FEAT-009 p_hat | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-006 |
| FEAT-010 expected_returns | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Draft; eligibility Q-002 |
| FEAT-011 variance | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Draft; eligibility Q-002 |
| FEAT-012 design_effect | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-004 |
| FEAT-013 residual_z | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-004 |
| FEAT-014 refund_ratio | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-004 |
| FEAT-015 median_days_to_return | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-003 |
| FEAT-016 median_days_to_return_z | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-004 |
| FEAT-017 claim_mix | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-004 |
| FEAT-018 device_fanout | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-004 |
| FEAT-019 address_fanout | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-004 |
| FEAT-020 payment_fanout | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-004 |
| FEAT-021 trend_90d | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-004 |
| FEAT-022 bracketing_flag | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-004 |
| FEAT-023 window_ratio | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-003 |
| FEAT-024 wardrobe_score | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-004 |
| FEAT-025 keyword_flags | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-013 |
| FEAT-026 graph_score | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-005 |
| FEAT-027 connectivity | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-016 |
| FEAT-028 damage_mix | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-016 |
| FEAT-029 latency_ratio | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-004 |
| FEAT-030 returner_risk_median | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-006 |
| FEAT-031 no_item_return_share | LLD M04?M12; field sources in feature dictionary | 03-features/feature-spec.yaml | feature/detection modules ? absent | FEATURE-006 plus arithmetic/graph/verdict cases | Blocked Q-016 |
| DATA-001?DATA-003 | LLD ?3/M03; dictionary | 02-data/data-contract.yaml | M03 absent; synthdata/validate.py partial evidence | DATA-TEST-001 / DATA-TEST-004 | Draft; not implemented or verified |
| DATA-004 | Architecture ?6.2; LLD ?4 | 02-data/data-split-spec.yaml | M16 absent | MODEL-003 | Draft; not implemented or verified |
| DATA-005 | Build Steps; current/archived generator | 02-data/synthetic-data-spec.md | synthdata/*.py exists; archive missing master | DATA-TEST-002 / DATA-TEST-003 | Draft; not implemented or verified |
| DQ-001?DQ-020 | LLD ?3.1.1 + explicit review completions | 02-data/data-quality-spec.yaml | M03 absent | DATA-TEST-001 / DATA-TEST-004 | Draft; not implemented or verified |
| CONS-001 / LEAK-001?LEAK-006 | HLD ?7.1/?8; Architecture ?6 | 03-features/leakage-prevention.md | pipeline/detection absent | FEATURE-006 / DATA-TEST-002 / MODEL-003 | Draft; not implemented or verified |
| REPRO-001 / MODEL-TRAIN-001 | HLD N1; LLD M09 | 04-model/training-spec.yaml | M09 absent | MODEL-001 / E2E-002 | Draft; not implemented or verified |
| MODEL-EVAL-001 / MODEL-SELECT-001 | Architecture ?6; LLD M16; gaps Q-009/010 | 04-model/model-selection-spec.yaml | M16 absent | MODEL-002 / MODEL-003 | Draft; not implemented or verified |
| MODEL-ARTIFACT-001 / POLICY-001 | LLD ?3.2/M11/M15 | 04-model/model-artifact-spec.yaml | M09/M11/M15 absent | MODEL-004 / API-003 | Draft; not implemented or verified |
| INF-CONTRACT-001 / INF-PRE-001 / INF-OUT-001 / INF-ERR-001 | HLD ?7/?8; LLD ??3/8 | 05-inference/inference-contract.yaml | pipeline/API absent | INF-001?INF-004 | Draft; not implemented or verified |
| API-REQ-001?API-REQ-006 / API-ERR-001 | LLD ?6; A-003/A-009 completions | 06-api/openapi.yaml | M17 absent | API-001?API-004 | Draft; not implemented or verified |
| UI-REQ-001?UI-REQ-006 / UI-API-001 / UI-AC-001?UI-AC-007 | HLD ?7; Architecture ?8; A-006 | 07-ui/ui-acceptance-criteria.md | M18 absent | UI-001?UI-005 | Draft; not implemented or verified |
| OPS-001?OPS-006 | HLD ?8/?10/?12; A-005 | 08-mlops/monitoring-spec.md | run manifest/registry/monitoring absent | MODEL-004 / INF-004 / E2E-003 | Draft; not implemented or verified |
| SEC-001?SEC-007 / PRIV-001 / SECRETS-001 | HLD ?8/?10; LLD M03/M15 | 09-security/security-requirements.md | M03/M14/M15/M17 absent | INF-002?INF-004 / API-002?API-004 | Draft; not implemented or verified |
| UC-001?UC-006 / AC-001?AC-010 | HLD ?3/?7; Architecture demo flow | 01-product/acceptance-criteria.md | M01?M18 mostly absent | E2E-001 plus acceptance table tests | Draft; not implemented or verified |
| TEST-STRATEGY-001 | LLD ?9; user SDD request | 10-testing/testing-strategy.md | test suite absent | specification consistency review | Draft; not implemented or verified |
