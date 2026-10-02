# API requirements

DRAFT. API-REQ-001 maps FR-009/NFR-006 to the six operations in openapi.yaml, transcribed from LLD ?6. All complete-population scoring is asynchronous; no /predict or synchronous /score is introduced. Architecture Appendix A mentions /score and /upload, while its revised main text and LLD require jobs; Q-008 records the missing transport contract instead of inventing endpoints.

API-REQ-002: every result read is bound to explicit run_id, completed run and compatible immutable artifacts. Approve lacks run_id in LLD and GET case lacks opener actor; these remain blockers Q-008. A read request must not secretly establish a case opener from an unauthenticated identity or mutate approval state.

API-REQ-003: approval/refusal records preserve actor, action, prior tier, run and case, timestamp and refusal reason. Self-approval is 409 SELF_APPROVAL_REFUSED. Repeated, conflicting and concurrent approvals, CLEAR semantics and role validation remain Q-007/Q-008/Q-011.

API-REQ-004: no authentication in local single-tenant MVP per HLD ?10. Do not advertise identity assurance from a body actor value. External exposure is outside approved scope. Ports/host in OpenAPI are proposed A-009. No API version path is mandated; info.version versions this draft contract only.

API-REQ-005: record sanitized request duration, response status, operation, job/run correlation and failure code. Batch stage durations belong to the manifest/logs. Acknowledgement latency, GET P95, pagination defaults/maximum, upload size, concurrency and client/server timeouts are TBD Q-014; model timeout is separately 30 seconds with one retry.

API-REQ-006: the source does not define upload registration, a scorecard operation, review-outcome capture, case opener event or run-manifest/version retrieval. Do not make UI read dataframes directly to bypass those gaps. Approve contract additions through Q-008 first.

Nested evidence/pass/graph wire shapes complete the outer LLD JSON for review under A-009. An OpenAPI parser accepting this file does not resolve business or lifecycle blockers.
