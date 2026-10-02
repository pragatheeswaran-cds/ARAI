"""The abuse layer: ring campaigns (with abuse-layer campaign orders) and solo abusive actions.

Everything here draws from its own keyed streams and only ever uses units that honest requests left
unreserved, so disabling abuse removes these events and nothing else. Abusive requests are built to look
like honest ones in everything but behaviour: the same claim-timing law and reason-code mix, ordinary
baskets with the target line anywhere in them, one order a day, and non-receipt claims that can cover a
whole parcel just as a genuinely lost parcel does.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from arai.generator.context import DAY, Context
from arai.generator.relationships import Relationships
from arai.generator.returns import DISCRETIONARY_CODES, FIT_CODES, claim_delay, settle
from arai.generator.sales import _pick, apply_fulfilment, draw_basket
from arai.rng import stream, token

NONRECEIPT, CONTENTS, TEMPORARY = "deceptive_nonreceipt_claim", "deceptive_contents_claim", "temporary_use_return"
FALSE_QUALITY_CODES = ("poor_quality", "not_as_described")
EVENT_COLUMNS = ["event_id", "cust", "order_id", "order_line_no", "unit_indices", "quantity", "sku_idx", "style_idx",
                 "line_quantity", "line_total_p", "window", "delivered_date", "kind", "cause", "reason_code",
                 "latency_days", "late", "u_time", "u_reject", "u_refund", "u_decision", "withdraw_planned", "u_withdraw_day"]


def _claim(ctx: Context, u: float):
    """A deceptive claim's reason code, drawn with the mix honest claims show per order (amendment 1.4)."""
    mix = ctx.s.amendment4["deceptive_claims"]["reason_code_mix"]
    codes = list(mix)
    code = codes[min(int(np.searchsorted(np.cumsum(list(mix.values())), u, side="right")), len(codes) - 1)]
    return (NONRECEIPT if code == "item_not_received" else CONTENTS), code


def _companion(ctx: Context, action_id: str, line_no: int):
    """Identifier, claim delay and settlement draws of a whole-parcel claim's line on another sale line.

    Each line of a genuinely lost parcel is claimed with its own draws, so the lines of a deceptive
    whole-parcel claim are too.
    """
    companion_id = f"{action_id}-L{line_no}"
    rng = stream(ctx.seed, companion_id, "parcel_companion")
    law = ctx.s.amendment3["claim_latency"]
    return companion_id, int(claim_delay(ctx, rng.gamma(law["shape"], law["scale_days"]))), rng.random(4)


def _event(action_id, cust, line, unit_indices, action_type, reason, latency, draws) -> dict:
    """One abusive return line: `unit_indices` are the claimed units of sale line `line`."""
    return {"event_id": action_id, "cust": cust, "order_id": line["order_id"], "order_line_no": int(line["order_line_no"]),
            "unit_indices": [int(i) for i in unit_indices], "quantity": len(unit_indices), "sku_idx": line["sku_idx"],
            "style_idx": line["style_idx"], "line_quantity": line["quantity"], "line_total_p": line["total_p"],
            "window": line["window"], "delivered_date": line["delivered_date"], "kind": "abuse", "cause": action_type,
            "reason_code": reason, "latency_days": int(latency), "late": False, "u_time": draws[0], "u_reject": draws[1],
            "u_refund": draws[2], "u_decision": draws[3], "withdraw_planned": False, "u_withdraw_day": 0.0}


def _action(action_id, cust, action_type, line=None, unit_indices=(), reason_uncompleted=None, **extra) -> dict:
    row = {"action_id": action_id, "cust": cust, "action_type": action_type,
           "order_id": None if line is None else line["order_id"],
           "order_line_no": None if line is None else int(line["order_line_no"]),
           "allocated_unit_indices": [int(i) for i in unit_indices], "completed_action": False,
           "coordination_group_id": None, "campaign_id": None, "claim_source": None,
           "uncompleted_reason": reason_uncompleted, "style_idx": None, "whole_parcel": False, "parcel_companion": False}
    row.update(extra)
    return row


