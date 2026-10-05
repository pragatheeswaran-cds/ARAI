"""Offline publication: turn a finished experiment into what serving may read (final-spec components 09, 10, 12).

Runs after selection (and after the final test, if there was one). It writes
- the baseline bundle and, when the selection is promotable, the selected model's bundle;
- the active pointer;
- `published/experiment.json`, the experiment report in the API's shape, and a labelled synthetic truth export
  for the evaluation page.
The worker loads the report and the truth export into PostgreSQL at startup; the API reads them from there
(decision AM-39). Serving never opens the private truth root.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from arai import bundles, modeling, paths
from arai.evaluation import ACTION_TYPES, SEGMENTS
from arai.selection import BASELINE

PRIMARY = "0.05"
CALIBRATION_RECORD = "records/2026-10-02-gate-dry-run.md"
SEGMENT_LABELS = {"legit_heavy_returner": "honest heavy returners", "defective_product_buyer": "honest defective-product buyers",
                  "benign_household": "honest household members"}
REFERENCE_LABELS = {"analyst_rulebook": "analyst rulebook", "volume_only_logreg": "volume-only model"}


def _metric(name, value, numerator=None, denominator=None, lower=None, upper=None, scope="") -> dict:
    number = lambda v: None if v is None or pd.isna(v) else float(v)  # noqa: E731
    return {"name": name, "value": number(value), "numerator": number(numerator), "denominator": number(denominator),
            "lower_95": number(lower), "upper_95": number(upper), "scope": scope}


SPREAD_NOTE = "; lower and upper are the spread over resampled whole worlds, not a significance test"
CIRCULAR_NOTE = "; this group is defined on return rate, the quantity the rule ranks by, so it is reported and is not evidence"


def _ranking_metrics(confusion: dict, scope: str, interval: dict | None = None) -> list:
    """Precision, recall, segment rates and recall by kind of abuse for one ranking at one budget."""
    interval = interval or {}
    out = [_metric("precision", confusion["precision"], confusion["true_positives"], confusion["k"],
                   interval.get("lower_95"), interval.get("upper_95"), scope + (SPREAD_NOTE if interval else "")),
           _metric("recall", confusion["recall"], confusion["true_positives"], confusion["positives"], scope=scope)]
    for segment in SEGMENTS:
        note = CIRCULAR_NOTE if segment == "legit_heavy_returner" else ""
        out.append(_metric(f"review rate, {SEGMENT_LABELS[segment]}", confusion[segment + "_fpr"], confusion[segment + "_selected"],
                           confusion[segment + "_size"], scope=scope + note))
    for action in (*ACTION_TYPES, "coordinated_action_flag"):
        out.append(_metric(f"recall, {action.replace('_', ' ').replace(' flag', '')}", confusion["recall_" + action], scope=scope))
    return out


def _share(name, numerator, denominator, scope) -> dict:
    return _metric(name, numerator / denominator if denominator else None, numerator, denominator, scope=scope)


def _account_metrics(account: dict | None, scope: str) -> list:
    """The error account. A total is a count with no denominator; every split is a share with both."""
    if not account:
        return []
    fp, fn, diff = account["false_positives"], account["false_negatives"], account["model_versus_baseline"]
    out = [_metric("false positives (count)", fp["false_positives"], scope=scope)]
    for key, label in (("legit_heavy_returner", "heavy returners"), ("defective_product_buyer", "defective-product buyers"),
                       ("benign_household", "household members"), ("repeat_genuine_claimant", "repeat genuine claimants"),
                       ("none_of_these", "in none of these groups")):
        out.append(_share(f"share of false positives who are {label}", fp[key], fp["false_positives"], scope + "; groups overlap"))
    out.append(_metric("false negatives (count)", fn["false_negatives"], scope=scope))
    for action in ACTION_TYPES:
        out.append(_share(f"share of false negatives with a {action.replace('_', ' ')}", fn[action], fn["false_negatives"],
                          scope + "; action types overlap"))
    for bucket in ("1", "2-3", "4+"):
        out.append(_share(f"abusers with {bucket} completed action(s) who were missed", fn[f"completed_actions_{bucket}"],
                          fn[f"positives_with_{bucket}_actions"], scope))
    out += [_metric("selected by the model and not by the return-rate rule (count)", diff["selected_by_model_only"], scope=scope),
            _share("share of model-only selections who are abusers", diff["of_which_abusers"], diff["selected_by_model_only"], scope),
            _metric("selected by the return-rate rule and not by the model (count)", diff["selected_by_baseline_only"], scope=scope),
            _share("share of rule-only selections who are honest", diff["of_which_honest"], diff["selected_by_baseline_only"], scope)]
    for segment in SEGMENTS:
        out.append(_share(f"share of rule-only selections who are {SEGMENT_LABELS[segment]}", diff[f"baseline_only_{segment}"],
                          diff["selected_by_baseline_only"], scope + "; groups overlap"))
    return out


def _evidence_metrics(evidence: dict | None, scope: str) -> tuple:
    if not evidence:
        return [], []
    styles = []
    for name in ("targeting", "quality"):
        e = evidence[name]
        styles += [_metric(f"{name} signal precision", e["precision"], e["true_positives"], e["fired"], scope=scope),
                   _metric(f"{name} signal recall, supported styles", e["recall"], e["true_positives"], e["truth_positive_styles"], scope=scope),
                   _metric(f"{name} signal recall, all styles", e["recall_all_styles"], scope=scope)]
    wardrobing = []
    for key, label in (("wardrobing_elevated", "elevated"), ("wardrobing_elevated_or_possible", "elevated or possible")):
        e = evidence[key]
        wardrobing += [_metric(f"wardrobing {label}: precision", e["precision"], e["true_positives"], e["flagged"], scope=scope),
                       _metric(f"wardrobing {label}: recall", e["recall"], e["true_positives"], e["temporary_use_customers"], scope=scope)]
    for key, label in (("honest_late_returners", "honest customers with a late request"), ("honest_size_bracketers", "honest size bracketers")):
        e = evidence["wardrobing_false_alerts"][key]
        wardrobing.append(_share(f"wardrobing alerts among {label}", e["alerted"], e["customers"], scope))
    return styles, wardrobing


def build_report(experiment_dir: Path, promoted_model_id: str | None) -> dict:
    """The experiment in the API's `Experiment` shape, from the frozen offline reports."""
    experiment_dir = Path(experiment_dir)
    load = lambda name: json.loads((experiment_dir / name).read_text(encoding="utf-8"))  # noqa: E731
    config, dry = load("config.json"), load("reports/dry_run.json")
    selection = load("selection.json") if (experiment_dir / "selection.json").is_file() else None
    validation = load("reports/validation.json") if (experiment_dir / "reports" / "validation.json").is_file() else None
    test = load("reports/test.json") if (experiment_dir / "reports" / "test.json").is_file() else None
    source = validation or dry
    scope = "validation worlds, 5% review budget" if validation else "training worlds out of fold (gate dry run), 5% review budget"
    intervals = {row["ranking"]: row for row in source["bootstrap"]}
    card = {row["ranking"]: row for row in source["scorecard"]}

    candidates = []
    for candidate in modeling.candidates():
        row = card[candidate.id]
        status = "not_evaluated" if validation is None else ("error" if str(row["reasons"]).startswith("fit rejected") else row["status"])
        candidates.append({"candidate_id": candidate.id, "ordinal": candidate.ordinal, "status": status,
                           "reasons": [r for r in str(row["reasons"] or "").split("; ") if r],
                           "metrics": _ranking_metrics(source["sensitivity"][candidate.id][PRIMARY], scope, intervals.get(candidate.id))})
    references = []
    for name, label in REFERENCE_LABELS.items():
        references += [dict(m, name=f"{label}: {m['name']}") for m in
                       _ranking_metrics(source["sensitivity"][name][PRIMARY], scope + "; report only", intervals.get(name))]
    calibration = dry["calibration"]
    references += [
        _metric("difficulty target check: return-rate rule precision", calibration["baseline_precision"],
                lower=calibration["baseline_target"][0], upper=calibration["baseline_target"][1],
                scope="difficulty calibration; training worlds out of fold; lower and upper are the target band, not an interval"),
        _metric("difficulty target check: best supervised precision", calibration["best_supervised_precision"],
                lower=calibration["best_supervised_target"][0], upper=calibration["best_supervised_target"][1],
                scope="difficulty calibration; training worlds out of fold; lower and upper are the target band, not an interval")]

    ablation_path = experiment_dir / "reports" / "timing_ablation.json"
    if ablation_path.is_file():                       # AM-31: how much of the result the timing features carry
        ablation = json.loads(ablation_path.read_text(encoding="utf-8"))
        for row in ablation["variants"]:
            references.append(_metric(f"{ablation['candidate_id']} precision, {row['variant']}", row["precision"], row["true_positives"],
                                      row["k"], scope="timing-feature ablation; training worlds out of fold, 5% review budget"))
        references.append(_metric("return-rate rule precision", ablation["baseline_precision"],
                                  scope="timing-feature ablation; training worlds out of fold, 5% review budget"))

    per_world, sensitivity = [], []
    for ranking, rows in source["per_world"].items():
        for row in rows:
            per_world.append(_metric(f"{ranking}: precision", row["precision"], row["true_positives"], row["k"],
                                     scope=f"world {row['index']}, 5% review budget"))
    for ranking, budgets in source["sensitivity"].items():
        for fraction, confusion in budgets.items():
            label = f"{float(fraction):.0%} review budget"
            sensitivity += [_metric(f"{ranking}: precision", confusion["precision"], confusion["true_positives"], confusion["k"], scope=label),
                            _metric(f"{ranking}: recall", confusion["recall"], confusion["true_positives"], confusion["positives"], scope=label)]
    if test:
        chosen = test["selected_model_id"]
        for ranking in (BASELINE, chosen):
            for m in _ranking_metrics(test["sensitivity"][ranking][PRIMARY], "final test worlds, 5% review budget",
                                      {row["ranking"]: row for row in test["bootstrap"]}.get(ranking)):
                sensitivity.append(dict(m, name=f"{ranking}: {m['name']}"))

    style_metrics, wardrobing_metrics = _evidence_metrics((validation or {}).get("evidence_report_only"), "validation worlds; report only")
    coverage = source["coverage"]
    where = "validation worlds" if validation else "training worlds"
    limitations = [f"{coverage['abusers_excluded']} of {coverage['abusers_all']} abusers on the {where} have fewer than three mature sale "
                   "lines and are outside the ranking.", "Simulated data from one generator: results show stability across simulated worlds, not "
                   "performance on real returns.",
                   "The result leans on when in the return window items come back, which the simulation makes sharper than real "
                   "behaviour would be; the precision without any timing feature is the figure to quote as robust.",
                   "The heavy-returner group is defined on return rate itself, so that gate leg cannot fail for a model and is not evidence."]
    limitations += [f"Segment {SEGMENT_LABELS[s]} has fewer than 200 members." for s in coverage["segments_below_minimum"]]
    if test:
        limitations.insert(1, f"{test['coverage']['abusers_excluded']} of {test['coverage']['abusers_all']} abusers on the final test "
                              "worlds are outside the ranking for the same reason.")
        limitations += [f"Final test: segment {SEGMENT_LABELS[s]} has fewer than 200 members." for s in test["coverage_limitations"]]
    if validation is None:
        limitations.append("Validation has not been run: every figure shown is a gate dry run on training worlds.")

    account = _account_metrics((validation or {}).get("error_account"), "validation worlds, selected model, 5% review budget")
    if test:
        account += _account_metrics(test.get("error_account"), "final test worlds, selected model, 5% review budget")
    return {
        "summary": {"experiment_id": config["experiment_id"], "config_hash": config["experiment_config_sha256"],
                    "selection_status": selection["selection_status"] if selection else "not_completed",
                    "selected_model_id": promoted_model_id,
                    "selected_candidate_id": selection["selected_model_id"] if selection else None,
                    "final_test_status": selection["final_test_status"] if selection else "not_run"},
        "synthetic_only": True,
        "baseline_metrics": _ranking_metrics(source["sensitivity"][BASELINE][PRIMARY], scope, intervals.get(BASELINE)),
        "candidates": candidates, "per_world_metrics": per_world, "sensitivity_metrics": sensitivity,
        "style_metrics": style_metrics, "wardrobing_metrics": wardrobing_metrics, "coverage_limitations": limitations,
        "report_only_evidence_metrics": True, "reference_metrics": references, "error_account": account,
        "difficulty_calibration": {"calibrated": False, "levers": [], "record_ref": CALIBRATION_RECORD},
    }


