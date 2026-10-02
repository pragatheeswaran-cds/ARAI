"""Batch scoring of one registered snapshot with one bound bundle (final-spec component 11).

Stages: features and graph -> eligibility -> frozen preprocessing and scores -> ranks and the review set ->
evidence -> files. Nothing is fitted, no label exists here, and results are written to a staging directory
that only becomes a run's output once every file is complete.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from arai import bundles, ranking
from arai import features as F
from arai.operational import cutoff_date

SMALL_POPULATION = 500           # below this many eligible customers peer aggregates move noticeably (feature review)
SUPPORT = ["mature_sale_lines", "mature_purchased_units", "mature_requested_units", "all_requested_units"]
TAGS = ("repeat_claims", "linked_claims", "late_returns", "returns_above_expected", "supported_links")
OUTPUT_FILES = ("run.json", "customers.parquet", "styles.parquet", "skus.parquet", "neighbors.parquet", "timeline.parquet",
                "customer_styles.parquet")
COMPLETE_MARKER = "COMPLETE"


@dataclass
class RunOutput:
    summary: dict
    customers: pd.DataFrame
    styles: pd.DataFrame
    skus: pd.DataFrame
    neighbors: pd.DataFrame
    timeline: pd.DataFrame
    customer_styles: pd.DataFrame


def _nullable_int(values: np.ndarray, mask: np.ndarray) -> pd.Series:
    out = pd.Series(pd.NA, index=range(len(mask)), dtype="Int64")
    out[mask] = values
    return out


def _tags(features: pd.DataFrame) -> pd.Series:
    fired = pd.DataFrame({
        "repeat_claims": features["claim_lines"] >= 2,
        "linked_claims": features["coordinated_claim_share"] > 0,
        "late_returns": features["late_return_lines"] >= 2,
        "returns_above_expected": features["residual_z"] >= 2,
        "supported_links": features["supported_neighbor_count"] >= 1,
    })
    return fired.apply(lambda row: "|".join(name for name in TAGS if row[name]), axis=1)


def _neighbors(result: F.FeatureResult) -> pd.DataFrame:
    """Both directions of every supported edge, with how many of the customer's claims the neighbour matches."""
    columns = ["customer_id", "neighbor_id", "shared_types", "shared_value_count", "supported", "max_value_fanout",
               "coordinated_claim_matches"]
    edges = result.graph.edges
    if not len(edges):
        return pd.DataFrame(columns=columns)
    claims = result.requests[result.requests["is_claim"]]
    by_customer = {c: g[["style_id", "request_day"]].to_numpy() for c, g in claims.groupby("customer_id")}
    window = np.timedelta64(F.LINK_DAYS, "D")

    def matches(own, other) -> int:
        mine, theirs = by_customer.get(own), by_customer.get(other)
        if mine is None or theirs is None:
            return 0
        return sum(any(style == s and abs(day - d) <= window for s, d in theirs) for style, day in mine)

    rows = []
    for edge in edges.itertuples(index=False):
        for own, other in ((edge.customer_a, edge.customer_b), (edge.customer_b, edge.customer_a)):
            rows.append((own, other, "|".join(edge.shared_types), int(edge.shared_value_count), True, int(edge.max_value_fanout),
                         matches(own, other)))
    return pd.DataFrame(rows, columns=columns).sort_values(["customer_id", "neighbor_id"]).reset_index(drop=True)


