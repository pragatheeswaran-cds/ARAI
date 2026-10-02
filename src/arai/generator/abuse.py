"""The abuse layer: ring campaigns (with abuse-layer campaign orders) and solo abusive actions.

Everything here draws from its own keyed streams and only ever uses units that honest requests left
unreserved, so disabling abuse removes these events and nothing else.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from arai.generator.context import DAY, Context
from arai.generator.relationships import Relationships
from arai.generator.returns import DEFECT_CODES, DISCRETIONARY_CODES, FIT_CODES, settle
from arai.generator.sales import _pick, apply_fulfilment, price_lines
from arai.rng import stream, token

NONRECEIPT, CONTENTS, TEMPORARY = "deceptive_nonreceipt_claim", "deceptive_contents_claim", "temporary_use_return"
CONTENTS_CODES = ("wrong_item_sent", "missing_parts", "empty_package")
FALSE_QUALITY_CODES = ("poor_quality", "not_as_described")
EVENT_COLUMNS = ["event_id", "cust", "order_id", "order_line_no", "unit_indices", "quantity", "sku_idx", "style_idx",
                 "line_quantity", "line_total_p", "window", "delivered_date", "kind", "cause", "reason_code",
                 "latency_days", "late", "u_time", "u_reject", "u_refund", "u_decision", "withdraw_planned", "u_withdraw_day"]


def _claim(u_type: float, u_code: float):
    """Nonreceipt and contents claims are equally likely; contents codes are uniform (claim_action_selection)."""
    if u_type < 0.5:
        return NONRECEIPT, "item_not_received"
    return CONTENTS, CONTENTS_CODES[int(u_code * len(CONTENTS_CODES))]


def _event(action_id, cust, unit, action_type, reason, latency, draws) -> dict:
    return {"event_id": action_id, "cust": cust, "order_id": unit["order_id"], "order_line_no": unit["order_line_no"],
            "unit_indices": [int(unit["unit_index"])], "quantity": 1, "sku_idx": unit["sku_idx"], "style_idx": unit["style_idx"],
            "line_quantity": unit["quantity"], "line_total_p": unit["total_p"], "window": unit["window"],
            "delivered_date": unit["delivered_date"], "kind": "abuse", "cause": action_type, "reason_code": reason,
            "latency_days": int(latency), "late": False, "u_time": draws[0], "u_reject": draws[1], "u_refund": draws[2],
            "u_decision": draws[3], "withdraw_planned": False, "u_withdraw_day": 0.0}


def choose_hot_list(ctx: Context) -> np.ndarray:
    """The world's private list of target styles, weighted by median catalog price."""
    styles, settings = ctx.catalog.styles, ctx.s.amendment["campaigns"]
    eligible = np.flatnonzero(styles["first_launch"].to_numpy().astype("datetime64[D]") <= ctx.history_start)
    weights = styles["median_price"].to_numpy()[eligible]
    size = min(settings["world_hot_list_size"], len(eligible))
    return np.sort(stream(ctx.seed, "world", "hot_list").choice(eligible, size=size, replace=False, p=weights / weights.sum()))


