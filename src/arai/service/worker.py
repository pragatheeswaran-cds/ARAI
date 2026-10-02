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


def reconcile(config: ServiceConfig, store: Store) -> dict:
    """Bring files and database back into agreement after a stop or a crash.

    - a run still marked running belonged to a process that died: it becomes interrupted;
    - staging directories and published directories of runs that never reached success are removed;
    - a succeeded run whose files have disappeared is marked failed instead of pointing at nothing.
    Notes, bindings and earlier results are never touched.
    """
    interrupted = store.interrupt_running()
    succeeded = {row["id"] for row in store.succeeded_runs()}
    removed = []
    root = scoring.runs_root(config.artifact_root)
    if root.is_dir():
        for path in root.iterdir():
            if path.is_dir() and (path.name.startswith(".staging-") or path.name not in succeeded):
                shutil.rmtree(path, ignore_errors=True)
                removed.append(path.name)
    missing = [run_id for run_id in succeeded if not scoring.is_complete(scoring.output_dir(config.artifact_root, run_id))]
    for run_id in missing:
        store.mark_output_missing(run_id)
    incoming = datasets.datasets_root(config.artifact_root)
    if incoming.is_dir():
        for path in incoming.glob(".incoming-*"):
            shutil.rmtree(path, ignore_errors=True)
    log.info("reconciled: interrupted=%d removed=%d output_missing=%d", len(interrupted), len(removed), len(missing))
    return {"interrupted": interrupted, "removed": removed, "output_missing": missing}


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
    stop = stop or threading.Event()
    while not stop.is_set():
        if process_one(config, store) is None:
            stop.wait(config.poll_seconds)


def start_thread(config: ServiceConfig, store: Store) -> tuple:
    """Run the worker inside the serving process (local profile). Returns (thread, stop event)."""
    stop = threading.Event()
    thread = threading.Thread(target=run_forever, args=(config, store, stop), name="arai-worker", daemon=True)
    thread.start()
    return thread, stop
