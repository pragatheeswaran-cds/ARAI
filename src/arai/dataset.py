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
from arai.generator import load_world

MODEL_FEATURES = F.feature_order()


def feature_dir(world_id: str, artifact_root: Path | None = None) -> Path:
    return Path(artifact_root or paths.ARTIFACT_ROOT) / "features" / world_id


def reference_from_worlds(world_ids: list) -> F.Reference:
    """Frozen training statistics from the named worlds (training worlds only)."""
    worlds = [load_world(w) for w in world_ids]
    return F.fit_reference([(w.tables, w.snapshot_date) for w in worlds])


def build_features(world_id: str, reference: F.Reference, artifact_root: Path | None = None) -> F.FeatureResult:
    """Compute and freeze the features and evidence of one world. Reads operational tables only."""
    world = load_world(world_id, artifact_root=artifact_root)
    result = F.compute_features(world.tables, world.snapshot_date, reference)
    out = feature_dir(world_id, artifact_root)
    out.mkdir(parents=True, exist_ok=True)
    result.features.assign(world_id=world_id).to_parquet(out / "features.parquet", index=False)
    result.styles.to_parquet(out / "styles.parquet", index=False)
    result.skus.to_parquet(out / "skus.parquet", index=False)
    result.wardrobing.to_parquet(out / "wardrobing.parquet", index=False)
    result.graph.edges.to_parquet(out / "edges.parquet", index=False)
    meta = {"world_id": world_id, "feature_order": MODEL_FEATURES, "fallback_uses": result.fallback_uses,
            "reference": reference.to_dict(), "dataset_manifest_sha256": hashlib.sha256(
                json.dumps(world.manifest, sort_keys=True).encode()).hexdigest(),
            "features_sha256": hashlib.sha256((out / "features.parquet").read_bytes()).hexdigest()}
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return result


def load_features(world_id: str, artifact_root: Path | None = None) -> pd.DataFrame:
    return pd.read_parquet(feature_dir(world_id, artifact_root) / "features.parquet")


def labelled(world_ids: list, artifact_root: Path | None = None, private_root: Path | None = None) -> pd.DataFrame:
    """Frozen features of several worlds with the private label joined on. Offline use only."""
    frames = []
    for world_id in world_ids:
        features = load_features(world_id, artifact_root)
        truth = pd.read_parquet(Path(private_root or paths.PRIVATE_TRUTH_ROOT) / world_id / "customer_truth.parquet")
        frames.append(features.merge(truth[["customer_id", "y_abuse"]], on="customer_id", validate="one_to_one"))
    return pd.concat(frames, ignore_index=True)
