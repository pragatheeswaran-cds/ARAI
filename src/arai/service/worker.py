"""The single scoring worker and startup reconciliation (final-spec components 11 and 14)."""
from __future__ import annotations

import logging
import shutil
import threading
import time
import uuid

from arai import bundles
from arai.service import datasets, scoring
from arai.service.config import ServiceConfig
from arai.service.store import Store

log = logging.getLogger("arai.worker")


STALE_UPLOAD_SECONDS = 3600


def reconcile(config: ServiceConfig, store: Store) -> dict:
    """Bring files and database back into agreement after a stop or a crash.

    - a run still marked running belonged to a process that died: it becomes interrupted;
    - staging and published directories of THIS database's runs that never reached success are removed;
    - a succeeded run whose files have disappeared is marked failed instead of pointing at nothing.
    A directory that belongs to no run in this database is never touched: it may be another deployment's result
    sharing the artifact root, and deleting it would destroy data this process knows nothing about. Notes,
    bindings and earlier results are never touched.
    """
    interrupted = store.interrupt_running(config.worker_id)
    statuses = store.run_statuses()
    removed, unknown = [], []
    root = scoring.runs_root(config.artifact_root)
    if root.is_dir():
        for path in root.iterdir():
            if not path.is_dir():
                continue
            run_id = path.name.removeprefix(".staging-")
            if run_id not in statuses:
                unknown.append(path.name)
            elif path.name.startswith(".staging-") or statuses[run_id] != "succeeded":
                shutil.rmtree(path, ignore_errors=True)
                removed.append(path.name)
    missing = [run_id for run_id, status in statuses.items()
               if status == "succeeded" and not scoring.is_complete(scoring.output_dir(config.artifact_root, run_id))]
    for run_id in missing:
        store.mark_output_missing(run_id)
    incoming = datasets.datasets_root(config.artifact_root)
    if incoming.is_dir():
        for path in incoming.glob(".incoming-*"):               # an abandoned upload; a fresh one may still be in flight
            if time.time() - path.stat().st_mtime > STALE_UPLOAD_SECONDS:
                shutil.rmtree(path, ignore_errors=True)
    if unknown:
        log.warning("left untouched: %d run directories that belong to no run in this database (is the artifact root shared?)", len(unknown))
    log.info("reconciled: interrupted=%d removed=%d output_missing=%d unknown=%d", len(interrupted), len(removed), len(missing), len(unknown))
    return {"interrupted": interrupted, "removed": removed, "output_missing": missing, "unknown": unknown}


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
        if hook:
            hook(name)

    try:
        stage("validate", 0.05)
        bundle = bundles.load_bundle(run["model_id"], config.artifact_root)        # the bound bundle, verified again
        tables, manifest = datasets.load(config.artifact_root, store.get_dataset(run["dataset_id"]))
        output = scoring.score_snapshot(tables, manifest, bundle, on_stage=stage)
        stage("publish", 0.9)
        output_key = scoring.publish(output, config.artifact_root, run_id)
        counts = {name: output.summary[name] for name in ("eligible_count", "excluded_count", "selected_count",
                                                          "model_only_count", "baseline_only_count")}
        if not store.finish_run(run_id, config.worker_id, output_key, counts):
            shutil.rmtree(scoring.output_dir(config.artifact_root, run_id), ignore_errors=True)
            log.warning("run=%s was no longer owned by this worker; output discarded", run_id)
        else:
            log.info("run=%s stage=done duration=%.1fs eligible=%d selected=%d model=%s", run_id, time.time() - started,
                     counts["eligible_count"], counts["selected_count"], run["model_id"])
    except Exception as error:                                   # noqa: BLE001  any failure fails the run, never the worker
        request_id = uuid.uuid4().hex
        code = "model_invalid" if isinstance(error, bundles.BundleError) else "scoring_failed"
        message = ("The bound model bundle failed verification." if code == "model_invalid"
                   else "Scoring failed before results were published. No partial result was kept.")
        shutil.rmtree(scoring.staging_dir(config.artifact_root, run_id), ignore_errors=True)
        store.fail_run(run_id, code, message, request_id)
        log.exception("run=%s error_code=%s request_id=%s", run_id, code, request_id)
    return run_id


def run_forever(config: ServiceConfig, store: Store, stop: threading.Event | None = None) -> None:
    """Process the queue until told to stop. A database or filesystem hiccup is logged and retried, never fatal."""
    stop = stop or threading.Event()
    failures = 0
    while not stop.is_set():
        try:
            idle = process_one(config, store) is None
            failures = 0
        except Exception:                                        # noqa: BLE001  e.g. the database is briefly unreachable
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