def export_truth(experiment_dir: Path, demo_world: str, private_root: Path | None = None) -> Path:
    """Synthetic truth of the demonstration world for the evaluation page: abusers first, then by identifier."""
    private = Path(private_root or paths.PRIVATE_TRUTH_ROOT) / demo_world
    truth = pd.read_parquet(private / "customer_truth.parquet")
    kinds = truth[list(ACTION_TYPES)].apply(lambda row: "|".join(a for a in ACTION_TYPES if row[a]), axis=1)
    out = pd.DataFrame({"world_id": demo_world, "customer_id": truth["customer_id"], "y_abuse": truth["y_abuse"].astype(int),
                        "action_types": kinds})
    out = out.sort_values(["y_abuse", "customer_id"], ascending=[False, True]).reset_index(drop=True)
    target = Path(experiment_dir) / "published" / "truth.parquet"
    target.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(target, index=False)
    return target


def publish(experiment_id: str, artifact_root: Path | None = None, private_root: Path | None = None,
            demo_world: str | None = None) -> dict:
    """Build bundles, decide what may be active, point serving at it, and write the published report.

    A selected model is promoted only when its final test passed. Otherwise serving falls back to the baseline
    and the pointer says why; a failed gate and a selection that was never made are different states.
    """
    experiment_dir = modeling.experiment_dir(experiment_id, artifact_root)
    baseline_id = bundles.build_baseline_bundle(experiment_dir, artifact_root)
    selection = json.loads((experiment_dir / "selection.json").read_text(encoding="utf-8")) if (experiment_dir / "selection.json").is_file() else None
    model_id, status, reason = None, "not_completed", "Model selection has not been completed for this experiment."
    if selection:
        status = selection["selection_status"]
        if status == "no_selected_model":
            reason = "No candidate passed the gate on the validation worlds."
        elif selection["final_test_status"] == "passed":
            model_id, reason = bundles.build_model_bundle(experiment_dir, selection["selected_model_id"], artifact_root), None
        elif selection["final_test_status"] == "not_run":
            status = "not_completed"
            reason = (f"{selection['selected_model_id']} was selected on validation; its final test has not been run, and a "
                      "model is promoted only after a passed final test.")
        else:
            status = "no_selected_model"
            reason = (f"{selection['selected_model_id']} was selected on validation but its final test is "
                      f"{selection['final_test_status']}; it is not promoted and no runner-up takes its place.")
    pointer = bundles.activate(model_id, baseline_id, "selected" if model_id else status, experiment_id, reason, artifact_root)
    report = build_report(experiment_dir, model_id)
    published = experiment_dir / "published"
    published.mkdir(parents=True, exist_ok=True)
    (published / "experiment.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if demo_world:
        export_truth(experiment_dir, demo_world, private_root)
    return {"pointer": pointer, "baseline_id": baseline_id, "model_id": model_id, "report": str(published / "experiment.json")}
