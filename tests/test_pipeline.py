"""The whole offline pipeline, end to end, on small worlds under temporary roots (final-spec components 07 to 10).

generate -> train -> dry run -> ablation -> stress -> validation and selection -> final test -> publish. The default
artifact and private roots point nowhere for the duration, so any step that forgets the root it was given fails here.
Worlds have 400 customers; the outcome of the gate at that size is noise and is not asserted, only that every step
runs, records what it must and refuses what it must.
"""
import json
import shutil

import pandas as pd
import pytest
import yaml

from arai import ablation, bundles, dataset, experiment, evaluation, paths, publishing, selection
from arai import features as F
from arai.generator import generate_world, write_world
from tests.test_service import conforms

EXPERIMENT = "EXP-E2E"


@pytest.fixture
def small(tmp_path, monkeypatch):
    """A copy of the contracts with 400-customer worlds, temporary roots, and default roots that do not exist."""
    spec = tmp_path / "spec"
    for part in ("contracts", "assets"):
        shutil.copytree(paths.SPEC_ROOT / part, spec / part)
    path = spec / "contracts" / "experiment.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["customers_per_world"] = 400
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr("arai.settings.SPEC_ROOT", spec)
    monkeypatch.setattr(paths, "ARTIFACT_ROOT", tmp_path / "default-root-must-not-be-used")
    monkeypatch.setattr(paths, "PRIVATE_TRUTH_ROOT", tmp_path / "default-private-must-not-be-used")
    monkeypatch.setattr(evaluation, "MIN_SEGMENT_SIZE", 20)            # five 400-customer worlds cannot reach 200 per segment
    monkeypatch.setattr(selection, "MIN_SEGMENT_SIZE", 20)
    roots = {"artifact_root": tmp_path / "artifacts", "private_root": tmp_path / "private"}

    def generate(seeds):
        for seed in seeds:
            write_world(generate_world(seed), roots["artifact_root"], roots["private_root"])
    return {"config": config, "roots": roots, "generate": generate, "out": roots["artifact_root"] / "experiments" / EXPERIMENT}


