# v0.2 disposition of historical questions

Business confirmation: user stated "we have same understanding now" on2026-09-25. Timestamp precision is the conversation date; no exact approval time is fabricated. [Scope record](../../docs/agreed-project-scope.md). Engineering choices below are assistant-authored specifications under that agreed direction, not additional user approvals.

| Historical issue | Current disposition / source |
|---|---|
| Q-001 seven tables | Retain seven operational tables; explicit adapters and v0.2 field additions in [data](../v0.2/data.md). Old archive is still nonconforming. |
| Q-002/003 exposure/time | Mature exposure, quantities, cutoff and line requested_at specified in data; historical missing line times cannot be fabricated. |
| Q-004/005 features/graph | Numeric formulas, nulls, bracketing and graph support specified in [features](../v0.2/features.md). Validation remains to run. |
| Q-006 old two-pass | Frozen main model replaces mandatory per-upload refit; optional separately registered system comparison must preserve fitted state. No old forest-refit semantics may leak into inference. |
| Q-007 authority | Decision-support UI and human notes only; LLM cannot clear customers or trigger retailer actions. |
| Q-008/011/019 lifecycle/storage/UI | Local SQLite metadata, Parquet artifacts, job idempotency and UI states specified in [serving](../v0.2/serving.md). |
| Q-009/012 selection/ranking | User-approved5% budget, precision/group gates; engineering rounding, pooling and ties specified in [modeling](../v0.2/modeling.md). |
| Q-010 seeds | New versioned world namespace/splits specified in [experiment](../v0.2/experiment.yaml); old inspected data never called sealed. Actual untouched status must be maintained during execution. |
| Q-013 explanation/artifact | Deterministic evidence primary; optional narrative cannot set scores; model format/load checks specified in serving. |
| Q-014 operations | Initial resource limits set; actual throughput/latency remains measurement work. |
| Q-015 privacy | Synthetic local demo boundary and no truth in inference/logs; production retention/authentication/encryption policy remains outside this scope. |
| Q-016 SKU | User preserves independent customer evidence; conservative SKU signals plus uncertainty specified in features. |
| Q-017 source authority | User-confirmed current scope exists; missing submission proposal is still missing and is not claimed inspected. |
| Q-018/021 evidence/shortcuts | Validation/shortcut checks specified; legacy score claims remain unverified. |
| Q-020 future MLOps | Remains future scope. |
| Q-022 scope | Image-free wardrobing retained; inspection-routing expansion removed; current confirmed scope controls. Historical mathematical ceiling claim is not an acceptance criterion for the revised comparison. |
| TEAM-D01 provenance | Missing team generator helpers remain an evidence gap; recover or implement documented contract before claiming reproducibility. |
| TEAM-D02/04/05 profiles/truth/events | Separate generator targets, action truth and observed features; no volume-only positives. Data specification supplies action semantics and generation defaults. |
| TEAM-D03 catalog | User approved team300SKU/INR/five-category policy and12-month history. Adapters preserve source artifacts. |
| TEAM-D06 validation | Hard structural failures, seeded manifests and snapshot checks specified; execution evidence still required. |

The dispositions distinguish specified behaviour from verified implementation. Do not mark old tests passed merely because the design conflict has been resolved on paper.
