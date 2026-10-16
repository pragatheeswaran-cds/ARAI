"""Batch scoring of one registered snapshot with one bound bundle (final-spec component 11).

Stages: features and graph -> eligibility -> frozen preprocessing and scores -> ranks and the review set ->
evidence. Nothing is fitted and no label exists here. The worker publishes the result to PostgreSQL in the
transaction that marks the run succeeded (decision AM-39).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

import networkx as nx
import numpy as np
import pandas as pd

from arai import bundles, contract, ranking
from arai import features as F
from arai.operational import cutoff_date
from arai.service import attribution

SMALL_POPULATION = 500           # below this many eligible customers peer aggregates move noticeably (feature review)
DRIFT_MIN_ELIGIBLE = 200         # below this the shares are too noisy to compare with training
DRIFT_P95_BAND = (0.025, 0.10)   # share scoring above the training 95th percentile that raises no warning (0.05 expected)
SUPPORT = ["mature_sale_lines", "mature_purchased_units", "mature_requested_units", "all_requested_units"]
TAGS = ("repeat_claims", "linked_claims", "late_returns", "returns_above_expected", "supported_links")
BAND_SD = 2                      # the normal band around the expected units is expected +/- BAND_SD standard deviations
HEAVY_RETURNER_QUANTILE = 0.9    # the gate's own definition of a heavy returner: raw rate at or above this quantile of eligible customers
# the one-line reason a customer outside the queue is shown with, as a template key the UI renders; the first rule that holds
CLEARED_REASONS = (("size_bracketing", lambda c: c["bracketing_share"] >= 0.5),
                   ("high_return_styles", lambda c: c["expected_return_rate"] >= 0.35),
                   ("as_basket_predicts", lambda c: c["residual_z"] < 1),
                   ("below_threshold", lambda c: pd.Series(True, index=c.index)))
LOUVAIN_FROM = 13                # a connected component with this many members or more is split by Louvain (fixed seed); smaller ones stand
STYLE_REASON_COLUMNS = ["style_id", "reason_code", "reason_group", "lines", "units"]
LAST_DAYS = 5                    # "late in the window" for a style: a request in the last five days of the return window
ATTRIBUTION_COLUMNS = ["customer_id", "family", "raw_score_without", "score_without", "delta_points", "in_queue_without"]
COMMUNITY_COLUMNS = ["community_id", "kind", "method", "size", "selected_count", "requested_units", "purchased_units",
                     "coordinated_claim_matches", "edges"]
# reason code -> the group the timeline shows beside it; the four groups partition the sixteen codes of the codebook
REASON_GROUPS = {code: group for group, name in (("transaction_claim", "transaction_claim"), ("item_complaint", "item_complaint_customer"),
                                                  ("fit", "fit"), ("discretionary", "discretionary"))
                 for code in contract.reason_group(name)}


@dataclass
class RunOutput:
    summary: dict
    customers: pd.DataFrame
    styles: pd.DataFrame
    skus: pd.DataFrame
    neighbors: pd.DataFrame
    timeline: pd.DataFrame
    customer_styles: pd.DataFrame
    communities: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=COMMUNITY_COLUMNS))
    attributions: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=ATTRIBUTION_COLUMNS))
    style_reasons: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=STYLE_REASON_COLUMNS))


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


def _basket(result: F.FeatureResult, index: pd.Index) -> pd.DataFrame:
    """The normal band of the basket expectation and the facts behind it, per customer, from the same lines the features use.

    sd = sqrt(d * sum(q * p * (1 - p))) over the customer's mature lines with d the mean lines per order-and-style
    group clipped to [1, 4], exactly as compute_features scales residual_z; the band is expected +/- 2 sd.
    Bracketing: units bought as two or more sizes of one style in one order, and how many of them were kept.
    Nothing is refit; these are sums over stored lines.
    """
    lines = result.lines
    mature = lines[lines["mature"]].copy()
    group = ["customer_id", "order_id", "style_id"]
    variance = (mature["quantity"] * mature["p_expected"] * (1 - mature["p_expected"])).groupby(mature["customer_id"]).sum()
    d = mature.groupby(group).size().groupby("customer_id").mean().clip(1, F.OVERDISPERSION_CAP)
    expected = (mature["quantity"] * mature["p_expected"]).groupby(mature["customer_id"]).sum()
    sd = np.sqrt(d * variance.where(variance > 0))
    sizes = mature.groupby(group)["size"].transform("nunique")
    bracketed = mature[sizes >= 2]
    out = pd.DataFrame(index=index)
    out["expected_sd"] = sd.reindex(index)
    out["expected_band_low"] = (expected - BAND_SD * sd).clip(lower=0).reindex(index)
    out["expected_band_high"] = (expected + BAND_SD * sd).reindex(index)
    out["bracket_groups"] = bracketed.drop_duplicates(group).groupby("customer_id").size().reindex(index, fill_value=0).astype(int)
    out["bracket_units_ordered"] = bracketed.groupby("customer_id")["quantity"].sum().reindex(index, fill_value=0).astype(int)
    out["bracket_units_kept"] = (bracketed["quantity"] - bracketed["requested_units"]).groupby(bracketed["customer_id"]).sum() \
        .reindex(index, fill_value=0).astype(int)
    timed = result.requests[result.requests["days"] >= 0]
    out["median_return_day"] = timed.groupby("customer_id")["days"].median().reindex(index)
    return out


def _cleared_reason(customers: pd.DataFrame) -> pd.Series:
    """Template key for every eligible customer outside the queue; None for the queue and for unranked customers."""
    reason = pd.Series(None, index=customers.index, dtype=object)
    cleared = (customers["eligibility_status"] == "eligible") & ~customers["selected_for_review"]
    for key, rule in reversed(CLEARED_REASONS):                   # the first rule in CLEARED_REASONS wins
        reason[cleared & rule(customers).fillna(False).astype(bool)] = key
    return reason


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


def _louvain(component: nx.Graph) -> list:
    """Louvain parts of one large component, each sorted, in order of their smallest member; no part is left alone.

    A member Louvain leaves by itself joins the part of its heaviest neighbour (smallest id on a tie), so every
    community has at least two members and the parts of one component partition it.
    """
    parts = [set(part) for part in nx.community.louvain_communities(component, weight="weight", seed=0)]
    while (alone := next((part for part in parts if len(part) == 1), None)) is not None:
        parts.remove(alone)
        member = next(iter(alone))
        neighbour = max(sorted(component.neighbors(member)), key=lambda n: component[member][n]["weight"])
        next(other for other in parts if neighbour in other).add(member)
    return [sorted(part) for part in sorted(parts, key=min)]


def community_kind(edges: list, selected: int, matched: int, share_positive: bool) -> str:
    """The kind of a group of linked accounts (decision D3 as revised by AM-66), from observed evidence only.

    Where some edge shares a payment instrument, the first rule stands: `ring` on one coordinated claim match, two or
    more members selected for review, or a member with a coordinated claim share above zero. Where every edge shares
    only an address and a device, the shape of a household, one matching claim is not enough: family members at an
    address where parcels go missing claim on the same order within days for honest reasons. Such a group is a `ring`
    only with two or more coordinated claim matches or two or more members selected for review.
    """
    if any("payment" in edge["types"] for edge in edges):
        ring = matched >= 1 or selected >= 2 or share_positive
    else:
        ring = matched >= 2 or selected >= 2
    return "ring" if ring else "household"


def _communities(world_id: str, graph_edges: pd.DataFrame, neighbors: pd.DataFrame, customers: pd.DataFrame) -> tuple:
    """Groups of linked accounts and the observable kind of each; (communities frame, customer_id -> community_id).

    A community is a connected component of the supported edges (two or more shared identifier types, values shared
    by more than 25 accounts already dropped), so components are small and the grouping is deterministic. A component
    of LOUVAIN_FROM members or more is split by Louvain on the edge weight with a fixed seed; `method` records which
    produced each community. The identifier is the world prefix and a hash of the sorted member ids, so the same
    accounts linked the same way get the same id in every run of the world.

    Kind (decision D3, revised by AM-66), from observed evidence only, truth is never read: see `community_kind`.
    A customer with no supported edge belongs to no community.
    """
    membership = pd.Series(None, index=pd.Index(customers["customer_id"]), dtype=object)
    if not len(graph_edges):
        return pd.DataFrame(columns=COMMUNITY_COLUMNS), membership
    matches = {}                                                     # undirected edge -> the larger of its two directions
    for row in neighbors.itertuples(index=False):
        key = (min(row.customer_id, row.neighbor_id), max(row.customer_id, row.neighbor_id))
        matches[key] = max(matches.get(key, 0), int(row.coordinated_claim_matches))
    graph = nx.Graph()
    for row in graph_edges.sort_values(["customer_a", "customer_b"]).itertuples(index=False):
        graph.add_edge(row.customer_a, row.customer_b, types=list(row.shared_types), weight=float(row.weight))
    groups = []
    for component in sorted(nx.connected_components(graph), key=min):
        if len(component) >= LOUVAIN_FROM:
            groups += [(members, "louvain") for members in _louvain(graph.subgraph(sorted(component)))]
        else:
            groups.append((sorted(component), "components"))
    by_id = customers.set_index("customer_id")
    rows = []
    for members, method in groups:
        digest = hashlib.sha256("|".join(members).encode("utf-8")).hexdigest()[:12].upper()
        community_id = f"{world_id}-L{digest}"
        membership[members] = community_id
        inside = set(members)
        edges = [{"a": a, "b": b, "types": data["types"], "coordinated_claim_matches": matches.get((a, b), 0)}
                 for a, b, data in sorted(((min(u, v), max(u, v), d) for u, v, d in graph.edges(members, data=True)
                                           if u in inside and v in inside), key=lambda e: e[:2])]
        own = by_id.loc[members]
        selected = int(own["selected_for_review"].sum())
        matched = sum(edge["coordinated_claim_matches"] for edge in edges)
        kind = community_kind(edges, selected, matched, bool((own["coordinated_claim_share"].fillna(0) > 0).any()))
        rows.append({"community_id": community_id, "kind": kind, "method": method,
                     "size": len(members), "selected_count": selected,
                     "requested_units": int(own["mature_requested_units"].sum()),
                     "purchased_units": int(own["mature_purchased_units"].sum()),
                     "coordinated_claim_matches": int(matched), "edges": json.dumps(edges)})     # one JSON text per community
    return pd.DataFrame(rows, columns=COMMUNITY_COLUMNS), membership


def _style_extras(tables: dict, result: F.FeatureResult, styles: pd.DataFrame, customers: pd.DataFrame) -> tuple:
    """(styles with the SKU screen's extra columns, reason rows per style, customer-style rows with their extra columns).

    Everything is a sum or a median over the mature lines and requests the style states were built from: the reasons
    by code and group, the median return day, the share of timed requests in the last five days of the window, how
    many returners are selected for review or in a ring, and the median score of the eligible returners. The name is
    "{brand} {category}" from sku_master (no name column exists), with the style id when that pair repeats in the run.
    """
    requests = result.requests[result.requests["mature"]]
    lines = result.lines[result.lines["mature"]]
    by_customer = customers.set_index("customer_id")
    out = styles.set_index("style_id")
    skus = tables["sku_master"].drop_duplicates("style_id").set_index("style_id")
    names = (skus["brand"].astype(str) + " " + skus["category"].astype(str)).reindex(out.index)
    repeated = names.map(names.value_counts()) > 1
    out["name"] = names.where(~repeated, names + " " + pd.Series(out.index, index=out.index)).fillna(pd.Series(out.index, index=out.index))
    timed = requests[requests["days"] >= 0]
    out["median_return_day"] = timed.groupby("style_id")["days"].median().reindex(out.index)
    late = timed["days"] >= timed["return_window_days"] - LAST_DAYS
    out["share_in_last_five_days"] = (late.groupby(timed["style_id"]).mean()).reindex(out.index)
    returners = requests.drop_duplicates(["style_id", "customer_id"])[["style_id", "customer_id"]]
    returners = returners.join(by_customer[["selected_for_review", "risk_score", "community_id", "eligibility_status"]], on="customer_id")
    ring_ids = set(getattr(result, "ring_ids", set()))
    out["flagged_returners"] = returners.groupby("style_id")["selected_for_review"].sum().reindex(out.index, fill_value=0).astype(int)
    out["ring_returners"] = returners["community_id"].isin(ring_ids).groupby(returners["style_id"]).sum().reindex(out.index, fill_value=0).astype(int)
    out["median_returner_score"] = returners[returners["eligibility_status"] == "eligible"].groupby("style_id")["risk_score"].median().reindex(out.index)
    reasons = requests.groupby(["style_id", "reason_code"]).agg(lines=("reason_code", "size"), units=("quantity_returned", "sum")).reset_index()
    reasons["reason_group"] = reasons["reason_code"].map(REASON_GROUPS)
    reasons = reasons.sort_values(["style_id", "units", "lines", "reason_code"], ascending=[True, False, False, True]).reset_index(drop=True)
    extras = result.requests.sort_values(["requested_at", "return_order_id", "return_line_no"]).groupby(["customer_id", "style_id"]).agg(
        return_lines=("reason_code", "size"), last_reason_code=("reason_code", "last")).reset_index()
    bought = lines.groupby(["customer_id", "style_id"]).size().rename("purchased_lines").reset_index()
    extras = extras.merge(bought, on=["customer_id", "style_id"], how="left")
    extras["purchased_lines"] = extras["purchased_lines"].fillna(0).astype(int)
    return out.reset_index(), reasons[STYLE_REASON_COLUMNS], extras


def _timeline(tables: dict, result: F.FeatureResult) -> pd.DataFrame:
    """Source transactions per customer: every sale line and every return request, with their own keys.

    Every event carries its facts as columns (order and line, quantity, size, reason code and group, day in the
    return window, item received, linked claim) beside the sentence built from them, so a reader never has to
    parse the sentence. A column that does not apply to an event kind is missing. The customer's free-text reason
    is evidence_only in the data contract and is never read here.
    """
    sku = tables["sku_master"].set_index("sku")
    lines = result.lines
    delivered = lines["delivered_date"].dt.strftime("%Y-%m-%d").fillna("not delivered")
    purchases = pd.DataFrame({
        "customer_id": lines["customer_id"], "source_ref": "sales_order_line:" + lines["order_id"] + "/" + lines["order_line_no"].astype(str),
        "event_type": "purchase", "observed_at": lines["order_date"].dt.strftime("%Y-%m-%d"),
        "description": ("Ordered " + lines["quantity"].astype(str) + " x " + lines["category"] + " size " + lines["size"].astype(str)
                        + "; " + lines["line_status"].str.replace("_", " ") + "; delivered " + delivered),
        "amount_inr": lines["line_total"].astype(float), "style_id": lines["style_id"], "sku": lines["sku"], "sort_at": lines["order_date"],
        "order_id": lines["order_id"], "order_line_no": lines["order_line_no"].astype(int), "quantity": lines["quantity"].astype(int),
        "size": lines["size"].astype(str), "window_days": lines["return_window_days"].astype(int), "line_status": lines["line_status"]})
    returns = tables["return_order_line"].merge(
        lines[["order_id", "order_line_no", "customer_id", "style_id", "size", "delivered_date", "return_window_days"]],
        on=["order_id", "order_line_no"])
    linked = result.requests.set_index(["return_order_id", "return_line_no"])["linked"]
    key = pd.MultiIndex.from_frame(returns[["return_order_id", "return_line_no"]])
    is_linked = linked.reindex(key).fillna(False).to_numpy(dtype=bool)
    days = (returns["requested_at"].dt.normalize() - returns["delivered_date"]).dt.days
    claim = returns["reason_code"].isin(F.CLAIM_CODES)
    received = pd.to_numeric(returns["return_received_flag"], errors="coerce")       # empty exactly when no item comes back
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
        "sort_at": returns["requested_at"],
        "order_id": returns["order_id"], "order_line_no": returns["order_line_no"].astype(int),
        "quantity": returns["quantity_returned"].astype(int), "size": returns["size"].astype(str),
        "reason_code": returns["reason_code"].astype(str), "reason_group": returns["reason_code"].map(REASON_GROUPS),
        "day_in_window": days.astype("Int64"), "window_days": returns["return_window_days"].astype(int),
        "line_status": returns["line_status"].astype(str), "item_received": (received == 1).where(received.notna(), None),
        "linked_claim": is_linked})
    timeline = pd.concat([purchases, requests], ignore_index=True)
    timeline["sku"] = timeline["sku"].where(timeline["sku"].isin(sku.index))
    return timeline.sort_values(["customer_id", "sort_at", "source_ref"]).drop(columns="sort_at").reset_index(drop=True)


def drift(bundle: bundles.Bundle, scored: pd.DataFrame, raw: np.ndarray) -> tuple:
    """(report, warnings): how this snapshot's scores and inputs sit against training (final-spec component 15).

    Scores: the share of eligible customers at or above the training 50th, 90th, 95th and 99th percentile; a
    snapshot like the training worlds gives .50, .10, .05 and .01. Inputs: the features whose median here lies
    outside the 10th to 90th percentile of training customers. It describes; it never refits, corrects or
    promotes, and a quiet report is no evidence of accuracy.
    """
    if len(scored) < DRIFT_MIN_ELIGIBLE:
        return {"checked": False, "reason": f"fewer than {DRIFT_MIN_ELIGIBLE} eligible customers"}, []
    percentile = bundles.reference_percentile(bundle, raw)
    shares = {f"p{q}": float((percentile >= q).mean()) for q in (50, 90, 95, 99)}
    outside = []
    for name, quantiles in (bundle.manifest.get("feature_quantiles") or {}).items():
        values = scored[name].to_numpy(dtype=float) if name in scored and quantiles else np.array([np.nan])
        if not np.isnan(values).all() and not quantiles[0] <= float(np.nanmedian(values)) <= quantiles[2]:
            outside.append(name)
    notes = []
    low, high = DRIFT_P95_BAND
    if not low <= shares["p95"] <= high:
        notes.append(f"{shares['p95']:.1%} of eligible customers score above the training 95th percentile (5% expected): "
                     "this snapshot differs from the training worlds, so percentiles and the review list deserve caution.")
    if outside:
        notes.append("Inputs outside the range seen in training (median beyond the training 10th-90th percentile): "
                     + ", ".join(sorted(outside)) + ".")
    return {"checked": True, "score_share_at_or_above_training_percentile": shares, "features_outside_training_range": sorted(outside)}, notes


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
    for name in F.WARDROBING_POINTS:
        customers["fired_" + name] = customers["customer_id"].map(wardrobing["fired_" + name]).astype(bool)
    for name in F.WARDROBING_SUPPORT:
        if name not in customers:
            customers[name] = customers["customer_id"].map(wardrobing[name])
    customers["evidence_tags"] = _tags(customers)
    basket = _basket(result, pd.Index(customers["customer_id"]))
    for name in basket.columns:
        customers[name] = basket[name].to_numpy()
    customers["cleared_reason"] = _cleared_reason(customers)
    neighbors = _neighbors(result)
    communities, membership = _communities(world_id, result.graph.edges, neighbors, customers)
    customers["community_id"] = customers["customer_id"].map(membership)
    # the score with each feature family at typical values (predict-side only), the chips' order and the rules that would have fired
    at_budget = (customers["rank"] == k).fillna(False).astype(bool)                 # the last customer inside the budget
    threshold_raw = float(customers.loc[at_budget, "raw_score"].iloc[0]) if k and at_budget.any() else None
    attributions, typical_from = attribution.attribute(bundle, customers[eligible], raw, customers.loc[eligible, "risk_score"].to_numpy(dtype=float),
                                                       threshold_raw)
    customers["primary_signals"] = attribution.primary_signals(customers.set_index("customer_id")["evidence_tags"], attributions).to_numpy()
    rules = attribution.rules_fired(customers, bundle)
    for name in rules.columns:
        customers[name] = rules[name].to_numpy()

    result.ring_ids = set(communities.loc[communities["kind"] == "ring", "community_id"])     # for the style screen's ring returners
    styles, style_reasons, style_extras = _style_extras(tables, result, result.styles.sort_values("style_id").reset_index(drop=True), customers)
    skus = result.skus.merge(tables["sku_master"][["sku", "size", "colour", "unit_price"]], on="sku", how="left") \
        .sort_values("sku").reset_index(drop=True)
    requests = result.requests
    customer_styles = requests.groupby(["customer_id", "style_id"]).agg(
        requested_units=("quantity_returned", "sum"), claim_lines=("is_claim", "sum"),
        linked_claim_lines=("linked", lambda s: int(s.fillna(False).sum()))).reset_index() if len(requests) else \
        pd.DataFrame(columns=["customer_id", "style_id", "requested_units", "claim_lines", "linked_claim_lines"])
    customer_styles = customer_styles.merge(style_extras, on=["customer_id", "style_id"], how="left")

    selected, baseline_selected = customers["selected_for_review"], customers["baseline_selected"]
    threshold = float(customers.loc[at_budget, "risk_score"].iloc[0]) if k and at_budget.any() else None
    requested = int(customers.loc[eligible, "mature_requested_units"].sum())
    purchased = int(customers.loc[eligible, "mature_purchased_units"].sum())
    rates = customers.loc[eligible, "raw_return_rate"].dropna()
    heavy_cutoff = float(rates.quantile(HEAVY_RETURNER_QUANTILE, interpolation="linear")) if len(rates) else None
    warnings = []
    if n < SMALL_POPULATION:
        warnings.append(f"Only {n} eligible customers: peer comparisons are unstable in a snapshot this small.")
    if result.fallback_uses:
        warnings.append(f"{result.fallback_uses} sale lines had no peers in their category and used the frozen training rate.")
    drift_report, drift_notes = drift(bundle, scored, raw)
    warnings += drift_notes
    if bundles.code_differs(bundle):
        warnings.append("The scoring code differs from the code this bundle was published with; republish the experiment "
                        "to confirm that features still match training.")
    summary = {
        "world_id": world_id, "model_id": bundle.model_id, "model_kind": bundle.kind, "cutoff": manifest["cutoff"],
        "customer_count": len(customers), "eligible_count": n, "excluded_count": int(len(customers) - n),
        "review_budget_k": int(k), "selected_count": int(selected.sum()),
        "model_only_count": int((selected & ~baseline_selected).sum()),
        "baseline_only_count": int((baseline_selected & ~selected).sum()),
        "both_count": int((selected & baseline_selected).sum()),
        "graph_edges": len(result.graph.edges), "identifier_values_dropped": int(result.graph.dropped_values),
        "category_fallback_uses": int(result.fallback_uses), "warnings": warnings, "drift": drift_report,
        # the queue's edge and the eligible population it is cut from, for the queue header and the threshold slider
        "threshold_score": threshold,
        "median_score": float(np.median(customers.loc[eligible, "risk_score"].to_numpy(dtype=float))) if n else None,
        "eligible_requested_units": requested, "eligible_purchased_units": purchased,
        "mean_return_rate": requested / purchased if purchased else None,
        "heavy_returner_cutoff": heavy_cutoff,
        # groups of linked accounts (connected components of the supported edges) and how many look coordinated
        "community_count": len(communities), "ring_count": int((communities["kind"] == "ring").sum()),
        "styles_with_verdict": int(styles["state"].isin(["quality", "targeting", "mixed_or_uncertain"]).sum()),
        # how the score breakdown was made: whose medians stood in for a family, and the raw score at the queue's edge
        "attribution": {"typical_from": typical_from, "threshold_raw_score": threshold_raw},
        "score_label": bundle.manifest["score_label"], "feature_order": bundle.feature_order,
    }
    return RunOutput(summary=summary, customers=customers, styles=styles, skus=skus, neighbors=neighbors,
                     timeline=_timeline(tables, result), customer_styles=customer_styles, communities=communities,
                     attributions=attributions, style_reasons=style_reasons)
