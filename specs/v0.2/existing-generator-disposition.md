# Existing generator reuse, repairs and conditional reconstruction

Status: evidence-backed requirements added following the user's request on2026-09-25. Reasoning, measurements and limitations: [generator reuse assessment](../../docs/generator-reuse-assessment.md). Existing source/data remain unchanged by the review.

## Required disposition

- Reuse the supplied300-SKU catalog and37-style commercial rules after an explicit canonical adapter. Do not regenerate it merely because the generating source is missing.
- Retain customer profile configuration as private generation input and exploratory reference. Do not use the current master CSV as the final labelled ML dataset.
- Recover missing SKU helper modules and the customer generation entry point. If unavailable, reconstruct only that generation layer under v0.2; retain working assets and distinguish new outputs from unverified original reproduction.
- Keep exploratory notebooks, fixing verified diagnostics and adding a separate executable validator. No full replacement is justified by current evidence.

## Requirements and exit checks

| ID | Requirement | Why / evidence | Exit check |
|---|---|---|---|
| REUSE-001 | Source/provenance inventory and explicit source paths | GEN-001, GEN-008 | Generator imports resolve from declared project paths; no hidden author-home fallback; manifest records code/config/catalog hashes |
| REUSE-002 | Catalog preservation with schema adapter | GEN-008; checked SKU catalog valid |300 SKUs/37 styles, prices, variants, policy and occasion flags survive adapter; source CSV hash retained |
| REUSE-003 | Separate profiles, action truth and operational inputs | GEN-002 | Altering private persona/status labels alone cannot change computed features or inference; completed action events define y_abuse |
| REUSE-004 | Generate real shared-identity structure and subgroup metadata | GEN-002 | Both benign households and coordinated abusive actions exist; scalar device targets never substitute for identity relationships |
| REUSE-005 | Calendar-feasible festive generation | GEN-003 | Customer with no eligible festive dates has realised festive share0; no pre-signup/out-of-window order; target deviation logged |
| REUSE-006 | Correct target versus observed gap semantics | GEN-004 | Observed mean gap equals consecutive timestamp differences and is null for0/1 orders; no tenure/orders equality requirement |
| REUSE-007 | Correct enrichment diagnostic | GEN-006 | N1000/fraud200/noise300/fraud_noise40 reports enrichment0.667, not enriched; recall20% separately; undefined denominators explicit |
| REUSE-008 | Machine-enforced data validation | GEN-007 | Negative tenure, duplicate keys and invalid dates fail the command and prevent accepted export/manifest; human-readable report still produced |
| REUSE-009 | Independent detection evaluation | GEN-005 | Notebook ARI/noise results labelled exploration; final scores come from untouched action-labelled worlds under model-selection protocol |
| REUSE-010 | Chronology and current-vs-historical activity | GEN-008 | No orders before launch/signup; final active_flag never invents retirement timing; policy preserved at sale |
| REUSE-011 | Reproducible generation and format parity | GEN-001 | Two runs under pinned dependencies/seed yield identical canonical tables; CSV/Parquet parity verified with an installed reader |
| REUSE-012 | Honest reconstruction boundary | GEN-001 | If source unavailable, new generator has a new version and acceptance evidence; it never claims recovery of the unknown original implementation |

## Rules preventing unnecessary replacement

The41-inactive-SKU count is a valid whole-style prefix near the45 target; do not split styles to force45. Wide legitimate return/device overlap is useful; do not remove it to improve scores. Constant style prices and repeated category windows are intentional approved simulation rules. Lack of transaction rows in a profile master is a missing downstream phase, not a corrupt customer table.

## Dependency order

1. Pin current artifacts and apply named adapters for development fixtures.
2. Recover source or implement the missing generation layer; isolate profiles/truth and define dated events.
3. Implement calendar/gap/identity requirements and hard validation.
4. Demonstrate reproducibility and canonical output parity on a small world.
5. Generate independent full worlds and proceed to the ML comparison.

No generator rewrite or data regeneration was performed merely by adding this specification. Failures found during implementation must be recorded with their reproduction before expanding replacement scope.
