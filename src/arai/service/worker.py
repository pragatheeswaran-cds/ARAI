"""The single scoring worker and startup reconciliation (final-spec components 11 and 14)."""
from __future__ import annotations

import logging
import shutil
import threading
import time
import uuid

from arai import bundles
from arai.service import datasets, ingest, memo, results, scoring, views
from arai.service.config import ServiceConfig
from arai.service.store import Cancelled, Store

log = logging.getLogger("arai.worker")


STALE_UPLOAD_SECONDS = 3600


def reconcile(config: ServiceConfig, store: Store) -> dict:
    """Bring the database back into agreement with what happened, after a stop or a crash, and load offline files.

    - a run this worker still holds as running belonged to its own earlier process, which died: it becomes
      interrupted. It has no results, because results are written in the transaction that marks success;
    - published experiment reports and the truth export are loaded into the database;
    - earlier succeeded runs whose results exist only as files are imported once; if the files are gone the run
      is marked failed instead of pointing at nothing.
    No file or directory of a run is ever deleted here. Notes, bindings and earlier results are never touched.
    """
    interrupted = store.interrupt_running(config.worker_id)
    experiments = ingest.sync_published(config, store)
    legacy = ingest.import_legacy_runs(config, store)
    incoming = datasets.datasets_root(config.artifact_root)
    if incoming.is_dir():
        for path in incoming.glob(".incoming-*"):               # an abandoned upload; a fresh one may still be in flight
            if time.time() - path.stat().st_mtime > STALE_UPLOAD_SECONDS:
                shutil.rmtree(path, ignore_errors=True)
    log.info("reconciled: interrupted=%d experiments=%d imported=%d output_missing=%d", len(interrupted), len(experiments),
             len(legacy["imported"]), len(legacy["output_missing"]))
    return {"interrupted": interrupted, "experiments": experiments, **legacy}


def process_one(config: ServiceConfig, store: Store, hook=None) -> str | None:
    """Claim and process one queued run. Returns its id, or None if the queue was empty.

    `hook(stage)` is called at each stage; tests use it to simulate a crash.
    """
    run = store.claim_next_run(config.worker_id)
    if run is None:
        return None
    run_id, started = run["id"], time.time()

    def stage(name: str, progress: float) -> None:
        store.update_stage(run_id, name, progress)
        store.heartbeat(config.worker_id)
        if hook:
            hook(name)

    try:
        stage("validate", 0.05)
        bundle = bundles.load_bundle(run["model_id"], config.artifact_root)        # the bound bundle, verified again
        tables, manifest = datasets.load(config.artifact_root, store.get_dataset(run["dataset_id"]))
        output = scoring.score_snapshot(tables, manifest, bundle, on_stage=stage)
        stage("publish", 0.9)
        counts = results.counts(output.summary)
        if not store.finish_run(run_id, config.worker_id, dict(output.summary, run_id=run_id), counts, results.tables(output)):
            log.warning("run=%s was no longer owned by this worker; nothing was published", run_id)
        else:
            log.info("run=%s stage=done duration=%.1fs eligible=%d selected=%d model=%s", run_id, time.time() - started,
                     counts["eligible_count"], counts["selected_count"], run["model_id"])
            write_memos(config, store, run_id)                         # after success: the results are served while memos arrive
    except Cancelled:
        store.cancel_run(run_id, config.worker_id)
        log.info("run=%s cancelled at stage", run_id)
    except Exception as error:                                   # any failure fails the run, never the worker
        request_id = uuid.uuid4().hex
        code = "model_invalid" if isinstance(error, bundles.BundleError) else "scoring_failed"
        message = ("The bound model bundle failed verification." if code == "model_invalid"
                   else "Scoring failed before results were published. No partial result was kept.")
        store.fail_run(run_id, code, message, request_id)
        log.exception("run=%s error_code=%s request_id=%s", run_id, code, request_id)
    return run_id


def write_memos(config: ServiceConfig, store: Store, run_id: str) -> dict | None:
    """Draft the investigation memos of a succeeded run from each case as the API serves it. Nothing here can fail the run."""
    try:
        run = store.get_run(run_id)
        case_of = lambda customer_id: views.case_body(store, run, store.run_customer(run_id, customer_id, run["world_id"], run["dataset_id"]),
                                                      lambda r: r)
        return memo.write_memos(config, store, run_id, case_of)
    except Exception:                                                # the run has succeeded; memos are a draft on top
        log.exception("run=%s memos could not be drafted", run_id)
        return None


def run_forever(config: ServiceConfig, store: Store, stop: threading.Event | None = None) -> None:
    """Process the queue until told to stop. A database or filesystem hiccup is logged and retried, never fatal."""
    stop = stop or threading.Event()
    failures = 0
    while not stop.is_set():
        try:
            store.heartbeat(config.worker_id)
            idle = process_one(config, store) is None
            failures = 0
        except Exception:                                        # e.g. the database is briefly unreachable
            failures += 1
            log.exception("worker loop error (%d in a row); retrying", failures)
            stop.wait(min(30.0, config.poll_seconds * 2 ** min(failures, 4)))
            continue
        if idle:
            stop.wait(config.poll_seconds)


def start_thread(config: ServiceConfig, store: Store) -> tuple:
    """Run the worker inside the serving process (local profile). Returns (thread, stop event)."""
    stop = threading.Event()
    thread = threading.Thread(target=run_forever, args=(config, store, stop), name="arai-worker", daemon=True)
    thread.start()
    return thread, stop
