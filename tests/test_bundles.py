"""Serving bundles and the active pointer (final-spec component 10, ART acceptance criteria)."""
import json
import shutil

import numpy as np
import pandas as pd
import pytest
import sklearn

from arai import bundles, ranking
from arai import features as F


@pytest.fixture
def root(trained, tmp_path):
    """A private copy of the trained experiment, so each test can damage its own bundles."""
    shutil.copytree(trained["artifact_root"] / "experiments", tmp_path / "experiments")
    return tmp_path


def _experiment(root):
    return root / "experiments" / "EXP-TEST"


def test_saved_bundle_reproduces_training_scores_and_the_ranked_selection(root, trained):
    frame = trained["frame"]
    model_id = bundles.build_model_bundle(_experiment(root), "logreg_c1", root)
    bundle = bundles.load_bundle(model_id, root)
    expected = pd.read_parquet(_experiment(root) / "candidates" / "logreg_c1" / "training_scores.parquet")["final_fit_score"].to_numpy()
    scores = bundles.raw_scores(bundle, frame)
    np.testing.assert_allclose(scores, expected, atol=1e-10, rtol=1e-8)
    ids = frame["customer_id"].to_numpy()
    assert (ranking.rank_world("W", ids, scores) == ranking.rank_world("W", ids, expected)).all()      # exact ranked selection
    assert bundle.kind == "supervised" and bundle.manifest["adapter"] == "decision_function"
    assert bundle.feature_order == F.feature_order() and bundle.reference.to_dict() == trained["reference"].to_dict()
    percentiles = bundles.reference_percentile(bundle, scores)
    assert percentiles.min() >= 0 and percentiles.max() <= 100
    forest = bundles.load_bundle(bundles.build_model_bundle(_experiment(root), "iforest_256", root), root)
    assert forest.kind == "unsupervised" and forest.manifest["adapter"] == "negative_score_samples"
    np.testing.assert_allclose(bundles.raw_scores(forest, frame), pd.read_parquet(
        _experiment(root) / "candidates" / "iforest_256" / "training_scores.parquet")["final_fit_score"].to_numpy(), atol=1e-10, rtol=1e-8)


def test_the_identifier_is_a_content_hash_and_bundles_are_never_rewritten(root):
    first = bundles.build_model_bundle(_experiment(root), "logreg_c1", root)
    directory = bundles.bundle_root(root) / first
    manifest = json.loads((directory / "bundle.json").read_text())
    assert "model_id" not in manifest                                   # the hash covers the manifest, so it cannot contain itself
    stamp = {p.name: p.stat().st_mtime_ns for p in directory.iterdir()}
    assert bundles.build_model_bundle(_experiment(root), "logreg_c1", root) == first
    assert {p.name: p.stat().st_mtime_ns for p in directory.iterdir()} == stamp
    assert not [p for p in bundles.bundle_root(root).iterdir() if p.name.startswith(".staging")]


@pytest.mark.parametrize("damage", ["model", "reference", "manifest", "extra_type", "library", "schema", "unknown"])
def test_any_mismatch_is_refused_before_use(root, monkeypatch, damage):
    model_id = bundles.build_model_bundle(_experiment(root), "logreg_c1", root)
    directory = bundles.bundle_root(root) / model_id
    if damage == "model":
        (directory / "model.skops").write_bytes((directory / "model.skops").read_bytes() + b"x")
    elif damage == "reference":
        pd.DataFrame({"score": [0.0, 1.0]}).to_parquet(directory / "reference_scores.parquet", index=False)
    elif damage == "manifest":
        manifest = json.loads((directory / "bundle.json").read_text())
        manifest["feature_reference"]["category_rate"]["Shirt"] = 0.99
        (directory / "bundle.json").write_text(json.dumps(manifest))
    elif damage == "extra_type":
        monkeypatch.setattr(bundles, "TRUSTED_TYPES", [])
        monkeypatch.setattr(bundles.sio, "get_untrusted_types", lambda file: ["os.system"])
    elif damage == "library":
        monkeypatch.setattr(sklearn, "__version__", "0.0.1")
    elif damage == "schema":
        monkeypatch.setattr(F, "feature_order", lambda spec_root=None: ["raw_return_rate"])
    elif damage == "unknown":
        model_id = "m-" + "0" * 24
    with pytest.raises(bundles.BundleError):
        bundles.load_bundle(model_id, root)