def _finish(ctx: Context, actions: list, events: list, after_cutoff: str):
    """Settle the abusive requests and mark each action completed only if its request is visible at the cutoff."""
    events = settle(ctx, pd.DataFrame(events, columns=EVENT_COLUMNS)) if events else pd.DataFrame(columns=EVENT_COLUMNS)
    visible = dict(zip(events["event_id"], events["visible"])) if len(events) else {}
    for action in actions:
        if action["order_id"] is not None:
            action["completed_action"] = bool(visible[action["action_id"]])
            action["uncompleted_reason"] = None if action["completed_action"] else after_cutoff
    return actions, events


def choose_hot_list(ctx: Context) -> np.ndarray:
    """The world's private list of target styles, weighted by median catalog price."""
    styles, settings = ctx.catalog.styles, ctx.s.amendment["campaigns"]
    eligible = np.flatnonzero(styles["first_launch"].to_numpy().astype("datetime64[D]") <= ctx.history_start)
    weights = styles["median_price"].to_numpy()[eligible]
    size = min(settings["world_hot_list_size"], len(eligible))
    return np.sort(stream(ctx.seed, "world", "hot_list").choice(eligible, size=size, replace=False, p=weights / weights.sum()))


def run_campaigns(ctx: Context, profiles: pd.DataFrame, rel: Relationships, units: pd.DataFrame,
                  reserved: np.ndarray, hot_list: np.ndarray, occupied: dict):
    """Ring campaigns. Returns (campaign truth, actions, campaign orders, campaign lines, abusive events).

    `occupied` maps a customer to the dates on which that account already has an order; a campaign order
    takes the first free day, so no account ever places two orders on one day.
    """
    s, seed, cat, world = ctx.s, ctx.seed, ctx.catalog, ctx.world_id
    cfg, accepted = s.amendment["campaigns"], s.accepted
    whole_parcel = s.amendment4["deceptive_claims"]["whole_parcel_claim_probability"]
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
        # the ring is active from the signup of its second claim-capable member (of its only one if alone)
        joined = np.sort(signup[capable])
        first_day = int((max(ctx.history_start, joined[min(1, len(joined) - 1)]) - ctx.history_start) / DAY)
        n_styles = min(int(rng.integers(s_lo, s_hi + 1)), len(hot_list))
        weights = price[hot_list] / price[hot_list].sum()
        group_styles = rng.choice(hot_list, size=n_styles, replace=False, p=weights)
        # dates are drawn over the whole window and kept only once the ring exists, so a ring that starts late
        # runs fewer campaigns instead of packing them into its last weeks
        days = np.sort(rng.choice(len(ctx.history), size=int(rng.integers(c_lo, c_hi + 1)), replace=False))
        days = days[days >= first_day]
        for j, day in enumerate(days):
            style = int(group_styles[rng.integers(len(group_styles))])
            campaign_date = ctx.history[day]
            campaign_id = f"{world}-K{token(seed, group_id, 'campaign:' + str(j))}"
            campaigns.append((world, campaign_id, group_id, cat.styles["style_id"].iloc[style], campaign_date))
            for member in capable:
                if campaign_date < signup[member]:          # not yet a member of the ring
                    continue
                cid = ctx.customer_ids[member]
                member_rng = stream(seed, cid, "campaign:" + campaign_id)
                u = member_rng.random(8)
                if u[0] >= cfg["participant_probability_per_date"]:
                    continue
                action_type, reason = _claim(ctx, u[1])
                attempt = {"action_id": f"{world}-X{token(seed, cid, 'action:' + campaign_id)}", "cust": member,
                           "action_type": action_type, "reason": reason, "campaign_id": campaign_id, "group_id": group_id,
                           "style_idx": style, "draws": u[3:7], "order": None, "lines": None, "target_line": None,
                           "reused": None, "reason_uncompleted": None,
                           "parcel": bool(action_type == NONRECEIPT and u[2] < whole_parcel),
                           "delay": int(claim_delay(ctx, member_rng.gamma(
                               s.amendment3["claim_latency"]["shape"], s.amendment3["claim_latency"]["scale_days"])))}
                rows = rows_of.get(member, np.array([], dtype=int))
                reusable = rows[(unit_style[rows] == style) & ~reserved[rows]
                                & (unit_delivered[rows] >= campaign_date - cfg["reuse_window_days_before_campaign_date"] * DAY)
                                & (unit_delivered[rows] <= campaign_date)]
                if len(reusable):
                    row = int(reusable[np.argsort(unit_delivered[reusable], kind="stable")[0]])
                    reserved[row] = True
                    attempt.update(source="reused_purchase", reused=units.iloc[row])
                    attempts.append(attempt)
                    continue
                attempt["source"] = "campaign_order"
                attempts.append(attempt)
                taken = occupied.setdefault(member, set())
                order_date = campaign_date + (o_lo + int(u[7] * (o_hi - o_lo + 1))) * DAY
                while order_date in taken and order_date <= ctx.snapshot:
                    order_date += DAY
                if order_date > ctx.snapshot:
                    attempt["reason_uncompleted"] = "after_cutoff"
                    continue
                festive = bool(ctx.festive_multiplier[int((order_date - ctx.history_start) / DAY)] > 0)
                basket = draw_basket(ctx, member_rng, order_date, festive, style)
                if basket is None:
                    attempt["reason_uncompleted"] = "pre_launch"
                    continue
                taken.add(order_date)
                n_lines = len(basket["sku_idx"])
                f = member_rng.random(5)
                dispatch = d_lo + int(f[0] * (d_hi - d_lo + 1))
                tail = f[1] < accepted["carrier_tail_probability"]
                transit = (t_lo + int(f[2] * (t_hi - t_lo + 1))) if tail else (r_lo + int(f[2] * (r_hi - r_lo + 1)))
                cancel_u = member_rng.random((n_lines, 2))
                used = rel.draw_identifiers(stream(seed, cid, "campaign_identifiers:" + campaign_id), member, 1)
                order_id = f"{world}-O{token(seed, cid, 'campaign_order:' + campaign_id)}"
                attempt["target_line"] = basket["target_position"] + 1
                attempt["order"] = {
                    "order_id": order_id, "cust": member, "order_date": order_date, "festive": festive,
                    "channel": channels[int(_pick(np.array([f[3]]), channel_p)[0])],
                    "address_id": used["address"][0], "device_id": used["device"][0], "payment_id": used["payment"][0],
                    "dispatch_days": dispatch, "transit_days": transit,
                    "lost": bool(f[4] < accepted["loss_probability_of_shipped"]), "layer": "campaign",
                    "campaign_id": campaign_id, "seq": -1, "co_order": False, "co_source": None}
                attempt["lines"] = [{
                    "order_id": order_id, "order_line_no": k + 1, "cust": member, "order_date": order_date,
                    "sku_idx": int(basket["sku_idx"][k]), "style_idx": int(basket["style_idx"][k]),
                    "quantity": int(basket["quantity"][k]), "unit_price_p": int(cat.sku_price_paise[basket["sku_idx"][k]]),
                    "discount_p": int(basket["discount_p"][k]), "total_p": int(basket["total_p"][k]),
                    "window": int(cat.sku_window[basket["sku_idx"][k]]), "bracketed": False,
                    "cancel": bool(cancel_u[k, 0] < accepted["cancel_probability"]),
                    "cancel_offset": int(cancel_u[k, 1] * (dispatch + 1)), "dispatch_days": dispatch,
                    "transit_days": transit, "lost": attempt["order"]["lost"], "address_id": used["address"][0],
                    "layer": "campaign", "co_source": None} for k in range(n_lines)]

    campaign_truth = pd.DataFrame(campaigns, columns=["world_id", "campaign_id", "coordination_group_id", "target_style_id", "campaign_date"])
    placed = [a for a in attempts if a["order"] is not None]
    c_orders = pd.DataFrame([a["order"] for a in placed])
    c_lines = pd.DataFrame([line for a in placed for line in a["lines"]])
    lines_of = {}
    if len(c_lines):
        c_lines = apply_fulfilment(ctx, c_lines)
        lines_of = {order_id: group for order_id, group in c_lines.groupby("order_id", sort=False)}

    actions, events = [], []
    for a in attempts:
        common = {"coordination_group_id": a["group_id"], "campaign_id": a["campaign_id"], "claim_source": a["source"]}
        if a["reused"] is not None:                      # a recent purchase of the target style, one unit
            unit = a["reused"]
            actions.append(_action(a["action_id"], a["cust"], a["action_type"], unit, [unit["unit_index"]],
                                   style_idx=a["style_idx"], **common))
            events.append(_event(a["action_id"], a["cust"], unit, [unit["unit_index"]], a["action_type"], a["reason"], a["delay"], a["draws"]))
            continue
        if a["order"] is None:
            actions.append(_action(a["action_id"], a["cust"], a["action_type"], reason_uncompleted=a["reason_uncompleted"],
                                   style_idx=a["style_idx"], **common))
            continue
        order_lines = lines_of[a["order"]["order_id"]].set_index("order_line_no")
        target = order_lines.loc[a["target_line"]]
        if target["line_status"] != "delivered":
            reason = "cancelled" if target["line_status"] == "cancelled" else ("lost_in_transit" if target["lost"] else "undelivered_by_cutoff")
            actions.append(_action(a["action_id"], a["cust"], a["action_type"], reason_uncompleted=reason,
                                   style_idx=a["style_idx"], **common))
            continue
        # the claim is on the target-style line, wherever it sits in the basket; a non-receipt claim may cover the parcel
        target = target.to_dict() | {"order_id": a["order"]["order_id"], "order_line_no": a["target_line"]}
        claimed = list(range(1, int(target["quantity"]) + 1)) if a["parcel"] else [1]
        actions.append(_action(a["action_id"], a["cust"], a["action_type"], target, claimed, style_idx=a["style_idx"],
                               whole_parcel=a["parcel"], **common))
        events.append(_event(a["action_id"], a["cust"], target, claimed, a["action_type"], a["reason"], a["delay"], a["draws"]))
        if a["parcel"]:
            for line_no, line in order_lines.iterrows():
                if line_no == a["target_line"] or line["line_status"] != "delivered":
                    continue
                companion = line.to_dict() | {"order_id": a["order"]["order_id"], "order_line_no": line_no}
                action_id, delay, draws = _companion(ctx, a["action_id"], line_no)
                indices = list(range(1, int(line["quantity"]) + 1))
                actions.append(_action(action_id, a["cust"], a["action_type"], companion, indices, whole_parcel=True,
                                       parcel_companion=True, **common))
                events.append(_event(action_id, a["cust"], companion, indices, a["action_type"], a["reason"], delay, draws))
    actions, events = _finish(ctx, actions, events, "claim_after_cutoff")
    return campaign_truth, actions, c_orders, c_lines, events


