"""One experiment end to end: train, dry-run the gate, validate and select, then one final test.

The order is enforced, not assumed (final-spec components 07 to 09):
  train -> gate dry run on out-of-fold training scores -> validation selection (frozen) -> final test, once.
A selected model is never refit on validation, and a failed test never switches to a runner-up.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from arai import dataset, evaluation, features as F, modeling, selection
from arai.evaluation import PRIMARY_FRACTION, SENSITIVITY_FRACTIONS
from arai.generator import load_world
from arai.settings import load_settings

DEFAULT_EXPERIMENT = "EXP-20261002-01"
REFERENCES = ("volume_only_logreg", "analyst_rulebook")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=_plain) + "\n", encoding="utf-8")


def _plain(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    raise TypeError(type(value))


def _records(frame: pd.DataFrame) -> list:
    return json.loads(frame.reset_index().to_json(orient="records"))


# ------------------------------------------------------------------ training
def train(experiment_id: str = DEFAULT_EXPERIMENT, artifact_root=None, private_root=None) -> dict:
    """Freeze the training reference and features, then fit the candidates and references."""
    settings = load_settings()
    train_worlds = [f"W{s}" for s in settings.experiment["train_seeds"]]
    out = modeling.experiment_dir(experiment_id, artifact_root)
    if (out / "selection.json").exists():
        raise RuntimeError("this experiment already has a frozen selection; start a new experiment instead of retraining")
    reference = dataset.reference_from_worlds(train_worlds)
    for world_id in train_worlds:
        dataset.build_features(world_id, reference, artifact_root)
    result = modeling.train_experiment(experiment_id, train_worlds, artifact_root, private_root)
    frame = modeling.training_frame(train_worlds, artifact_root, private_root)
    thresholds = selection.rulebook_thresholds(frame)
    _write(out / "references" / "analyst_rulebook" / "thresholds.json",
           {"thresholds": thresholds, "rules": list(selection.RULEBOOK_RULES), "fitted_on": train_worlds})
    # the baseline bundle is training statistics only and depends on no candidate (final-spec component 10)
    _write(out / "baseline" / "baseline.json", {
        "kind": "baseline_fallback", "score": "raw_return_rate", "reference": reference.to_dict(),
        "training_worlds": train_worlds, "label": "Return-rate reference percentile"})
    pd.DataFrame({"score": np.sort(frame["raw_return_rate"].to_numpy())}).to_parquet(out / "baseline" / "reference_scores.parquet", index=False)
    return result


# ------------------------------------------------------------------ scoring worlds with frozen artifacts
def _reference(out: Path) -> F.Reference:
    return F.Reference.from_dict(json.loads((out / "baseline" / "baseline.json").read_text())["reference"])


def _training_rankings(out: Path, frame: pd.DataFrame) -> pd.DataFrame:
    """Out-of-fold (or, for isolation forests, in-sample) training scores joined to the evaluation frame."""
    config = json.loads((out / "config.json").read_text())
    for candidate in modeling.candidates():
        scores = pd.read_parquet(out / "candidates" / candidate.id / "training_scores.parquet")
        frame = frame.merge(scores[["world_id", "customer_id", "reference_score"]].rename(columns={"reference_score": candidate.id}),
                            on=["world_id", "customer_id"], validate="one_to_one")
    volume = pd.read_parquet(out / "references" / "volume_only_logreg" / "training_scores.parquet")
    frame = frame.merge(volume[["world_id", "customer_id", "reference_score"]].rename(columns={"reference_score": "volume_only_logreg"}),
                        on=["world_id", "customer_id"], validate="one_to_one")
    frame["analyst_rulebook"] = selection.rulebook_out_of_fold(frame, config["folds"])
    return frame


def _frozen_rankings(out: Path, frame: pd.DataFrame, only: list | None = None) -> pd.DataFrame:
    """Scores from the frozen final estimators and frozen rulebook thresholds. Nothing is fitted here."""
    for candidate in modeling.candidates():
        if only is not None and candidate.id not in only:
            continue
        pipeline = modeling.load_pipeline(out / "candidates" / candidate.id / "model.skops")
        frame[candidate.id] = modeling.raw_scores(candidate, pipeline, frame)
    if only is None:
        volume = modeling.volume_only_reference()
        frame[volume.id] = modeling.raw_scores(volume, modeling.load_pipeline(out / "references" / volume.id / "model.skops"), frame)
        thresholds = json.loads((out / "references" / "analyst_rulebook" / "thresholds.json").read_text())["thresholds"]
        frame["analyst_rulebook"] = selection.rulebook_score(frame, thresholds)
    return frame


def _rankings(only: list | None = None) -> tuple:
    rankings, selectable = {selection.BASELINE: selection.BASELINE}, {}
    records = {c.id: c for c in modeling.candidates()}
    for candidate_id, candidate in records.items():
        if only is None or candidate_id in only:
            rankings[candidate_id] = candidate_id
            selectable[candidate_id] = candidate.ordinal
    if only is None:
        rankings.update({name: name for name in REFERENCES})
    return rankings, selectable


def _report(frame: pd.DataFrame, rankings: dict, selectable: dict, rejected: dict, world_ids: list, private_root=None,
            require_coverage: bool = True) -> dict:
    card = selection.scorecard(frame, rankings, selectable, require_coverage)
    for candidate_id, reason in rejected.items():           # a candidate that failed to fit cannot pass
        if candidate_id in card.index:
            card.loc[candidate_id, ["status", "reasons"]] = ["rejected", f"fit rejected: {reason}"]
    sensitivity = {name: {str(f): evaluation.confusion(frame, evaluation.select(frame, column, f))
                          for f in (PRIMARY_FRACTION, *SENSITIVITY_FRACTIONS)} for name, column in rankings.items()}
    worlds = {name: _records(evaluation.per_world(frame, evaluation.select(frame, column)))
              for name, column in rankings.items()}
    return {"scorecard": _records(card), "sensitivity": sensitivity, "per_world": worlds,
            "bootstrap": _records(evaluation.bootstrap(frame, rankings, selection.BASELINE)),
            "coverage": evaluation.coverage(frame, world_ids, private_root), "card": card}


def _fit_rejections(out: Path) -> dict:
    rejected = {}
    for candidate in modeling.candidates():
        record = json.loads((out / "candidates" / candidate.id / "record.json").read_text())
        if record["status"] != "fitted":
            rejected[candidate.id] = record["rejection"]
    return rejected


# ------------------------------------------------------------------ gate dry run and calibration
def dry_run(experiment_id: str = DEFAULT_EXPERIMENT, artifact_root=None, private_root=None) -> dict:
    """The full gate on out-of-fold training scores, before any validation world exists. It selects nothing."""
    settings = load_settings()
    out = modeling.experiment_dir(experiment_id, artifact_root)
    train_worlds = [f"W{s}" for s in settings.experiment["train_seeds"]]
    frame = _training_rankings(out, evaluation.evaluation_frame(train_worlds, artifact_root, private_root))
    rankings, selectable = _rankings()
    report = _report(frame, rankings, selectable, _fit_rejections(out), train_worlds, private_root)
    card = report.pop("card")
    supervised = card[(card["role"] == "candidate") & card.index.isin([c.id for c in modeling.candidates() if c.supervised])]
    targets = settings.experiment["difficulty_calibration"]["targets"]
    best = float(supervised["precision"].max())
    baseline = float(card.loc[selection.BASELINE, "precision"])
    payload = {
        "kind": "gate dry run on out-of-fold training scores; diagnostic only, selects nothing",
        "experiment_id": experiment_id, "recorded_at": _now(), "worlds": train_worlds,
        "isolation_forest_scores": "in-sample, optimistic", **report,
        "would_pass": card[(card["role"] == "candidate") & (card["status"] == "passed")].index.tolist(),
        "calibration": {
            "measured_on": "pooled out-of-fold training-world scores at the 5% budget",
            "baseline_precision": baseline, "baseline_target": targets["baseline_precision"],
            "baseline_in_band": targets["baseline_precision"][0] <= baseline <= targets["baseline_precision"][1],
            "best_supervised_precision": best, "best_supervised_target": targets["best_supervised_precision"],
            "best_in_band": targets["best_supervised_precision"][0] <= best <= targets["best_supervised_precision"][1],
            "above_ceiling": best > targets["raise_difficulty_above"]},
    }
    _write(out / "reports" / "dry_run.json", payload)
    return payload | {"card": card}


# ------------------------------------------------------------------ validation and selection
def validate(experiment_id: str = DEFAULT_EXPERIMENT, artifact_root=None, private_root=None) -> dict:
    """Score the validation worlds with the frozen estimators, apply the gate and freeze the selection."""
    settings = load_settings()
    out = modeling.experiment_dir(experiment_id, artifact_root)
    if not (out / "reports" / "dry_run.json").exists():
        raise RuntimeError("the gate dry run must be recorded before validation")
    if (out / "selection.json").exists():
        raise RuntimeError("selection is already frozen for this experiment")
    worlds = [f"W{s}" for s in settings.experiment["validation_seeds"]]
    reference = _reference(out)
    for world_id in worlds:
        dataset.build_features(world_id, reference, artifact_root)
    frame = _frozen_rankings(out, evaluation.evaluation_frame(worlds, artifact_root, private_root))
    rankings, selectable = _rankings()
    report = _report(frame, rankings, selectable, _fit_rejections(out), worlds, private_root)
    card = report.pop("card")
    chosen = selection.choose(card)
    evidence = evidence_metrics(worlds, artifact_root, private_root)
    account = None
    if chosen:
        counts = evaluation.private_counts(worlds, private_root)
        joined = frame.merge(counts, on=["world_id", "customer_id"], validate="one_to_one")
        account = evaluation.error_account(joined, evaluation.select(joined, chosen), evaluation.select(joined, selection.BASELINE),
                                           joined["completed_actions"])
    _write(out / "reports" / "validation.json", {"experiment_id": experiment_id, "recorded_at": _now(), "worlds": worlds, **report,
                                                 "evidence_report_only": evidence, "error_account": account})
    record = {"experiment_id": experiment_id, "frozen_at": _now(), "validation_worlds": worlds,
              "selection_status": "selected" if chosen else "no_selected_model", "selected_model_id": chosen,
              "selected_model_sha256": json.loads((out / "candidates" / chosen / "record.json").read_text())["model_sha256"] if chosen else None,
              "rule": "strictly higher precision than the raw-return-rate baseline and no higher false-positive rate in each "
                      "benign segment at the 5% budget; then precision, worst segment rate, registered ordinal",
              "candidates": _records(card[card["role"] == "candidate"][["precision", "status", "reasons", "ordinal"]]),
              "final_test_status": "not_run"}
    _write(out / "selection.json", record)
    return record | {"card": card}


# ------------------------------------------------------------------ final test, once
def final_test(experiment_id: str = DEFAULT_EXPERIMENT, artifact_root=None, private_root=None) -> dict:
    """Evaluate the frozen selection once on the untouched test worlds. A failure blocks promotion; no runner-up."""
    settings = load_settings()
    out = modeling.experiment_dir(experiment_id, artifact_root)
    if not (out / "selection.json").exists():
        raise RuntimeError("selection must be frozen before the test worlds are scored")
    if (out / "reports" / "test.json").exists():
        raise RuntimeError("the final test has already been run for this experiment; it runs once")
    record = json.loads((out / "selection.json").read_text())
    chosen = record["selected_model_id"]
    if chosen is None:
        raise RuntimeError("no model was selected; there is nothing to test and the baseline fallback applies")
    worlds = [f"W{s}" for s in settings.experiment["test_seeds"]]
    reference = _reference(out)
    for world_id in worlds:
        dataset.build_features(world_id, reference, artifact_root)
    frame = _frozen_rankings(out, evaluation.evaluation_frame(worlds, artifact_root, private_root), only=[chosen])
    rankings, selectable = _rankings(only=[chosen])
    report = _report(frame, rankings, selectable, {}, worlds, private_root, require_coverage=False)
    card = report.pop("card")
    coverage = report["coverage"]
    empty = [s for s, size in coverage["segment_sizes"].items() if size == 0]
    passed = card.loc[chosen, "status"] == "passed"
    status = "unverifiable" if empty else ("passed" if passed else "failed")
    counts = evaluation.private_counts(worlds, private_root)
    joined = frame.merge(counts, on=["world_id", "customer_id"], validate="one_to_one")
    account = evaluation.error_account(joined, evaluation.select(joined, chosen), evaluation.select(joined, selection.BASELINE),
                                       joined["completed_actions"])
    payload = {"experiment_id": experiment_id, "recorded_at": _now(), "worlds": worlds, "selected_model_id": chosen,
               "final_test_status": status, **report, "coverage_limitations": coverage["segments_below_minimum"],
               "evidence_report_only": evidence_metrics(worlds, artifact_root, private_root), "error_account": account}
    _write(out / "reports" / "test.json", payload)
    record["final_test_status"] = status
    record["tested_at"] = _now()
    _write(out / "selection.json", record)
    return payload | {"card": card}


# ------------------------------------------------------------------ report-only evidence metrics
def evidence_metrics(world_ids: list, artifact_root=None, private_root=None) -> dict:
    """Style signals and the wardrobing indicator against private truth. Reported, never gated."""
    styles, rows = [], []
    for world_id in world_ids:
        world = load_world(world_id, artifact_root, private_root)
        directory = dataset.feature_dir(world_id, artifact_root)
        truth = world.truth["product_truth"][["style_id", "defect_state", "targeting_level"]]
        styles.append(pd.read_parquet(directory / "styles.parquet").merge(truth, on="style_id").assign(world_id=world_id))
        features = dataset.load_features(world_id, artifact_root)
        wardrobing = pd.read_parquet(directory / "wardrobing.parquet")[["customer_id", "status"]]
        truth_c = world.truth["customer_truth"][["customer_id", "y_abuse", "temporary_use_return"]]
        rows.append(features[["customer_id", "eligible", "late_window_share", "bracketing_share"]].merge(wardrobing, on="customer_id").merge(truth_c, on="customer_id"))
    styles, customers = pd.concat(styles, ignore_index=True), pd.concat(rows, ignore_index=True)
    supported = styles[styles["mature_sale_lines"] >= F.STYLE_SUPPORT]
    out = {"style_states_by_truth": pd.crosstab([supported["defect_state"], supported["targeting_level"]], supported["state"]).reset_index().to_dict(orient="records")}
    for name, fired, truth in (("targeting", supported["targeting_signal"], supported["targeting_level"] == "targeted"),
                               ("quality", supported["quality_signal"], supported["defect_state"] == "defect_prone")):
        tp = int((fired & truth).sum())
        out[name] = {"fired": int(fired.sum()), "true_positives": tp, "truth_positive_styles": int(truth.sum()),
                     "precision": evaluation.ratio(tp, fired.sum()), "recall": evaluation.ratio(tp, truth.sum()),
                     "recall_all_styles": evaluation.ratio(tp, (styles["targeting_level"] == "targeted").sum() if name == "targeting"
                                                           else (styles["defect_state"] == "defect_prone").sum())}
    eligible = customers[customers["eligible"]]
    actual = eligible["temporary_use_return"].astype(bool)
    for label, flagged in (("wardrobing_elevated", eligible["status"] == "elevated"),
                           ("wardrobing_elevated_or_possible", eligible["status"].isin(["elevated", "possible"]))):
        tp = int((flagged & actual).sum())
        out[label] = {"flagged": int(flagged.sum()), "true_positives": tp, "temporary_use_customers": int(actual.sum()),
                      "precision": evaluation.ratio(tp, flagged.sum()), "recall": evaluation.ratio(tp, actual.sum())}
    honest = eligible[eligible["y_abuse"] == 0]
    alerts = honest["status"].isin(["elevated", "possible"])
    out["wardrobing_false_alerts"] = {
        "honest_late_returners": {"customers": int((honest["late_window_share"] > 0).sum()),
                                  "alerted": int((alerts & (honest["late_window_share"] > 0)).sum())},
        "honest_size_bracketers": {"customers": int((honest["bracketing_share"] > 0).sum()),
                                   "alerted": int((alerts & (honest["bracketing_share"] > 0)).sum())}}
    return out
