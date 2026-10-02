# UI/API integration

UI-API-001. DRAFT. The API owns data validation, feature generation, model fitting, scores, policy and persistence; UI owns presentation and permitted request input. Never read scored dataframes directly to fill a missing API.

| UI action | LLD operation | Required client behaviour | Contract gap |
|---|---|---|---|
| Start generated run | POST /jobs | Send generated, seed, config_hash; store returned job_id | Config selection and latency limits Q-014 |
| Start upload | POST /jobs | Send upload, file_id, config_hash after approved registration | Registration/transport missing Q-008 |
| Poll progress | GET /jobs/{job_id} | Poll until done/failed; never duplicate submission after ambiguous timeout automatically | Poll interval, restart/idempotency Q-008/Q-014 |
| Read queue | GET /flagged | Send run_id and bounded pagination; retain run while selecting | Default limits/order and flagged definition Q-012/Q-014 |
| Open case | GET /case/{customer_id} | Send run_id; render typed evidence and nullable memo | Opener recording and version metadata Q-008 |
| Read products | GET /skus | Send run_id; show no-verdict separately | More M12 signals and export Q-008/Q-016 |
| Approve/review | POST /case/{customer_id}/approve | Send actor/action; handle 409 visibly; wait for durable decision_id | Run binding, normal outcomes and duplicates Q-007/Q-008/Q-011 |
| Read scorecard | Not specified | Remain blocked; no invented endpoint or direct-file bypass | Q-008 |

On run change invalidate prior queue/case/SKU responses; a late response for the previous run must not overwrite the current screen (A-006). UI must not silently switch to latest run or use a cached case from another snapshot. Errors follow ../06-api/error-contract.yaml and contain no raw values.