def run_solo_actions(ctx: Context, profiles: pd.DataFrame, orders: pd.DataFrame, units: pd.DataFrame, reserved: np.ndarray):
    """Solo abusive actions on base-layer delivered orders. Returns (actions, abusive events)."""
    s, seed, cat, world = ctx.s, ctx.seed, ctx.catalog, ctx.world_id
    weighting = s.amendment["temporary_use_occasion_weighting"]
    latency_law = s.amendment3["claim_latency"]
    whole_parcel = s.amendment4["deceptive_claims"]["whole_parcel_claim_probability"]
    fit_share = s.accepted["temp_reason_mix"]["fit_or_discretionary"]
    rates = {"claim": profiles["claim_action_rate"].to_numpy(), "temporary_use": profiles["temporary_use_action_rate"].to_numpy()}
    capable = {"claim": profiles["claim_propensity"].to_numpy(), "temporary_use": profiles["temporary_use_propensity"].to_numpy()}
    unit_rows = units.groupby("order_id", sort=False).indices
    occasion = cat.sku_occasion[units["sku_idx"].to_numpy()]
    window = units["window"].to_numpy()
    unit_line = units["order_line_no"].to_numpy()
    unit_index = units["unit_index"].to_numpy()
    unit_order = units["order_id"].to_numpy(dtype=object)
    base_orders = orders[orders["layer"] == "base"]
    orders_of = {c: g["order_id"].to_numpy() for c, g in base_orders.groupby("cust", sort=True)}

    actions, events = [], []
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
            gamma = rng.gamma(latency_law["shape"], latency_law["scale_days"], len(relevant))
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
                action_type, reason = _claim(ctx, u[k, 2]) if family == "claim" else (TEMPORARY, None)
                if not len(pool):
                    actions.append(_action(action_id, cust, action_type, reason_uncompleted="no_unreserved_unit"))
                    continue
                row = int(pool[int(u[k, 1] * len(pool))])
                parcel = False
                if family == "claim":
                    latency = int(claim_delay(ctx, gamma[k]))               # the one law for every transaction claim
                    parcel = bool(action_type == NONRECEIPT and u[k, 3] < whole_parcel)
                else:
                    if u[k, 2] < fit_share:
                        codes = FIT_CODES if u[k, 3] < 0.5 else DISCRETIONARY_CODES
                    else:
                        codes = FALSE_QUALITY_CODES
                    reason = codes[int(u[k, 4] * len(codes))]
                    latency = int(np.rint(beta[k] * window[row]))
                proposals.append((row, action_id, action_type, reason, latency, u[k, 5:9], parcel))

        # two families wanting the same unit: keyed random winner, no replacement unit for the loser
        by_row, winners = {}, []
        for proposal in proposals:
            by_row.setdefault(proposal[0], []).append(proposal)
        for row, contenders in by_row.items():
            winner = 0
            if len(contenders) > 1:
                winner = int(stream(seed, contenders[0][1], "unit_conflict").random() * len(contenders))
            for index, proposal in enumerate(contenders):
                if index != winner:
                    actions.append(_action(proposal[1], cust, proposal[2], reason_uncompleted="unit_conflict"))
                    continue
                reserved[row] = True
                winners.append(proposal)
        # a whole-parcel non-receipt claim then takes every unit of the order that is still unreserved
        for row, action_id, action_type, reason, latency, draws, parcel in winners:
            line = units.iloc[row]
            indices = [int(unit_index[row])]
            companions = {}
            if parcel:
                rows = unit_rows[unit_order[row]]
                for other in rows[~reserved[rows]]:
                    reserved[other] = True
                    if unit_line[other] == unit_line[row]:
                        indices.append(int(unit_index[other]))
                    else:
                        companions.setdefault(int(unit_line[other]), []).append(int(other))
            actions.append(_action(action_id, cust, action_type, line, indices, whole_parcel=parcel))
            events.append(_event(action_id, cust, line, indices, action_type, reason, latency, draws))
            for line_no, others in companions.items():
                companion_id, delay, companion_draws = _companion(ctx, action_id, line_no)
                companion_line = units.iloc[others[0]]
                companion_indices = [int(unit_index[o]) for o in others]
                actions.append(_action(companion_id, cust, action_type, companion_line, companion_indices,
                                       whole_parcel=True, parcel_companion=True))
                events.append(_event(companion_id, cust, companion_line, companion_indices, action_type, reason, delay,
                                     companion_draws))
    return _finish(ctx, actions, events, "request_after_cutoff")