def run_campaigns(ctx: Context, profiles: pd.DataFrame, rel: Relationships, units: pd.DataFrame,
                  reserved: np.ndarray, hot_list: np.ndarray):
    """Ring campaigns. Returns (campaign truth, actions, campaign orders, campaign lines, abusive events)."""
    s, seed, cat, world = ctx.s, ctx.seed, ctx.catalog, ctx.world_id
    cfg, accepted = s.amendment["campaigns"], s.accepted
    gamma = s.defaults["campaign_gamma"]
    claim_capable = profiles["claim_propensity"].to_numpy()
    signup = profiles["signup_date"].to_numpy().astype("datetime64[D]")
    price = cat.styles["median_price"].to_numpy()
    rows_of = units.groupby("cust", sort=True).indices
    unit_style = units["style_idx"].to_numpy()
    unit_delivered = units["delivered_date"].to_numpy().astype("datetime64[D]")
    s_lo, s_hi = cfg["group_target_styles"]
    c_lo, c_hi = cfg["group_campaign_dates"]
    o_lo, o_hi = cfg["campaign_order"]["order_date_offset_days"]
    d_lo, d_hi = accepted["dispatch_days"]
    r_lo, r_hi = accepted["carrier_regular_days"]
    t_lo, t_hi = accepted["carrier_tail_days"]
    channels = list(s.amendment["emitted_constants"]["order_channel"])
    channel_p = list(s.amendment["emitted_constants"]["order_channel"].values())

    campaigns, attempts = [], []
    for group_id, group in rel.groups.items():
        capable = [m for m in group["members"] if claim_capable[m]]
        if group["type"] != "coordination" or not capable:
            continue
        rng = stream(seed, group_id, "campaign")
        # the ring forms when its last claim-capable member signs up; campaigns fall between then and the snapshot
        first_day = int((max(ctx.history_start, signup[capable].max()) - ctx.history_start) / DAY)
        n_styles = min(int(rng.integers(s_lo, s_hi + 1)), len(hot_list))
        weights = price[hot_list] / price[hot_list].sum()
        group_styles = rng.choice(hot_list, size=n_styles, replace=False, p=weights)
        open_days = len(ctx.history) - first_day
        days = first_day + np.sort(rng.choice(open_days, size=min(int(rng.integers(c_lo, c_hi + 1)), open_days), replace=False))
        for j, day in enumerate(days):
            style = int(group_styles[rng.integers(len(group_styles))])
            campaign_date = ctx.history[day]
            campaign_id = f"{world}-K{token(seed, group_id, 'campaign:' + str(j))}"
            campaigns.append((world, campaign_id, group_id, cat.styles["style_id"].iloc[style], campaign_date))
            for member in capable:
                cid = ctx.customer_ids[member]
                member_rng = stream(seed, cid, "campaign:" + campaign_id)
                u = member_rng.random(16)
                if u[0] >= cfg["participant_probability_per_date"]:
                    continue
                action_type, reason = _claim(u[1], u[2])
                attempt = {"action_id": f"{world}-X{token(seed, cid, 'action:' + campaign_id)}", "cust": member,
                           "action_type": action_type, "reason": reason, "campaign_id": campaign_id, "group_id": group_id,
                           "style_idx": style, "draws": u[3:7], "unit": None, "order": None, "reason_uncompleted": None,
                           "delay": min(int(gamma["truncate_after_days"]),
                                        int(np.rint(member_rng.gamma(gamma["shape"], gamma["scale_days"]))))}
                rows = rows_of.get(member, np.array([], dtype=int))
                reusable = rows[(unit_style[rows] == style) & ~reserved[rows]
                                & (unit_delivered[rows] >= campaign_date - cfg["reuse_window_days_before_campaign_date"] * DAY)
                                & (unit_delivered[rows] <= campaign_date)]
                if len(reusable):
                    row = int(reusable[np.argsort(unit_delivered[reusable], kind="stable")[0]])
                    reserved[row] = True
                    attempt.update(source="reused_purchase", unit=units.iloc[row])
                else:
                    attempt["source"] = "campaign_order"
                    order_date = campaign_date + (o_lo + int(u[7] * (o_hi - o_lo + 1))) * DAY
                    variants = np.flatnonzero((cat.sku_style == style) & (cat.sku_launch <= order_date))
                    if order_date < signup[member]:
                        attempt["reason_uncompleted"] = "pre_signup"
                    elif order_date > ctx.snapshot:
                        attempt["reason_uncompleted"] = "after_cutoff"
                    elif not len(variants):
                        attempt["reason_uncompleted"] = "pre_launch"
                    else:
                        sku = int(variants[int(u[8] * len(variants))])
                        festive = bool(ctx.festive_multiplier[int((order_date - ctx.history_start) / DAY)] > 0)
                        discount, total = price_lines(ctx, np.array([sku]), np.array([1]), np.array([festive]),
                                                      np.array([u[9]]), np.array([u[10]]))
                        dispatch = d_lo + int(u[11] * (d_hi - d_lo + 1))
                        tail = u[12] < accepted["carrier_tail_probability"]
                        transit = (t_lo + int(u[13] * (t_hi - t_lo + 1))) if tail else (r_lo + int(u[13] * (r_hi - r_lo + 1)))
                        used = rel.draw_identifiers(stream(seed, cid, "campaign_identifiers:" + campaign_id), member, 1)
                        cancel = bool(member_rng.random() < accepted["cancel_probability"])
                        attempt["order"] = {
                            "order_id": f"{world}-O{token(seed, cid, 'campaign_order:' + campaign_id)}", "cust": member,
                            "order_date": order_date, "festive": festive, "channel": channels[int(_pick(np.array([u[14]]), channel_p)[0])],
                            "address_id": used["address"][0], "device_id": used["device"][0], "payment_id": used["payment"][0],
                            "dispatch_days": dispatch, "transit_days": transit,
                            "lost": bool(u[15] < accepted["loss_probability_of_shipped"]), "layer": "campaign",
                            "campaign_id": campaign_id, "seq": -1,
                            "line": {"order_line_no": 1, "sku_idx": sku, "style_idx": style, "quantity": 1,
                                     "unit_price_p": int(cat.sku_price_paise[sku]), "discount_p": int(discount[0]),
                                     "total_p": int(total[0]), "window": int(cat.sku_window[sku]), "bracketed": False,
                                     "cancel": cancel, "cancel_offset": int(member_rng.integers(0, dispatch + 1))}}
                attempts.append(attempt)

    campaign_truth = pd.DataFrame(campaigns, columns=["world_id", "campaign_id", "coordination_group_id", "target_style_id", "campaign_date"])
    placed = [a for a in attempts if a["order"] is not None]
    order_columns = ["order_id", "cust", "order_date", "festive", "channel", "address_id", "device_id", "payment_id",
                     "dispatch_days", "transit_days", "lost", "layer", "campaign_id", "seq"]
    c_orders = pd.DataFrame([{k: a["order"][k] for k in order_columns} for a in placed], columns=order_columns)
    c_lines = pd.DataFrame([dict(a["order"]["line"], order_id=a["order"]["order_id"], cust=a["cust"],
                                 order_date=a["order"]["order_date"], dispatch_days=a["order"]["dispatch_days"],
                                 transit_days=a["order"]["transit_days"], lost=a["order"]["lost"],
                                 address_id=a["order"]["address_id"], layer="campaign") for a in placed])
    if len(c_lines):
        c_lines = apply_fulfilment(ctx, c_lines)
        for a, (_, line) in zip(placed, c_lines.iterrows()):
            if line["line_status"] == "delivered":
                a["unit"] = pd.Series({"order_id": line["order_id"], "order_line_no": 1, "unit_index": 1,
                                       "sku_idx": line["sku_idx"], "style_idx": line["style_idx"], "quantity": 1,
                                       "total_p": line["total_p"], "window": line["window"],
                                       "delivered_date": line["delivered_date"]})
            elif line["line_status"] == "cancelled":
                a["reason_uncompleted"] = "cancelled"
            else:
                a["reason_uncompleted"] = "lost_in_transit" if line["lost"] else "undelivered_by_cutoff"

    events = [_event(a["action_id"], a["cust"], a["unit"], a["action_type"], a["reason"], a["delay"], a["draws"])
              for a in attempts if a["unit"] is not None]
    events = settle(ctx, pd.DataFrame(events, columns=EVENT_COLUMNS)) if events else pd.DataFrame(columns=EVENT_COLUMNS)
    visible = dict(zip(events["event_id"], events["visible"])) if len(events) else {}
    actions = []
    for a in attempts:
        completed = bool(visible.get(a["action_id"], False))
        if a["unit"] is not None and not completed:
            a["reason_uncompleted"] = "claim_after_cutoff"
        unit = a["unit"]
        actions.append({"action_id": a["action_id"], "cust": a["cust"], "action_type": a["action_type"],
                        "order_id": None if unit is None else unit["order_id"],
                        "order_line_no": None if unit is None else int(unit["order_line_no"]),
                        "allocated_unit_indices": [] if unit is None else [int(unit["unit_index"])],
                        "completed_action": completed, "coordination_group_id": a["group_id"], "campaign_id": a["campaign_id"],
                        "claim_source": a["source"], "uncompleted_reason": None if completed else a["reason_uncompleted"],
                        "style_idx": a["style_idx"]})
    return campaign_truth, actions, c_orders, c_lines, events


