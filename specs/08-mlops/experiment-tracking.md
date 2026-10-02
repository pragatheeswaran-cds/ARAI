# Experiment tracking

OPS-001. DRAFT. HLD ?8.2 and LLD ?3.2 require local run manifests; A-005 proposes their use as the experiment ledger without adding a hosted tracker.

Record run_id, start/end timestamps, as-of date, dataset/source/schema/feature/config hashes, code revision or unavailable reason, all seeds, complete forest parameters, graph settings and partition hash, exclusion sets, pass-specific artifact hashes, feature order and transforms, stage durations, row/quarantine counts, warning/degradation codes and environment versions. Evaluation records additionally carry candidate IDs, seed-role allocation, budget, metric numerators/denominators, interval method and selection/rejection reason.

Separate operational fit runs from evaluation experiments. Production-like uploads have no labels, so metrics are explicitly not_evaluated rather than fabricated. No raw input values, identifiers, text, salts or provider keys in tracking records. Provider model ID, prompt/schema version, packet hash, cache status, attempt count, cost and duration are safe provenance subject to Q-015.

Freeze code/config/generator hashes before sealed evaluation; log attempted mismatches as refused. Selection ordering and metric acceptance remain Q-009/Q-010. Verification: MODEL-003, INF-004, E2E-002.
