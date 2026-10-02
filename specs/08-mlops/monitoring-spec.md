# Monitoring

OPS-005. DRAFT. HLD ?10 limits MVP observability to local manifest/logs. Record service request duration/status, job stage duration/progress/failure, total run time, input/accepted/quarantined counts by reason, unknown categories and missing values, graph component size/unusable status, memo success/failure/retry/cache counts and provider cost/duration.

Persist distributions of each approved feature, all three component scores, blended_raw, risk percentile, tiers and wardrobe bands for offline inspection (A-005). Compare within compatible schema/feature/policy versions. Percentile tiers alone conceal population-wide risk changes, so preserve raw blended/component distributions (HLD ?12).

No alert threshold is supplied: service/batch limits and quarantine trigger are TBD Q-014. Do not silently install monitoring services or label a run healthy based on unknown limits. Privacy/property failures block publication independently of an operational alert threshold.

No real fraud outcomes exist. Synthetic metrics are reported by M16 only; reviewer actions are not automatically fraud labels. The queue records all scored customers and review sampling rate .01 from LLD ?4 so later selection-bias analysis remains possible; sampling mechanism is not yet specified (Q-009/Q-012). Delayed outcome collection and business performance monitoring are future Q-020.

Verification: API-004, INF-004, MODEL-002, E2E-001. Ownership follows Lead for run health, App for service/logs and DS1 for evaluation; production on-call ownership TBD Q-020.
