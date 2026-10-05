"""Honest return requests and the shared rules that settle any request at the cutoff.

Honest events are generated first and reserve their units. Abuse is layered on afterwards from separate
random streams, so switching abuse off leaves every honest request untouched.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from arai.generator.context import DAY, Context
from arai.rng import keyed_uniform, stream
from arai.settings import beta_law

CLAIM_CODES = ("item_not_received", "wrong_item_sent", "missing_parts", "empty_package")
DEFECT_CODES = ("defective", "poor_quality", "not_as_described")
FIT_CODES = ("wrong_size", "didnt_fit")
DISCRETIONARY_CODES = ("didnt_suit", "changed_my_mind", "not_as_expected", "found_better_price",
                       "ordered_by_mistake", "late_delivery")
NO_ITEM_CODES = ("item_not_received", "empty_package")   # reason_code.requires_item_return = 0
# honest_cause_priority (generator-config): one resolved cause per unit, latent causes kept privately
FULFILMENT, DAMAGE, DEFECT, ORDINARY = "genuine_fulfilment_failure", "carrier_damage", "latent_defect", "ordinary_fit_preference"


def _logit(p):
    return np.log(p / (1.0 - p))


def address_multipliers(ctx: Context, addresses) -> dict:
    """Private per-address multiplier g = Z^2 (mean 1) on genuine fulfilment-failure rates."""
    return {a: float(stream(ctx.seed, a, "genuine_failure").standard_normal() ** 2) for a in addresses}


def product_truth_draws(ctx: Context):
    """Which styles are defect-prone and which SKUs have a fit issue. Redrawn per world; the catalog is fixed."""
    s, cat = ctx.s, ctx.catalog
    rng = stream(ctx.seed, "world", "product_truth")
    share = min(1.0, s.accepted["defect_style_share"] * s.overrides.get("defect_incidence_scale", 1.0))
    # an exact count (3 of 37 at 8%) so every world has defective-product buyers to evaluate against
    defect_prone = np.zeros(len(cat.styles), dtype=bool)
    defect_prone[rng.choice(len(cat.styles), size=max(1, int(round(share * len(cat.styles)))), replace=False)] = True
    fit_issue = rng.random(len(cat.sku_master)) < s.impl["fit_issue_sku_share"]
    return defect_prone, fit_issue


def time_of_day(ctx: Context, u: np.ndarray) -> np.ndarray:
    lo, hi = ctx.s.impl["request_hours"]
    return (lo * 3600 + u * (hi - lo) * 3600).astype(int) * np.timedelta64(1, "s")


def claim_delay(ctx: Context, gamma):
    """Days from delivery to a transaction claim: one law for genuine, solo deceptive and coordinated claims."""
    return np.minimum(ctx.s.amendment3["claim_latency"]["truncate_after_days"], np.rint(gamma)).astype(int)


def delivery_incidents(ctx: Context, units: pd.DataFrame) -> np.ndarray:
    """Units lost in a delivery incident: an address has a bad 14-day block and whole parcels to it go missing."""
    cfg = ctx.s.amendment3["delivery_incidents"]
    delivered = units["delivered_date"].to_numpy().astype("datetime64[D]")
    block = ((delivered - ctx.history_start) / DAY).astype(int) // cfg["block_days"]
    block_key = units["address_id"].to_numpy(dtype=object) + "|" + block.astype(str).astype(object)
    bad_block = {k: keyed_uniform(ctx.seed, k, "delivery_incident") < cfg["probability_per_address_block"]
                 for k in set(block_key)}
    in_bad_block = np.array([bad_block[k] for k in block_key], dtype=bool)
    orders = units["order_id"].to_numpy(dtype=object)
    lost = {o: keyed_uniform(ctx.seed, o, "incident_parcel") < cfg["parcel_failure_probability"]
            for o in set(orders[in_bad_block])}
    return in_bad_block & np.array([lost.get(o, False) for o in orders], dtype=bool)


def build_honest_events(ctx: Context, profiles: pd.DataFrame, units: pd.DataFrame, defect_prone, fit_issue, g_address,
                        purpose: str = "honest"):
    """Honest requests on delivered units. Returns (unit facts, request events).

    `purpose` names the random streams: base units use "honest"; the unclaimed units of campaign orders use
    their own, so adding the abuse layer never changes a base draw.
    """
    s, seed, cat = ctx.s, ctx.seed, ctx.catalog
    accepted, defaults, impl = s.accepted, s.defaults, s.impl
    latency_law = s.amendment3["claim_latency"]
    n = len(units)
    u = np.empty((n, 14))
    noise = np.empty(n)
    beta = np.empty(n)
    gamma = np.empty(n)
    for cust, rows in units.groupby("cust", sort=True).indices.items():
        rng = stream(seed, ctx.customer_ids[cust], purpose)
        u[rows] = rng.random((len(rows), 14))
        noise[rows] = rng.normal(size=len(rows))
        beta[rows] = rng.beta(2.0, 5.0, len(rows))                 # generator-config: request_latency.honest
        gamma[rows] = rng.gamma(latency_law["shape"], latency_law["scale_days"], len(rows))

    cust = units["cust"].to_numpy()
    sku = units["sku_idx"].to_numpy()
    style = units["style_idx"].to_numpy()
    window = units["window"].to_numpy()
    category = cat.styles["category"].to_numpy(dtype=object)[style]

    p_defect = np.where(defect_prone[style], defaults["defect_unit_probability"]["defect_prone_style"],
                        defaults["defect_unit_probability"]["ordinary_style"])
    defective = u[:, 0] < p_defect
    # independent failures per unit, scaled by the address multiplier; parcel-level incidents on top
    claim_rates = np.array([accepted["genuine_claim_rates"][c] for c in CLAIM_CODES])
    claim_rates[CLAIM_CODES.index("item_not_received")] = s.amendment3["delivery_incidents"]["independent_item_not_received_rate"]
    g = np.array([g_address[a] for a in units["address_id"].to_numpy()])
    incident = delivery_incidents(ctx, units)
    independent = u[:, 1] < np.minimum(1.0, claim_rates.sum() * g)
    independent_code = np.array(CLAIM_CODES, dtype=object)[np.minimum(
        np.searchsorted(np.cumsum(claim_rates / claim_rates.sum()), u[:, 2], side="right"), len(CLAIM_CODES) - 1)]
    # household co-orders travel with the order they follow: same address, same fate
    order_id = units["order_id"].to_numpy(dtype=object)
    address = units["address_id"].to_numpy(dtype=object)
    not_received = incident | (independent & (independent_code == "item_not_received"))
    lost_orders = set(order_id[not_received])
    address_of = dict(zip(order_id, address))
    source = units["co_source"].to_numpy(dtype=object)
    probability = s.amendment3["household_co_orders"]["shared_fate_probability"]
    shared = np.array([src is not None and src in lost_orders and address_of.get(src) == adr
                       and keyed_uniform(seed, oid, "shared_fate") < probability
                       for src, adr, oid in zip(source, address, order_id)], dtype=bool)
    incident = incident | shared
    fulfilment = incident | independent
    fulfilment_code = np.where(incident, "item_not_received", independent_code).astype(object)
    damage = u[:, 3] < accepted["carrier_damage_rate"]

    logit = defaults["ordinary_logit"]
    propensity = np.clip(profiles["target_return_propensity"].to_numpy()[cust], 0.001, 0.999)
    category_rate = np.array([defaults["ordinary_category_rate"][c] for c in category])
    score = (_logit(propensity) + _logit(category_rate) - _logit(0.20)
             + logit["bracketing_increment"] * units["bracketed"].to_numpy()
             + logit["fit_issue_increment"] * fit_issue[sku]
             + logit["defective_unit_increment"] * defective
             + logit["noise_normal_sd"] * noise)
    ordinary = u[:, 4] < 1.0 / (1.0 + np.exp(-score))

    cause = np.select([fulfilment, damage, ordinary & defective, ordinary], [FULFILMENT, DAMAGE, DEFECT, ORDINARY], default="")
    facts = units[["order_id", "order_line_no", "unit_index", "cust", "style_idx", "delivered_date", "layer"]].assign(
        received_defective_unit=defective,
        genuine_fulfilment_cause=np.where(fulfilment, fulfilment_code, None),
        carrier_damage=damage, delivery_incident=incident, honest_cause=cause)

    # one request per (sale line, cause); the first unit's draws describe the request
    returned = np.flatnonzero(cause != "")
    key = pd.DataFrame({"order_id": units["order_id"].to_numpy()[returned],
                        "order_line_no": units["order_line_no"].to_numpy()[returned], "cause": cause[returned],
                        "row": returned, "unit_index": units["unit_index"].to_numpy()[returned]})
    grouped = key.groupby(["order_id", "order_line_no", "cause"], sort=False)
    first = grouped["row"].first().to_numpy()
    unit_lists = grouped["unit_index"].agg(list).to_numpy()

    e_cause = cause[first]
    fit_first = np.where(fit_issue[sku[first]], u[first, 5] < impl["fit_issue_fit_reason_probability"], u[first, 5] < 0.5)
    fit_code = np.array(FIT_CODES, dtype=object)[(u[first, 6] * len(FIT_CODES)).astype(int)]
    discretionary_code = np.array(DISCRETIONARY_CODES, dtype=object)[(u[first, 6] * len(DISCRETIONARY_CODES)).astype(int)]
    defect_code = np.array(DEFECT_CODES, dtype=object)[(u[first, 6] * len(DEFECT_CODES)).astype(int)]
    reason = np.select([e_cause == FULFILMENT, e_cause == DAMAGE, e_cause == DEFECT, fit_first],
                       [fulfilment_code[first], "damaged", defect_code, fit_code], default=discretionary_code).astype(object)

    e_window = window[first]
    # amendment_3_0: an honest item return follows the late law with a probability that depends on the account's habit
    timing = s.realism["honest_return_timing"]
    late_a, late_b = beta_law(timing["late_law"])
    u_late, beta_late = np.empty(n), np.empty(n)
    for c, rows in units.groupby("cust", sort=True).indices.items():
        extra = stream(seed, ctx.customer_ids[c], purpose + ":return_timing")       # its own stream: no existing draw moves
        u_late[rows] = extra.random(len(rows))
        beta_late[rows] = extra.beta(late_a, late_b, len(rows))
    habit = profiles["late_returner"].to_numpy()[cust[first]]
    by_late_law = u_late[first] < np.where(habit, timing["late_returner_probability"], timing["background_probability"])
    fraction = np.where(by_late_law, beta_late[first], beta[first])
    latency = np.where(e_cause == FULFILMENT, claim_delay(ctx, gamma[first]), np.rint(fraction * e_window).astype(int))
    # a capped share of honest item returns arrives after the window and is rejected (max_late_request_share)
    item_return = np.flatnonzero(e_cause != FULFILMENT)
    late = np.zeros(len(first), dtype=bool)
    late_rng = stream(seed, "world", "late_requests:" + purpose)
    n_late = int(np.floor(accepted["max_late_request_share"] * len(item_return)))
    late[late_rng.permutation(item_return)[:n_late]] = True
    latency = np.where(late, e_window + 1 + (u[first, 8] * e_window).astype(int), latency)

    events = pd.DataFrame({
        "event_id": [f"H|{o}|{l}|{c}" for o, l, c in zip(units["order_id"].to_numpy()[first],
                                                       units["order_line_no"].to_numpy()[first], e_cause)],
        "cust": cust[first], "order_id": units["order_id"].to_numpy()[first],
        "order_line_no": units["order_line_no"].to_numpy()[first], "unit_indices": unit_lists,
        "quantity": [len(x) for x in unit_lists], "sku_idx": sku[first], "style_idx": style[first],
        "line_quantity": units["quantity"].to_numpy()[first], "line_total_p": units["total_p"].to_numpy()[first],
        "window": e_window, "delivered_date": units["delivered_date"].to_numpy()[first].astype("datetime64[D]"),
        "kind": "honest", "cause": e_cause, "reason_code": reason, "latency_days": latency, "late": late,
        "u_time": u[first, 9], "u_reject": u[first, 10], "u_refund": u[first, 11], "u_decision": u[first, 12],
        "withdraw_planned": (e_cause != FULFILMENT) & (u[first, 13] < accepted["honest_withdraw_probability"]),
        "u_withdraw_day": u[first, 8],
    })
    return facts, settle(ctx, events)


def settle(ctx: Context, events: pd.DataFrame) -> pd.DataFrame:
    """Request time and the status, refund and receipt each request shows at the cutoff.

    Honest and abusive requests use identical rules, so status and timing cannot reveal intent. Late requests
    are rejected, in-window requests are rejected with one shared probability, and refunds for item returns
    never precede receipt.
    """
    accepted, impl = ctx.s.accepted, ctx.s.impl
    delivered = events["delivered_date"].to_numpy().astype("datetime64[D]")
    request_date = delivered + events["latency_days"].to_numpy() * DAY
    requested_at = request_date.astype("datetime64[s]") + time_of_day(ctx, events["u_time"].to_numpy())
    visible = requested_at <= ctx.cutoff_ts

    needs_item = ~np.isin(events["reason_code"].to_numpy(dtype=object), NO_ITEM_CODES)
    w_lo, w_hi = impl["withdraw_days"]
    withdrawn = events["withdraw_planned"].to_numpy() & (
        request_date + (w_lo + (events["u_withdraw_day"].to_numpy() * (w_hi - w_lo + 1)).astype(int)) * DAY <= ctx.snapshot)
    d_lo, d_hi = impl["decision_days"]
    decision = request_date + (d_lo + (events["u_decision"].to_numpy() * (d_hi - d_lo + 1)).astype(int)) * DAY
    rejected = (events["late"].to_numpy() | (events["u_reject"].to_numpy() < accepted["in_window_rejection_probability"])) \
        & (decision <= ctx.snapshot)
    i_lo, i_hi = accepted["item_refund_days"]
    n_lo, n_hi = accepted["no_item_refund_days"]
    u_refund = events["u_refund"].to_numpy()
    refund_days = np.where(needs_item, i_lo + (u_refund * (i_hi - i_lo + 1)).astype(int),
                           n_lo + (u_refund * (n_hi - n_lo + 1)).astype(int))
    refunded = request_date + refund_days * DAY <= ctx.snapshot

    will_reject = events["late"].to_numpy() | (events["u_reject"].to_numpy() < accepted["in_window_rejection_probability"])
    status = np.select([withdrawn, rejected, refunded & ~will_reject], ["withdrawn", "rejected", "refunded"],
                       default="pending").astype(object)
    received = needs_item & ~withdrawn & ~will_reject & (request_date + impl["return_receipt_days"] * DAY <= ctx.snapshot)
    refund = np.where(status == "refunded",
                      events["line_total_p"].to_numpy() * events["quantity"].to_numpy() // events["line_quantity"].to_numpy(), 0)
    return events.assign(request_date=request_date, requested_at=requested_at, visible=visible, needs_item=needs_item,
                         line_status=status, refund_p=refund,
                         return_received_flag=np.where(needs_item, received.astype(float), np.nan))