def test_the_offline_pipeline_runs_end_to_end_under_the_roots_it_is_given(small, monkeypatch):
    config, roots, out = small["config"], small["roots"], small["out"]
    artifact_root = roots["artifact_root"]
    read = lambda name: json.loads((out / name).read_text(encoding="utf-8"))  # noqa: E731

    # ---- training: records the code that fitted the models, the cutoff and the training quantiles
    halved = next(seed for seed, text in config["stress_seeds"].items() if "action rate x0.5" in text)
    small["generate"](config["train_seeds"] + [halved])
    with monkeypatch.context() as patched:                                     # a training world that needs the all-worlds fallback
        build = dataset.build_features
        patched.setattr(dataset, "build_features", lambda *a, **k: type("R", (), {"fallback_uses": 3})() if build(*a, **k) else None)
        with pytest.raises(RuntimeError, match="category fallback"):
            experiment.train("EXP-FALLBACK", **roots)
    result = experiment.train(EXPERIMENT, **roots)
    assert [c["status"] for c in result["candidates"]] == ["fitted"] * 6
    assert [c["honest_group_weights"] for c in result["candidates"]][2:5] == [{"repeat_genuine_claimant": w} for w in (4, 6, 8)]
    trained = read("config.json")
    assert trained["scoring_code_sha256"] == bundles.code_sha256() and trained["cutoff"].startswith("2026-09-09")
    assert set(trained["feature_quantiles"]) == set(dataset.MODEL_FEATURES)

    # ---- gate dry run: the calibration disclosure is recorded with it, and only permitted levers are accepted
    with pytest.raises(ValueError, match="not a permitted calibration lever"):
        experiment.dry_run(EXPERIMENT, **roots, levers_changed=["household generation"])
    experiment.dry_run(EXPERIMENT, **roots, levers_changed=["genuine claim rates"], record_ref="records/calibration.md")
    assert read("reports/dry_run.json")["calibration"]["levers_changed"] == ["genuine claim rates"]

    # ---- what the result depends on, and the stress table, are pipeline outputs
    measured = ablation.run(EXPERIMENT, **roots)
    assert [row["key"] for row in measured["variants"]] == ["all", "first_contract", "without_late_return_lines", "without_timing",
                                                            "without_claims", "without_claims_and_timing"]
    assert measured["variants"][1]["features"] == 17
    groups = {row["group"]: row for row in measured["honest_groups"]["groups"]}
    assert set(groups) == set(ablation.GROUP_LABELS)
    by_failures = [groups[g] for g in ("repeat_genuine_claimant", "one_genuine_failure", "no_genuine_failure")]
    false_positives = measured["honest_groups"]["false_positives"]
    assert sum(g["model_selected"] for g in by_failures) == false_positives["model"]["false_positives"]   # the three split the honest
    assert false_positives["model"]["repeat_genuine_claimants"] == groups["repeat_genuine_claimant"]["model_selected"]
    stress = experiment.stress(EXPERIMENT, **roots)
    assert [w["world_id"] for w in stress["worlds"]] == [f"W{halved}"] and "action rate" in stress["worlds"][0]["mechanism"]
    assert {r["ranking"] for r in stress["worlds"][0]["rankings"]} >= {"raw_return_rate", "hgb_leaf15", "analyst_rulebook"}

    # ---- validation: worlds from another generator are refused; then selection is frozen
    small["generate"](config["validation_seeds"])
    first_training, first_validation = f"W{config['train_seeds'][0]}", f"W{config['validation_seeds'][0]}"
    manifest = artifact_root / "worlds" / first_validation / "operational" / "manifest.json"
    original = manifest.read_bytes()
    tampered = json.loads(original)
    tampered["generator"]["code_sha256"] = "0" * 64
    manifest.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(RuntimeError, match="different code or configuration"):
        experiment.validate(EXPERIMENT, **roots)
    manifest.write_bytes(original)
    record = experiment.validate(EXPERIMENT, **roots)
    assert record["selection_status"] in ("selected", "no_selected_model") and (out / "selection.json").is_file()
    with pytest.raises(RuntimeError, match="frozen selection"):
        experiment.train(EXPERIMENT, **roots)

    # ---- labels are joined only with the truth written with the world
    truth_file = roots["private_root"] / first_training / "customer_truth.parquet"
    kept = truth_file.read_bytes()
    truth = pd.read_parquet(truth_file)
    truth.assign(y_abuse=1 - truth["y_abuse"]).to_parquet(truth_file, index=False)
    with pytest.raises(ValueError, match="differs from the one written with the world"):
        dataset.labelled([first_training], **roots)
    truth_file.write_bytes(kept)

    # ---- the final test runs once
    small["generate"](config["test_seeds"])
    chosen = record["selected_model_id"]
    if chosen:
        tested = experiment.final_test(EXPERIMENT, **roots)
        assert tested["final_test_status"] in ("passed", "failed", "unverifiable")
        with pytest.raises(RuntimeError, match="runs once"):
            experiment.final_test(EXPERIMENT, **roots)
    else:
        with pytest.raises(RuntimeError, match="no model was selected"):
            experiment.final_test(EXPERIMENT, **roots)

    # ---- publication: a failure before the end leaves serving untouched
    assert bundles.read_active(artifact_root) is None
    with monkeypatch.context() as patched:                                     # feature code that no longer matches training
        patched.setattr(F, "LATE_FROM", 0.5)
        with pytest.raises(RuntimeError, match="no longer reproduces the features"):
            publishing.publish(EXPERIMENT, **roots)
    with monkeypatch.context() as patched:                                     # a report that cannot be built
        patched.setattr(publishing, "build_report", lambda *a, **k: (_ for _ in ()).throw(KeyError("broken report")))
        with pytest.raises(KeyError):
            publishing.publish(EXPERIMENT, **roots)
    assert bundles.read_active(artifact_root) is None and not (out / "published" / "experiment.json").exists()

    published = publishing.publish(EXPERIMENT, **roots)
    pointer = bundles.read_active(artifact_root)
    assert pointer["baseline_id"] == published["baseline_id"] and pointer["model_id"] == published["model_id"]
    served = bundles.load_bundle(pointer["model_id"] or pointer["baseline_id"], artifact_root)
    assert served.manifest["training_code_sha256"] == trained["scoring_code_sha256"] and served.manifest["training_code_source"] == "training record"
    assert served.manifest["training_cutoff"] == trained["cutoff"] and served.manifest["feature_check"]["world_id"] == first_training
    assert served.manifest["feature_quantiles"]["raw_return_rate"] == trained["feature_quantiles"]["raw_return_rate"]
    assert not bundles.code_differs(served)

    report = json.loads((out / "published" / "experiment.json").read_text(encoding="utf-8"))
    conforms("Experiment", report)
    assert report["difficulty_calibration"] == {"calibrated": True, "levers": ["genuine claim rates"], "record_ref": "records/calibration.md"}
    slices = {m["slice"] for m in report["reference_metrics"]}
    assert {"ablation", "honest_groups", "calibration", f"stress:W{halved}"} <= slices
    every = [m for key in ("baseline_metrics", "per_world_metrics", "sensitivity_metrics", "reference_metrics", "error_account",
                           "style_metrics", "wardrobing_metrics") for m in report[key]] + [m for c in report["candidates"] for m in c["metrics"]]
    assert all(m["code"] for m in every)                                       # every published number can be found without its wording
    limits = " ".join(report["coverage_limitations"])
    assert "Two signals carry the model" in limits and "two or more genuinely failed deliveries" in limits
    assert "review rate, honest repeat genuine claimants" in {m["name"] for m in report["baseline_metrics"]}      # the fourth leg is reported
    if chosen:
        assert "Quote the gap to the rule, not the level" in limits
