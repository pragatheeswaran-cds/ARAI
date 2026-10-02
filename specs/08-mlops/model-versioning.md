# Versioning

OPS-003. DRAFT. A score belongs to run_id + customer_id + pass. Dataset_version identifies source contents/manifest; schema_version identifies the approved seven-table schema; feature_version identifies formulas and ordered allow-list; model_version identifies algorithm, complete parameters, environment and fitted contents; policy_version identifies tier/action rules; config_hash captures the effective combination. No version implies model approval.

MVP source says frozen schema, not runtime version negotiation. Version tags in this SDD set and artifact metadata provide provenance (A-001/A-005), not a redesign to support multiple public API generations. Changing data, observation window, formula, seed, exclusion policy or parameter creates new provenance; never overwrite old scores.

Record code commit when available, otherwise source-file hashes and an unavailable reason (A-007). Current workspace has no .git metadata. Model format/version compatibility and serialization are Q-013; mismatches reject load. Memo provenance includes provider/model, prompt/schema version and packet hash; live prose nondeterminism does not weaken deterministic score lineage.

Verification: MODEL-004, INF-004, E2E-002.
