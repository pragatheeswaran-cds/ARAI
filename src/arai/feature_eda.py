"""Exploration of the engineered features against private truth (development worlds only).

Features are computed first and frozen; truth is joined afterwards. Nothing here feeds back into a feature.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from arai import eda
from arai.dataset import EVIDENCE_FEATURES, MODEL_FEATURES

ALL_MEASURES = MODEL_FEATURES + EVIDENCE_FEATURES


def labelled_frame(world, result) -> pd.DataFrame:
    """One world's feature rows with label, action types, persona and benign segments (private truth)."""
    truth = world.truth["customer_truth"]
    profile = world.truth["customer_profile"][["customer_id", "persona"]]
    segments = eda.benign_segments(world)[["customer_id", "legit_heavy_returner", "defective_product_buyer", "benign_household"]]
    frame = result.features.merge(truth, on="customer_id").merge(profile, on="customer_id").merge(segments, on="customer_id")
    frame["world_id"] = world.world_id
    actions = world.truth["action_truth"]
    done = actions[actions["completed_action"] & ~actions["parcel_companion"]].groupby("customer_id").size()
    frame["completed_actions"] = frame["customer_id"].map(done).fillna(0).astype(int)
    claim = frame["deceptive_nonreceipt_claim"] | frame["deceptive_contents_claim"]
    frame["group"] = np.select(
        [frame["coordinated_action_flag"], claim & frame["temporary_use_return"], claim, frame["temporary_use_return"],
         frame["legit_heavy_returner"], frame["defective_product_buyer"], frame["benign_household"]],
        ["abuser: ring claims", "abuser: claims and temporary use", "abuser: solo claims", "abuser: temporary use",
         "honest: heavy returner", "honest: defective-product buyer", "honest: household"], default="honest: other")
    return frame


def univariate(frame: pd.DataFrame) -> pd.DataFrame:
    """How well each feature alone separates abusers from honest eligible customers, and how often it is missing.

    AUC is computed where the feature exists; `auc_of_missing` scores the missing-value indicator alone.
    A feature that is undefined mostly for one class separates through its absence.
    """
    eligible = frame[frame["eligible"]]
    y = eligible["y_abuse"]
    rows = []
    for name in ALL_MEASURES:
        values = eligible[name]
        present = values.notna()
        per_world = [eda.auc(g.loc[g[name].notna(), name], g.loc[g[name].notna(), "y_abuse"]) for _, g in eligible.groupby("world_id")]
        per_world = [a for a in per_world if a is not None]
        rows.append({
            "feature": name, "auc": eda.auc(values[present], y[present]),
            "auc_min_world": min(per_world) if per_world else None, "auc_max_world": max(per_world) if per_world else None,
            "missing_honest": float((~present)[y == 0].mean()), "missing_abuser": float((~present)[y == 1].mean()),
            "auc_of_missing": eda.auc((~present).astype(int), y) if present.nunique() > 1 else None,
            "median_honest": float(values[y == 0].median()), "median_abuser": float(values[y == 1].median()),
        })
    return pd.DataFrame(rows).set_index("feature")


def group_profile(frame: pd.DataFrame) -> pd.DataFrame:
    """Mean of each feature by behaviour group among eligible customers: which signal belongs to which behaviour."""
    eligible = frame[frame["eligible"]]
    table = eligible.groupby("group")[ALL_MEASURES].mean().T
    table.loc["customers"] = eligible.groupby("group").size()
    return table


def correlations(frame: pd.DataFrame) -> pd.DataFrame:
    eligible = frame[frame["eligible"]]
    return eligible[ALL_MEASURES].corr(method="spearman")


def strongest_pairs(corr: pd.DataFrame, top: int = 10) -> pd.DataFrame:
    pairs = corr.where(np.triu(np.ones(corr.shape, dtype=bool), k=1)).stack().rename("spearman")
    pairs = pairs.reindex(pairs.abs().sort_values(ascending=False).index).head(top)
    return pairs.reset_index().rename(columns={"level_0": "feature_a", "level_1": "feature_b"})


