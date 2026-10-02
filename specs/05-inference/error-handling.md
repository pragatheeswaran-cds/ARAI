# Inference failures

INF-ERR-001. DRAFT. Sources: HLD ?8.4; LLD ??8?9. Contract failure (missing file/column) fails before scoring; invalid rows quarantine with reasons. Warn for source-reference issues and excessive quarantine rate once Q-014 defines threshold. Do not silently drop an invalid return and count the sale as a benign retained item: treatment is Q-002.

Invalid config (weights, k<=0, unknown feature) fails before fitting. Degenerate graph reports unusable; blend fallback awaits Q-005. Empty populations, all-quarantined batches, zero-norm groups and thin histories need Q-004/Q-012 policy; they cannot produce fabricated zero-risk success.

Provider timeout at 30 seconds or invalid output allows at most one retry, then stores no memo and routes evidence to human review. A missing provider does not block batch completion. Invalid citation is discarded; it must never be persisted/rendered as a validated memo. Source ?9 allows a run to fail on absent citations while M15 degrades the case: proposed interpretation is fail on invalid memo escaping validation, not on a safely discarded response; confirm Q-013.

Privacy leakage in packets/prompts and reproducibility violations fail publication. Packet cap applies to UTF-8 bytes, not Python character count; reduce history then neighbours, recording reductions. Still-too-large policy is Q-013, never truncation of arbitrary JSON.

Job progress exposes a sanitized error; raw identifiers, free text, salt/provider secrets and stack traces stay out of responses and routine logs. Durable failed-job publication and restart behaviour await Q-011. API error envelope is canonical in ../06-api/error-contract.yaml.