def _timeline(tables: dict, result: F.FeatureResult) -> pd.DataFrame:
    """Source transactions per customer: every sale line and every return request, with their own keys."""
    sku = tables["sku_master"].set_index("sku")
    lines = result.lines
    delivered = lines["delivered_date"].dt.strftime("%Y-%m-%d").fillna("not delivered")
    purchases = pd.DataFrame({
        "customer_id": lines["customer_id"], "source_ref": "sales_order_line:" + lines["order_id"] + "/" + lines["order_line_no"].astype(str),
        "event_type": "purchase", "observed_at": lines["order_date"].dt.strftime("%Y-%m-%d"),
        "description": ("Ordered " + lines["quantity"].astype(str) + " x " + lines["category"] + " size " + lines["size"].astype(str)
                        + "; " + lines["line_status"].str.replace("_", " ") + "; delivered " + delivered),
        "amount_inr": lines["line_total"].astype(float), "style_id": lines["style_id"], "sku": lines["sku"], "sort_at": lines["order_date"]})
    returns = tables["return_order_line"].merge(
        lines[["order_id", "order_line_no", "customer_id", "style_id", "delivered_date", "return_window_days"]], on=["order_id", "order_line_no"])
    linked = result.requests.set_index(["return_order_id", "return_line_no"])["linked"]
    key = pd.MultiIndex.from_frame(returns[["return_order_id", "return_line_no"]])
    is_linked = linked.reindex(key).fillna(False).to_numpy(dtype=bool)
    days = (returns["requested_at"].dt.normalize() - returns["delivered_date"]).dt.days
    claim = returns["reason_code"].isin(F.CLAIM_CODES)
    requests = pd.DataFrame({
        "customer_id": returns["customer_id"],
        "source_ref": "return_order_line:" + returns["return_order_id"].astype(str) + "/" + returns["return_line_no"].astype(str),
        "event_type": np.where(claim, "transaction_claim", "return_request"),
        "observed_at": returns["requested_at"].dt.strftime("%Y-%m-%dT%H:%M:%S") + "+05:30",
        "description": (returns["reason_code"].astype(str).str.replace("_", " ") + ": " + returns["quantity_returned"].astype(str)
                        + " unit(s), day " + days.astype(str) + " of a " + returns["return_window_days"].astype(str) + "-day window; "
                        + returns["line_status"].astype(str)
                        + pd.Series(np.where(is_linked, "; a linked account claimed on this style within 7 days", ""), index=returns.index)),
        "amount_inr": returns["refund_amount"].astype(float), "style_id": returns["style_id"], "sku": returns["sku"],
        "sort_at": returns["requested_at"]})
    timeline = pd.concat([purchases, requests], ignore_index=True)
    timeline["sku"] = timeline["sku"].where(timeline["sku"].isin(sku.index))
    return timeline.sort_values(["customer_id", "sort_at", "source_ref"]).drop(columns="sort_at").reset_index(drop=True)


