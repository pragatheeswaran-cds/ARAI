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

import io
import json
import os
import subprocess
from pathlib import Path

import pandas as pd

from arai import bundles, contract, dataset, modeling, paths
from arai import features as F
from arai.evaluation import ACTION_TYPES, SEGMENTS
from arai.selection import BASELINE

PRIMARY = "0.05"
CALIBRATION_RECORD = "records/2026-10-02-gate-dry-run.md"      # for dry runs recorded before they named their record
SEGMENT_LABELS = {"legit_heavy_returner": "honest heavy returners", "defective_product_buyer": "honest defective-product buyers",
                  "benign_household": "honest household members", "repeat_genuine_claimant": "honest repeat genuine claimants",
                  "one_genuine_failure": "honest customers with one genuine delivery failure"}
REFERENCE_LABELS = {"analyst_rulebook": "analyst rulebook", "volume_only_logreg": "volume-only model"}


def _metric(name, value, numerator=None, denominator=None, lower=None, upper=None, scope="", code=None, ranking=None,
            slice=None) -> dict:
    """One reported number. `code`, `ranking` and `slice` identify it; `name` and `scope` are display text and may be reworded."""
    number = lambda v: None if v is None or pd.isna(v) else float(v)
    return {"code": code, "ranking": ranking, "slice": slice, "name": name, "value": number(value), "numerator": number(numerator),
            "denominator": number(denominator), "lower_95": number(lower), "upper_95": number(upper), "scope": scope}


SPREAD_NOTE = "; lower and upper are the spread over resampled whole worlds, not a significance test"
CIRCULAR_NOTE = "; this group is defined on return rate, the quantity the rule ranks by, so it is reported and is not evidence"
OLD_ABLATION_KEYS = {"all features": "all", "without late_return_lines": "without_late_return_lines",
                     "without any timing feature": "without_timing"}


def _ranking_metrics(confusion: dict, scope: str, interval: dict | None = None, ranking: str | None = None,
                     slice: str | None = None) -> list:
    """Precision, recall, segment rates and recall by kind of abuse for one ranking at one budget."""
    interval = interval or {}
    ids = {"ranking": ranking, "slice": slice}
    out = [_metric("precision", confusion["precision"], confusion["true_positives"], confusion["k"],
                   interval.get("lower_95"), interval.get("upper_95"), scope + (SPREAD_NOTE if interval else ""), code="precision", **ids),
           _metric("recall", confusion["recall"], confusion["true_positives"], confusion["positives"], scope=scope, code="recall", **ids)]
    for segment in SEGMENTS:
        note = CIRCULAR_NOTE if segment == "legit_heavy_returner" else ""
        out.append(_metric(f"review rate, {SEGMENT_LABELS[segment]}", confusion[segment + "_fpr"], confusion[segment + "_selected"],
                           confusion[segment + "_size"], scope=scope + note, code=f"review_rate.{segment}", **ids))
    for action in (*ACTION_TYPES, "coordinated_action_flag"):
        kind = action.replace("_flag", "")
        out.append(_metric(f"recall, {kind.replace('_', ' ')}", confusion["recall_" + action], scope=scope, code=f"recall.{kind}", **ids))
    return out


def _share(name, numerator, denominator, scope, **ids) -> dict:
    return _metric(name, numerator / denominator if denominator else None, numerator, denominator, scope=scope, **ids)


