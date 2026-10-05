"""Training (final-spec component 07, TRAIN acceptance criteria) on a small synthetic matrix."""
import json

import numpy as np
import pandas as pd
import pytest
import skops.io as sio

from arai import evaluation, modeling
from arai.dataset import MODEL_FEATURES
from arai.settings import load_settings

WORLDS = [f"W21{i:02d}" for i in range(1, 11)]


def synthetic_frame(rows_per_world: int = 120, seed: int = 0) -> pd.DataFrame:
    """Ten small 'worlds' with the contract's feature columns, some nulls and a label two features explain."""
    rng = np.random.default_rng(seed)
    frames = []
    for world in WORLDS:
        x = pd.DataFrame(rng.normal(size=(rows_per_world, len(MODEL_FEATURES))), columns=MODEL_FEATURES)
        x["claim_share"] = x["claim_share"].where(rng.random(rows_per_world) > 0.3)          # null for some rows
        signal = 1.5 * x["raw_return_rate"] + 1.0 * x["claim_share"].fillna(0)
        y = (signal + rng.normal(scale=0.8, size=rows_per_world) > 1.5).astype(int)
        frames.append(x.assign(world_id=world, customer_id=[f"{world}-C{i}" for i in range(rows_per_world)], eligible=True, y_abuse=y))
    return pd.concat(frames, ignore_index=True)


@pytest.fixture(scope="module")
def frame():
    return synthetic_frame()


def _candidate(candidate_id):
    return next(c for c in modeling.candidates() if c.id == candidate_id)


def test_seed_sets_are_disjoint_and_identifiers_are_world_namespaced(world):
    experiment = load_settings().experiment
    sets = [experiment[k] for k in ("fixture_seeds", "train_seeds", "validation_seeds", "test_seeds", "demo_seeds", "stress_seeds")]
    seeds = [s for group in sets for s in group]
    assert len(seeds) == len(set(seeds))
    # every customer and every linkable identifier carries its world, so no relationship can cross worlds
    assert world.tables["customer_master"]["customer_id"].str.startswith(world.world_id + "-").all()
    for column in ("address_id", "device_id", "payment_id"):
        assert world.tables["sales_order"][column].str.startswith(world.world_id + "-").all()


def test_scorecards_refuse_fixture_worlds(written, world):
    root = written["operational"].parents[2]
    with pytest.raises(ValueError, match="fixture"):
        evaluation.evaluation_frame([world.world_id], artifact_root=root, private_root=written["private"].parent)


def test_folds_hold_out_two_worlds_each_and_need_ten_worlds():
    folds = modeling.fold_map(WORLDS)
    assert sorted(folds.values()) == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4] and folds["W2101"] == folds["W2102"] == 0
    with pytest.raises(ValueError):
        modeling.fold_map(WORLDS[:9])


def test_learned_transforms_are_fitted_on_training_rows_only(frame):
    candidate = _candidate("logreg_c1")
    shifted = frame.copy()
    held_out = shifted["world_id"].isin(["W2101", "W2102"])
    shifted.loc[held_out, MODEL_FEATURES] += 1000.0              # absurd values in the held-out worlds
    pipeline, _ = modeling.fit(candidate, shifted[~held_out], shifted.loc[~held_out, "y_abuse"])
    medians = pipeline.named_steps["prepare"].transformer_list[0][1].statistics_
    np.testing.assert_allclose(medians, frame.loc[~held_out, MODEL_FEATURES].median().to_numpy())
    assert np.abs(pipeline.named_steps["scale"].mean_[:len(MODEL_FEATURES)]).max() < 1.0


def test_each_out_of_fold_row_is_scored_without_its_world(frame):
    candidate = _candidate("logreg_c1")
    folds = modeling.fold_map(WORLDS)
    scores, _ = modeling.out_of_fold(candidate, frame, folds)
    assert scores.notna().all()
    held_out = frame["world_id"].isin(["W2103", "W2104"])       # fold 1
    pipeline, _ = modeling.fit(candidate, frame[~held_out], frame.loc[~held_out, "y_abuse"])
    np.testing.assert_allclose(scores[held_out].to_numpy(), modeling.raw_scores(candidate, pipeline, frame[held_out]))
    everything, _ = modeling.fit(candidate, frame, frame["y_abuse"])
    assert not np.allclose(scores[held_out].to_numpy(), modeling.raw_scores(candidate, everything, frame[held_out]))


def test_training_assembly_audits_world_ids(frame, monkeypatch):
    monkeypatch.setattr(modeling.dataset, "labelled", lambda worlds, a=None, p=None: frame[frame["world_id"] != "W2110"])
    with pytest.raises(ValueError, match="exactly the requested worlds"):
        modeling.training_frame(WORLDS)


