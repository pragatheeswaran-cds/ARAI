# Model artifact, inference, FastAPI and UI

## Immutable model bundle

Bundle model_id is a content-addressed version. Include fitted model/preprocessing pipeline, ordered feature schema, training fallback statistics, frozen risk-CDF reference, score adapter, candidate configuration, selection/final-evaluation records, source data/code/config hashes and exact Python/library versions. Record training cutoff and schema version. Separate this reusable bundle from per-job features, graph, evidence and predictions.

Use skops serialization for supported estimators, plus JSON/Parquet for metadata/reference tables. Verify support for the selected pipeline in the locked environment before implementing promotion. Load only locally produced bundles with an explicit type allow-list and verified hashes; the API does not accept user-supplied model files. A metadata mismatch or unknown type fails loading. [scikit-learn persistence guidance](https://scikit-learn.org/stable/model_persistence.html) explains serialization choices and version-compatibility limits; compatibility must be checked, not assumed.

Promotion writes a new immutable directory, validates it, then atomically updates a local active-model pointer. A scoring job binds to the model hash at submission. Later promotion cannot change an in-flight job. Training/selection happen via offline commands, never inside inference routes. No fit or fit_transform call is allowed during prediction.

## Inference steps and outputs

1. Bind registered dataset manifest/hash and active model/version.
2. Validate seven operational tables and schema/retail policy.
3. Construct the immutable cutoff snapshot and deterministic features/SKU/graph evidence.
4. Mark insufficient-history rows; transform eligible rows with frozen preprocessing.
5. Score, orient raw scores, calculate frozen-reference risk, and rank within the eligible batch.
6. Build customer and SKU evidence, including independent wardrobing bands.
7. Atomically publish predictions and evidence, then mark the job succeeded.

Required prediction columns: run_id, model_id, world_id, customer_id, cutoff, eligibility_status, nullable raw_score/risk_score/rank, selected_for_review, support_counts, evidence_refs, wardrobing_status. selected_for_review uses approved top5% policy. Do not emit LOW/MEDIUM/HIGH as though calibrated thresholds were approved; use review_priority and insufficient_history statuses. SKU results include evidence axes and uncertainty, not automatic customer clearance.

## Local service contract

FastAPI binds to loopback by default. SQLite stores job/upload/review metadata; Parquet stores immutable operational/features/prediction artifacts. Use one background worker and SQLite transactions. A crashed running job becomes interrupted on startup; retry creates a new run ID against the same dataset/model hashes. Do not silently publish partial predictions.

| Method/path | Request | Success / behaviour |
|---|---|---|
| POST /datasets | multipart seven named CSV files plus JSON manifest, schema_version=v0.2 |201 dataset_id, manifest_hash, validation_status; invalid upload422 |
| POST /inference-jobs | JSON dataset_id, optional registered model_id, idempotency_key |202 run_id, status=queued, model_id; no available promoted model409 |
| GET /inference-jobs/{run_id} | none |200 status, stage, progress, timestamps, model/dataset hashes, nullable error |
| GET /inference-jobs/{run_id}/customers | cursor, limit<=100, review_only, eligibility, evidence filter |200 stable ranked page; unfinished run409 |
| GET /inference-jobs/{run_id}/customers/{customer_id} | none |200 score, observed evidence, linked SKUs and relationship support |
| GET /inference-jobs/{run_id}/skus | cursor, limit<=100, evidence-state filter |200 SKU queue with denominators and supporting cases |
| POST /inference-jobs/{run_id}/customers/{customer_id}/reviews | reviewer_name, disposition, note, idempotency_key |201 appended analyst note; no retailer account action |
| GET /experiments/{experiment_id} | none |200 versioned comparison/gate results; truth rows never exposed through inference routes |
| GET /health | none |200 liveness and model-ready boolean; no secret/path disclosure |

Review dispositions: needs_investigation, likely_legitimate, unresolved. They are human opinions with timestamps, not new training truth. Duplicate idempotency_key+same body returns the original result; same key+different body409. Job statuses queued/running/succeeded/failed/interrupted are monotonic except no manual state mutation. Unknown IDs404; contract errors422; resource limit413; model mismatch409; unexpected failures500 with public error_code and private diagnostic log reference.

Initial local limits:500MB upload total,2million combined operational rows,1 active scoring worker. These are engineering limits, not throughput claims. Poll every2seconds. Return acknowledgment before processing. Measure end-to-end duration and API P95 on the actual demo machine before setting a performance claim. Do not log raw identity strings or private ground truth. No production-authentication claim for this local demo.

## UI contract

1. Dataset/run page: catalog policy, cutoff/history span, validation findings, active model and job progress. No training button inside scoring flow.
2. Customer queue: default review-priority rows, ranked risk, supporting signal tags; explain reference-percentile score in a tooltip. Show excluded-history counts explicitly.
3. Customer case: timeline, observed denominators, product explanations, household/coordination evidence, separate wardrobing signal, append-only review note. Never display hidden synthetic labels here.
4. SKU queue/detail: suspected quality/targeting/uncertainty, evidence and linked customer cases. No automatic unflag-all action.
5. Evaluation page: baseline/candidate table, gate pass/fail, legitimate-group errors, per-type recovery,1/5/10% budgets and separate final-test status. Ground-truth reveal exists only in this evaluation context, clearly labelled simulation.

All pages define loading, empty, insufficient-support and failure states. Keyboard-accessible controls, text labels alongside colours and table headers are required. Evidence works without an LLM; an optional generated narrative may summarize the packet but cannot set scores, labels or decisions. If enabled later, pin its model/prompt and show deterministic evidence on failure.