def _account_metrics(account: dict | None, scope: str, slice: str) -> list:
    """The error account. A total is a count with no denominator; every split is a share with both."""
    if not account:
        return []
    fp, fn, diff = account["false_positives"], account["false_negatives"], account["model_versus_baseline"]
    out = [_metric("false positives (count)", fp["false_positives"], scope=scope, code="errors.false_positives.count", slice=slice)]
    for key, label in (("legit_heavy_returner", "heavy returners"), ("defective_product_buyer", "defective-product buyers"),
                       ("benign_household", "household members"), ("repeat_genuine_claimant", "repeat genuine claimants"),
                       ("one_genuine_failure", "customers with one genuine delivery failure"), ("none_of_these", "in none of these groups")):
        if key not in fp:                                       # a report recorded under a contract without this leg
            continue
        out.append(_share(f"share of false positives who are {label}", fp[key], fp["false_positives"], scope + "; groups overlap",
                          code=f"errors.false_positive_share.{key}", slice=slice))
    out.append(_metric("false negatives (count)", fn["false_negatives"], scope=scope, code="errors.false_negatives.count", slice=slice))
    for action in ACTION_TYPES:
        out.append(_share(f"share of false negatives with a {action.replace('_', ' ')}", fn[action], fn["false_negatives"],
                          scope + "; action types overlap", code=f"errors.false_negative_share.{action}", slice=slice))
    for bucket in ("1", "2-3", "4+"):
        out.append(_share(f"abusers with {bucket} completed action(s) who were missed", fn[f"completed_actions_{bucket}"],
                          fn[f"positives_with_{bucket}_actions"], scope, code=f"errors.missed_share.actions_{bucket}", slice=slice))
    out += [_metric("selected by the model and not by the return-rate rule (count)", diff["selected_by_model_only"], scope=scope,
                    code="errors.model_only.count", slice=slice),
            _share("share of model-only selections who are abusers", diff["of_which_abusers"], diff["selected_by_model_only"], scope,
                   code="errors.model_only_abuser_share", slice=slice),
            _metric("selected by the return-rate rule and not by the model (count)", diff["selected_by_baseline_only"], scope=scope,
                    code="errors.rule_only.count", slice=slice),
            _share("share of rule-only selections who are honest", diff["of_which_honest"], diff["selected_by_baseline_only"], scope,
                   code="errors.rule_only_honest_share", slice=slice)]
    for segment in SEGMENTS:
        out.append(_share(f"share of rule-only selections who are {SEGMENT_LABELS[segment]}", diff[f"baseline_only_{segment}"],
                          diff["selected_by_baseline_only"], scope + "; groups overlap", code=f"errors.rule_only_share.{segment}", slice=slice))
    return out


def _evidence_metrics(evidence: dict | None, scope: str, slice: str) -> tuple:
    if not evidence:
        return [], []
    styles = []
    for name in ("targeting", "quality"):
        e = evidence[name]
        styles += [_metric(f"{name} signal precision", e["precision"], e["true_positives"], e["fired"], scope=scope,
                           code=f"style.{name}.precision", slice=slice),
                   _metric(f"{name} signal recall, supported styles", e["recall"], e["true_positives"], e["truth_positive_styles"], scope=scope,
                           code=f"style.{name}.recall_supported", slice=slice),
                   _metric(f"{name} signal recall, all styles", e["recall_all_styles"], scope=scope, code=f"style.{name}.recall_all", slice=slice)]
    wardrobing = []
    for key, label in (("wardrobing_elevated", "elevated"), ("wardrobing_possible", "possible"),
                       ("wardrobing_elevated_or_possible", "elevated or possible")):
        if key not in evidence:                                 # a report recorded before the possible band was reported alone
            continue
        e = evidence[key]
        wardrobing += [_metric(f"wardrobing {label}: precision", e["precision"], e["true_positives"], e["flagged"], scope=scope,
                               code=f"{key}.precision", slice=slice),
                       _metric(f"wardrobing {label}: recall", e["recall"], e["true_positives"], e["temporary_use_customers"], scope=scope,
                               code=f"{key}.recall", slice=slice)]
    for key, label in (("honest_late_returners", "honest customers with a late request"), ("honest_size_bracketers", "honest size bracketers"),
                       ("honest_late_occasion_returners", "honest customers with a late return of occasion wear")):
        if key not in evidence["wardrobing_false_alerts"]:
            continue
        e = evidence["wardrobing_false_alerts"][key]
        wardrobing.append(_share(f"wardrobing alerts among {label}", e["alerted"], e["customers"], scope,
                                 code=f"wardrobing_false_alerts.{key}", slice=slice))
    return styles, wardrobing