def score_snapshot(tables: dict, manifest: dict, bundle: bundles.Bundle, on_stage=lambda stage, progress: None) -> RunOutput:
    """Score every customer of one snapshot. Raises on a non-finite score; an empty graph or no eligible customer is valid."""
    world_id = manifest["world_id"]
    on_stage("features", 0.15)
    result = F.compute_features(tables, cutoff_date(manifest), bundle.reference)
    features = result.features.sort_values("customer_id").reset_index(drop=True)

    on_stage("eligibility", 0.45)
    eligible = features["eligible"].to_numpy(dtype=bool)
    n = int(eligible.sum())
    scored = features[eligible]
    ids = scored["customer_id"].to_numpy()

    on_stage("scoring", 0.55)
    raw = bundles.raw_scores(bundle, scored) if n else np.array([])
    if n and not np.isfinite(raw).all():
        raise ValueError("the bundle produced a missing or non-finite score")
    k = ranking.budget(n) if n else 0
    rank = ranking.rank_world(world_id, ids, raw) if n else np.array([], dtype=int)
    if bundle.kind == bundles.BASELINE_KIND:
        baseline_rank = rank                                    # under fallback the two rankings are the same ranking
    else:
        baseline_rank = ranking.rank_world(world_id, ids, scored["raw_return_rate"].to_numpy()) if n else rank

    customers = features.copy()
    customers["eligibility_status"] = np.where(eligible, "eligible", "insufficient_history")
    customers["raw_score"] = np.nan
    customers["risk_score"] = np.nan
    if n:
        customers.loc[eligible, "raw_score"] = raw
        customers.loc[eligible, "risk_score"] = np.clip(bundles.reference_percentile(bundle, raw), 0.0, 100.0)
    customers["rank"] = _nullable_int(rank, eligible)
    customers["baseline_rank"] = _nullable_int(baseline_rank, eligible)
    customers["selected_for_review"] = (customers["rank"] <= k).fillna(False).astype(bool)
    customers["baseline_selected"] = (customers["baseline_rank"] <= k).fillna(False).astype(bool)
    # queue order: ranked customers by rank, then unranked customers by identifier
    position = customers["rank"].astype("float").fillna(np.inf)
    order = np.lexsort((customers["customer_id"].to_numpy(), position.to_numpy()))
    customers["queue_position"] = 0
    customers.loc[order, "queue_position"] = np.arange(1, len(customers) + 1)

    on_stage("evidence", 0.7)
    wardrobing = result.wardrobing.set_index("customer_id")
    customers["wardrobing_status"] = customers["customer_id"].map(wardrobing["status"])
    customers["indicator_score"] = customers["customer_id"].map(wardrobing["indicator_score"]).astype("Int64")
    customers["late_return_share"] = customers["customer_id"].map(wardrobing["late_return_share"])
    for name in F.WARDROBING_POINTS:
        customers["fired_" + name] = customers["customer_id"].map(wardrobing["fired_" + name]).astype(bool)
    for name in F.WARDROBING_SUPPORT:
        if name not in customers:
            customers[name] = customers["customer_id"].map(wardrobing[name])
    customers["evidence_tags"] = _tags(customers)

    styles = result.styles.sort_values("style_id").reset_index(drop=True)
    skus = result.skus.merge(tables["sku_master"][["sku", "size", "colour", "unit_price"]], on="sku", how="left") \
        .sort_values("sku").reset_index(drop=True)
    requests = result.requests
    customer_styles = requests.groupby(["customer_id", "style_id"]).agg(
        requested_units=("quantity_returned", "sum"), claim_lines=("is_claim", "sum"),
        linked_claim_lines=("linked", lambda s: int(s.fillna(False).sum()))).reset_index() if len(requests) else \
        pd.DataFrame(columns=["customer_id", "style_id", "requested_units", "claim_lines", "linked_claim_lines"])

    selected, baseline_selected = customers["selected_for_review"], customers["baseline_selected"]
    warnings = []
    if n < SMALL_POPULATION:
        warnings.append(f"Only {n} eligible customers: peer comparisons are unstable in a snapshot this small.")
    if result.fallback_uses:
        warnings.append(f"{result.fallback_uses} sale lines had no peers in their category and used the frozen training rate.")
    summary = {
        "world_id": world_id, "model_id": bundle.model_id, "model_kind": bundle.kind, "cutoff": manifest["cutoff"],
        "customer_count": int(len(customers)), "eligible_count": n, "excluded_count": int(len(customers) - n),
        "review_budget_k": int(k), "selected_count": int(selected.sum()),
        "model_only_count": int((selected & ~baseline_selected).sum()),
        "baseline_only_count": int((baseline_selected & ~selected).sum()),
        "both_count": int((selected & baseline_selected).sum()),
        "graph_edges": int(len(result.graph.edges)), "identifier_values_dropped": int(result.graph.dropped_values),
        "category_fallback_uses": int(result.fallback_uses), "warnings": warnings,
        "score_label": bundle.manifest["score_label"], "feature_order": bundle.feature_order,
    }
    return RunOutput(summary=summary, customers=customers, styles=styles, skus=skus, neighbors=_neighbors(result),
                     timeline=_timeline(tables, result), customer_styles=customer_styles)


# ------------------------------------------------------------------ publication
def runs_root(artifact_root: Path) -> Path:
    return Path(artifact_root) / "runs"


def staging_dir(artifact_root: Path, run_id: str) -> Path:
    return runs_root(artifact_root) / f".staging-{run_id}"


def output_dir(artifact_root: Path, run_id: str) -> Path:
    return runs_root(artifact_root) / run_id


def is_complete(directory: Path) -> bool:
    return (directory / COMPLETE_MARKER).is_file() and all((directory / name).is_file() for name in OUTPUT_FILES)


def publish(output: RunOutput, artifact_root: Path, run_id: str) -> str:
    """Write every file to a staging directory, mark it complete, then rename it into place.

    A crash before the rename leaves only a staging directory, which startup reconciliation removes. Returns the
    artifact key (relative to the artifact root) of the published directory.
    """
    staged, final = staging_dir(artifact_root, run_id), output_dir(artifact_root, run_id)
    if final.exists():
        raise FileExistsError(f"run {run_id} already has published output")
    if staged.exists():
        shutil.rmtree(staged)
    staged.mkdir(parents=True)
    (staged / "run.json").write_text(json.dumps(dict(output.summary, run_id=run_id), indent=2) + "\n", encoding="utf-8")
    for name in ("customers", "styles", "skus", "neighbors", "timeline", "customer_styles"):
        getattr(output, name).to_parquet(staged / f"{name}.parquet", index=False)
    (staged / COMPLETE_MARKER).write_text(run_id + "\n", encoding="utf-8")
    os.replace(staged, final)
    return f"runs/{run_id}"
