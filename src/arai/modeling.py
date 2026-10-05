"""Training dataset, model fitting and out-of-fold scoring (final-spec component 07).

Five fixed candidates share the same eligible rows and ordered features. Everything learned (medians,
indicators, scaler, estimator) is fitted on training worlds only, and inside each fold on that fold's
training worlds only. The unsupervised candidates never see a label. Nothing here runs at inference.
"""
from __future__ import annotations

import hashlib
import json
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
import skops
import skops.io as sio
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import MissingIndicator, SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import StandardScaler

from arai import dataset, paths
from arai.bundles import code_sha256, load_pipeline, percentile  # noqa: F401  (one implementation, owned by the serving side)
from arai.dataset import MODEL_FEATURES
from arai.settings import load_settings

FAMILIES = {"LogisticRegression": LogisticRegression, "HistGradientBoostingClassifier": HistGradientBoostingClassifier,
            "IsolationForest": IsolationForest}
VOLUME_FEATURES = ["mature_sale_lines", "log_order_count"]
N_FOLDS = 5


@dataclass
class Candidate:
    id: str
    ordinal: int
    family: str
    supervised: bool
    params: dict
    features: list = field(default_factory=lambda: list(MODEL_FEATURES))
    selectable: bool = True                     # report-only references can never be selected
    honest_group_weights: dict = field(default_factory=dict)    # training-only weight on honest members of a gate segment


def candidates(settings=None) -> list:
    """The five registered candidates, exactly as contracts/experiment.yaml lists them."""
    experiment = (settings or load_settings()).experiment
    return [Candidate(c["id"], c["ordinal"], c["family"], c["supervised"], dict(c["params"]),
                      honest_group_weights=dict(c.get("honest_group_weights", {}))) for c in experiment["candidates"]]


def volume_only_reference(settings=None) -> Candidate:
    """Report-only: the logistic candidate's settings with order volume as its only input."""
    logistic = next(c for c in candidates(settings) if c.id == "logreg_c1")
    return Candidate("volume_only_logreg", 0, logistic.family, True, dict(logistic.params), list(VOLUME_FEATURES), selectable=False)