def _dependence_metrics(experiment_dir: Path) -> tuple:
    """(metrics, facts) of what the result depends on: feature-family ablations and honest-group review rates.

    Read from reports/ablation.json (`arai ablation`); an experiment recorded before that command existed has only
    the timing rows of reports/timing_ablation.json. `facts` feeds the plain-language limitations.
    """
    path = next((p for p in (experiment_dir / "reports" / "ablation.json", experiment_dir / "reports" / "timing_ablation.json")
                 if p.is_file()), None)
    if path is None:
        return [], {}
    ablation = json.loads(path.read_text(encoding="utf-8"))
    candidate, scope = ablation["candidate_id"], "feature ablation; training worlds out of fold, 5% review budget"
    metrics, facts = [], {"candidate": candidate, "rule": ablation["baseline_precision"]}
    for row in ablation["variants"]:
        key = row.get("key") or OLD_ABLATION_KEYS.get(row["variant"], row["variant"])
        facts[key] = row["precision"]
        metrics.append(_metric(f"{candidate} precision, {row['variant']}", row["precision"], row["true_positives"], row["k"], scope=scope,
                               code=f"ablation.{key}", ranking=candidate, slice="ablation"))
    metrics.append(_metric("return-rate rule precision", ablation["baseline_precision"], scope=scope, code="ablation.rule",
                           ranking=BASELINE, slice="ablation"))
    groups = ablation.get("honest_groups")
    if groups:
        scope = "training worlds out of fold, 5% review budget; groups overlap"
        for row in groups["groups"]:
            for who, ranking in (("model", candidate), ("rule", BASELINE)):
                metrics.append(_metric(f"review rate of {row['label']}: {'model' if who == 'model' else 'return-rate rule'}",
                                       row[who + "_rate"], row[who + "_selected"], row["customers"], scope=scope,
                                       code=f"group_review_rate.{row['group']}", ranking=ranking, slice="honest_groups"))
            facts["group." + row["group"]] = (row["model_rate"], row["rule_rate"])
        for who, ranking in (("model", candidate), ("rule", BASELINE)):
            share = groups["false_positives"][who]
            metrics.append(_metric(f"share of false positives who are repeat genuine claimants: {'model' if who == 'model' else 'return-rate rule'}",
                                   share["share"], share["repeat_genuine_claimants"], share["false_positives"], scope=scope,
                                   code="false_positive_share.repeat_genuine_claimant", ranking=ranking, slice="honest_groups"))
        facts["repeat_share_of_false_positives"] = groups["false_positives"]["model"]["share"]
    return metrics, facts


def _stress_metrics(experiment_dir: Path, chosen: str | None) -> tuple:
    """(metrics, facts) of the frozen estimators on the stress worlds (reports/stress.json, `arai stress`)."""
    path = experiment_dir / "reports" / "stress.json"
    if not path.is_file():
        return [], {}
    metrics, model, rule, passed = [], [], [], 0
    for world in json.loads(path.read_text(encoding="utf-8"))["worlds"]:
        for row in world["rankings"]:
            verdict = f"; gate {row['status']}" if row["role"] == "candidate" else ""
            ids = {"ranking": row["ranking"], "slice": f"stress:{world['world_id']}"}
            scope = f"{world['world_id']}: {world['mechanism']}"          # shown as the row title; the budget is the primary 5%
            metrics.append(_metric(f"{row['ranking']}: precision{verdict}", row["precision"], row["true_positives"], row["k"], scope=scope,
                                   code="precision", **ids))
            if row["role"] == "candidate":
                metrics.append(_metric(f"{row['ranking']}: gate passed (1) or not (0)", float(row["status"] == "passed"), scope=scope,
                                       code="gate_passed", **ids))
            if row["ranking"] == chosen:
                model.append(row["precision"])
                passed += row["status"] == "passed"
            if row["ranking"] == BASELINE:
                rule.append(row["precision"])
    facts = {"worlds": len(rule), "rule": (min(rule), max(rule))}
    if model:
        facts.update(model=(min(model), max(model)), passed=passed)
    return metrics, facts


