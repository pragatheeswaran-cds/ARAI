# FastAPI and API contract

Version 1.8 (amended 2026-10-05) | Implementation baseline | Component API

## Requirements and boundary

Implement FastAPI under /api/v1 with bundled OpenAPI normative for schemas, methods, filters and errors. No old /jobs or /approve routes. Cover dataset list/register/detail, run list/submit/status, customer queue/case/reviews, style queue/detail and SKU drill-down, experiment list/report, health. Runs live under /runs; the v1.0 /inference-jobs paths are withdrawn.

Upload exactly seven named CSV parts plus manifest JSON string. Reject private/unknown fields, client paths and traversal; internal storage paths server-generated. Synchronous structural validation returns201 only accepted (existing identical dataset200); scoring async202. Invalid422, resource413, unknown404, not-ready/model/idempotency conflict409, unexpected500 safe code/request_id no stack/path/secret.

world_id/content immutable. Idempotency scope endpoint+dataset for inference; endpoint+world/customer for notes; key<=128 with canonical payload hash. Repeat same returns original resource; changed body409. Customer ID must belong to run world.

Stable cursor tied to run+normalized filters+sort; invalid/context-changed/misshapen422. TruthPage names the world it reveals (world_id). Customer order rank then unranked ID; styles by style_id. Default limit50,max100; empty items=[]/next_cursor=null. The customer queue comparison filter (all, model_only, baseline_only, both) partitions eligible customers by model versus return-rate-rule selection. Filters change display only, not run score/selection.

Run carries warnings recorded at scoring (fewer than 500 eligible customers, a category fallback, scores or inputs outside the training range, or scoring code changed since publication). Contract 1.3.0: every Metric carries code, ranking and slice, which identify it; name and scope are display text and may be reworded. Health carries queue_depth and worker_seconds_since_seen (null if no worker ever reported), which are informative and not part of scoring_ready. ExperimentSummary carries selected_candidate_id (the registered candidate) beside selected_model_id (the promoted bundle, null unless promoted). A nullable enumeration lists null among its values. Review fields reviewer_name/disposition/note/idempotency_key; dispositions needs_investigation,likely_legitimate,unresolved. Append-only, server timestamp, immutable origin run/model. Free-text attribution is not authenticated identity.

Local explicit CORS UI origins; VM same-origin reverse proxy shared login covers both UI and API. No app signup/profile/password endpoints. Experiment truth reveal separated from inference and synthetic-labelled.

## Inputs, outputs and dependencies

- Inputs: Multipart CSV+manifest and typed JSON.
- Outputs: Responses matching contracts/openapi.yaml.
- Dependencies: Inference/storage.

## Acceptance criteria

| ID | Pass condition and required evidence |
|---|---|
| API-AC-01 | All actual requests/responses validate against OpenAPI including201/202 and documented errors. |
| API-AC-02 | Upload parts/limits/hash/count/ownership/path-traversal fixtures enforced. |
| API-AC-03 | Cursors return no duplicates/gaps and cannot cross run/filter. |
| API-AC-04 | Every UI action has an endpoint, with no training/refund/block/delete-note operation. |
| API-AC-05 | Unknown404, unfinished409, conflict409 and validation422 are distinguished. |
| API-AC-06 | Unlisted CORS origin denied; VM API unauthenticated denied. |
| API-AC-07 | comparison filter values partition eligible customers consistently with the run counts and stable cursors; ineligible customers appear only under all. |
| API-AC-08 | Every published metric has a code; Health reports the queue depth and the worker heartbeat; a login header that is not ASCII is refused with 401. |

Acceptance status is recorded per criterion in acceptance-register.csv (status, evidence, date, reviewer). Prose requirements are not implementation evidence.
