"""Feature engineering and explanatory evidence (final-spec component 06).

Everything here reads the seven operational tables only. No private truth, persona, target or identifier
value enters a feature; identifiers are used for equality alone. One row per customer and world.

Outputs:
- the 18 ordered model features of contracts/features.yaml,
- the observed relationship graph (an edge needs two shared identifier types),
- style and SKU evidence (quality and targeting signals),
- the wardrobing indicator, which is independent of the model score.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

import numpy as np
import pandas as pd
import yaml

from arai.paths import SPEC_ROOT

CLAIM_CODES = ("wrong_item_sent", "missing_parts", "item_not_received", "empty_package")
COMPLAINT_CODES = ("damaged", "defective", "poor_quality", "not_as_described")       # item_complaint_customer
QUALITY_CODES = ("defective", "poor_quality", "not_as_described")                    # item_complaint_sku_quality
DISCRETIONARY_CODES = ("didnt_suit", "changed_my_mind", "not_as_expected", "found_better_price",
                       "ordered_by_mistake", "late_delivery")
IDENTIFIERS = ("address_id", "device_id", "payment_id")
LINE_KEY = ["order_id", "order_line_no"]

ELIGIBLE_MIN_LINES = 3          # experiment.yaml eligibility.min_mature_sale_lines
SHRINKAGE = 20                  # prior strength of the two-level expectation
OVERDISPERSION_CAP = 4
FANOUT_CAP = 25
LINK_DAYS = 7
WINDOW_RATIO_CAP = 2.0
STYLE_SUPPORT = 20              # mature sale lines a style or SKU needs before evidence is shown
QUALITY_DAMAGE_SHARE = 0.30
TARGETING_LINKED_CLAIMERS = 3
TARGETING_LINKED_SHARE = 0.075
# wardrobing: integer points, never floating point (decimal weights miss the band boundaries)
WARDROBING_POINTS = {"latency_z": 30, "median_window_ratio": 25, "occasion_return_share": 15,
                     "discretionary_share": 20, "bracketing_share": 10}
WARDROBING_ELEVATED, WARDROBING_POSSIBLE = 65, 45
TIMING_SIGNALS = ("latency_z", "median_window_ratio")


def feature_order(spec_root=None) -> list:
    """The ordered model features, read from the contract so code and contract cannot drift apart."""
    contract = yaml.safe_load(((spec_root or SPEC_ROOT) / "contracts" / "features.yaml").read_text(encoding="utf-8"))
    return [f["name"] for f in contract["ordered_features"]]


@dataclass
class Reference:
    """Statistics frozen from training worlds: fallbacks for peerless categories and the latency baseline."""
    category_rate: dict                  # category -> mature requested units / mature purchased units
    latency_median: dict                 # category -> median capped days from delivery to request
    latency_iqr: dict                    # category -> interquartile range of the same

    def to_dict(self) -> dict:
        return {"category_rate": self.category_rate, "latency_median": self.latency_median, "latency_iqr": self.latency_iqr}

    @classmethod
    def from_dict(cls, data: dict) -> "Reference":
        return cls(dict(data["category_rate"]), dict(data["latency_median"]), dict(data["latency_iqr"]))


@dataclass
class Graph:
    edges: pd.DataFrame                  # customer_a, customer_b, shared_types, shared_value_count, max_value_fanout
    neighbours: dict                     # customer_id -> set of supported neighbours
    fanout: dict                         # identifier column -> Series(value -> distinct accounts)
    dropped_values: int                  # identifier values removed for exceeding the fan-out cap


@dataclass
class FeatureResult:
    features: pd.DataFrame               # one row per customer: the 18 features plus eligibility and support counts
    graph: Graph
    styles: pd.DataFrame
    skus: pd.DataFrame
    wardrobing: pd.DataFrame
    lines: pd.DataFrame = field(repr=False)        # sale lines with maturity, requested units and expected probability
    requests: pd.DataFrame = field(repr=False)     # visible non-withdrawn requests with timing and reason group
    fallback_uses: int = 0                         # sale lines whose category had no peers and used the frozen mean


# ------------------------------------------------------------------ shared preparation
def _prepare(tables: dict, cutoff) -> tuple:
    """Sale lines and visible non-withdrawn requests with everything the features need.

    Return lines are aggregated per sale line before joining to sales, so exposure is never duplicated.
    """
    cutoff = pd.Timestamp(cutoff).normalize()
    unknown = set(tables["sales_order_line"]["sku"]) - set(tables["sku_master"]["sku"])
    if unknown:
        raise ValueError(f"sale lines reference unknown SKUs: {sorted(unknown)[:5]}")
    lines = tables["sales_order_line"].merge(
        tables["sales_order"][["order_id", "customer_id", "order_date", *IDENTIFIERS]], on="order_id") \
        .merge(tables["sku_master"][["sku", "style_id", "category", "size", "is_occasion_wear"]], on="sku")
    lines["delivered"] = lines["line_status"] == "delivered"
    lines["mature"] = lines["delivered"] & (
        lines["delivered_date"] + pd.to_timedelta(lines["return_window_days"], unit="D") <= cutoff)
    lines["net_unit_value"] = lines["line_total"] / lines["quantity"]

    returns = tables["return_order_line"]
    active = returns[returns["line_status"] != "withdrawn"]
    lines = lines.merge(active.groupby(LINE_KEY)["quantity_returned"].sum().rename("requested_units"), on=LINE_KEY, how="left")
    lines["requested_units"] = lines["requested_units"].fillna(0).astype(int)

    requests = active.merge(lines[LINE_KEY + ["customer_id", "style_id", "category", "is_occasion_wear", "delivered_date",
                                              "return_window_days", "mature", "net_unit_value"]], on=LINE_KEY)
    requests["days"] = (requests["requested_at"].dt.normalize() - requests["delivered_date"]).dt.days
    requests["window_ratio"] = np.minimum(WINDOW_RATIO_CAP, requests["days"] / requests["return_window_days"])
    requests["capped_days"] = np.minimum(requests["days"], WINDOW_RATIO_CAP * requests["return_window_days"])
    requests["is_claim"] = requests["reason_code"].isin(CLAIM_CODES)
    requests["request_day"] = requests["requested_at"].dt.normalize()
    return lines, requests, cutoff


def fit_reference(worlds: list) -> Reference:
    """Frozen training statistics from (tables, cutoff) pairs. Training worlds only; never refit at inference."""
    mature, latency = [], []
    for tables, cutoff in worlds:
        lines, requests, _ = _prepare(tables, cutoff)
        mature.append(lines.loc[lines["mature"], ["category", "quantity", "requested_units"]])
        latency.append(requests[["category", "capped_days"]])
    mature, latency = pd.concat(mature), pd.concat(latency)
    totals = mature.groupby("category")[["requested_units", "quantity"]].sum()
    spread = latency.groupby("category")["capped_days"].quantile([0.25, 0.5, 0.75]).unstack()
    return Reference(category_rate=(totals["requested_units"] / totals["quantity"]).to_dict(),
                     latency_median=spread[0.5].to_dict(), latency_iqr=(spread[0.75] - spread[0.25]).to_dict())


# ------------------------------------------------------------------ graph
def build_graph(orders: pd.DataFrame) -> Graph:
    """Supported relationships from identifier equality.

    A value shared by more than 25 accounts is dropped. An edge needs at least two shared identifier types;
    several shared values of one type still count as one type. Membership of a link is not guilt.
    """
    shared, fanout, dropped = {}, {}, 0
    for kind in IDENTIFIERS:
        accounts = orders.groupby(kind)["customer_id"].unique()
        sizes = accounts.map(len)
        fanout[kind] = sizes
        dropped += int((sizes > FANOUT_CAP).sum())
        for value, members in accounts[(sizes >= 2) & (sizes <= FANOUT_CAP)].items():
            for pair in combinations(sorted(members), 2):
                entry = shared.setdefault(pair, {})
                entry.setdefault(kind, []).append(len(members))
    rows, neighbours = [], {}
    for (a, b), kinds in shared.items():
        if len(kinds) < 2:
            continue
        neighbours.setdefault(a, set()).add(b)
        neighbours.setdefault(b, set()).add(a)
        rows.append({"customer_a": a, "customer_b": b, "shared_types": sorted(k.replace("_id", "") for k in kinds),
                     "shared_value_count": sum(len(v) for v in kinds.values()),
                     "max_value_fanout": max(max(v) for v in kinds.values()),
                     "weight": sum(1.0 / np.log2(1 + min(v)) for v in kinds.values())})
    edges = pd.DataFrame(rows, columns=["customer_a", "customer_b", "shared_types", "shared_value_count", "max_value_fanout", "weight"])
    return Graph(edges=edges, neighbours=neighbours, fanout=fanout, dropped_values=dropped)


def linked_claims(requests: pd.DataFrame, neighbours: dict) -> pd.DataFrame:
    """Claim lines with `linked`: a supported neighbour claimed on the same style within seven days."""
    claims = requests[requests["is_claim"]].copy()
    linked = np.zeros(len(claims), dtype=bool)
    matches = np.zeros(len(claims), dtype=int)
    for _, group in claims.groupby("style_id"):
        customers, days = group["customer_id"].to_numpy(), group["request_day"].to_numpy()
        positions = claims.index.get_indexer(group.index)
        for i in range(len(group)):
            mine = neighbours.get(customers[i])
            if not mine:
                continue
            near = np.abs((days - days[i]) / np.timedelta64(1, "D")) <= LINK_DAYS
            count = len({c for c in customers[near] if c in mine})
            linked[positions[i]] = count > 0
            matches[positions[i]] = count
    claims["linked"] = linked
    claims["linked_neighbours"] = matches
    return claims


# ------------------------------------------------------------------ customer features
def _expected(lines: pd.DataFrame, reference: Reference | None) -> tuple:
    """Two-level, self-excluded expected return probability for every mature sale line."""
    mature = lines[lines["mature"]].copy()
    q, r = "quantity", "requested_units"
    for level in ("category", "style_id", "sku"):
        mature[[f"N_{level}", f"R_{level}"]] = mature.groupby(level)[[q, r]].transform("sum")
        mature[[f"n_{level}", f"r_{level}"]] = mature.groupby(["customer_id", level])[[q, r]].transform("sum")
    peers = mature["N_category"] - mature["n_category"]
    fallback = peers <= 0
    if fallback.any():
        if reference is None:
            raise ValueError("a category has no peers and no frozen training reference was supplied")
        missing = set(mature.loc[fallback, "category"]) - set(reference.category_rate)
        if missing:
            raise ValueError(f"no frozen category mean for {sorted(missing)}")
    mu_category = np.where(fallback, mature["category"].map(reference.category_rate if reference else {}).astype(float),
                           (mature["R_category"] - mature["r_category"]) / peers.where(~fallback, 1))
    mu_style = (mature["R_style_id"] - mature["r_style_id"] + SHRINKAGE * mu_category) / \
               (mature["N_style_id"] - mature["n_style_id"] + SHRINKAGE)
    mature["p_expected"] = (mature["R_sku"] - mature["r_sku"] + SHRINKAGE * mu_style) / \
                           (mature["N_sku"] - mature["n_sku"] + SHRINKAGE)
    return mature, int(fallback.sum())


def _share(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """A share that is null, never zero, when its denominator is zero or missing."""
    numerator, denominator = numerator.align(denominator, join="right", fill_value=0)
    return (numerator / denominator.where(denominator > 0)).astype(float)


def compute_features(tables: dict, cutoff, reference: Reference | None = None) -> FeatureResult:
    """All features and evidence for one snapshot. Aggregates are recomputed; nothing learned is refit."""
    lines, requests, cutoff = _prepare(tables, cutoff)
    customers = tables["customer_master"]["customer_id"]
    out = pd.DataFrame(index=pd.Index(customers, name="customer_id"))
    mature, fallback_uses = _expected(lines, reference)
    delivered = lines[lines["delivered"]]

    # exposure and volume
    out["mature_sale_lines"] = mature.groupby("customer_id").size().reindex(out.index, fill_value=0)
    out["log_order_count"] = np.log1p(delivered.groupby("customer_id")["order_id"].nunique().reindex(out.index, fill_value=0))
    N = mature.groupby("customer_id")["quantity"].sum()
    R = mature.groupby("customer_id")["requested_units"].sum()
    out["raw_return_rate"] = _share(R, N.reindex(out.index, fill_value=0))

    # expected rate and residual
    mature["expected_units"] = mature["quantity"] * mature["p_expected"]
    mature["variance"] = mature["quantity"] * mature["p_expected"] * (1 - mature["p_expected"])
    E = mature.groupby("customer_id")["expected_units"].sum()
    V = mature.groupby("customer_id")["variance"].sum()
    out["expected_return_rate"] = _share(E, N.reindex(out.index, fill_value=0))
    lines_per_group = mature.groupby(["customer_id", "order_id", "style_id"]).size().groupby("customer_id").mean()
    d = lines_per_group.clip(1, OVERDISPERSION_CAP)
    z = (R - E) / np.sqrt(d * V.where(V > 0))
    out["residual_z"] = z.reindex(out.index)

    # composition and timing: every visible non-withdrawn request, mature or not
    units = requests.groupby("customer_id")["quantity_returned"].sum().reindex(out.index, fill_value=0)

    def unit_share(mask) -> pd.Series:
        return _share(requests[mask].groupby("customer_id")["quantity_returned"].sum(), units)

    out["claim_share"] = unit_share(requests["is_claim"])
    purchased_value = mature.groupby("customer_id")["line_total"].sum()
    requested_value = (mature["requested_units"] * mature["net_unit_value"]).groupby(mature["customer_id"]).sum()
    out["requested_refund_ratio"] = _share(requested_value, purchased_value.reindex(out.index, fill_value=0))
    out["damage_reason_share"] = unit_share(requests["reason_code"].isin(COMPLAINT_CODES))

    sizes = mature.groupby(["customer_id", "order_id", "style_id"])["size"].transform("nunique")
    out["bracketing_share"] = _share(mature[sizes >= 2].groupby("customer_id")["quantity"].sum(), N.reindex(out.index, fill_value=0))

    timed = requests[requests["days"] >= 0]
    timed_units = timed.groupby("customer_id")["quantity_returned"].sum().reindex(out.index, fill_value=0)
    out["late_window_share"] = _share(timed[timed["window_ratio"] >= 0.75].groupby("customer_id")["quantity_returned"].sum(), timed_units)
    out["median_window_ratio"] = timed.groupby("customer_id")["window_ratio"].median().reindex(out.index)
    out["occasion_return_share"] = unit_share(requests["is_occasion_wear"] == 1)
    out["discretionary_share"] = unit_share(requests["reason_code"].isin(DISCRETIONARY_CODES))

    # trend: mature return rate of the last 90 delivery days minus the 90 before
    age = (cutoff - mature["delivered_date"]).dt.days
    recent, earlier = mature[age <= 89], mature[(age >= 90) & (age <= 179)]
    rate = lambda part: _share(part.groupby("customer_id")["requested_units"].sum(),
                               part.groupby("customer_id")["quantity"].sum().reindex(out.index, fill_value=0))
    out["trend_90d"] = rate(recent) - rate(earlier)
    delivered_units = delivered.groupby("customer_id")["quantity"].sum().reindex(out.index, fill_value=0)
    out["open_window_share"] = _share(delivered[~delivered["mature"]].groupby("customer_id")["quantity"].sum(), delivered_units)

    # relationships
    orders = tables["sales_order"]
    graph = build_graph(orders)
    own_fanout = pd.concat([orders[["customer_id", kind]].drop_duplicates().assign(
        fanout=lambda f, k=kind: f[k].map(graph.fanout[k])) [["customer_id", "fanout"]] for kind in IDENTIFIERS])
    out["max_identifier_fanout"] = own_fanout.groupby("customer_id")["fanout"].max().clip(upper=FANOUT_CAP) \
        .reindex(out.index, fill_value=0).astype(int)
    out["supported_neighbor_count"] = pd.Series({c: len(n) for c, n in graph.neighbours.items()}, dtype=float) \
        .reindex(out.index, fill_value=0).astype(int)
    claims = linked_claims(requests, graph.neighbours)
    out["coordinated_claim_share"] = claims.groupby("customer_id")["linked"].mean().reindex(out.index)

    features = out[feature_order()].copy()
    features["eligible"] = features["mature_sale_lines"] >= ELIGIBLE_MIN_LINES
    features["mature_purchased_units"] = N.reindex(out.index, fill_value=0).astype(int)
    features["mature_requested_units"] = R.reindex(out.index, fill_value=0).astype(int)
    features["all_requested_units"] = units.astype(int)
    features["expected_units"] = E.reindex(out.index)
    features = features.reset_index()

    lines = lines.merge(mature[LINE_KEY + ["p_expected"]], on=LINE_KEY, how="left")
    styles, skus = style_evidence(lines, requests, claims, reference)
    wardrobing = wardrobing_indicator(features, requests, reference)
    return FeatureResult(features=features, graph=graph, styles=styles, skus=skus, wardrobing=wardrobing,
                         lines=lines, requests=requests.merge(claims[["return_order_id", "return_line_no", "linked", "linked_neighbours"]],
                                                              on=["return_order_id", "return_line_no"], how="left"),
                         fallback_uses=fallback_uses)


# ------------------------------------------------------------------ style and SKU evidence
def style_evidence(lines: pd.DataFrame, requests: pd.DataFrame, claims: pd.DataFrame, reference: Reference | None) -> tuple:
    """Quality and targeting signals per style, and support per SKU. Evidence, never a verdict on a customer."""
    mature = lines[lines["mature"]]
    styles = mature.groupby("style_id").agg(category=("category", "first"), mature_sale_lines=("sku", "size"),
                                            purchased_units=("quantity", "sum"), requested_units=("requested_units", "sum"))
    styles["unique_returners"] = mature[mature["requested_units"] > 0].groupby("style_id")["customer_id"].nunique()
    mature_requests = requests[requests["mature"]]
    quality = mature_requests[mature_requests["reason_code"].isin(QUALITY_CODES)].groupby("style_id")["quantity_returned"].sum()
    claim_units = mature_requests[mature_requests["is_claim"]].groupby("style_id")["quantity_returned"].sum()
    link = claims.groupby("style_id").agg(claim_lines=("linked", "size"), linked_claim_lines=("linked", "sum"))
    link["linked_claimers"] = claims[claims["linked"]].groupby("style_id")["customer_id"].nunique()
    styles = styles.join(quality.rename("quality_units")).join(claim_units.rename("claim_units")).join(link).fillna(0)
    for column in ("unique_returners", "quality_units", "claim_units", "claim_lines", "linked_claim_lines", "linked_claimers"):
        styles[column] = styles[column].astype(int)
    requested = styles["requested_units"].where(styles["requested_units"] > 0)
    styles["raw_return_rate"] = styles["requested_units"] / styles["purchased_units"]
    prior = styles["category"].map(reference.category_rate) if reference else np.nan
    styles["shrunk_return_rate"] = (styles["requested_units"] + SHRINKAGE * prior) / (styles["purchased_units"] + SHRINKAGE)
    styles["damage_share"] = styles["quality_units"] / requested
    styles["claim_share"] = styles["claim_units"] / requested
    styles["linked_claim_share"] = styles["linked_claim_lines"] / styles["claim_lines"].where(styles["claim_lines"] > 0)
    styles["quality_signal"] = styles["damage_share"] >= QUALITY_DAMAGE_SHARE
    styles["targeting_signal"] = (styles["linked_claimers"] >= TARGETING_LINKED_CLAIMERS) & \
                                 (styles["linked_claim_share"] >= TARGETING_LINKED_SHARE)
    supported = styles["mature_sale_lines"] >= STYLE_SUPPORT
    styles["state"] = np.select(
        [~supported, (styles["requested_units"] == 0) & (styles["claim_lines"] == 0),
         styles["quality_signal"] & styles["targeting_signal"], styles["quality_signal"], styles["targeting_signal"]],
        ["insufficient_support", "no_return_evidence", "mixed_or_uncertain", "quality", "targeting"], default="no_elevated_signal")
    styles.loc[~supported, ["damage_share", "claim_share", "linked_claim_share"]] = np.nan
    styles.loc[~supported, ["quality_signal", "targeting_signal"]] = False

    skus = mature.groupby("sku").agg(style_id=("style_id", "first"), mature_sale_lines=("sku", "size"),
                                     purchased_units=("quantity", "sum"), requested_units=("requested_units", "sum"))
    skus["support_status"] = np.select([skus["mature_sale_lines"] < STYLE_SUPPORT, skus["requested_units"] == 0],
                                       ["insufficient_support", "no_return_evidence"], default="supported")
    return styles.reset_index(), skus.reset_index()


# ------------------------------------------------------------------ wardrobing indicator
def wardrobing_indicator(features: pd.DataFrame, requests: pd.DataFrame, reference: Reference | None) -> pd.DataFrame:
    """Image-free behavioural indicator of temporary use. It cannot establish wear and never enters the model score."""
    out = features[["customer_id", "median_window_ratio", "occasion_return_share", "discretionary_share", "bracketing_share"]].copy()
    if reference is not None and len(requests):
        median = requests["category"].map(reference.latency_median).astype(float)
        iqr = requests["category"].map(reference.latency_iqr).astype(float)
        z = (requests["capped_days"] - median) / np.maximum(1.0, iqr)
        latency = pd.DataFrame({"customer_id": requests["customer_id"], "z": z, "known": median.notna() & iqr.notna()})
        per_customer = latency.groupby("customer_id").agg(latency_z=("z", "mean"), baseline_known=("known", "all"))
        out = out.merge(per_customer, on="customer_id", how="left")
        out.loc[out["baseline_known"] == False, "latency_z"] = np.nan          # noqa: E712  a missing baseline is not a zero
    else:
        out["latency_z"] = np.nan
    has_requests = out["customer_id"].isin(requests["customer_id"])
    fired = pd.DataFrame({
        "latency_z": out["latency_z"] >= 1,
        "median_window_ratio": out["median_window_ratio"] >= 0.75,
        "occasion_return_share": out["occasion_return_share"] >= 0.5,
        "discretionary_share": out["discretionary_share"] >= 0.5,
        "bracketing_share": out["bracketing_share"] < 0.1,
    })
    complete = out[list(WARDROBING_POINTS)].notna().all(axis=1)
    score = sum(fired[name].astype(int) * points for name, points in WARDROBING_POINTS.items())
    timing = fired[list(TIMING_SIGNALS)].any(axis=1)
    status = np.select([~has_requests, ~complete, timing & (score >= WARDROBING_ELEVATED), timing & (score >= WARDROBING_POSSIBLE)],
                       ["insufficient_evidence", "incomplete", "elevated", "possible"], default="no_elevated_signal")
    out["status"] = status
    out["indicator_score"] = score.where(has_requests & complete).astype("Int64")
    for name in WARDROBING_POINTS:
        out["fired_" + name] = (fired[name] & has_requests & complete).to_numpy()
    return out
