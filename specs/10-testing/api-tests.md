# Api Tests

DRAFT ? verification specifications only, not implemented or executed tests. Sources: LLD ?5/?9 and referenced canonical specs.

| Test ID | Requirements | Level / concern | Fixture and expected result |
|---|---|---|---|
| API-001 | FR-009; NFR-006; API-REQ-001/005 | Job contract/integration | POST generated/upload branches validate; 202 arrives before controlled slow worker completes. Poll queued/running/done/failed; done has durable run_id, failure has safe error. GET does not wait on worker. Exact performance limits require Q-014. |
| API-002 | API-ERR-001; SEC-004/007; API-REQ-002 | Schema and negative contract | Validate six operations against OpenAPI including nullable memo/verdict. Wrong type/unknown field/source mismatch ->422; unknown resource->404; unready run->409 per A-003. limit0/offset-1 rejected. Nonfinite scores never emitted; traversal-like file_id never authorizes paths; approved upload limits await Q-008/Q-014. |
| API-003 | FR-008; AC-007; NFR-005; SEC-003 | Approval safety | Same actor as trusted opener ->409 SELF_APPROVAL_REFUSED plus audit record; distinct approved actor records decision only after durable log. Altered body actor cannot establish real identity assurance. Missing run/opener, duplicates/concurrent/conflicting decisions and CLEAR require Q-007/Q-008/Q-011 before fixtures can be frozen. |
| API-004 | NFR-003; API-REQ-003/005; SEC-006; OPS-005 | Audit and failure integration | Every scored customer including unflagged has queue row; every open/action/refusal event traceable with run/case/actor and time. Kill/restart and disk-write failure cannot claim successful unlogged approval. Append-only concurrency/recovery implementation awaits Q-011. No raw values or secrets in logs. |