def test_path_like_identifiers_are_refused(root):
    for name in ("../experiments", "..", "a/b", "a\\b"):
        with pytest.raises(bundles.BundleError):
            bundles.load_bundle(name, root)


def test_a_rejected_candidate_cannot_be_bundled(root):
    record_path = _experiment(root) / "candidates" / "logreg_c1" / "record.json"
    record = json.loads(record_path.read_text())
    record_path.write_text(json.dumps(dict(record, status="rejected", rejection="did not converge")))
    with pytest.raises(bundles.BundleError, match="rejected"):
        bundles.build_model_bundle(_experiment(root), "logreg_c1", root)


def test_baseline_needs_no_candidate_and_nothing_is_fitted_at_scoring(root, trained, monkeypatch):
    shutil.rmtree(_experiment(root) / "candidates")                      # no estimator exists anywhere
    baseline = bundles.load_bundle(bundles.build_baseline_bundle(_experiment(root), root), root)
    assert baseline.kind == "baseline_fallback" and baseline.pipeline is None
    assert baseline.manifest["score_label"] == "Return-rate reference percentile"
    frame = trained["frame"]
    np.testing.assert_array_equal(bundles.raw_scores(baseline, frame), frame["raw_return_rate"].to_numpy())
    reference = np.array([0.1, 0.2, 0.2, 0.4])
    np.testing.assert_allclose(bundles.percentile(reference, [0.0, 0.2, 0.3, 0.9]), [0.0, 50.0, 75.0, 100.0])


def test_scoring_never_calls_fit(root, trained, monkeypatch):
    from sklearn.base import BaseEstimator
    from sklearn.pipeline import Pipeline

    bundle = bundles.load_bundle(bundles.build_model_bundle(_experiment(root), "logreg_c1", root), root)

    def forbidden(*args, **kwargs):
        raise AssertionError("fit called during inference")
    for owner in (Pipeline, type(bundle.pipeline.named_steps["model"]), type(bundle.pipeline.named_steps["scale"])):
        for method in ("fit", "fit_transform", "partial_fit"):
            if hasattr(owner, method):
                monkeypatch.setattr(owner, method, forbidden)
    assert isinstance(bundle.pipeline, BaseEstimator)
    assert np.isfinite(bundles.raw_scores(bundle, trained["frame"])).all()


def test_activation_is_atomic_versioned_and_never_falls_back_silently(root):
    with pytest.raises(bundles.BundleError):
        bundles.resolve_active(root)                                     # nothing activated: no scoring bundle at all
    baseline_id = bundles.build_baseline_bundle(_experiment(root), root)
    model_id = bundles.build_model_bundle(_experiment(root), "logreg_c1", root)
    first = bundles.activate(None, baseline_id, "not_completed", "EXP-TEST", "selection not completed", root)
    assert first["version"] == 1 and bundles.resolve_active(root).model_id == baseline_id
    second = bundles.activate(model_id, baseline_id, "selected", "EXP-TEST", None, root)
    assert second["version"] == 2 and bundles.resolve_active(root).model_id == model_id
    with pytest.raises(ValueError):
        bundles.activate(model_id, baseline_id, "no_selected_model", artifact_root=root)       # a promoted model means selected
    with pytest.raises(ValueError):
        bundles.activate(None, baseline_id, "selected", artifact_root=root)
    with pytest.raises(bundles.BundleError):
        bundles.activate(baseline_id, baseline_id, "selected", artifact_root=root)              # a baseline is not a model
    with pytest.raises(bundles.BundleError):
        bundles.activate("m-" + "1" * 24, baseline_id, "selected", artifact_root=root)          # unverified bundle: pointer unchanged
    assert bundles.read_active(root)["version"] == 2
    history = (root / "active" / "history.jsonl").read_text().strip().splitlines()
    assert [json.loads(line)["version"] for line in history] == [1, 2]
    # a corrupt promoted model fails; it is not replaced by the baseline behind the user's back
    (bundles.bundle_root(root) / model_id / "model.skops").write_bytes(b"corrupt")
    with pytest.raises(bundles.BundleError):
        bundles.resolve_active(root)