@pytest.mark.parametrize("candidate_id", ["logreg_c1", "hgb_leaf15", "iforest_256"])
def test_candidate_record_and_single_serving_estimator(frame, tmp_path, candidate_id):
    candidate = _candidate(candidate_id)
    record = modeling.train_candidate(candidate, frame, modeling.fold_map(WORLDS), tmp_path / candidate_id)
    assert sorted(p.name for p in (tmp_path / candidate_id).iterdir()) == [
        "model.skops", "record.json", "reference_scores.parquet", "training_scores.parquet"]      # no fold models
    assert record == json.loads((tmp_path / candidate_id / "record.json").read_text())
    assert record["status"] == "fitted" and record["rejection"] is None and record["features"] == MODEL_FEATURES
    assert len(record["model_sha256"]) == 64 and record["duration_seconds"] >= 0 and isinstance(record["warnings"], list)
    assert set(candidate.params) < set(record["params"])                                          # expanded, not only the listed ones
    assert record["training_rows"] == len(frame) and record["training_worlds"] == WORLDS
    expected = "out-of-fold" if candidate.supervised else "in-sample"
    assert record["reference_kind"].startswith(expected)
    reference = pd.read_parquet(tmp_path / candidate_id / "reference_scores.parquet")["score"]
    assert reference.is_monotonic_increasing and len(reference) == len(frame)
    loaded = modeling.load_pipeline(tmp_path / candidate_id / "model.skops")
    scores = pd.read_parquet(tmp_path / candidate_id / "training_scores.parquet")
    np.testing.assert_allclose(modeling.raw_scores(candidate, loaded, frame), scores["final_fit_score"].to_numpy())


def test_a_candidate_that_does_not_converge_is_rejected(frame, tmp_path):
    logistic = _candidate("logreg_c1")
    stubborn = modeling.Candidate("logreg_stub", 9, logistic.family, True, dict(logistic.params, max_iter=1))
    record = modeling.train_candidate(stubborn, frame, modeling.fold_map(WORLDS), tmp_path / "stub")
    assert record["status"] == "rejected" and record["rejection"] == "did not converge"
    assert any("ConvergenceWarning" in w for w in record["warnings"])


def test_unsupervised_fit_never_reads_a_label(frame):
    candidate = _candidate("iforest_256")
    unlabeled = frame.drop(columns="y_abuse")
    pipeline, _ = modeling.fit(candidate, unlabeled)                       # works with no label column at all
    flipped, _ = modeling.fit(candidate, frame.assign(y_abuse=1 - frame["y_abuse"]), 1 - frame["y_abuse"])
    np.testing.assert_allclose(modeling.raw_scores(candidate, pipeline, frame), modeling.raw_scores(candidate, flipped, frame))
    with pytest.raises(ValueError, match="needs labels"):
        modeling.fit(_candidate("hgb_leaf15"), unlabeled)


def test_volume_only_reference_is_never_selectable():
    reference = modeling.volume_only_reference()
    assert reference.features == ["mature_sale_lines", "log_order_count"] and not reference.selectable
    assert reference.params == _candidate("logreg_c1").params
    assert [c.id for c in modeling.candidates()] == ["logreg_c1", "hgb_leaf15", "hgb_leaf15_w4", "hgb_leaf15_w6", "hgb_leaf15_w8",
                                                     "iforest_256"]


def test_percentile_is_position_in_the_frozen_reference():
    reference = np.array([1.0, 2.0, 2.0, 4.0])
    np.testing.assert_allclose(modeling.percentile(reference, [0.0, 2.0, 3.0, 9.0]), [0.0, 50.0, 75.0, 100.0])


def test_the_loader_refuses_types_outside_the_allow_list(tmp_path):
    from sklearn.preprocessing import FunctionTransformer
    import os

    path = tmp_path / "hostile.skops"
    sio.dump(FunctionTransformer(func=os.getcwd), path)
    with pytest.raises(Exception, match="allow-list"):
        modeling.load_pipeline(path)


def test_weighted_candidates_count_honest_gate_members_more_in_training_and_never_as_a_feature(frame):
    """Experiment contract 2.0: the weight uses private truth as the label does, in training only."""
    weighted, plain = _candidate("hgb_leaf15_w6"), _candidate("hgb_leaf15")
    assert weighted.honest_group_weights == {"repeat_genuine_claimant": 6} and weighted.params == plain.params
    assert "repeat_genuine_claimant" not in weighted.features and not plain.honest_group_weights
    rng = np.random.default_rng(1)
    data = frame.assign(repeat_genuine_claimant=(frame["y_abuse"] == 0) & (rng.random(len(frame)) < 0.2))
    weights = modeling.training_weights(weighted, data)
    assert set(np.unique(weights)) == {1.0, 6.0} and (weights[data["repeat_genuine_claimant"].to_numpy()] == 6.0).all()
    assert modeling.training_weights(plain, data) is None
    a, _ = modeling.fit(weighted, data, data["y_abuse"])
    b, _ = modeling.fit(plain, data, data["y_abuse"])
    assert not np.allclose(modeling.raw_scores(weighted, a, data), modeling.raw_scores(plain, b, data))   # the weight changes the model
    assert a.n_features_in_ == len(MODEL_FEATURES)                                            # and adds no input
    with pytest.raises(KeyError):
        modeling.fit(weighted, frame, frame["y_abuse"])                                       # no group flag, no silent unweighted fit
    leaky = modeling.Candidate("x", 9, plain.family, True, dict(plain.params), list(MODEL_FEATURES) + ["repeat_genuine_claimant"],
                               honest_group_weights={"repeat_genuine_claimant": 6})
    with pytest.raises(ValueError, match="can never be a feature"):
        modeling.training_weights(leaky, data)
