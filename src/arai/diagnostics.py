"""Offline diagnostics for development worlds (final-spec component 05).

These join operational tables to private truth, so they are for fixture, training and stress worlds only.
Nothing computed here may be persisted as an operational feature.
"""
from __future__ import annotations

import hashlib
import math
from itertools import combinations

import numpy as np
import pandas as pd


CLAIM_CODES = ("wrong_item_sent", "missing_parts", "item_not_received", "empty_package")
QUALITY_CODES = ("defective", "poor_quality", "not_as_described")
ELIGIBLE_MIN_LINES = 3      # experiment.yaml eligibility
FANOUT_CAP = 25             # an identifier shared by more accounts than this is dropped
LINK_DAYS = 7
# style signals (final-spec component 06; the targeting share was confirmed on the training worlds, AM-17)
QUALITY_DAMAGE_SHARE = 0.30
TARGETING_LINKED_CLAIMERS = 3
TARGETING_LINKED_SHARE = 0.05


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


def _tie_break(world_id: str, customer_id: str) -> str:
    return hashlib.sha256(f"review-tie-v02|{world_id}|{customer_id}".encode("utf-8")).hexdigest()


def top_fraction(world, summary: pd.DataFrame, score: str, fraction: float = 0.05) -> pd.DataFrame:
    """The review selection: top ceil(fraction*N) eligible customers by score, ties by the public hash rule."""
    eligible = summary[summary["eligible"]].copy()
    eligible["tie"] = [_tie_break(world.world_id, c) for c in eligible["customer_id"]]
    k = min(len(eligible), math.ceil(fraction * len(eligible)))
    return eligible.sort_values([score, "tie"], ascending=[False, True], kind="stable").head(k)


def precision_at(world, summary: pd.DataFrame, score: str, fraction: float = 0.05) -> dict:
    selected = top_fraction(world, summary, score, fraction)
    positives = int(summary.loc[summary["eligible"], "y_abuse"].sum())
    hits = int(selected["y_abuse"].sum())
    return {"k": len(selected), "true_positives": hits, "precision": hits / len(selected) if len(selected) else None,
            "recall": hits / positives if positives else None, "eligible_positives": positives}


def observed_graph(world) -> dict:
    """Supported neighbours from operational identifiers: an edge needs at least two shared identifier types."""
    orders = world.tables["sales_order"]
    shared = {}
    for kind in ("address_id", "device_id", "payment_id"):
        for accounts in orders.groupby(kind)["customer_id"].unique():
            if 2 <= len(accounts) <= FANOUT_CAP:
                for pair in combinations(sorted(accounts), 2):
                    shared.setdefault(pair, set()).add(kind)
    neighbours = {}
    for (a, b), kinds in shared.items():
        if len(kinds) >= 2:
            neighbours.setdefault(a, set()).add(b)
            neighbours.setdefault(b, set()).add(a)
    return neighbours


def style_evidence(world) -> pd.DataFrame:
    """Style-level quality and targeting evidence (final-spec component 06) beside the private style truth."""
    t = world.tables
    lines = sale_lines(world)
    mature = lines[lines["mature"]]
    base = mature.groupby("style_id").agg(category=("category", "first"), mature_sale_lines=("sku", "size"),
                                          purchased_units=("quantity", "sum"), requested_units=("requested_units", "sum"))
    returns = t["return_order_line"].merge(lines[["order_id", "order_line_no", "style_id", "customer_id", "mature"]],
                                           on=["order_id", "order_line_no"])
    returns = returns[returns["line_status"] != "withdrawn"]
    mature_returns = returns[returns["mature"]]
    quality_units = mature_returns[mature_returns["reason_code"].isin(QUALITY_CODES)].groupby("style_id")["quantity_returned"].sum()
    claim_units = mature_returns[mature_returns["reason_code"].isin(CLAIM_CODES)].groupby("style_id")["quantity_returned"].sum()

    neighbours = observed_graph(world)
    claims = returns[returns["reason_code"].isin(CLAIM_CODES)].copy()
    claims["day"] = claims["requested_at"].dt.normalize()
    linked = np.zeros(len(claims), dtype=bool)
    for _, group in claims.groupby("style_id"):
        customers, days = group["customer_id"].to_numpy(), group["day"].to_numpy()
        positions = claims.index.get_indexer(group.index)
        for i in range(len(group)):
            near = np.abs((days - days[i]) / np.timedelta64(1, "D")) <= LINK_DAYS
            linked[positions[i]] = any(c in neighbours.get(customers[i], ()) for c in customers[near])
    claims["linked"] = linked
    link = claims.groupby("style_id").agg(claim_lines=("linked", "size"), linked_claim_lines=("linked", "sum"))
    link["linked_claimers"] = claims[claims["linked"]].groupby("style_id")["customer_id"].nunique()

    out = base.join(quality_units.rename("quality_units")).join(claim_units.rename("claim_units")).join(link).fillna(0)
    out["return_rate"] = out["requested_units"] / out["purchased_units"]
    out["damage_share"] = np.where(out["requested_units"] > 0, out["quality_units"] / out["requested_units"].replace(0, np.nan), np.nan)
    out["claim_share"] = np.where(out["requested_units"] > 0, out["claim_units"] / out["requested_units"].replace(0, np.nan), np.nan)
    out["linked_claim_share"] = np.where(out["claim_lines"] > 0, out["linked_claim_lines"] / out["claim_lines"].replace(0, np.nan), np.nan)
    out["quality_signal"] = out["damage_share"] >= QUALITY_DAMAGE_SHARE
    out["targeting_signal"] = (out["linked_claimers"] >= TARGETING_LINKED_CLAIMERS) & (out["linked_claim_share"] >= TARGETING_LINKED_SHARE)
    supported = out["mature_sale_lines"] >= 20
    out["state"] = np.select(
        [~supported, (out["requested_units"] == 0) & (out["claim_lines"] == 0), out["quality_signal"] & out["targeting_signal"],
         out["quality_signal"], out["targeting_signal"]],
        ["insufficient_support", "no_return_evidence", "mixed_or_uncertain", "quality", "targeting"], default="no_elevated_signal")
    truth = world.truth["product_truth"].set_index("style_id")[["defect_state", "hot_listed", "targeting_level"]]
    return out.join(truth).reset_index()


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
