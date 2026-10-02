# Serving, front end and runtime, 2026-10-02

Specification v1.5, components 10 (artifacts), 11 (inference), 12 (API), 13 (UI), 14 (storage), 15 (deployment).
Source: `src/arai/bundles.py`, `src/arai/publishing.py`, `src/arai/service/`, `src/arai/operational.py`,
`src/arai/ranking.py`, `src/arai/cli.py`, `web/`, `Dockerfile`, `docker-compose.yml`, `deploy/`.

## What exists

- **Bundles.** An immutable directory per model, named by a hash of its own content: the fitted pipeline (none
  for the baseline), the ordered feature schema, the frozen category fallbacks, the sorted training score
  reference and provenance. Loading verifies every file hash, the feature schema against the contract, library
  versions and the serialised types before anything is used. The active pointer is replaced atomically and keeps
  a history. Promoted: `m-9cddb57173724327cd08ed8a` (boosted trees, 15 leaves); baseline
  `b-18b8321c6b190ef9cd738b1d` (pointer version 2; version 1 named the same estimator bundled before the review
  fixes changed the code hash; both bundles remain on disk and the first run stays bound to the first).
- **Storage.** PostgreSQL through versioned SQL migrations: datasets, models, the active model, runs,
  experiments, append-only reviews, idempotency keys. Artifact keys are relative to the artifact root.
- **Inference.** Stages validate, features, eligibility, scoring, evidence, publish. Output is written to a
  staging directory, marked complete, renamed into place, and only then recorded as succeeded. One worker claims
  runs with `FOR UPDATE SKIP LOCKED`. A run keeps the dataset and bundle it was submitted with.
- **API.** FastAPI under `/api/v1`, the sixteen operations of `contracts/openapi.yaml` (1.2.0) and no other.
  Every response body in the service tests is validated against the contract.
- **UI.** React/Vite/TypeScript with types generated from the contract: overview, datasets and runs, customer
  queue and case (evidence, timeline, relationships, notes), style queue and detail, evaluation.
- **Runtime.** `arai local` (embedded PostgreSQL, API, worker and built UI in one process) and a Compose file
  (PostgreSQL, API, worker, nginx with the UI).

## Measured

| Check | Result |
|---|---|
| Python tests | 162 pass (bundles 15, service 33, plus the offline suites) |
| Front-end unit tests | 8 pass |
| Browser walkthrough of the running application | 44 of 44 checks (`reports/ui/2026-10-02/walkthrough-result.json`, screenshots beside it) |
| Browser check of the baseline-fallback state on a temporary instance | 11 of 11 checks (`fallback-result.json`) |
| Upload and validation of a 10,000-customer world through the API | 9-11 seconds |
| Scoring that world | about 12 seconds, development machine |
| Same world scored in the Linux container and on Windows | identical eligibility, scores (largest difference 0.0), ranks, review set and baseline ranks |
| Fixture world 2001 generated in the Linux container | all seven CSV files byte-identical to the Windows-generated world |
| Compose stack | builds from a clean context; health reports the promoted model; `data/private` is not visible in any container |

In the demonstration world the run scores 5,690 eligible customers, selects 285, and the model's and the rule's
lists differ in 215 customers each.

## An incident worth recording

Starting the Compose stack while `arai local` was running exposed a data-loss bug. Both pointed at the same
artifact folder with different databases, and the Compose worker's startup clean-up deleted the local stack's
published run because that run was not in its own database. The run was rescored; nothing irreplaceable was
lost. The clean-up now removes only directories of runs that its own database knows and that never reached
success; any other directory is left untouched and logged (test added). The API also shows a succeeded run
whose files have gone as failed at once, instead of waiting for a restart. Two deployments should still not
share one artifact folder.

## Review findings and what was done

Front end and deployment: `records/2026-10-02-frontend-critic-review.md`.

| Finding | Action |
|---|---|
| Target shown without saying it was not met | The evaluation page now says "not met" in a callout at the top and beside the figure. |
| Timing dependence buried at the bottom | The top row carries "Without timing features" and a "Read this first" callout states it. |
| Dangling succeeded run | Fixed in the API (see the incident above). |
| Double click creates two runs | One key per intended submission; buttons disabled while a request is in flight. |
| Late "load more" page mixes filters | Pages issued for an older filter set are dropped. |
| Hard-coded world protocol | Removed. |
| Coverage sentence without scope | Scoped to validation; the test figure added. |
| Case page does not say why model and rule differ | A "What the record shows" panel states four facts in plain words: return rate against expected, claims, late returns, linked accounts with matching claims. |
| Tabs without a tab panel | `tabpanel`, `aria-controls` and `aria-labelledby` added. |
| Request for `/experiments/none` | Not sent any more. |
| nginx does not protect the UI in the VM profile | Not done: the VM profile was not deployed (OPS-AC-05 stays NOT_RUN). The API enforces the shared login; a TLS proxy with the same login in front of nginx is still needed for a VM. |
| Empty service from a clean clone | By design; the README says the artifact folder must be produced or copied. |

Serving side: `records/2026-10-02-serving-critic-review.md`, with dispositions in that record's closing section.

## Not done

- No VM deployment, TLS or IP allow-list (OPS-AC-05).
- No database dump-and-restore rehearsal; no rehearsal on the presentation machine (STORE-AC-05, OPS-AC-06 and
  TEST-AC-04 are partial).
- Upload size and row limits have no fixture at the limit.
- The UI has no graph visualisation; relationships are a table, as the specification allows.
