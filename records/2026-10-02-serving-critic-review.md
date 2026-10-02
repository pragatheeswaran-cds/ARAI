# Independent review of the serving side, 2026-10-02

Reviewer: an independent critic agent on the Fable model, briefed as a chief data scientist and ML systems
architect. It worked read-only on commit `f9e3961` and the working tree, built its own temporary instances for
write paths, and sent only GET requests to the live instance. "M" marks what it measured, "R" what it read.
The text below is the critic's report, lightly reformatted; the closing section records what was done.

## Verdict

**Fit to demonstrate as is** for a local, single-operator demonstration. Train/serve skew is zero, the live
instance conforms to the contract, and no label leaks. Two robustness and defence gaps should be fixed before
any shared or VM deployment, not before the demonstration.

## Findings

No blocker.

**MAJOR 1 (M). The serialised-type allow-list was not real protection** (`bundles.load_pipeline`). The check
accepted any type whose name began with `sklearn.` or `numpy.` and then loaded the file trusting everything
found. The reviewer built a model file naming `numpy.testing._private.utils.runstring` (which executes code);
the prefix check passed and the payload ran. File hashes make a swapped model evident only against someone who
cannot also rewrite the bundle's own metadata: integrity, not authenticity. Fix: an exact set of type names.

**MAJOR 2 (M). One transient database error killed the worker for good** (`worker.run_forever`). With no
exception handling around the loop, an error while claiming a run ended the thread; in the single-process
profile the API kept reporting ready while the queue never drained. Fix: catch, log, back off; make readiness
reflect a dead worker.

**MINOR 3 (M). Startup reconciliation ignored ownership.** A second process reconciling beside a live worker
marked the live run interrupted; the live worker then discarded its finished output. Fix: interrupt only runs
this worker identity holds.

**MINOR 4 (M). A dataset whose files vanished was stuck**: the identical upload returned the existing record
without restoring the files, and every run on it failed. Fix: restore the files on an identical upload.

**MINOR 5 (M). Forged cursors returned 500.** The cursor's context hash is unkeyed and the position was not
type-checked: a well-formed cursor with a nonsense position crashed the queue and run lists (the body stayed
safe). Fix: validate the position's shape per list.

**MINOR 6 (M). Health was expensive**: it loaded both bundles from disk and wrote to the database on every call
(267 ms median); the UI polls it. Fix: cache on the state of the files.

**MINOR 7 (R/M). Provenance recorded but unchecked**: the bundle's dependency-lock hash differs from the current
lock (library versions still equal, so loading passes). `retry_of` exists in the schema and is never filled.

**MINOR 8 (R). Truth export**: `/experiments/{id}/truth` serves the labels of the same world the live run
shows, so the demonstration queue's labels are one join away. It is labelled synthetic, separate from inference
and never read from the private root at serving time: defensible, but the page did not say which world it
reveals.

**MINOR 9 (M).** The `x-request-id` header was absent on 500 responses (the body carried it).

**Test gaps.** No test for the publishing step or for the experiment routes with data; the 413 limit; cursors on
run and review lists; the 401 body against the schema; the "unknown type" case passed trivially; no database
backup and restore.

## Checked and found sound

- **Skew (M, test world W2301).** Operational CSV through `score_snapshot` with the promoted bundle against the
  frozen features and the candidate pipeline: 28 feature columns identical, eligibility identical (5,669),
  largest score difference 0.0, ranks, review set (284), baseline ranks and baseline set identical, percentile
  difference 0.0, ineligible rows null and unselected. The published demonstration run equals a fresh scoring on
  every column.
- **Live GET sweep (M).** Health, dataset and run lists, 10,000 customers paged, 35 cases, styles, 5 style
  details, the experiment and truth pages and error bodies: no schema violation; the comparison parts are 215 /
  215 / 70 and match the run counts; no label-like token in any case or style response; a path-traversal
  request for a file outside the UI returns the UI's index page.
- **Privacy boundary (R/M).** The service imports no offline module; Compose mounts the artifact folder only;
  the image excludes data; evidence tags and the wardrobing indicator derive from measured features only.
- **Concurrency (M).** Six simultaneous uploads of two contents for one world gave exactly one 201, two 200 and
  three 409, with one directory. Idempotency scope and the 409 on a changed body match the specification; the
  claim uses `FOR UPDATE SKIP LOCKED`; a crash before publication leaves nothing; a note on a queued run is 409.
- **Bundles (R/M).** The identifier is excluded from the hashed manifest; activation verifies both bundles and
  then renames; feature-order and library checks refuse mismatches; publication stages, marks and renames.
- CORS allow-list and the VM-profile login as specified.

## Not checked

The Docker instance beyond health; the React UI; database backup and restore; VM TLS and IP allow-list; the
500 MB and 2,000,000-row limits; nginx authorisation pass-through; latency under concurrent load.

## What was done

| Finding | Action |
|---|---|
| Allow-list by prefix | `bundles.TRUSTED_TYPES` is now an exact set of four names (the three families' own types); loading trusts only that set. Tests: a `numpy.`-prefixed hostile name is refused; the shipped candidates serialise nothing outside the set. Bundles are still integrity-checked, not signed: the artifact folder must be writable only by the operator. |
| Worker dies on a database error | The loop catches, logs and backs off; in the single-process profile health reports scoring not ready if the worker thread has stopped. Tests added. |
| Reconciliation ignores ownership | Only runs claimed by this worker identity are interrupted; directories of runs unknown to this database are never deleted. Tests added. |
| Vanished dataset stuck | An identical upload restores the files. Test added. |
| Forged cursors | Positions are type-checked per list; malformed ones return 422. Test added. |
| Health cost | The verified state is cached on the modification time and size of the pointer and bundle files, so a changed or corrupted file is still noticed. |
| Lock hash unchecked | A warning is logged when a bundle was built under another lock; library versions are still compared exactly. `retry_of` is left unfilled: the contract's run request has no field for it. |
| Truth page does not name its world | `TruthPage.world_id` added to the contract and shown on the evaluation page. |
| Header missing on 500 | Added. |
| Test gaps | Added: published report against the contract and the offline reports, experiment and truth routes, 413, cursors on runs and reviews, the 401 body, relocation of the artifact root. Still missing: a fixture at the real 500 MB and 2,000,000-row limits, and a database dump and restore. |
