# Training and serving consistency

CONS-001. HLD ?7.1 and LLD M09/M13 define population-fitted inference. Each submitted complete batch computes category statistics, ranks, forest fit and graph; a saved forest is a run-reproduction artifact, not a single-row prediction service.

Generated and uploaded seven-table batches must enter the same ingestion and transformation path. Persist exact feature order/types, eligibility/as-of policy, category statistics, rank transforms, null policy, model parameters, graph partition, pass/exclusion set and config version. UI never recomputes these.

Same snapshot, configuration, seeds, dependency environment and canonical row ordering must yield identical ranking and pass delta. Sort/rank tie rules await Q-012. Stored model and transform hashes must match the run manifest; mismatched bundles cannot serve a claimed reproduced run. The salt version belongs in provenance, never the secret salt.

Pass 2 calls the same formulas with approved exclusion changes; whether forest and graph are frozen or refitted is Q-006. Regression fixtures must detect stale pass-1 rules blended with pass-2 residuals. Snapshot/source-window mismatches must be visible errors, not hidden imputations.

Verification: FEATURE-006, MODEL-001, INF-001, E2E-002. No separate online path or additional algorithm is authorized.
