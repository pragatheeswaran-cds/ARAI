# Inference Tests

DRAFT ? verification specifications only, not implemented or executed tests. Sources: LLD ?5/?9 and referenced canonical specs.

| Test ID | Requirements | Level / concern | Fixture and expected result |
|---|---|---|---|
| INF-001 | INF-CONTRACT-001/INF-PRE-001/INF-OUT-001; CONS-001 | Batch integration | Same approved population through generated/upload source produces same features, components and both-pass scores. Scores 0..100 are percentiles, not probabilities. No single-row serving shortcut, hidden UI transform or stale pass1 rule with pass2 features. Q-006/Q-008/Q-012 dependencies explicit. |
| INF-002 | NFR-004; AC-006; SEC-001/002; PRIV-001; SECRETS-001 | Privacy/adversarial property | Use exact source attack strings plus Unicode text and fixture raw IDs. Scan downstream frames, serialized artifacts, packet/prompt, logs/errors and UI; no forbidden content. Packet UTF-8 size<=8192 after caps; 400 orders/30 neighbours obey 12 evidence items/15 neighbours/180-day history. Still oversized case blocked Q-013. |
| INF-003 | FR-007; NFR-002; INF-ERR-001; SEC-003 | Memo fallback and grounding | Valid citation accepted; fabricated 91% against packet82% discarded. Invalid JSON/enum, timeout/provider offline each permits at most one retry then evidence-only. Invalid memo never stored as validated. Change memo tier/prose while deterministic account effects remain unchanged; Q-007 needed for complete policy. |
| INF-004 | MODEL-ARTIFACT-001; OPS-001/003/004/005; SEC-007 | Run failure/replay | Bad weights/k/allow-list fail pre-fit; privacy leakage fails publication; graph degeneration is visibly unusable, with approved fallback Q-005. Corrupt manifest/model prevents serve; absent provider supports offline fallback. Check safe stage/error records and cache version/hash mismatch. |
