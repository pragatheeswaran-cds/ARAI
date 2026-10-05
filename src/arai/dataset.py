"""Feature artifacts and model matrices (final-spec components 06 and 07).

Features are computed per world from operational tables and frozen on disk. Private labels are joined only
afterwards, in `labelled`, and only for offline training and evaluation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from arai import features as F
from arai import paths
from arai.generator import world as generated
from arai.generator.assemble import OPERATIONAL_TABLES

MODEL_FEATURES = F.feature_order()
EVIDENCE_FEATURES = F.evidence_features()


def feature_dir(world_id: str, artifact_root: Path | None = None) -> Path:
    return Path(artifact_root or paths.ARTIFACT_ROOT) / "features" / world_id


def load_manifest(world_id: str, artifact_root: Path | None = None) -> tuple:
    """(world directory, operational manifest) of a stored world."""
    base = Path(artifact_root or paths.ARTIFACT_ROOT) / "worlds" / world_id
    return base, json.loads((base / "operational" / "manifest.json").read_text(encoding="utf-8"))


def load_operational(world_id: str, artifact_root: Path | None = None) -> tuple:
    """(tables, manifest) of a stored world. Private truth is never opened on this path."""
    base, manifest = load_manifest(world_id, artifact_root)
    tables = {name: pd.read_parquet(base / "parquet" / f"{name}.parquet") for name in OPERATIONAL_TABLES}
    return tables, manifest


def snapshot_date(manifest: dict):
    return pd.Timestamp(manifest["cutoff"][:10]).date()


def reference_from_worlds(world_ids: list, artifact_root: Path | None = None) -> F.Reference:
    """Frozen training statistics from the named worlds (training worlds only)."""
    worlds = [load_operational(w, artifact_root) for w in world_ids]
    return F.fit_reference([(tables, snapshot_date(manifest)) for tables, manifest in worlds])


def build_features(world_id: str, reference: F.Reference, artifact_root: Path | None = None) -> F.FeatureResult:
    """Compute and freeze the features and evidence of one world. Reads operational tables only."""
    tables, manifest = load_operational(world_id, artifact_root)
    result = F.compute_features(tables, snapshot_date(manifest), reference)
    out = feature_dir(world_id, artifact_root)
    out.mkdir(parents=True, exist_ok=True)
    result.features.assign(world_id=world_id).to_parquet(out / "features.parquet", index=False)
    result.styles.to_parquet(out / "styles.parquet", index=False)
    result.skus.to_parquet(out / "skus.parquet", index=False)
    result.wardrobing.to_parquet(out / "wardrobing.parquet", index=False)
    result.graph.edges.to_parquet(out / "edges.parquet", index=False)
    meta = {"world_id": world_id, "feature_order": MODEL_FEATURES, "fallback_uses": result.fallback_uses,
            "reference": reference.to_dict(), "dataset_manifest_sha256": hashlib.sha256(
                json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
            "features_sha256": hashlib.sha256((out / "features.parquet").read_bytes()).hexdigest()}
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return result


def verify_truth(world_id: str, artifact_root: Path | None = None, private_root: Path | None = None) -> Path:
    """Check that the private truth on disk is the truth written with this operational world; returns its directory.

    A world is written in place, so an interrupted or partial regeneration could leave new tables beside old truth.
    The private manifest records the hash of the operational manifest it was written with and of every truth file.
    """
    sha256 = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()  # noqa: E731
    operational = Path(artifact_root or paths.ARTIFACT_ROOT) / "worlds" / world_id / "operational" / "manifest.json"
    private = Path(private_root or paths.PRIVATE_TRUTH_ROOT) / world_id
    record = private / "private-manifest.json"
    if not record.is_file():
        raise ValueError(f"{world_id}: private truth has no manifest; regenerate the world before joining labels")
    recorded = json.loads(record.read_text(encoding="utf-8"))
    if recorded["operational_manifest_sha256"] != sha256(operational):
        raise ValueError(f"{world_id}: private truth was written with a different operational world; regenerate the world")
    for name, entry in recorded["files"].items():
        path = private / entry["filename"]
        if not path.is_file() or sha256(path) != entry["sha256"]:
            raise ValueError(f"{world_id}: truth table {name} is missing or differs from the one written with the world")
    return private


def load_world(world_id: str, artifact_root: Path | None = None, private_root: Path | None = None):
    """A stored world with its private truth, after checking that the truth belongs to it. Offline use only."""
    verify_truth(world_id, artifact_root, private_root)
    return generated.load_world(world_id, artifact_root, private_root)


def load_features(world_id: str, artifact_root: Path | None = None) -> pd.DataFrame:
    return pd.read_parquet(feature_dir(world_id, artifact_root) / "features.parquet")


def labelled(world_ids: list, artifact_root: Path | None = None, private_root: Path | None = None) -> pd.DataFrame:
    """Frozen features of several worlds with the private label joined on. Offline use only."""
    frames = []
    for world_id in world_ids:
        features = load_features(world_id, artifact_root)
        truth = pd.read_parquet(verify_truth(world_id, artifact_root, private_root) / "customer_truth.parquet")
        frames.append(features.merge(truth[["customer_id", "y_abuse"]], on="customer_id", validate="one_to_one"))
    return pd.concat(frames, ignore_index=True)
