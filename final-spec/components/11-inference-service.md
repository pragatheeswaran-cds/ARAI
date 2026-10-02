# Batch inference and job lifecycle

Version 1.0 | Implementation baseline | Component INF

## Requirements and boundary

Bind dataset and active promoted or valid baseline hash at submission. Queue one worker. States queued->running->succeeded|failed; crashed running ->interrupted on restart. Queued can resume. Retry failed/interrupted creates new run with original bindings and new key.

Stages: validate snapshot ->features/graph/style ->eligibility ->frozen preprocessing ->score/reference percentile/rank/top5% ->evidence ->atomic publication. No results before succeeded. Stage files then publish and mark success; reconcile crash orphans without partial outputs.

Prediction fields include run_id/model_id/model_kind/dataset_id/world_id/cutoff/customer_id, eligibility_status, nullable raw_score/risk_score/rank, selected_for_review, support_counts/evidence_refs/wardrobing. Ineligible unranked scores null selected=false, but case evidence visible. Customer evidence includes source transactions, mature/raw/expected/value denominators, products, supported neighbors, separate wardrobing. No private truth or causal claims.

Fallback banner states actual failed gate or selection not completed; retain valid active model unless explicitly switched. Graph failure fails job, empty graph valid. Resource limits500,000,000 upload bytes,2,000,000 rows,one worker,page<=100,poll2seconds. Measure runtime/API latency on target machine before claims.

## Inputs, outputs and dependencies

- Inputs: Registered complete dataset, optional eligible model, idempotency key.
- Outputs: Run-bound predictions and evidence.
- Dependencies: Validation/features/artifacts/PostgreSQL.

## Acceptance criteria

| ID | Pass condition and required evidence |
|---|---|
| INF-AC-01 | Submission acknowledgement precedes scoring completion and stages persist. |
| INF-AC-02 | Duplicate scoped key/body returns same resource; changed body409. |
| INF-AC-03 | Crash cannot publish partial success; restart preserves notes/bindings. |
| INF-AC-04 | Population counts and eligible/ineligible nullable fields reconcile. |
| INF-AC-05 | No-winner path yields complete labelled baseline evidence; corrupt active model fails. |

Acceptance status: **NOT_RUN**. Record executed results and artifact hashes; prose requirements are not implementation evidence.
