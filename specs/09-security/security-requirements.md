# Security requirements

DRAFT. Sources: HLD ??8.1/10/11; LLD M03/M14/M15 and ?6.

SEC-001: hash device/address/payment identifiers at ingestion using an approved salted equality-preserving method. No raw identifier downstream; algorithm, key/salt management and scope remain Q-015. Hashing is pseudonymisation, not proof of anonymity.

SEC-002: raw reason_text is attacker-controlled, processed only by the approved deterministic keyword layer at the ingestion boundary and excluded from downstream frames, artifacts, prompts and logs. No keyword algorithm is yet approved (Q-013). Grounding rejects fabricated cited values; a parsed JSON shape alone is insufficient.

SEC-003: the LLM has no tools or account action permissions. Keep score, memo and deterministic gate separate. Q-007 blocks auto-clear and score-to-routing semantics. Severe outcomes are queued for a second actor; actor-string inequality in an unauthenticated demo is not verified identity or RBAC.

SEC-004: validate input structure, enum/type/range, relationships, file registration and bounds. A user-supplied file_id cannot authorize arbitrary path reads. Archive traversal, decompression limits, symlinks and file-size protections must be specified if upload archives are approved (Q-008/Q-014); no upload transport is silently chosen.

SEC-005: local single-tenant no-auth MVP per HLD. Binding/access rules, disk encryption and any transport encryption need Q-015. External network deployment and real PII use require separately approved security scope; no production-security claim is made.

SEC-006: log every review/approval/refusal with provenance; fail approval if the decision cannot be durably recorded (proposed safety completion, Q-011). Append-only semantics do not alone prevent a local administrator rewriting a file; production tamper evidence is outside current scope.

SEC-007: UI renders model prose as text, excludes secrets/raw identifiers from errors, and does not trust client action permissions. No filesystem/upload content is executed. Model artifact loading accepts only verified approved bundles; serialization format is Q-013.

Verification: DATA-TEST-002, INF-002/INF-003/INF-004, API-002/API-003/API-004 and UI-003. SEC-004/005 operational details remain open, not waived.
