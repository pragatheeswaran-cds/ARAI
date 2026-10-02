# Reproducibility

REPRO-001 (NFR-001). DRAFT. Record dataset/source hashes, seed, run_date, config, ordered feature list, transform state, forest parameters, graph seed/resolution/partition, exclusions, dependency lock and code revision (or explicit unavailable reason). Timestamp/run IDs may differ; deterministic ranking payload must not. Current source lacks a dependency lock and root config; do not claim reproduction has passed.

Use seed 20250901 for design defaults; development/test worlds follow data-split-spec.yaml after Q-010 approval. Pin every stochastic entry point, including Louvain. Define deterministic input order and tie rules before implementation (Q-012). Persist fits for audit even though new uploads refit.

Verify same seed/snapshot/config/environment twice produces identical scores, ranks, partition and packet hashes; different seed gives a different world. Cache metadata must include packet hash, model/provider version, prompt/schema version and configuration (A-005 extension; Q-013 review). A cached explanation never substitutes for a missing or mismatched score run.

Do not demand byte-identical timestamps or claim deterministic live LLM prose. Memo cache provides reproducible presentation; deterministic scoring and gate behaviour do not depend on provider prose. New full SHA-256 hashes (A-007) supplement the archive's 16-hex prefixes.
