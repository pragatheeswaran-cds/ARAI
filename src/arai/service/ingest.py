"""Loading offline files into PostgreSQL (final-spec component 14, decision AM-39).

The API reads only the database. Two kinds of file still exist outside it and are loaded here, by the worker at
startup and never by a request: the experiment report and truth export that `arai publish` writes, and the result
files of runs that were scored before results moved into the database.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from arai.service import results
from arai.service.config import ServiceConfig
from arai.service.scoring import RunOutput
from arai.service.store import Store

log = logging.getLogger("arai.ingest")
LEGACY_TABLES = ("customers", "styles", "skus", "neighbors", "timeline", "customer_styles")
LEGACY_OPTIONAL = ("communities", "attributions")                 # result files a later version writes beside the six; absent from earlier runs
LEGACY_MARKER = "COMPLETE"


def _truth(path: Path) -> tuple:
    """(world, rows) of a truth export in its published order; (None, []) when none was published."""
    if not path.is_file():
        return None, []
    frame = pd.read_parquet(path)
    if not len(frame):
        return None, []
    # exports written before the world was recorded carry it only as the prefix of the customer identifier
    world = str(frame["world_id"].iloc[0]) if "world_id" in frame else str(frame["customer_id"].iloc[0]).rsplit("-", 1)[0]
    rows = [(position, str(customer_id), int(y_abuse), [kind for kind in str(kinds or "").split("|") if kind])
            for position, (customer_id, y_abuse, kinds) in enumerate(zip(frame["customer_id"].tolist(), frame["y_abuse"].tolist(),
                                                                         frame["action_types"].tolist()))]
    return world, rows


def sync_published(config: ServiceConfig, store: Store) -> list:
    """Load every published experiment report, with its truth export, into the database. Returns the identifiers."""
    root = Path(config.artifact_root) / "experiments"
    loaded = []
    if not root.is_dir():
        return loaded
    for path in sorted(root.glob("*/published/experiment.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        base = path.parents[1]
        rel = lambda p: p.relative_to(config.artifact_root).as_posix() if p.is_file() else None  # noqa: E731
        world, rows = _truth(path.with_name("truth.parquet"))
        store.load_experiment({"id": report["summary"]["experiment_id"], "config_hash": report["summary"]["config_hash"],
                               "report_key": rel(path), "selection_key": rel(base / "selection.json"),
                               "test_key": rel(base / "reports" / "test.json")}, report, world, rows)
        loaded.append(report["summary"]["experiment_id"])
    return loaded


def import_legacy_runs(config: ServiceConfig, store: Store) -> dict:
    """Load the result files of earlier succeeded runs into the database, once each. The files are left in place.

    A run whose files are gone is marked failed (output_missing) instead of staying succeeded with nothing behind it.
    """
    imported, missing = [], []
    for run_id in store.runs_without_results():
        directory = Path(config.artifact_root) / "runs" / run_id
        names = ["run.json", LEGACY_MARKER, *(f"{name}.parquet" for name in LEGACY_TABLES)]
        if not all((directory / name).is_file() for name in names):
            store.mark_output_missing(run_id)
            missing.append(run_id)
            continue
        try:
            summary = json.loads((directory / "run.json").read_text(encoding="utf-8"))
            present = [*LEGACY_TABLES, *(name for name in LEGACY_OPTIONAL if (directory / f"{name}.parquet").is_file())]
            output = RunOutput(summary=summary, **{name: pd.read_parquet(directory / f"{name}.parquet") for name in present})
            if store.import_results(run_id, summary, results.tables(output)):
                imported.append(run_id)
        except Exception:                                        # noqa: BLE001  one unreadable run must not stop the others
            log.exception("run=%s result files could not be imported; the run stays unavailable until they can", run_id)
    return {"imported": imported, "output_missing": missing}
