# Batch inference and job lifecycle

Version 1.8 (amended 2026-10-05) | Implementation baseline | Component INF

## Requirements and boundary

Bind dataset and active promoted or valid baseline hash at submission. Queue one worker. States queued->running->succeeded|failed; crashed running ->interrupted on restart. Queued can resume. Retry failed/interrupted creates new run with original bindings and new key.

Stages: validate snapshot ->features/graph/style ->eligibility ->frozen preprocessing ->score/reference percentile/rank/top5% ->evidence ->atomic publication. No results before succeeded. Results are written to PostgreSQL in the transaction that marks success, so a crash or a failed write leaves no partial output (component 14). Reconciliation interrupts only runs held by this worker identity and deletes no run directory. A run scored before version 1.7 whose result files are gone is reported as failed (output_missing). Each run records a drift report with its summary: the share of eligible customers at or above the training 50th, 90th, 95th and 99th score percentile, and the features whose median lies outside the training 10th-90th percentile range. It warns when the share above the 95th percentile leaves .025-.10, when an input is out of range, and when the scoring code differs from the code the bundle was published with. The report describes; it never refits, corrects or promotes. The worker loop survives a transient database error; in the single-process profile readiness is false when the worker has stopped.

Prediction fields include run_id/model_id/model_kind/dataset_id/world_id/cutoff/customer_id, eligibility_status, nullable raw_score/risk_score/rank, selected_for_review, nullable baseline_rank, baseline_selected, support_counts/evidence_refs/wardrobing. baseline_rank orders eligible customers by raw_return_rate under the standard tie rule and baseline_selected marks its top k, the same k as the model; ineligible customers get null/false; under baseline fallback they equal rank/selected_for_review. The run records model_only_count and baseline_only_count. Ineligible unranked scores null selected=false, but case evidence visible. Customer evidence includes source transactions, mature/raw/expected/value denominators, products, supported neighbors, separate wardrobing. Contract 1.6.0 (AM-57): the evidence stage groups the supported edges into communities (connected components; Louvain with a fixed seed only inside a component of thirteen or more members) and gives each the kind one stated rule over observed evidence yields (ring: a coordinated claim match on an edge, two or more members selected, or a member with a coordinated claim share above zero; household otherwise); the run records community_count and ring_count. The kind is evidence about the group, never a verdict on a member. Contract 1.7.0 (AM-58): after selection the evidence stage re-scores every eligible customer with the frozen pipeline once per feature family (claims, timing, expected_vs_actual, composition, volume; together the 43 model features) with that family at the bundle's training median, predict-side only, and records the score without it and whether the raw score stays at or above the raw score at rank k; it orders the evidence tags by those family deltas and evaluates the analyst rulebook's five rules from the bundle's training thresholds. Nothing is fitted and no score, rank or selection changes. No private truth or causal claims.

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
| INF-AC-06 | baseline_rank/baseline_selected use the same k and ties as the model, equal rank/selection under fallback, and the run counts match the comparison filters. |
| INF-AC-07 | A run records its drift report; shifted scores or inputs and a changed scoring code each raise a warning, and a snapshot like training raises none. |

Acceptance status is recorded per criterion in acceptance-register.csv (status, evidence, date, reviewer). Prose requirements are not implementation evidence.
