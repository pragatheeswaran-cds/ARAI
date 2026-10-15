# PostgreSQL, immutable storage and audit

Version 1.8 (amended 2026-10-05) | Implementation baseline | Component STORE

## Requirements and boundary

PostgreSQL holds the metadata and everything the API serves: run results (customers, styles, SKUs, neighbors, timeline, customer-style links, communities, attributions), the published experiment report and the demonstration truth export. The API opens no data file to answer a request. Files remain for inputs and models only: registered snapshots (CSV and Parquet, read by the worker), skops bundles with their JSON metadata and the active pointer, and the offline experiment records. Relative artifact keys under configured roots, no laptop paths. No SQLite.

Tables: datasets(id,unique world_id,manifest_hash,schema_version,cutoff,artifact_key,created_at); models(hash id,kind,metadata_key,validity); active_model singleton/version; runs(id,dataset/model FKs,status/stage/timestamps/summary/safe_error); run_customers(run,queue_position,customer,eligibility,scores,ranks,selection,support counts,evidence tags,wardrobing,measures,community_id since schema version 5); run_styles; run_skus; run_neighbors; run_timeline (schema version 4 adds the facts of each event as nullable columns beside its sentence); run_customer_styles; run_communities(run,community_id,kind,method,size,selected_count,requested_units,purchased_units,coordinated_claim_matches,edges JSONB; schema version 5); run_attributions(run,customer,family,raw_score_without,score_without,delta_points,in_queue_without; schema version 6); experiments(id,config_hash,selection/test artifact keys,report,truth world); experiment_truth(experiment,position,customer,y_abuse,action_types); workers(worker_id,started_at,seen_at); reviews(id,world/customer,origin run/model FKs,reviewer,kind since schema version 7,disposition,note,created_at; append-only, the workflow state is derived on read); idempotency(unique scope+key,request_hash,response_ref). Database UTC timestamps; IST display.

Transactional submission/activation/idempotency. An identical upload of a registered world restores its stored files if they have vanished. Atomic claim prevents duplicate processing even with accidental second worker. A run's result rows and its succeeded status are written in one transaction: a succeeded run always has its complete results and no other run has any. Result rows are never updated. The worker loads the published experiment report and truth export at startup, and imports once the result files of runs scored before version 1.7; such a run whose files are gone is marked failed (output_missing).

Notes append only across same immutable world/customer; correction new note, no delete/edit endpoints. No authenticated-identity claim for reviewer_name. Preserve failures/interrupted jobs and prior experiments. Logs include stage/duration/count/hash/request/error code but not raw identities/notes/truth/secrets. Migrations version schema and are applied under an advisory lock, because the API and the worker start together; back up the database (which now holds every result) together with the registered snapshots and bundles as a consistent set.

## Inputs, outputs and dependencies

- Inputs: Dataset/job/model/experiment/review events.
- Outputs: Transactional metadata and immutable artifacts.
- Dependencies: Data/artifact/API contracts.

## Acceptance criteria

| ID | Pass condition and required evidence |
|---|---|
| STORE-AC-01 | Concurrent duplicate requests yield one resource. |
| STORE-AC-02 | Two worker claims cannot both own same job. |
| STORE-AC-03 | A crash, or a failure while results are written, never exposes a succeeded run without its complete results, nor results of a run that did not succeed. |
| STORE-AC-04 | RunA note appears in runB same world/customer with original attribution. |
| STORE-AC-05 | Backup restores to relocated root without laptop path dependencies. |
| STORE-AC-06 | Every API read of run results, the experiment report and the truth export is answered from PostgreSQL; no result file is written or opened. |
| STORE-AC-07 | Results of runs scored before version 1.7 are imported once from their files and answer identically; a run whose files are gone is failed, not empty. |

Acceptance status is recorded per criterion in acceptance-register.csv (status, evidence, date, reviewer). Prose requirements are not implementation evidence.