def _stress_wardrobing(experiment_dir: Path) -> list:
    """The wardrobing indicator on each stress world (reports/stress.json), where the simulated behaviour is varied."""
    path = experiment_dir / "reports" / "stress.json"
    if not path.is_file():
        return []
    out = []
    for world in json.loads(path.read_text(encoding="utf-8"))["worlds"]:
        scope = f"stress world {world['world_id']}: {world['mechanism']}; one world, report only"
        for key, label in (("wardrobing_elevated", "elevated"), ("wardrobing_elevated_or_possible", "elevated or possible")):
            e = (world.get("wardrobing") or {}).get(key)
            if e:
                out += [_metric(f"wardrobing {label}: precision", e["precision"], e["true_positives"], e["flagged"], scope=scope,
                                code=f"{key}.precision", slice=f"stress:{world['world_id']}"),
                        _metric(f"wardrobing {label}: recall", e["recall"], e["true_positives"], e["temporary_use_customers"], scope=scope,
                                code=f"{key}.recall", slice=f"stress:{world['world_id']}")]
    return out


def _dependence_limitations(dependence: dict, stress: dict) -> list:
    """The three statements a reader needs before quoting the headline, in plain words, from the measured facts."""
    out, pct = [], lambda v: f"{100 * v:.0f}%"
    if "without_claims" in dependence:
        out.append(f"Two signals carry the model: how much of what a customer asks back is a transaction claim, and item returns made "
                   f"late in the return window. Out of fold on training worlds its precision is {pct(dependence['all'])} with all "
                   f"features, {pct(dependence['without_claims'])} without the claim features, {pct(dependence['without_timing'])} without "
                   f"the timing features and {pct(dependence['without_claims_and_timing'])} without both, against {pct(dependence['rule'])} "
                   "for the return-rate rule. How sharply both signals separate abusers is a setting of this simulation.")
    else:
        out.append("The result leans on when in the return window items come back, which the simulation makes sharper than real "
                   "behaviour would be; the precision without any timing feature is the figure to quote as robust.")
    if "group.repeat_genuine_claimant" in dependence:
        model, rule = dependence["group.repeat_genuine_claimant"]
        gated = "repeat_genuine_claimant" in SEGMENTS
        share = pct(dependence["repeat_share_of_false_positives"])
        if model > rule:
            out.append(f"Honest customers with two or more genuinely failed deliveries are sent for review more often by the model than "
                       f"by the return-rate rule ({100 * model:.1f}% against {100 * rule:.1f}% on training worlds, out of fold) and are "
                       f"{share} of the model's false positives. " + ("The gate has a leg for this group; this figure is from training "
                       "worlds." if gated else "The promotion gate has no leg for this group."))
        else:
            out.append(f"Honest customers with two or more genuinely failed deliveries are a gate group: the model sends "
                       f"{100 * model:.1f}% of them for review against {100 * rule:.1f}% for the return-rate rule (training worlds, out "
                       f"of fold). They are still {share} of the model's false positives, and the model was trained to weigh them more "
                       "heavily, which uses simulation truth that real data would not have.")
    if "group.one_genuine_failure" in dependence and "one_genuine_failure" in SEGMENTS:
        model, rule = dependence["group.one_genuine_failure"]
        out.append(f"Honest customers with exactly one genuinely failed delivery have a gate leg of their own, so that protecting repeat "
                   f"claimants is not paid for by reviewing them instead: the model sends {100 * model:.1f}% of them for review against "
                   f"{100 * rule:.1f}% for the return-rate rule (training worlds, out of fold).")
    if "model" in stress:
        out.append(f"The level of the result follows the simulated behaviour: across the {stress['worlds']} stress worlds the selected "
                   f"model's precision ranges from {pct(stress['model'][0])} to {pct(stress['model'][1])} and the rule's from "
                   f"{pct(stress['rule'][0])} to {pct(stress['rule'][1])}; the model passes the gate on {stress['passed']} of them. "
                   "Quote the gap to the rule, not the level.")
    return out


