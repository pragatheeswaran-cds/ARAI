# Model Tests

DRAFT ? verification specifications only, not implemented or executed tests. Sources: LLD ?5/?9 and referenced canonical specs.

| Test ID | Requirements | Level / concern | Fixture and expected result |
|---|---|---|---|
| MODEL-001 | MODEL-TRAIN-001; REPRO-001; LEAK-001/002 | Fit contract and determinism | Assert exact eight-feature allow-list; no raw rates/counts/labels/IDs; rank transform uses approved tie/null policy; pinned seed/config/inputs reproduce forest scores and partition. Missing feature fails naming it. No supervised weights/resampling are introduced. |
| MODEL-002 | FR-010; MODEL-EVAL-001; AC-009 | Evaluation arithmetic | Hand label fixture checks TP/FP/FN/TN, precision/recall/FPR, all segments and exact k matching baseline/full/ablations. Wilson 38/40 at 95% approximately [.835,.986]. Seed aggregation mean +/-2*SE checked independently. Undefined denominators yield null/reason. Ceiling cannot be guessed as perfect label oracle; Q-009. |
| MODEL-003 | MODEL-SELECT-001; DATA-004; NFR-008 | Selection and sealed-test gate | Unresolved primary metric/threshold/tie rule rejects selection; frozen candidate order and approved metrics deterministically choose same result. Changed config/code/generator hash refuses sealed run; test results cannot enter selection. Record contamination/re-run attempts. No claim of achieved acceptance until Q-009/Q-010 resolved. |
| MODEL-004 | MODEL-ARTIFACT-001; OPS-002/003 | Artifact registration and compatibility | Remove or corrupt each required artifact/hash; registration/load fails. Swap feature order, preprocessing, policy or pass-specific model and reject. Valid complete bundle reproduces stored ranking. Model format and registry persistence await Q-011/Q-013. |