def make_pipeline(candidate: Candidate) -> Pipeline:
    """Training-median imputation, one missing-value indicator per feature, a scaler for logistic regression only."""
    prepare = FeatureUnion([("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
                            ("missing", MissingIndicator(features="all"))])
    steps = [("prepare", prepare)]
    if candidate.family == "LogisticRegression":
        steps.append(("scale", StandardScaler()))
    steps.append(("model", FAMILIES[candidate.family](**candidate.params)))
    return Pipeline(steps)


def training_weights(candidate: Candidate, X: pd.DataFrame) -> np.ndarray | None:
    """Per-row training weights: honest members of a gate segment count more as negatives (experiment.yaml).

    The group flags are private truth, joined for training exactly as the label is. They are never model inputs
    and nothing of the kind exists, or is needed, when a snapshot is scored.
    """
    if not candidate.honest_group_weights:
        return None
    weights = np.ones(len(X))
    for group, weight in candidate.honest_group_weights.items():
        if group in candidate.features:
            raise ValueError(f"{group} is private truth and can never be a feature")
        weights[X[group].to_numpy(dtype=bool)] = float(weight)
    return weights


def fit(candidate: Candidate, X: pd.DataFrame, y=None):
    """Fit one pipeline; returns (pipeline, warnings). Unsupervised candidates are fitted without any label."""
    pipeline = make_pipeline(candidate)
    matrix = X[candidate.features].to_numpy(dtype=float)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        if candidate.supervised:
            if y is None:
                raise ValueError(f"{candidate.id} is supervised and needs labels")
            weights = training_weights(candidate, X)
            pipeline.fit(matrix, np.asarray(y), **({} if weights is None else {"model__sample_weight": weights}))
        else:
            pipeline.fit(matrix)                # no label reaches an unsupervised fit
    return pipeline, [f"{w.category.__name__}: {w.message}" for w in caught]


def raw_scores(candidate: Candidate, pipeline: Pipeline, X: pd.DataFrame) -> np.ndarray:
    """Ranking score, higher = more suspicious: decision_function, or negative score_samples for isolation forests."""
    matrix = X[candidate.features].to_numpy(dtype=float)
    return pipeline.decision_function(matrix) if candidate.supervised else -pipeline.score_samples(matrix)


def fold_map(world_ids: list) -> dict:
    """Five folds grouped by world, two worlds held out per fold (sorted world order, consecutive pairs)."""
    ordered = sorted(world_ids)
    if len(ordered) != 2 * N_FOLDS:
        raise ValueError("the reference procedure expects ten training worlds")
    return {world: index // 2 for index, world in enumerate(ordered)}


def out_of_fold(candidate: Candidate, frame: pd.DataFrame, folds: dict) -> tuple:
    """Scores for every training row from a pipeline that never saw that row's world."""
    scores = pd.Series(np.nan, index=frame.index)
    notes = []
    fold_of = frame["world_id"].map(folds)
    for fold in range(N_FOLDS):
        held_out = fold_of == fold
        train = frame[~held_out]
        assert not set(train["world_id"]) & set(frame.loc[held_out, "world_id"])
        pipeline, caught = fit(candidate, train, train["y_abuse"] if candidate.supervised else None)
        notes += caught
        scores[held_out] = raw_scores(candidate, pipeline, frame[held_out])
    return scores, notes


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def feature_quantiles(frame: pd.DataFrame) -> dict:
    """10th, 50th and 90th percentile of every model feature over eligible training rows (None where never observed).

    They travel with the bundle so a scoring run can say when a snapshot's inputs sit outside what training saw.
    """
    out = {}
    for name in MODEL_FEATURES:
        values = frame[name].to_numpy(dtype=float)
        out[name] = None if np.isnan(values).all() else [float(q) for q in np.nanquantile(values, [0.1, 0.5, 0.9])]
    return out


def training_frame(world_ids: list, artifact_root: Path | None = None, private_root: Path | None = None) -> pd.DataFrame:
    """Eligible rows of the training worlds with their label. Labels are joined after features were frozen."""
    frame = dataset.labelled(world_ids, artifact_root, private_root)
    audit = frame.groupby("world_id").size()
    if set(audit.index) != set(world_ids):
        raise ValueError("training assembly does not contain exactly the requested worlds")
    return frame[frame["eligible"]].reset_index(drop=True)


def train_candidate(candidate: Candidate, frame: pd.DataFrame, folds: dict, out_dir: Path) -> dict:
    """Out-of-fold scores, the final estimator fitted once on all training worlds, and the candidate record."""
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    notes, rejection = [], None
    if candidate.supervised:
        reference, notes = out_of_fold(candidate, frame, folds)
        reference_kind = "out-of-fold, 5 folds grouped by world"
    pipeline, caught = fit(candidate, frame, frame["y_abuse"] if candidate.supervised else None)
    notes += caught
    final = raw_scores(candidate, pipeline, frame)
    if not candidate.supervised:
        reference, reference_kind = pd.Series(final, index=frame.index), "in-sample training scores (optimistic)"
    if any("ConvergenceWarning" in note for note in notes):
        rejection = "did not converge"
    elif not (np.isfinite(reference).all() and np.isfinite(final).all()):
        rejection = "non-finite score"

    sio.dump(pipeline, out_dir / "model.skops")
    scores = frame[["world_id", "customer_id"]].assign(reference_score=reference.to_numpy(), final_fit_score=final)
    scores.to_parquet(out_dir / "training_scores.parquet", index=False)
    pd.DataFrame({"score": np.sort(reference.to_numpy())}).to_parquet(out_dir / "reference_scores.parquet", index=False)
    record = {
        "candidate_id": candidate.id, "ordinal": candidate.ordinal, "family": candidate.family,
        "supervised": candidate.supervised, "selectable": candidate.selectable, "features": candidate.features,
        "honest_group_weights": candidate.honest_group_weights,
        "params": {k: (v if isinstance(v, (int, float, str, bool, type(None))) else str(v))
                   for k, v in pipeline.named_steps["model"].get_params().items()},
        "preprocessing": [name for name, _ in pipeline.steps[:-1]], "reference_kind": reference_kind,
        "training_rows": int(len(frame)), "training_positives": int(frame["y_abuse"].sum()),
        "training_worlds": sorted(frame["world_id"].unique()), "folds": folds if candidate.supervised else None,
        "duration_seconds": round(time.time() - started, 2), "warnings": sorted(set(notes)),
        "status": "rejected" if rejection else "fitted", "rejection": rejection,
        "model_sha256": _sha256(out_dir / "model.skops"),
        "libraries": {"scikit-learn": sklearn.__version__, "skops": skops.__version__, "numpy": np.__version__},
    }
    (out_dir / "record.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def experiment_dir(experiment_id: str, artifact_root: Path | None = None) -> Path:
    return Path(artifact_root or paths.ARTIFACT_ROOT) / "experiments" / experiment_id


def train_experiment(experiment_id: str, train_worlds: list, artifact_root: Path | None = None,
                     private_root: Path | None = None) -> dict:
    """Fit every candidate and the volume-only reference on the training worlds and write their records."""
    settings = load_settings()
    out = experiment_dir(experiment_id, artifact_root)
    frame = training_frame(train_worlds, artifact_root, private_root)
    folds = fold_map(train_worlds)
    features_sha = {w: json.loads((dataset.feature_dir(w, artifact_root) / "meta.json").read_text())["features_sha256"]
                    for w in train_worlds}
    records = [train_candidate(c, frame, folds, out / "candidates" / c.id) for c in candidates(settings)]
    reference = train_candidate(volume_only_reference(settings), frame, folds, out / "references" / "volume_only_logreg")
    _, manifest = dataset.load_manifest(train_worlds[0], artifact_root)
    config = {"experiment_id": experiment_id, "training_worlds": sorted(train_worlds), "folds": folds,
              "feature_order": MODEL_FEATURES, "features_sha256": features_sha,
              "scoring_code_sha256": code_sha256(), "cutoff": manifest["cutoff"], "feature_quantiles": feature_quantiles(frame),
              "experiment_config_sha256": hashlib.sha256(
                  (settings.spec_root / "contracts" / "experiment.yaml").read_bytes()).hexdigest(),
              "eligible_training_rows": int(len(frame)), "training_positives": int(frame["y_abuse"].sum())}
    (out / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return {"config": config, "candidates": records, "references": [reference]}
