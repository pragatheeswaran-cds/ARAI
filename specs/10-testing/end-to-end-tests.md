# End To End Tests

DRAFT ? verification specifications only, not implemented or executed tests. Sources: LLD ?5/?9 and referenced canonical specs.

| Test ID | Requirements | Level / concern | Fixture and expected result |
|---|---|---|---|
| E2E-001 | FR-001?FR-010; AC-001?AC-010 | Approved vertical slice | Seven-file approved fixture -> job -> both-pass ranking -> queue/case/SKU evidence -> validated memo or fallback -> distinct-actor review -> complete audit and evaluation. Include benign-heavy/household/defect and all abuse segments. Fail if any required lifecycle step relies on unresolved Q-007/Q-008. |
| E2E-002 | NFR-001/002/003/008; REPRO-001 | Reproduction and provenance | Future clean-checkout repeated runs under identical pinned environment produce byte-identical deterministic ranking and packet hashes, correct run/version links and complete population denominator. Corrupted artifacts/config mismatch rejected; sealed data cannot select a winner. |
| E2E-003 | NFR-007; OPS-004 | Offline/recovery rehearsal | Two-machine clean setup with network disabled completes prepared demo using compatible cache/evidence-only fallback; provider failure never changes gate behaviour. Restart/disk failure truthfully reflected; rollback restores compatible full bundle while retaining audit. Recovery limits TBD Q-011/Q-014. |
