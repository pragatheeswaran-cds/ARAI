"""Dataset registration: validate an uploaded snapshot and store it immutably (final-spec components 04, 12, 14).

Storage paths are generated here from the content hash; no client-supplied name or path is ever used.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

import pandas as pd

from arai.operational import TABLES, read_csv_world
from arai.service.store import Conflict, Store, snapshot_conflict_message
from arai.validation import MAX_UPLOAD_BYTES, Report, validate_world


class Rejected(Exception):
    """The upload failed structural validation (HTTP 422)."""

    def __init__(self, report: Report | None, message: str, code: str = "validation_failed"):
        super().__init__(message)
        self.report, self.message, self.code = report, message, code


class TooLarge(Exception):
    """The upload exceeds a resource limit (HTTP 413)."""


def datasets_root(artifact_root: Path) -> Path:
    return Path(artifact_root) / "datasets"


def register(store: Store, artifact_root: Path, manifest_text: str, files: dict) -> tuple:
    """Validate and register one snapshot. Returns (dataset row, created).

    `files` maps each of the seven table names to the uploaded bytes. Anything else was rejected by the caller.
    """
    if set(files) != set(TABLES):
        raise Rejected(None, "Exactly the seven operational tables are required.", "invalid_upload")
    if sum(len(content) for content in files.values()) > MAX_UPLOAD_BYTES:
        raise TooLarge("upload exceeds the size limit")
    try:
        manifest = json.loads(manifest_text)
    except (TypeError, ValueError):
        raise Rejected(None, "The manifest is not valid JSON.", "invalid_manifest") from None
    if not isinstance(manifest, dict):
        raise Rejected(None, "The manifest must be a JSON object.", "invalid_manifest")

    manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8") + b"\n"
    manifest_hash = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    root = datasets_root(artifact_root)
    incoming = root / f".incoming-{uuid.uuid4().hex}"
    operational = incoming / "operational"
    operational.mkdir(parents=True)
    try:
        (operational / "manifest.json").write_bytes(manifest_bytes)
        for name in TABLES:
            (operational / f"{name}.csv").write_bytes(files[name])
        report = validate_world(operational)
        if report.violations and any(v["rule_id"] == "L001" for v in report.violations):
            raise TooLarge("upload exceeds a resource limit")
        if not report.accepted:
            raise Rejected(report, "The snapshot failed structural validation; nothing was stored.")
        world_id = manifest["world_id"]
        existing = store.dataset_by_snapshot(world_id, manifest["cutoff"])       # a dataset is a snapshot: world and cutoff (AM-68)
        if existing and existing["manifest_hash"] != manifest_hash:
            raise Conflict("world_content_differs", snapshot_conflict_message(world_id, manifest["cutoff"]))
        tables, _ = read_csv_world(operational)
        parquet = incoming / "parquet"
        parquet.mkdir()
        for name, table in tables.items():
            table.to_parquet(parquet / f"{name}.parquet", index=False)
        dataset_id = "ds-" + manifest_hash[:20]
        final = root / dataset_id
        if existing and (Path(artifact_root) / existing["artifact_key"] / "parquet").is_dir():
            return existing, False                        # identical content, already stored
        row, created = store.register_dataset({
            "id": dataset_id, "world_id": world_id, "manifest_hash": manifest_hash, "schema_version": manifest["schema_version"],
            "cutoff": manifest["cutoff"], "history_start": manifest["history_start"], "purpose": manifest["purpose"],
            "customer_count": int(len(tables["customer_master"])), "artifact_key": f"datasets/{dataset_id}"})
        if not (final / "parquet").is_dir():              # new, or registered earlier and its files have since vanished
            if final.exists():
                shutil.rmtree(final)
            os.replace(incoming, final)
        return row, created
    finally:
        if incoming.exists():
            shutil.rmtree(incoming, ignore_errors=True)


def load(artifact_root: Path, dataset: dict) -> tuple:
    """(tables, manifest) of a registered dataset, after checking that the stored files are still the registered ones."""
    base = Path(artifact_root) / dataset["artifact_key"]
    manifest = json.loads((base / "operational" / "manifest.json").read_text(encoding="utf-8"))
    for name in TABLES:
        path = base / "operational" / f"{name}.csv"
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["files"][name]["sha256"]:
            raise ValueError(f"stored file {name}.csv no longer matches the registered manifest")
    tables = {name: pd.read_parquet(base / "parquet" / f"{name}.parquet") for name in TABLES}
    return tables, manifest