def build_report(experiment_dir: Path, promoted_model_id: str | None) -> dict:
    """The experiment in the API's `Experiment` shape, from the frozen offline reports."""
    experiment_dir = Path(experiment_dir)
    load = lambda name: json.loads((experiment_dir / name).read_text(encoding="utf-8"))
    config, dry = load("config.json"), load("reports/dry_run.json")
    selection = load("selection.json") if (experiment_dir / "selection.json").is_file() else None
    validation = load("reports/validation.json") if (experiment_dir / "reports" / "validation.json").is_file() else None
    test = load("reports/test.json") if (experiment_dir / "reports" / "test.json").is_file() else None
    source, main = validation or dry, "validation" if validation else "dry_run"
    scope = "validation worlds, 5% review budget" if validation else "training worlds out of fold (gate dry run), 5% review budget"
    intervals = {row["ranking"]: row for row in source["bootstrap"]}
    card = {row["ranking"]: row for row in source["scorecard"]}

    candidates = []
    for candidate in modeling.candidates():
        row = card[candidate.id]
        status = "not_evaluated" if validation is None else ("error" if str(row["reasons"]).startswith("fit rejected") else row["status"])
        candidates.append({"candidate_id": candidate.id, "ordinal": candidate.ordinal, "status": status,
                           "reasons": [r for r in str(row["reasons"] or "").split("; ") if r],
                           "metrics": _ranking_metrics(source["sensitivity"][candidate.id][PRIMARY], scope, intervals.get(candidate.id),
                                                       candidate.id, main)})
    references = []
    for name, label in REFERENCE_LABELS.items():
        references += [dict(m, name=f"{label}: {m['name']}") for m in
                       _ranking_metrics(source["sensitivity"][name][PRIMARY], scope + "; report only", intervals.get(name), name, main)]
    calibration = dry["calibration"]
    target_scope = "difficulty calibration; training worlds out of fold; lower and upper are the target band, not an interval"
    references += [
        _metric("difficulty target check: return-rate rule precision", calibration["baseline_precision"],
                lower=calibration["baseline_target"][0], upper=calibration["baseline_target"][1], scope=target_scope,
                code="calibration.baseline_precision", ranking=BASELINE, slice="calibration"),
        _metric("difficulty target check: best supervised precision", calibration["best_supervised_precision"],
                lower=calibration["best_supervised_target"][0], upper=calibration["best_supervised_target"][1], scope=target_scope,
                code="calibration.best_supervised_precision", slice="calibration")]
    chosen = selection["selected_model_id"] if selection else None
    dependence_metrics, dependence = _dependence_metrics(experiment_dir)        # AM-31, AM-40
    stress_metrics, stress = _stress_metrics(experiment_dir, chosen)
    references += dependence_metrics + stress_metrics

    per_world, sensitivity = [], []
    for ranking, rows in source["per_world"].items():
        for row in rows:
            per_world.append(_metric(f"{ranking}: precision", row["precision"], row["true_positives"], row["k"],
                                     scope=f"world {row['index']}, 5% review budget", code="precision", ranking=ranking,
                                     slice=f"world:{row['index']}"))
    for ranking, budgets in source["sensitivity"].items():
        for fraction, confusion in budgets.items():
            label, ids = f"{float(fraction):.0%} review budget", {"ranking": ranking, "slice": f"budget:{fraction}"}
            sensitivity += [_metric(f"{ranking}: precision", confusion["precision"], confusion["true_positives"], confusion["k"], scope=label,
                                    code="precision", **ids),
                            _metric(f"{ranking}: recall", confusion["recall"], confusion["true_positives"], confusion["positives"], scope=label,
                                    code="recall", **ids)]
    if test:
        tested = test["selected_model_id"]
        for ranking in (BASELINE, tested):
            for m in _ranking_metrics(test["sensitivity"][ranking][PRIMARY], "final test worlds, 5% review budget",
                                      {row["ranking"]: row for row in test["bootstrap"]}.get(ranking), ranking, "test"):
                sensitivity.append(dict(m, name=f"{ranking}: {m['name']}"))

    style_metrics, wardrobing_metrics = _evidence_metrics((validation or {}).get("evidence_report_only"), "validation worlds; report only",
                                                          "validation")
    coverage = source["coverage"]
    where = "validation worlds" if validation else "training worlds"
    limitations = [(f"{coverage['abusers_excluded']} of {coverage['abusers_all']} abusers on the {where} have fewer than three mature sale "
                    "lines and are outside the ranking."),
                   "Simulated data from one generator: results show stability across simulated worlds, not performance on real returns.",
                   *_dependence_limitations(dependence, stress),
                   "The heavy-returner group is defined on return rate itself, so that gate leg cannot fail for a model and is not evidence."]
    limitations += [f"Segment {SEGMENT_LABELS[s]} has fewer than 200 members." for s in coverage["segments_below_minimum"]]
    if test:
        limitations.insert(1, f"{test['coverage']['abusers_excluded']} of {test['coverage']['abusers_all']} abusers on the final test "
                              "worlds are outside the ranking for the same reason.")
        limitations += [f"Final test: segment {SEGMENT_LABELS[s]} has fewer than 200 members." for s in test["coverage_limitations"]]
    if validation is None:
        limitations.append("Validation has not been run: every figure shown is a gate dry run on training worlds.")

    account = _account_metrics((validation or {}).get("error_account"), "validation worlds, selected model, 5% review budget", "validation")
    if test:
        account += _account_metrics(test.get("error_account"), "final test worlds, selected model, 5% review budget", "test")
    levers = calibration.get("levers_changed", [])                      # recorded with the gate dry run
    return {
        "summary": {"experiment_id": config["experiment_id"], "config_hash": config["experiment_config_sha256"],
                    "selection_status": selection["selection_status"] if selection else "not_completed",
                    "selected_model_id": promoted_model_id,
                    "selected_candidate_id": chosen,
                    "final_test_status": selection["final_test_status"] if selection else "not_run",
                    # the run manifest of the evaluation page: the publishing commit and the seeds the contract fixes
                    "git_sha": git_sha(), **experiment_seeds()},
        "synthetic_only": True,
        "baseline_metrics": _ranking_metrics(source["sensitivity"][BASELINE][PRIMARY], scope, intervals.get(BASELINE), BASELINE, main),
        "candidates": candidates, "per_world_metrics": per_world, "sensitivity_metrics": sensitivity,
        "style_metrics": style_metrics, "wardrobing_metrics": wardrobing_metrics + _stress_wardrobing(experiment_dir),
        "coverage_limitations": limitations,
        "report_only_evidence_metrics": True, "reference_metrics": references, "error_account": account,
        "difficulty_calibration": {"calibrated": bool(levers), "levers": list(levers),
                                   "record_ref": calibration.get("record_ref") or CALIBRATION_RECORD},
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


def verify_feature_code(experiment_dir: Path, artifact_root: Path | None = None) -> dict:
    """Recompute the features of one training world with the current code and compare them with the frozen ones.

    A code hash only says that some file changed. This says whether the change matters: a bundle is published
    only if the code that will score with it reproduces, value for value, the features its model was fitted on.
    """
    config = json.loads((Path(experiment_dir) / "config.json").read_text(encoding="utf-8"))
    world_id = config["training_worlds"][0]
    baseline = json.loads((Path(experiment_dir) / "baseline" / "baseline.json").read_text(encoding="utf-8"))
    try:
        tables, manifest = dataset.load_operational(world_id, artifact_root)
        frozen = dataset.load_features(world_id, artifact_root)
    except FileNotFoundError:
        raise RuntimeError(f"training world {world_id} is needed to verify the feature code before publishing") from None
    result = F.compute_features(tables, dataset.snapshot_date(manifest), F.Reference.from_dict(baseline["reference"]))
    buffer = io.BytesIO()
    result.features.assign(world_id=world_id).to_parquet(buffer, index=False)      # the same round trip the frozen file took
    try:
        pd.testing.assert_frame_equal(pd.read_parquet(buffer), frozen, check_exact=True)
    except AssertionError as difference:
        first = str(difference).splitlines()[0]
        raise RuntimeError(f"the feature code no longer reproduces the features {config['experiment_id']} was trained on "
                           f"({world_id}): {first}. Restore the code, or train a new experiment.") from None
    return {"world_id": world_id, "features_sha256": config["features_sha256"][world_id], "rows": len(frozen),
            "cutoff": manifest["cutoff"]}


def git_sha() -> str | None:
    """The commit of the code that publishes, or None outside a repository. Publishing re-verifies that this code still
    reproduces the frozen training features, so the hash names code that is known to match the experiment."""
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=paths.REPO_ROOT, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 and len(out.stdout.strip()) == 40 else None


def experiment_seeds() -> dict:
    """The world seeds experiment.yaml fixes, as the published summary lists them (training, validation, test, demo, stress)."""
    spec = contract._load("experiment.yaml")
    return {name: [int(seed) for seed in (spec.get(name) or [])] for name in SEED_KEYS}


SEED_KEYS = ("train_seeds", "validation_seeds", "test_seeds", "demo_seeds", "stress_seeds")


def publish(experiment_id: str, artifact_root: Path | None = None, private_root: Path | None = None,
            demo_world: str | None = None) -> dict:
    """Build bundles, decide what may be active, point serving at it, and write the published report.

    A selected model is promoted only when its final test passed. Otherwise serving falls back to the baseline
    and the pointer says why; a failed gate and a selection that was never made are different states.
    """
    experiment_dir = modeling.experiment_dir(experiment_id, artifact_root)
    verified = verify_feature_code(experiment_dir, artifact_root)
    config = json.loads((experiment_dir / "config.json").read_text(encoding="utf-8"))
    quantiles = config.get("feature_quantiles")
    if quantiles is None:                             # trained before quantiles were recorded: take them from the frozen features
        frozen = pd.concat([dataset.load_features(w, artifact_root) for w in config["training_worlds"]], ignore_index=True)
        quantiles = modeling.feature_quantiles(frozen[frozen["eligible"]])
    baseline_id = bundles.build_baseline_bundle(experiment_dir, artifact_root, verified, quantiles)
    selection = json.loads((experiment_dir / "selection.json").read_text(encoding="utf-8")) if (experiment_dir / "selection.json").is_file() else None
    model_id, status, reason = None, "not_completed", "Model selection has not been completed for this experiment."
    if selection:
        status = selection["selection_status"]
        if status == "no_selected_model":
            reason = "No candidate passed the gate on the validation worlds."
        elif selection["final_test_status"] == "passed":
            model_id, reason = bundles.build_model_bundle(experiment_dir, selection["selected_model_id"], artifact_root, verified, quantiles), None
        elif selection["final_test_status"] == "not_run":
            status = "not_completed"
            reason = (f"{selection['selected_model_id']} was selected on validation; its final test has not been run, and a "
                      "model is promoted only after a passed final test.")
        else:
            status = "no_selected_model"
            reason = (f"{selection['selected_model_id']} was selected on validation but its final test is "
                      f"{selection['final_test_status']}; it is not promoted and no runner-up takes its place.")
    # everything that can fail is built and written first; serving is pointed at the bundle last, so a failed
    # publication never leaves a newly active model beside a stale or missing report
    report = build_report(experiment_dir, model_id)
    published = experiment_dir / "published"
    published.mkdir(parents=True, exist_ok=True)
    staged = published / "experiment.json.tmp"
    staged.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if demo_world:
        export_truth(experiment_dir, demo_world, private_root)
    os.replace(staged, published / "experiment.json")
    pointer = bundles.activate(model_id, baseline_id, "selected" if model_id else status, experiment_id, reason, artifact_root)
    return {"pointer": pointer, "baseline_id": baseline_id, "model_id": model_id, "report": str(published / "experiment.json")}
