# Functional requirements

DRAFT. HLD ?3 is the primary source. All are specified for future verification; none is implemented by this task.

| ID | Source | Requirement | Planned modules | Open dependencies |
|---|---|---|---|---|
| FR-001 | HLD F1 | Rank serial-return evidence using basket-normalised residuals and expose legitimate-heavy-returner false positives at matched budgets. | M04?M06/M08/M16 | Q-002/Q-004/Q-009 |
| FR-002 | HLD F2 | Surface refund-claim abuse using claim mix, rules and the explicit Isolation Forest allow-list. | M06/M08/M09 | Q-004/Q-009 |
| FR-003 | HLD F3 | Build degree-capped, weighted identity links and deterministic communities; show ring evidence without treating linkage alone as guilt. | M10 | Q-005 |
| FR-004 | HLD F4 | Report wardrobing band and fired signals separately from blended risk, with an inline limitation that transactional data cannot confirm wear. | M07/M18 | Q-004 |
| FR-005 | HLD F5 | Emit SKU quality_issue, abuse_target, normal or no verdict with contributing signals and min-sales guard. | M12 | Q-016 |
| FR-006 | HLD F6 | Run two passes through the same baseline path; persist both scores/delta and evaluate all benign segments. An empty exclusion set produces identical passes. | M05/M13/M16 | Q-006/Q-009 |
| FR-007 | HLD F7 | Provide rule IDs, feature evidence, graph context and computed counterfactuals. Memos cite packet values only; provider failure yields evidence with no prose. | M11/M14/M15 | Q-012/Q-013 |
| FR-008 | HLD F8 | Keep automated components from acting on customer accounts; record review and refusal events and require a distinct second actor for severe approval. | M15/M17 | Q-007/Q-008 |
| FR-009 | HLD F9 | Submit a conforming seven-file population through the same asynchronous batch pipeline used for generated data. | M03/M17/M18 | Q-001/Q-008 |
| FR-010 | HLD F10 | Compare full ranking with raw-return-rate ranking at equal k, with per-segment results, ablation and sealed-seed intervals. | M16 | Q-009/Q-010 |
