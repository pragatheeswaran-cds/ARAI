"""Feature engineering and explanatory evidence (final-spec component 06).

Everything here reads the seven operational tables only. No private truth, persona, target or identifier
value enters a feature; identifiers are used for equality alone. One row per customer and world.

Outputs:
- the ordered model features of contracts/features.yaml,
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

from arai import contract
from arai.paths import SPEC_ROOT

# reason-code groups and the eligibility minimum come from the contracts, never from a second copy here
CLAIM_CODES = contract.reason_group("transaction_claim")
COMPLAINT_CODES = contract.reason_group("item_complaint_customer")
QUALITY_CODES = contract.reason_group("item_complaint_sku_quality")
DISCRETIONARY_CODES = contract.reason_group("discretionary")
IDENTIFIERS = ("address_id", "device_id", "payment_id")
LINE_KEY = ["order_id", "order_line_no"]

ELIGIBLE_MIN_LINES = contract.eligibility_min_lines()
SHRINKAGE = 20                  # prior strength of the two-level expectation
OVERDISPERSION_CAP = 4
FANOUT_CAP = 25
LINK_DAYS = 7
WINDOW_RATIO_CAP = 2.0
STYLE_SUPPORT = 20              # mature sale lines a style or SKU needs before evidence is shown
QUALITY_DAMAGE_SHARE = 0.30
TARGETING_LINKED_CLAIMERS = 3
TARGETING_LINKED_SHARE = 0.075
# a late return: an item return requested in the last quarter of its return window, and still inside it
LATE_FROM, LATE_TO = 0.75, 1.0
# wardrobing: integer points, never floating point (decimal weights miss the band boundaries)
WARDROBING_POINTS = {"repeat_late_returns": 50, "late_return": 25, "late_occasion_return": 15, "late_return_share": 10}
WARDROBING_ELEVATED, WARDROBING_POSSIBLE = 75, 35
WARDROBING_SUPPORT = ["item_return_lines", "late_return_lines", "late_occasion_return_lines"]


def _contract(spec_root=None) -> dict:
    return yaml.safe_load(((spec_root or SPEC_ROOT) / "contracts" / "features.yaml").read_text(encoding="utf-8"))


def feature_order(spec_root=None) -> list:
    """The ordered model features, read from the contract so code and contract cannot drift apart."""
    return [f["name"] for f in _contract(spec_root)["ordered_features"]]


def evidence_features(spec_root=None) -> list:
    """Measures computed with the features and shown to the analyst, but never given to a model."""
    return [f["name"] for f in _contract(spec_root)["evidence_only"]["features"]]


@dataclass
class Reference:
    """Statistics frozen from training worlds: the fallback rate for a category with no peers in a snapshot."""
    category_rate: dict                  # category -> mature requested units / mature purchased units

    def to_dict(self) -> dict:
        return {"category_rate": self.category_rate}

    @classmethod
    def from_dict(cls, data: dict) -> "Reference":
        return cls(dict(data["category_rate"]))


@dataclass
class Graph:
    edges: pd.DataFrame                  # customer_a, customer_b, shared_types, shared_value_count, max_value_fanout
    neighbours: dict                     # customer_id -> set of supported neighbours
    fanout: dict                         # identifier column -> Series(value -> distinct accounts)
    dropped_values: int                  # identifier values removed for exceeding the fan-out cap


@dataclass
class FeatureResult:
    features: pd.DataFrame               # one row per customer: model features, evidence, eligibility, support counts
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
    requests["is_claim"] = requests["reason_code"].isin(CLAIM_CODES)
    requests["late_return"] = ~requests["is_claim"] & (requests["days"] >= 0) & \
        requests["days"].between(LATE_FROM * requests["return_window_days"], LATE_TO * requests["return_window_days"])
    requests["request_day"] = requests["requested_at"].dt.normalize()
    return lines, requests, cutoff


def fit_reference(worlds: list) -> Reference:
    """Frozen training statistics from (tables, cutoff) pairs. Training worlds only; never refit at inference."""
    mature = []
    for tables, cutoff in worlds:
        lines, _, _ = _prepare(tables, cutoff)
        mature.append(lines.loc[lines["mature"], ["category", "quantity", "requested_units"]])
    totals = pd.concat(mature).groupby("category")[["requested_units", "quantity"]].sum()
    return Reference(category_rate=(totals["requested_units"] / totals["quantity"]).to_dict())


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
    # late returns: item returns (never claims) requested in the last quarter of the window and still inside it
    item_returns = timed[~timed["is_claim"]]
    late = requests[requests["late_return"]]
    count = lambda part: part.groupby("customer_id").size().reindex(out.index, fill_value=0).astype(int)
    out["item_return_lines"] = count(item_returns)
    out["late_return_lines"] = count(late)
    out["late_occasion_return_lines"] = count(late[late["is_occasion_wear"] == 1])
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

    chosen = feature_order() + evidence_features()
    features = out[chosen].copy()                                     # model features first, then evidence-only link measures
    for name in WARDROBING_SUPPORT:                                   # support counts, unless the contract makes one a feature
        if name not in chosen:
            features[name] = out[name]
    features["eligible"] = features["mature_sale_lines"] >= ELIGIBLE_MIN_LINES
    features["mature_purchased_units"] = N.reindex(out.index, fill_value=0).astype(int)
    features["mature_requested_units"] = R.reindex(out.index, fill_value=0).astype(int)
    features["all_requested_units"] = units.astype(int)
    features["claim_lines"] = claims.groupby("customer_id").size().reindex(out.index, fill_value=0).astype(int)
    features["timed_return_lines"] = timed.groupby("customer_id").size().reindex(out.index, fill_value=0).astype(int)
    features["expected_units"] = E.reindex(out.index)
    features = features.reset_index()

    lines = lines.merge(mature[LINE_KEY + ["p_expected"]], on=LINE_KEY, how="left")
    styles, skus = style_evidence(lines, requests, claims, reference)
    wardrobing = wardrobing_indicator(out[WARDROBING_SUPPORT].reset_index())
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
def wardrobing_indicator(counts: pd.DataFrame) -> pd.DataFrame:
    """Image-free behavioural indicator of temporary use. It cannot establish wear and never enters the model score.

    Built on item returns requested in the last quarter of the return window: once is common, repeatedly is not.
    `counts` has customer_id, item_return_lines, late_return_lines and late_occasion_return_lines.
    """
    out = counts[["customer_id", *WARDROBING_SUPPORT]].copy()
    has_returns = out["item_return_lines"] > 0
    out["late_return_share"] = (out["late_return_lines"] / out["item_return_lines"].where(has_returns)).astype(float)
    fired = pd.DataFrame({
        "repeat_late_returns": out["late_return_lines"] >= 2,
        "late_return": out["late_return_lines"] >= 1,
        "late_occasion_return": out["late_occasion_return_lines"] >= 1,
        "late_return_share": out["late_return_share"] >= 0.5,
    })
    score = sum(fired[name].astype(int) * points for name, points in WARDROBING_POINTS.items())
    out["status"] = np.select([~has_returns, score >= WARDROBING_ELEVATED, score >= WARDROBING_POSSIBLE],
                              ["insufficient_evidence", "elevated", "possible"], default="no_elevated_signal")
    out["indicator_score"] = score.where(has_returns).astype("Int64")
    for name in WARDROBING_POINTS:
        out["fired_" + name] = (fired[name] & has_returns).to_numpy()
    return out
