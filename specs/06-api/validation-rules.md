# API validation rules

DRAFT. Canonical syntax is openapi.yaml; A-003/A-009 mark proposed completions.

Generated jobs require integer seed and non-empty config_hash; uploaded jobs require non-empty registered file_id and config_hash. The oneOf branches exclude irrelevant source-specific properties. Resolve hashes/IDs through trusted registrations; never treat a client file_id as a filesystem path. Upload format/registration and payload limits remain Q-008/Q-014.

Path/query IDs are non-empty opaque strings. run_id is required for flagged, case and SKU reads. limit if supplied is positive; offset nonnegative; maximum/default/pagination ordering await Q-012/Q-014. Reject NaN/Infinity scores. Response risk_score is a 0?100 percentile, not probability.

Job transitions are queued ? running ? done or failed; failed before running is possible for startup validation. Publish done only with a durable compatible run. Proposed progress is 0?1 (A-009), with required run_id on done and readable sanitized error on failed; these conditional invariants are tested beyond basic schema validation. No restart/cancellation API is specified.

Empty successful collections are [], distinct from missing resource 404 or unready run 409. memo=null means evidence-only; never substitute a fabricated explanation. Nullable SKU metrics indicate undefined statistics, with UI no-data messaging; Q-016 governs exact conditions.

Validate all seven input tables per data specs. No new business thresholds are owned by API or UI. Approval state, run binding and trusted opener records cannot be inferred until Q-008 is resolved.
