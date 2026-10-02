# PostgreSQL, immutable storage and audit

Version 1.6 (amended 2026-10-02) | Implementation baseline | Component STORE

## Requirements and boundary

PostgreSQL metadata; Parquet/JSON/skops filesystem artifacts. Relative artifact keys under configured roots, no laptop paths. No SQLite.

Tables: datasets(id,unique world_id,manifest_hash,schema_version,cutoff,artifact_key,created_at); models(hash id,kind,metadata_key,validity); active_model singleton/version; runs(id,dataset/model FKs,status/stage/timestamps/output_key/safe_error); experiments(id,config_hash,selection/test artifact keys); reviews(id,world/customer,origin run/model FKs,reviewer,disposition,note,created_at); idempotency(unique scope+key,request_hash,response_ref). Database UTC timestamps; IST display.

Transactional submission/activation/idempotency. An identical upload of a registered world restores its stored files if they have vanished. Atomic claim prevents duplicate processing even with accidental second worker. DB transaction+filesystem rename not one transaction: staging/completion marker and startup reconciliation; no succeeded before complete files.

Notes append only across same immutable world/customer; correction new note, no delete/edit endpoints. No authenticated-identity claim for reviewer_name. Preserve failures/interrupted jobs and prior experiments. Logs include stage/duration/count/hash/request/error code but not raw identities/notes/truth/secrets. Migrations version schema; backup DB plus referenced artifacts as a consistent set.

## Inputs, outputs and dependencies

- Inputs: Dataset/job/model/experiment/review events.
- Outputs: Transactional metadata and immutable artifacts.
- Dependencies: Data/artifact/API contracts.

## Acceptance criteria

| ID | Pass condition and required evidence |
|---|---|
| STORE-AC-01 | Concurrent duplicate requests yield one resource. |
| STORE-AC-02 | Two worker claims cannot both own same job. |
| STORE-AC-03 | Crash/restart never exposes succeeded with missing files. |
| STORE-AC-04 | RunA note appears in runB same world/customer with original attribution. |
| STORE-AC-05 | Backup restores to relocated root without laptop path dependencies. |

Acceptance status: **NOT_RUN**. Record executed results and artifact hashes; prose requirements are not implementation evidence.