def run_solo_actions(ctx: Context, profiles: pd.DataFrame, orders: pd.DataFrame, units: pd.DataFrame, reserved: np.ndarray):
    """Solo abusive actions on base-layer delivered orders. Returns (actions, abusive events)."""
    s, seed, cat, world = ctx.s, ctx.seed, ctx.catalog, ctx.world_id
    weighting = s.amendment["temporary_use_occasion_weighting"]
    fit_share = s.accepted["temp_reason_mix"]["fit_or_discretionary"]
    rates = {"claim": profiles["claim_action_rate"].to_numpy(), "temporary_use": profiles["temporary_use_action_rate"].to_numpy()}
    capable = {"claim": profiles["claim_propensity"].to_numpy(), "temporary_use": profiles["temporary_use_propensity"].to_numpy()}
    unit_rows = units.groupby("order_id", sort=False).indices
    occasion = cat.sku_occasion[units["sku_idx"].to_numpy()]
    window = units["window"].to_numpy()
    base_orders = orders[orders["layer"] == "base"]
    orders_of = {c: g["order_id"].to_numpy() for c, g in base_orders.groupby("cust", sort=True)}

    actions, events = [], []

    def record(action_id, cust, action_type, row, reason_uncompleted):
        unit = None if row is None else units.iloc[row]
        actions.append({"action_id": action_id, "cust": cust, "action_type": action_type,
                        "order_id": None if unit is None else unit["order_id"],
                        "order_line_no": None if unit is None else int(unit["order_line_no"]),
                        "allocated_unit_indices": [] if unit is None else [int(unit["unit_index"])],
                        "completed_action": False, "coordination_group_id": None, "campaign_id": None,
                        "claim_source": None, "uncompleted_reason": reason_uncompleted, "style_idx": None})

    for cust in np.flatnonzero(capable["claim"] | capable["temporary_use"]):
        cid = ctx.customer_ids[cust]
        relevant = [o for o in orders_of.get(cust, []) if o in unit_rows]     # orders with a delivered unit
        proposals = []
        for family in ("claim", "temporary_use"):
            if not capable[family][cust] or not relevant:
                continue
            rng = stream(seed, cid, "solo:" + family)
            u = rng.random((len(relevant), 9))
            beta = rng.beta(5.0, 2.0, len(relevant))                         # request_latency.temporary_use
            for k, order_id in enumerate(relevant):
                rows = unit_rows[order_id]
                free = rows[~reserved[rows]]
                pool, probability = free, rates[family][cust]
                if family == "temporary_use":
                    occasion_free = free[occasion[free]]
                    multiplier = weighting["occasion_order_multiplier"] if len(occasion_free) else weighting["other_order_multiplier"]
                    probability = min(1.0, probability * multiplier)
                    pool = occasion_free if len(occasion_free) else free
                if u[k, 0] >= probability:
                    continue
                action_id = f"{world}-X{token(seed, cid, 'action:' + family + ':' + order_id)}"
                action_type, reason = _claim(u[k, 2], u[k, 3]) if family == "claim" else (TEMPORARY, None)
                if not len(pool):
                    record(action_id, cust, action_type, None, "no_unreserved_unit")
                    continue
                row = int(pool[int(u[k, 1] * len(pool))])
                if family == "claim":
                    latency = int(u[k, 4] * (min(10, window[row]) + 1))      # request_latency.solo_claim
                else:
                    if u[k, 2] < fit_share:
                        codes = FIT_CODES if u[k, 3] < 0.5 else DISCRETIONARY_CODES
                    else:
                        codes = FALSE_QUALITY_CODES
                    reason = codes[int(u[k, 4] * len(codes))]
                    latency = int(np.rint(beta[k] * window[row]))
                proposals.append((row, action_id, action_type, reason, latency, u[k, 5:9]))

        # two families wanting the same unit: keyed random winner, no replacement unit for the loser
        by_row = {}
        for proposal in proposals:
            by_row.setdefault(proposal[0], []).append(proposal)
        for row, contenders in by_row.items():
            winner = 0
            if len(contenders) > 1:
                winner = int(stream(seed, contenders[0][1], "unit_conflict").random() * len(contenders))
            for index, (_, action_id, action_type, reason, latency, draws) in enumerate(contenders):
                if index != winner:
                    record(action_id, cust, action_type, None, "unit_conflict")
                    continue
                reserved[row] = True
                record(action_id, cust, action_type, row, None)
                events.append(_event(action_id, cust, units.iloc[row], action_type, reason, latency, draws))

    events = settle(ctx, pd.DataFrame(events, columns=EVENT_COLUMNS)) if events else pd.DataFrame(columns=EVENT_COLUMNS)
    visible = dict(zip(events["event_id"], events["visible"])) if len(events) else {}
    for action in actions:
        if action["order_id"] is not None:
            action["completed_action"] = bool(visible[action["action_id"]])
            action["uncompleted_reason"] = None if action["completed_action"] else "request_after_cutoff"
    return actions, events
