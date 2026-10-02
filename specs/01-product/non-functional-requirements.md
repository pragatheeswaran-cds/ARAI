# Non-functional requirements

DRAFT. No numeric latency/service/quality threshold has been invented.

| ID | Source | Verification condition | Test |
|---|---|---|---|
| NFR-001 | HLD N1 | Same data/seed/config/environment produces byte-identical ranking; manifest identifies input, config, code, model and partition hashes. | E2E-002 |
| NFR-002 | HLD N2 | Every contribution is traceable to rule IDs, feature deviations and graph evidence; unsupported memo citations are rejected. | INF-003 |
| NFR-003 | HLD N3 | Every scored customer, including unflagged, has a queue record; every review action/refusal has an append-only audit event. Persistence protocol Q-011. | API-004 |
| NFR-004 | HLD N4 | No raw device/address/payment value or customer free text passes ingestion; no identifiers enter provider packets. | INF-002 |
| NFR-005 | HLD N5 | No LLM output can execute customer consequences; severe approval refuses self-approval and logs the attempt. Q-007/Q-008 block full policy. | API-003 |
| NFR-006 | HLD N6 | Full 25,000-return workload duration, job acknowledgement and API P95 limits are TBD Q-014; service calls must not wait for scoring completion. | API-001 |
| NFR-007 | HLD N7 | Future clean-checkout one-command run and offline demo complete on two machines with cached memos or evidence-only fallback. | E2E-003 |
| NFR-008 | HLD N8 | Published synthetic metrics use frozen sealed seeds, stated denominators and intervals; no sealed result feeds selection. | MODEL-003 |
