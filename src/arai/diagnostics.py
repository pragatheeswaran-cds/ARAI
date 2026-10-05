"""Offline diagnostics for development worlds (final-spec component 05).

These join operational tables to private truth, so they are for fixture, training and stress worlds only.
Nothing computed here may be persisted as an operational feature.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from arai import features, ranking
from arai.features import (CLAIM_CODES, ELIGIBLE_MIN_LINES, FANOUT_CAP, LINK_DAYS, QUALITY_CODES,  # noqa: F401  re-exported
                           QUALITY_DAMAGE_SHARE, TARGETING_LINKED_CLAIMERS, TARGETING_LINKED_SHARE)


def sale_lines(world) -> pd.DataFrame:
    """Sale lines with customer, style, maturity and non-withdrawn requested units."""
    t = world.tables
    cutoff = pd.Timestamp(world.snapshot_date)
    lines = t["sales_order_line"].merge(t["sales_order"][["order_id", "customer_id", "order_date"]], on="order_id") \
                                 .merge(t["sku_master"][["sku", "style_id", "category", "is_occasion_wear"]], on="sku")
    lines["mature"] = (lines["line_status"] == "delivered") & (
        lines["delivered_date"] + pd.to_timedelta(lines["return_window_days"], unit="D") <= cutoff)
    active = t["return_order_line"][t["return_order_line"]["line_status"] != "withdrawn"]
    requested = active.groupby(["order_id", "order_line_no"])["quantity_returned"].sum().rename("requested_units")
    lines = lines.merge(requested, on=["order_id", "order_line_no"], how="left")
    lines["requested_units"] = lines["requested_units"].fillna(0).astype(int)
    return lines


def customer_summary(world) -> pd.DataFrame:
    """One row per customer: mature exposure, raw return rate, eligibility and private label."""
    lines = sale_lines(world)
    mature = lines[lines["mature"]]
    per = mature.groupby("customer_id").agg(mature_sale_lines=("sku", "size"), mature_units=("quantity", "sum"),
                                            mature_requested=("requested_units", "sum"))
    orders = world.tables["sales_order"].groupby("customer_id").size().rename("orders")
    returns = world.tables["return_order_line"].merge(world.tables["return_order"][["return_order_id", "customer_id"]], on="return_order_id")
    returns = returns[returns["line_status"] != "withdrawn"]
    claims = returns[returns["reason_code"].isin(CLAIM_CODES)].groupby("customer_id").size().rename("claim_lines")
    out = world.tables["customer_master"][["customer_id"]].merge(per, on="customer_id", how="left") \
        .merge(orders, on="customer_id", how="left").merge(claims, on="customer_id", how="left").fillna(0)
    out["raw_return_rate"] = np.where(out["mature_units"] > 0, out["mature_requested"] / out["mature_units"].replace(0, np.nan), np.nan)
    out["eligible"] = out["mature_sale_lines"] >= ELIGIBLE_MIN_LINES
    truth = world.truth["customer_truth"][["customer_id", "y_abuse", "deceptive_nonreceipt_claim", "deceptive_contents_claim",
                                           "temporary_use_return", "coordinated_action_flag", "household_id",
                                           "coordination_group_id"]]
    profile = world.truth["customer_profile"][["customer_id", "persona", "heavy_return_overlay", "claim_propensity",
                                               "temporary_use_propensity"]]
    return out.merge(truth, on="customer_id").merge(profile, on="customer_id")


def top_fraction(world, summary: pd.DataFrame, score: str, fraction: float = ranking.PRIMARY_FRACTION) -> pd.DataFrame:
    """The review selection, by the one rule evaluation and serving use (ranking.py)."""
    eligible = summary[summary["eligible"]].copy()
    if not len(eligible):
        return eligible
    ranks = ranking.rank_world(world.world_id, eligible["customer_id"], eligible[score])
    return eligible.assign(_rank=ranks).sort_values("_rank").head(ranking.budget(len(eligible), fraction)).drop(columns="_rank")


def precision_at(world, summary: pd.DataFrame, score: str, fraction: float = ranking.PRIMARY_FRACTION) -> dict:
    selected = top_fraction(world, summary, score, fraction)
    positives = int(summary.loc[summary["eligible"], "y_abuse"].sum())
    hits = int(selected["y_abuse"].sum())
    return {"k": len(selected), "true_positives": hits, "precision": hits / len(selected) if len(selected) else None,
            "recall": hits / positives if positives else None, "eligible_positives": positives}


def observed_graph(world) -> dict:
    """Supported neighbours from operational identifiers (the feature module's graph)."""
    return features.build_graph(world.tables["sales_order"]).neighbours


def linked_claims(world) -> pd.DataFrame:
    """Visible transaction-claim lines with `linked`: a supported neighbour claimed on the same style within 7 days."""
    _, requests, _ = features._prepare(world.tables, world.snapshot_date)
    return features.linked_claims(requests, observed_graph(world))


def style_evidence(world) -> pd.DataFrame:
    """Style-level quality and targeting evidence (the feature module's, unchanged) beside the private style truth."""
    lines, requests, _ = features._prepare(world.tables, world.snapshot_date)
    claims = features.linked_claims(requests, observed_graph(world))
    styles, _ = features.style_evidence(lines, requests, claims, reference=None)
    truth = world.truth["product_truth"][["style_id", "defect_state", "hot_listed", "targeting_level"]]
    return styles.assign(return_rate=styles["raw_return_rate"]).merge(truth, on="style_id", how="left")


def generation_report(world) -> dict:
    """Headline checks of realised behaviour against the generation targets."""
    t, truth = world.tables, world.truth
    lines = sale_lines(world)
    delivered = lines[lines["line_status"] == "delivered"]
    summary = customer_summary(world)
    eligible = summary[summary["eligible"]]
    returns = t["return_order_line"]
    actions = truth["action_truth"]
    units = truth["unit_truth"]
    profile = truth["customer_profile"]
    report = {
        "world_id": world.world_id, "customers": len(summary), "orders": len(t["sales_order"]),
        "sale_lines": len(lines), "return_lines": len(returns),
        "campaign_orders": int((truth["order_truth"]["layer"] == "campaign").sum()),
        "line_status_share": lines["line_status"].value_counts(normalize=True).round(4).to_dict(),
        "delivered_units": int(delivered["quantity"].sum()),
        "return_line_status_share": returns["line_status"].value_counts(normalize=True).round(4).to_dict(),
        "genuine_claim_rate_per_delivered_unit": round(float(units["genuine_fulfilment_cause"].notna().mean()), 5),
        "carrier_damage_rate": round(float(units["carrier_damage"].mean()), 5),
        "propensity_share": {"claim": round(float(profile["claim_propensity"].mean()), 4),
                             "temporary_use": round(float(profile["temporary_use_propensity"].mean()), 4),
                             "both": round(float((profile["claim_propensity"] & profile["temporary_use_propensity"]).mean()), 4)},
        "eligible_customers": int(len(eligible)), "eligible_share": round(len(eligible) / len(summary), 4),
        "abusers_all": int(summary["y_abuse"].sum()), "abusers_eligible": int(eligible["y_abuse"].sum()),
        "abusers_excluded_by_eligibility": int((summary["y_abuse"] == 1).sum() - eligible["y_abuse"].sum()),
        "prevalence_among_eligible": round(float(eligible["y_abuse"].mean()), 4) if len(eligible) else None,
        "actions_completed": actions[actions["completed_action"]]["action_type"].value_counts().to_dict(),
        "actions_uncompleted": actions[~actions["completed_action"]]["uncompleted_reason"].value_counts().to_dict(),
        "coordinated_claims_by_source": actions[actions["completed_action"] & actions["campaign_id"].notna()]["claim_source"].value_counts().to_dict(),
        "targeting_level": truth["product_truth"]["targeting_level"].value_counts().to_dict(),
        "baseline_precision_at_5pct": precision_at(world, summary, "raw_return_rate"),
    }
    return report