def wardrobing_report(frame: pd.DataFrame, wardrobing: pd.DataFrame) -> dict:
    """The wardrobing indicator against actual temporary-use actions, with its false alerts on honest look-alikes."""
    data = frame.merge(wardrobing[["world_id", "customer_id", "status", "indicator_score", "late_return_lines"]]
                       .rename(columns={"late_return_lines": "late_lines"}), on=["world_id", "customer_id"])
    eligible = data[data["eligible"]]
    truth = eligible["temporary_use_return"].astype(bool)
    rows = []
    for label, flagged in (("elevated", eligible["status"] == "elevated"),
                           ("elevated or possible", eligible["status"].isin(["elevated", "possible"]))):
        rows.append({"band": label, "flagged": int(flagged.sum()), "true_temporary_use": int((flagged & truth).sum()),
                     "precision": eda.ratio((flagged & truth).sum(), flagged.sum()),
                     "recall": eda.ratio((flagged & truth).sum(), truth.sum()), "temporary_use_customers": int(truth.sum())})
    honest = eligible[eligible["y_abuse"] == 0]
    alerts = honest["status"].isin(["elevated", "possible"])
    late = honest["late_lines"] > 0                             # an honest customer with any late in-window item return
    bracketer = honest["bracketing_share"] > 0
    false_alerts = pd.DataFrame([
        {"honest_group": "any late item return", "customers": int(late.sum()), "alerted": int((alerts & late).sum()),
         "alert_rate": eda.ratio((alerts & late).sum(), late.sum())},
        {"honest_group": "size bracketers", "customers": int(bracketer.sum()), "alerted": int((alerts & bracketer).sum()),
         "alert_rate": eda.ratio((alerts & bracketer).sum(), bracketer.sum())},
        {"honest_group": "all honest eligible", "customers": len(honest), "alerted": int(alerts.sum()),
         "alert_rate": eda.ratio(alerts.sum(), len(honest))}])
    return {"bands": pd.DataFrame(rows), "false_alerts": false_alerts,
            "status_by_truth": pd.crosstab(eligible["status"], truth.map({True: "temporary use", False: "no temporary use"}))}


def by_abuse_type(frame: pd.DataFrame) -> pd.DataFrame:
    """AUC of each feature for one kind of abuser against every honest eligible customer.

    Missing values take the pooled median, as the models do, so a feature that is undefined for a group scores
    near one half instead of being skipped. This shows which behaviour each feature can and cannot see.
    """
    eligible = frame[frame["eligible"]]
    honest = eligible[eligible["y_abuse"] == 0]
    filled = eligible[ALL_MEASURES].fillna(eligible[ALL_MEASURES].median())
    groups = [g for g in eligible["group"].unique() if g.startswith("abuser")]
    table = {}
    for group in sorted(groups):
        members = eligible[eligible["group"] == group]
        index = honest.index.append(members.index)
        label = np.r_[np.zeros(len(honest)), np.ones(len(members))]
        table[f"{group} ({len(members)})"] = {name: eda.auc(filled.loc[index, name], label) for name in ALL_MEASURES}
    return pd.DataFrame(table)


def lookalikes(frame: pd.DataFrame) -> dict:
    """Honest customers who look like abusers, and abusers who look honest, counted before any model exists.

    - ring members with no completed action: honest by label, linked like a ring;
    - repeat claimants: honest customers with two or more claim lines, against abusers who only made claims alone;
    - one-action abusers: a single completed action is little to see.
    """
    eligible = frame[frame["eligible"]]
    honest, abusers = eligible[eligible["y_abuse"] == 0], eligible[eligible["y_abuse"] == 1]
    repeat = honest[honest["claim_lines"] >= 2]
    solo = abusers[abusers["group"] == "abuser: solo claims"]
    pair = pd.concat([repeat.assign(target=0), solo.assign(target=1)])
    counts = pd.DataFrame([
        {"group": "eligible honest customers", "customers": len(honest)},
        {"group": "honest ring members (no completed action yet)", "customers": int(honest["coordination_group_id"].notna().sum())},
        {"group": "honest with any claim line", "customers": int((honest["claim_lines"] >= 1).sum())},
        {"group": "honest repeat claimants (two or more claim lines)", "customers": len(repeat)},
        {"group": "eligible abusers", "customers": len(abusers)},
        {"group": "abusers with two or more claim lines", "customers": int((abusers["claim_lines"] >= 2).sum())},
        {"group": "abusers with exactly one completed action", "customers": int((abusers["completed_actions"] == 1).sum())},
        {"group": "abusers with no claim line (temporary use only)", "customers": int((abusers["claim_lines"] == 0).sum())},
    ])
    separation = pd.DataFrame([
        {"measure": name, "auc_solo_claim_abuser_vs_honest_repeat_claimant":
            eda.auc(pair[name].fillna(pair[name].median()), pair["target"])}
        for name in ("claim_lines", "claim_share", "raw_return_rate", "residual_z", "requested_refund_ratio", "mature_sale_lines")])
    return {"counts": counts, "separation": separation,
            "one_action_share_of_abusers": eda.ratio((abusers["completed_actions"] == 1).sum(), len(abusers))}
