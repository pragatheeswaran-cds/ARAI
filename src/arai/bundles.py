"""Serving bundles and the active pointer (final-spec component 10).

A bundle is an immutable directory holding everything scoring needs and nothing else: the fitted pipeline (none
for the baseline), the ordered feature schema, the frozen category fallbacks and the sorted training score
reference. Its identifier is a hash of its own content, so a bundle cannot be changed without changing its name,
and selection or test reports refer to it by that name instead of being written into it.

Nothing here fits anything. Private truth is never read.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
import skops

from arai import features as F
from arai import modeling, paths

BUNDLE_SCHEMA = "1.0"
BASELINE_KIND = "baseline_fallback"
ADAPTERS = {"supervised": "decision_function", "unsupervised": "negative_score_samples", BASELINE_KIND: "raw_return_rate"}
BASELINE_LABEL = "Return-rate reference percentile"
CODE_FILES = ("features.py", "dataset.py", "modeling.py", "bundles.py")


class BundleError(Exception):
    """A bundle that must not be used: missing, altered, or built for another schema or library."""


@dataclass
class Bundle:
    model_id: str
    kind: str                       # supervised | unsupervised | baseline_fallback
    manifest: dict
    reference_scores: np.ndarray    # sorted training reference (out-of-fold, in-sample for forests, raw rate for the baseline)
    pipeline: object | None         # None for the baseline
    directory: Path

    @property
    def feature_order(self) -> list:
        return self.manifest["feature_order"]

    @property
    def reference(self) -> F.Reference:
        return F.Reference.from_dict(self.manifest["feature_reference"])


def bundle_root(artifact_root: Path | None = None) -> Path:
    return Path(artifact_root or paths.ARTIFACT_ROOT) / "bundles"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def code_sha256() -> str:
    """Hash of the code that turns operational tables into scores."""
    h = hashlib.sha256()
    package = paths.REPO_ROOT / "src" / "arai"
    for name in CODE_FILES:
        h.update(name.encode() + b"\0" + (package / name).read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def _logical_reference_hash(scores: np.ndarray) -> str:
    """Hash of the reference values themselves, independent of how Parquet happens to compress them."""
    return hashlib.sha256(np.sort(np.asarray(scores, dtype="<f8")).tobytes()).hexdigest()


def _write_bundle(manifest: dict, reference_scores: np.ndarray, model_file: Path | None, artifact_root: Path | None) -> str:
    """Stage the bundle in a temporary directory, verify it, then rename it into place. Never overwrites."""
    root = bundle_root(artifact_root)
    root.mkdir(parents=True, exist_ok=True)
    reference_scores = np.sort(np.asarray(reference_scores, dtype=float))
    manifest = dict(manifest, bundle_schema=BUNDLE_SCHEMA, reference_count=int(len(reference_scores)),
                    reference_logical_sha256=_logical_reference_hash(reference_scores),
                    model_sha256=_sha256(model_file) if model_file else None)
    # the identifier covers the content only: it is not stored inside the hashed manifest, so nothing is circular
    model_id = ("b-" if manifest["kind"] == BASELINE_KIND else "m-") + hashlib.sha256(_canonical(manifest)).hexdigest()[:24]
    final = root / model_id
    if final.exists():
        load_bundle(model_id, artifact_root)             # an existing bundle is verified, never rewritten
        return model_id
    staging = root / f".staging-{model_id}-{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    pd.DataFrame({"score": reference_scores}).to_parquet(staging / "reference_scores.parquet", index=False)
    files = {"reference_scores.parquet": _sha256(staging / "reference_scores.parquet")}
    if model_file:
        shutil.copyfile(model_file, staging / "model.skops")
        files["model.skops"] = _sha256(staging / "model.skops")
    (staging / "bundle.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (staging / "files.json").write_text(json.dumps({"model_id": model_id, "files": files}, indent=2) + "\n", encoding="utf-8")
    os.replace(staging, final)
    load_bundle(model_id, artifact_root)
    return model_id


def _provenance(experiment_dir: Path) -> dict:
    config = json.loads((experiment_dir / "config.json").read_text(encoding="utf-8"))
    lock = paths.REPO_ROOT / "uv.lock"
    return {"experiment_id": config["experiment_id"], "training_worlds": config["training_worlds"],
            "training_features_sha256": config["features_sha256"], "experiment_config_sha256": config["experiment_config_sha256"],
            "code_sha256": code_sha256(), "dependency_lock_sha256": _sha256(lock) if lock.exists() else None,
            "libraries": {"scikit-learn": sklearn.__version__, "skops": skops.__version__, "numpy": np.__version__}}


def build_model_bundle(experiment_dir: Path, candidate_id: str, artifact_root: Path | None = None) -> str:
    """Bundle one fitted candidate exactly as training left it. The estimator is copied, never refitted."""
    experiment_dir = Path(experiment_dir)
    source = experiment_dir / "candidates" / candidate_id
    record = json.loads((source / "record.json").read_text(encoding="utf-8"))
    if record["status"] != "fitted":
        raise BundleError(f"{candidate_id} was rejected at fit time: {record['rejection']}")
    if _sha256(source / "model.skops") != record["model_sha256"]:
        raise BundleError(f"{candidate_id}: the fitted model differs from the hash in its training record")
    baseline = json.loads((experiment_dir / "baseline" / "baseline.json").read_text(encoding="utf-8"))
    kind = "supervised" if record["supervised"] else "unsupervised"
    manifest = {"kind": kind, "candidate_id": candidate_id, "family": record["family"], "adapter": ADAPTERS[kind],
                "feature_order": record["features"], "feature_reference": baseline["reference"], "params": record["params"],
                "preprocessing": record["preprocessing"], "reference_kind": record["reference_kind"],
                "score_label": "Training reference percentile", **_provenance(experiment_dir)}
    reference = pd.read_parquet(source / "reference_scores.parquet")["score"].to_numpy()
    return _write_bundle(manifest, reference, source / "model.skops", artifact_root)


def build_baseline_bundle(experiment_dir: Path, artifact_root: Path | None = None) -> str:
    """The fallback: training statistics only. It depends on no candidate and exists before any comparison."""
    experiment_dir = Path(experiment_dir)
    baseline = json.loads((experiment_dir / "baseline" / "baseline.json").read_text(encoding="utf-8"))
    manifest = {"kind": BASELINE_KIND, "candidate_id": None, "family": None, "adapter": ADAPTERS[BASELINE_KIND],
                "feature_order": ["raw_return_rate"], "feature_reference": baseline["reference"], "params": {},
                "preprocessing": [], "reference_kind": "eligible training raw_return_rate", "score_label": BASELINE_LABEL,
                **_provenance(experiment_dir)}
    reference = pd.read_parquet(experiment_dir / "baseline" / "reference_scores.parquet")["score"].to_numpy()
    return _write_bundle(manifest, reference, None, artifact_root)


def load_bundle(model_id: str, artifact_root: Path | None = None) -> Bundle:
    """Verify and load a bundle. Any mismatch raises before the bundle can be used."""
    directory = bundle_root(artifact_root) / model_id
    if "/" in model_id or "\\" in model_id or ".." in model_id or not (directory / "bundle.json").is_file():
        raise BundleError(f"unknown bundle {model_id!r}")
    manifest = json.loads((directory / "bundle.json").read_text(encoding="utf-8"))
    files = json.loads((directory / "files.json").read_text(encoding="utf-8"))
    expected = ("b-" if manifest.get("kind") == BASELINE_KIND else "m-") + hashlib.sha256(_canonical(manifest)).hexdigest()[:24]
    if expected != model_id or files["model_id"] != model_id:
        raise BundleError(f"{model_id}: bundle metadata does not match its identifier")
    if manifest.get("bundle_schema") != BUNDLE_SCHEMA:
        raise BundleError(f"{model_id}: bundle schema {manifest.get('bundle_schema')!r} is not supported")
    for name, digest in files["files"].items():
        if not (directory / name).is_file() or _sha256(directory / name) != digest:
            raise BundleError(f"{model_id}: {name} is missing or altered")
    libraries = manifest["libraries"]
    if libraries["scikit-learn"] != sklearn.__version__ or libraries["skops"] != skops.__version__:
        raise BundleError(f"{model_id}: built with scikit-learn {libraries['scikit-learn']} / skops {libraries['skops']}, "
                          f"running {sklearn.__version__} / {skops.__version__}")
    kind = manifest["kind"]
    if kind == BASELINE_KIND:
        if manifest["feature_order"] != ["raw_return_rate"] or "model.skops" in files["files"]:
            raise BundleError(f"{model_id}: a baseline bundle carries no estimator")
        pipeline = None
    else:
        if manifest["feature_order"] != F.feature_order():
            raise BundleError(f"{model_id}: feature schema differs from the feature contract in this installation")
        if manifest["model_sha256"] != files["files"].get("model.skops"):
            raise BundleError(f"{model_id}: estimator hash mismatch")
        pipeline = modeling.load_pipeline(directory / "model.skops")           # refuses types outside the allow-list
    reference = pd.read_parquet(directory / "reference_scores.parquet")["score"].to_numpy()
    if len(reference) != manifest["reference_count"] or _logical_reference_hash(reference) != manifest["reference_logical_sha256"]:
        raise BundleError(f"{model_id}: score reference does not match its recorded hash")
    return Bundle(model_id=model_id, kind=kind, manifest=manifest, reference_scores=np.sort(reference), pipeline=pipeline,
                  directory=directory)


def raw_scores(bundle: Bundle, frame: pd.DataFrame) -> np.ndarray:
    """Ranking scores for eligible rows, higher = more suspicious. Only predict-side methods are ever called."""
    if bundle.kind == BASELINE_KIND:
        return frame["raw_return_rate"].to_numpy(dtype=float)
    matrix = frame[bundle.feature_order].to_numpy(dtype=float)
    if bundle.kind == "supervised":
        return bundle.pipeline.decision_function(matrix)
    return -bundle.pipeline.score_samples(matrix)


def reference_percentile(bundle: Bundle, scores) -> np.ndarray:
    """Position in the frozen training reference, 0-100. A percentile, not a probability."""
    return modeling.percentile(bundle.reference_scores, scores)


# ------------------------------------------------------------------ the active pointer
def _active_path(artifact_root: Path | None = None) -> Path:
    return Path(artifact_root or paths.ARTIFACT_ROOT) / "active" / "active.json"


def read_active(artifact_root: Path | None = None) -> dict | None:
    path = _active_path(artifact_root)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def activate(model_id: str | None, baseline_id: str, selection_status: str, experiment_id: str | None = None,
             reason: str | None = None, artifact_root: Path | None = None) -> dict:
    """Point serving at a verified bundle. Both bundles are verified first; the pointer is replaced atomically.

    model_id None means baseline fallback. selection_status is not_completed, selected or no_selected_model, so
    a missing selection is never reported as a failed gate.
    """
    if selection_status not in ("not_completed", "selected", "no_selected_model"):
        raise ValueError(f"unknown selection status {selection_status!r}")
    if (model_id is None) == (selection_status == "selected"):
        raise ValueError("a promoted model needs selection_status 'selected', and only then")
    baseline = load_bundle(baseline_id, artifact_root)
    if baseline.kind != BASELINE_KIND:
        raise BundleError(f"{baseline_id} is not a baseline bundle")
    if model_id is not None and load_bundle(model_id, artifact_root).kind == BASELINE_KIND:
        raise BundleError(f"{model_id} is a baseline bundle and cannot be promoted as a model")
    previous = read_active(artifact_root)
    pointer = {"version": (previous["version"] + 1) if previous else 1, "model_id": model_id, "baseline_id": baseline_id,
               "selection_status": selection_status, "experiment_id": experiment_id, "reason": reason,
               "activated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    path = _active_path(artifact_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(f".active-{os.getpid()}.json")
    staged.write_text(json.dumps(pointer, indent=2) + "\n", encoding="utf-8")
    os.replace(staged, path)
    history = path.with_name("history.jsonl")
    with history.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(pointer) + "\n")
    return pointer


def resolve_active(artifact_root: Path | None = None) -> Bundle:
    """The bundle a new run binds to: the promoted model if there is one, otherwise the baseline.

    A corrupt promoted model raises; it is never silently replaced by the baseline.
    """
    pointer = read_active(artifact_root)
    if pointer is None:
        raise BundleError("no active bundle: neither a model nor a baseline has been activated")
    return load_bundle(pointer["model_id"] or pointer["baseline_id"], artifact_root)
