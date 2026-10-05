"""What the result depends on, and whom the model wrongly sends for review (decisions AM-31 and AM-40).

Out of fold on the ten training worlds, for one candidate at the review budget:
- precision with all features and without each family the model leans on (claims, timing, both);
- the share of each honest group sent for review by the model and by the return-rate rule, including honest
  customers with repeated genuine delivery failures, a group the promotion gate has no leg for.
Training worlds only: it reads no validation or test world and changes no fitted model, so it can be recorded at
any time and belongs in every published report.
"""
from __future__ import annotations

import json

import pandas as pd

from arai import evaluation, modeling
from arai.settings import load_settings

# every feature that reads when in the return window items come back, and every feature that reads transaction claims
TIMING_FEATURES = ("late_return_lines", "late_window_share", "median_window_ratio", "item_ratio_max", "item_ratio_second",
                   "item_ratio_mean", "mid_late_lines", "late_occasion_return_lines", "mid_or_late_occasion_lines", "item_in_window_lines")
CLAIM_FEATURES = ("claim_share", "coordinated_claim_share", "claim_lines", "claim_order_count", "claim_order_rate", "claim_unit_rate",
                  "claim_excess_z", "claimed_share_of_claim_orders", "whole_order_claim_share", "claim_day_span", "claim_distinct_days",
                  "claims_in_densest_fortnight", "nonreceipt_share_of_claims", "multi_code_claim_orders", "multi_code_claim_share",
                  "max_claim_lines_per_order", "claimed_order_size_ratio", "claim_style_others_rate_mean", "claim_style_others_rate_max",
                  "claim_value_ratio")
FIRST_CONTRACT_FEATURES = 17            # feature contract 1.4 is the first 17 features of contract 2.0, in the same order
VARIANTS = (("all", "all features", ()),
            ("first_contract", "only the 17 features of the first experiment", None),
            ("without_late_return_lines", "without late_return_lines", ("late_return_lines",)),
            ("without_timing", "without any timing feature", TIMING_FEATURES),
            ("without_claims", "without any claim feature", CLAIM_FEATURES),
            ("without_claims_and_timing", "without any claim or timing feature", CLAIM_FEATURES + TIMING_FEATURES))
REPEAT_CLAIMANT = "repeat_genuine_claimant"
GROUP_LABELS = {REPEAT_CLAIMANT: "honest customers with two or more genuinely failed deliveries",
                "one_genuine_failure": "honest customers with exactly one genuinely failed delivery",
                "no_genuine_failure": "honest customers with no genuine delivery failure",
                "legit_heavy_returner": "honest heavy returners",
                "defective_product_buyer": "honest defective-product buyers",
                "benign_household": "honest household members"}


def group_label(group: str) -> str:
    return GROUP_LABELS[group] + (" (gate leg)" if group in evaluation.SEGMENTS else "")


def ablate(frame: pd.DataFrame, folds: dict, candidate: modeling.Candidate) -> tuple:
    """(one row per variant, the review selection made with all features). `frame` is an evaluation frame."""
    rows, selected = [], None
    for key, name, dropped in VARIANTS:
        features = candidate.features[:FIRST_CONTRACT_FEATURES] if dropped is None else [f for f in candidate.features if f not in dropped]
        variant = modeling.Candidate(candidate.id, candidate.ordinal, candidate.family, candidate.supervised, dict(candidate.params), features,
                                     honest_group_weights=dict(candidate.honest_group_weights))
        scores, _ = modeling.out_of_fold(variant, frame, folds)
        scored = frame.assign(_score=scores)
        chosen = evaluation.select(scored, "_score")
        result = evaluation.confusion(scored, chosen)
        rows.append({"key": key, "variant": name, "features": len(features), "k": result["k"], "true_positives": result["true_positives"],
                     "precision": result["precision"],
                     **{"recall_" + action: result["recall_" + action] for action in evaluation.ACTION_TYPES}})
        if key == "all":
            selected = chosen
    return rows, selected


def honest_groups(frame: pd.DataFrame, model_selected: pd.Series, rule_selected: pd.Series) -> dict:
    """Review rates of honest groups under the model and under the rule. `frame` carries genuine_claim_units."""
    honest = frame["y_abuse"] == 0
    members = {REPEAT_CLAIMANT: honest & (frame["genuine_claim_units"] >= evaluation.REPEAT_CLAIMANT_UNITS),
               "one_genuine_failure": honest & (frame["genuine_claim_units"] == 1),
               "no_genuine_failure": honest & (frame["genuine_claim_units"] == 0),
               **{segment: frame[segment].astype(bool) for segment in evaluation.SEGMENTS}}
    rows = []
    for key, mask in members.items():
        size = int(mask.sum())
        by_model, by_rule = int((model_selected & mask).sum()), int((rule_selected & mask).sum())
        rows.append({"group": key, "label": group_label(key), "customers": size, "model_selected": by_model, "rule_selected": by_rule,
                     "model_rate": evaluation.ratio(by_model, size), "rule_rate": evaluation.ratio(by_rule, size)})
    repeat = members[REPEAT_CLAIMANT]
    false_positives = {name: {"false_positives": int((chosen & honest).sum()), "repeat_genuine_claimants": int((chosen & repeat).sum()),
                              "share": evaluation.ratio((chosen & repeat).sum(), (chosen & honest).sum())}
                       for name, chosen in (("model", model_selected), ("rule", rule_selected))}
    return {"groups": rows, "false_positives": false_positives}


def default_candidate(out) -> str:
    """The selected candidate if selection is frozen, otherwise the best supervised candidate of the gate dry run."""
    if (out / "selection.json").is_file():
        chosen = json.loads((out / "selection.json").read_text(encoding="utf-8"))["selected_model_id"]
        if chosen:
            return chosen
    card = json.loads((out / "reports" / "dry_run.json").read_text(encoding="utf-8"))["scorecard"]
    supervised = {c.id for c in modeling.candidates() if c.supervised}
    return max((row for row in card if row["ranking"] in supervised), key=lambda row: row["precision"])["ranking"]


def run(experiment_id: str, candidate_id: str | None = None, artifact_root=None, private_root=None) -> dict:
    """Measure and record reports/ablation.json for one candidate (default: see default_candidate)."""
    settings = load_settings()
    out = modeling.experiment_dir(experiment_id, artifact_root)
    worlds = [f"W{s}" for s in settings.experiment["train_seeds"]]
    candidate_id = candidate_id or default_candidate(out)
    registered = next(c for c in modeling.candidates(settings) if c.id == candidate_id)
    if not registered.supervised:
        raise ValueError("the ablation is defined for supervised candidates: out-of-fold scores need labels")
    frame = evaluation.evaluation_frame(worlds, artifact_root, private_root)
    frame = frame.merge(evaluation.private_counts(worlds, artifact_root, private_root), on=["world_id", "customer_id"], validate="one_to_one")
    rule_selected = evaluation.select(frame, "raw_return_rate")
    rows, model_selected = ablate(frame, modeling.fold_map(worlds), registered)
    payload = {"experiment_id": experiment_id, "candidate_id": candidate_id, "measured_on": "training worlds, out of fold, 5% budget",
               "timing_features": list(TIMING_FEATURES), "claim_features": list(CLAIM_FEATURES),
               "baseline_precision": evaluation.confusion(frame, rule_selected)["precision"], "variants": rows,
               "honest_groups": honest_groups(frame, model_selected, rule_selected)}
    (out / "reports").mkdir(parents=True, exist_ok=True)
    (out / "reports" / "ablation.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
