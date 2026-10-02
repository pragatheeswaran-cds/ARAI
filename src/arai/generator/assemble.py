"""Turn generated events into the seven operational tables and the separate private truth tables."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from arai.generator.abuse import CONTENTS, NONRECEIPT, TEMPORARY
from arai.generator.context import DAY, Context
from arai.generator.returns import DEFECT, FULFILMENT
from arai.rng import stream, token

OPERATIONAL_TABLES = ("customer_master", "sku_master", "reason_code", "sales_order", "sales_order_line",
                      "return_order", "return_order_line")
PRIMARY_KEYS = {"customer_master": ["customer_id"], "sku_master": ["sku"], "reason_code": ["reason_code"],
                "sales_order": ["order_id"], "sales_order_line": ["order_id", "order_line_no"],
                "return_order": ["return_order_id"], "return_order_line": ["return_order_id", "return_line_no"]}


def _rupees(paise) -> np.ndarray:
    return np.asarray(paise, dtype=np.int64) / 100.0


def _days(values) -> pd.Series:
    """Date column: day precision, NaT for null."""
    return pd.Series(np.asarray(values).astype("datetime64[D]").astype("datetime64[s]"))


def build_return_tables(ctx: Context, events: pd.DataFrame):
    """Return headers and lines from the requests visible at the cutoff.

    One rule for every request, honest or abusive: a customer's requests are taken in time order, a header
    covers its first request date and the following day, and lines are numbered by request time. Header
    structure therefore says nothing about intent.
    """
    s, seed, world = ctx.s, ctx.seed, ctx.world_id
    span = s.impl["header_span_days"] * DAY
    # ties in time are broken by a hash of the event, never by its kind
    events = events.assign(tie=[token(seed, e, "request_order") for e in events["event_id"]])
    events = events.sort_values(["cust", "requested_at", "tie"], kind="stable").reset_index(drop=True)
    cust = events["cust"].to_numpy()
    request_date = events["request_date"].to_numpy().astype("datetime64[D]")
    event_id = events["event_id"].to_numpy(dtype=object)
    header_key = np.empty(len(events), dtype=object)
    current = (None, None, None)                   # customer, first request date, key of the open header
    for row in range(len(events)):
        if current[0] != cust[row] or request_date[row] > current[1] + span:
            current = (cust[row], request_date[row], event_id[row])
        header_key[row] = current[2]
    events["return_order_id"] = [f"{world}-R{token(seed, ctx.customer_ids[c], 'return:' + k)}" for c, k in zip(cust, header_key)]
    events["return_line_no"] = events.groupby("return_order_id", sort=False).cumcount() + 1
    events = events.drop(columns="tie")

    lines = pd.DataFrame({
        "return_order_id": events["return_order_id"], "return_line_no": events["return_line_no"],
        "order_id": events["order_id"], "order_line_no": events["order_line_no"].astype(int),
        "sku": ctx.catalog.sku_master["sku"].to_numpy()[events["sku_idx"].to_numpy(dtype=int)],
        "quantity_returned": events["quantity"].astype(int), "reason_code": events["reason_code"],
        "requested_at": events["requested_at"], "available_at": events["requested_at"],
        "line_status": events["line_status"], "refund_amount": _rupees(events["refund_p"]),
        "return_received_flag": events["return_received_flag"].astype("Int64"),
        "reason_text": None, "disposition": None,
    })
    refund_methods, channels = s.accepted["refund_methods"], s.accepted["channels"]
    grouped = events.groupby("return_order_id", sort=True)
    header = grouped.agg(cust=("cust", "first"), return_created_at=("requested_at", "max"),
                         refund_p=("refund_p", "sum"), needs_item=("needs_item", "any")).reset_index()
    u = np.array([stream(seed, h, "header").random(2) for h in header["return_order_id"]]).reshape(-1, 2)
    channel = np.array(list(channels), dtype=object)[np.minimum(
        np.searchsorted(np.cumsum(list(channels.values())), u[:, 0], side="right"), len(channels) - 1)]
    method = np.array(list(refund_methods), dtype=object)[np.minimum(
        np.searchsorted(np.cumsum(list(refund_methods.values())), u[:, 1], side="right"), len(refund_methods) - 1)]
    headers = pd.DataFrame({
        "return_order_id": header["return_order_id"], "customer_id": ctx.customer_ids[header["cust"].to_numpy(dtype=int)],
        "return_created_at": header["return_created_at"],
        "return_channel": np.where(header["needs_item"].to_numpy(), channel, "not_applicable"),
        "refund_method": method, "refund_total": _rupees(header["refund_p"]), "available_at": header["return_created_at"],
    })
    return headers, lines, events


def empty_table(columns: dict) -> pd.DataFrame:
    """A table with the contract's columns and types and no rows."""
    dtype = {"date": "datetime64[s]", "timestamp": "datetime64[s]", "number": "float64", "integer": "Int64", "string": "object"}
    return pd.DataFrame({name: pd.Series(dtype=dtype[spec["type"]]) for name, spec in columns.items()})


def build_reference_tables(ctx: Context, profiles) -> dict:
    cat, constants = ctx.catalog, ctx.s.amendment["emitted_constants"]
    return {
        "customer_master": pd.DataFrame({
            "customer_id": profiles["customer_id"], "signup_date": _days(profiles["signup_date"]),
            "account_status": "unknown", "loyalty_tier": constants["loyalty_tier"],
            "marketing_channel": constants["marketing_channel"]}),
        "sku_master": cat.sku_master.assign(launch_date=_days(cat.sku_launch)),
        "reason_code": cat.reason_code.copy(),
    }


def build_operational(ctx: Context, profiles, orders, lines, return_headers, return_lines) -> dict:
    cat = ctx.catalog
    subtotal = lines.groupby("order_id", sort=False)["total_p"].sum()
    subtotal = subtotal.reindex(orders["order_id"]).to_numpy()
    accepted = ctx.s.accepted
    shipping = np.where(subtotal >= accepted["free_shipping_subtotal"] * 100, 0, accepted["otherwise_shipping"] * 100)
    sku = cat.sku_master["sku"].to_numpy()
    tables = {
        **build_reference_tables(ctx, profiles),
        "sales_order": pd.DataFrame({
            "order_id": orders["order_id"].to_numpy(), "customer_id": ctx.customer_ids[orders["cust"].to_numpy(dtype=int)],
            "order_date": _days(orders["order_date"]), "channel": orders["channel"].to_numpy(),
            "address_id": orders["address_id"].to_numpy(), "device_id": orders["device_id"].to_numpy(),
            "payment_id": orders["payment_id"].to_numpy(), "currency": "INR", "order_subtotal": _rupees(subtotal),
            "order_shipping": _rupees(shipping), "order_total": _rupees(subtotal + shipping)}),
        "sales_order_line": pd.DataFrame({
            "order_id": lines["order_id"].to_numpy(), "order_line_no": lines["order_line_no"].to_numpy(dtype=int),
            "sku": sku[lines["sku_idx"].to_numpy(dtype=int)], "quantity": lines["quantity"].to_numpy(dtype=int),
            "unit_price": _rupees(lines["unit_price_p"]), "line_discount": _rupees(lines["discount_p"]),
            "line_total": _rupees(lines["total_p"]), "return_window_days": lines["window"].to_numpy(dtype=int),
            "line_status": lines["line_status"].to_numpy(), "shipped_date": _days(lines["shipped_date"]),
            "delivered_date": _days(lines["delivered_date"])}),
        "return_order": return_headers,
        "return_order_line": return_lines,
    }
    return {name: tables[name].sort_values(PRIMARY_KEYS[name], kind="stable").reset_index(drop=True) for name in OPERATIONAL_TABLES}


def build_truth(ctx: Context, profiles, rel, orders, lines, unit_facts, campaign_units, events, actions, campaign_truth,
                defect_prone, fit_issue, g_address, hot_list, reservations) -> dict:
    """Private truth. Lives outside every inference mount; labels reconstruct from these joins alone."""
    world, cat, ids = ctx.world_id, ctx.catalog, ctx.customer_ids
    minimum = ctx.s.amendment["targeting_truth"]["min_accounts_per_group"]
    style_ids = cat.styles["style_id"].to_numpy()

    action = pd.DataFrame(actions, columns=["action_id", "cust", "action_type", "order_id", "order_line_no",
                                            "allocated_unit_indices", "completed_action", "coordination_group_id",
                                            "campaign_id", "claim_source", "uncompleted_reason", "style_idx",
                                            "whole_parcel", "parcel_companion"])
    placed = events[events["kind"] == "abuse"].set_index("event_id") if len(events) else pd.DataFrame()
    def lookup(column):
        return [placed[column].get(a) if c else None for a, c in zip(action["action_id"], action["completed_action"])]
    action_truth = pd.DataFrame({
        "world_id": world, "action_id": action["action_id"], "customer_id": ids[action["cust"].to_numpy(dtype=int)],
        "order_id": action["order_id"], "order_line_no": action["order_line_no"].astype("Int64"),
        "allocated_unit_indices": action["allocated_unit_indices"], "action_type": action["action_type"],
        "action_time": lookup("requested_at"), "completed_action": action["completed_action"].astype(bool),
        "return_order_id": lookup("return_order_id"), "return_line_no": pd.array(lookup("return_line_no"), dtype="Int64"),
        "requested_at": lookup("requested_at"), "available_at": lookup("requested_at"),
        "coordination_group_id": action["coordination_group_id"], "campaign_id": action["campaign_id"],
        "claim_source": action["claim_source"], "uncompleted_reason": action["uncompleted_reason"],
        "whole_parcel": action["whole_parcel"].astype(bool), "parcel_companion": action["parcel_companion"].astype(bool)})

    completed = action[action["completed_action"].astype(bool)]
    flags = {t: np.zeros(ctx.n, dtype=bool) for t in (NONRECEIPT, CONTENTS, TEMPORARY)}
    for kind, cust in zip(completed["action_type"], completed["cust"]):
        flags[kind][cust] = True
    coordinated = np.zeros(ctx.n, dtype=bool)
    coordinated[completed.loc[completed["campaign_id"].notna(), "cust"].to_numpy(dtype=int)] = True
    y = flags[NONRECEIPT] | flags[CONTENTS] | flags[TEMPORARY]
    customer_truth = pd.DataFrame({
        "world_id": world, "customer_id": ids, "y_abuse": y.astype(int),
        "deceptive_nonreceipt_claim": flags[NONRECEIPT], "deceptive_contents_claim": flags[CONTENTS],
        "temporary_use_return": flags[TEMPORARY], "coordinated_action_flag": coordinated,
        "household_id": rel.household_id, "coordination_group_id": rel.coordination_group_id,
        "shared_location_id": rel.shared_location_id})

    # style truth: planned and completed targeting per group, graded by distinct completing accounts
    planned = campaign_truth.groupby("target_style_id")["coordination_group_id"].agg(lambda g: sorted(set(g))).to_dict()
    # a whole-parcel claim's lines on other sale lines are not purchases of the target style
    coordinated_actions = completed[completed["campaign_id"].notna() & ~completed["parcel_companion"].astype(bool)]
    accounts = {}
    for style, group, cust in zip(coordinated_actions["style_idx"], coordinated_actions["coordination_group_id"],
                                  coordinated_actions["cust"]):
        accounts.setdefault(style_ids[int(style)], {}).setdefault(group, set()).add(int(cust))
    by_group = {style: {g: len(members) for g, members in groups.items()} for style, groups in accounts.items()}
    level = [("targeted" if max(by_group.get(st, {}).values(), default=0) >= minimum
              else "sub_threshold" if by_group.get(st) else "none") for st in style_ids]
    defaults = ctx.s.defaults["defect_unit_probability"]
    product_truth = pd.DataFrame({
        "world_id": world, "style_id": style_ids, "defect_state": np.where(defect_prone, "defect_prone", "ordinary"),
        "latent_defect_probability": np.where(defect_prone, defaults["defect_prone_style"], defaults["ordinary_style"]),
        "planned_targeted_by": [planned.get(st, []) for st in style_ids],
        "completed_targeted_by": [sorted(by_group.get(st, {})) for st in style_ids],
        "hot_listed": np.isin(np.arange(len(style_ids)), hot_list),
        "coordinated_claim_accounts_by_group": [json.dumps(by_group.get(st, {}), sort_keys=True) for st in style_ids],
        "targeting_level": level, "targeted": [x == "targeted" for x in level]})

    temporary_units, nonreceipt_units = set(), set()
    for _, a in completed.iterrows():
        for index in a["allocated_unit_indices"]:
            key = (a["order_id"], a["order_line_no"], index)
            if a["action_type"] == TEMPORARY:
                temporary_units.add(key)
            elif a["action_type"] == NONRECEIPT:
                nonreceipt_units.add(key)
    all_units = pd.concat([unit_facts, campaign_units], ignore_index=True) if len(campaign_units) else unit_facts
    unit_keys = list(zip(all_units["order_id"], all_units["order_line_no"], all_units["unit_index"]))
    genuine_nonreceipt = (all_units["genuine_fulfilment_cause"] == "item_not_received").to_numpy(dtype=bool)
    unit_truth = pd.DataFrame({
        "world_id": world, "order_id": all_units["order_id"], "order_line_no": all_units["order_line_no"].astype(int),
        "unit_index": all_units["unit_index"].astype(int), "actual_receipt": ~genuine_nonreceipt,
        "received_defective_unit": all_units["received_defective_unit"].astype(bool),
        "genuine_fulfilment_cause": all_units["genuine_fulfilment_cause"],
        "carrier_damage": all_units["carrier_damage"].astype(bool),
        "delivery_incident": all_units["delivery_incident"].astype(bool),
        "temporary_use": [k in temporary_units for k in unit_keys]})
    line_truth = (unit_truth.assign(genuine_nonreceipt=genuine_nonreceipt,
                                    deceptive_nonreceipt=[k in nonreceipt_units for k in unit_keys])
                  .groupby(["world_id", "order_id", "order_line_no"], sort=True)
                  [["received_defective_unit", "temporary_use", "genuine_nonreceipt", "deceptive_nonreceipt"]].any().reset_index())

    profile_columns = ["persona", "annual_order_target", "target_order_count", "target_return_propensity", "target_festive_share",
                       "target_days_per_order", "claim_propensity", "temporary_use_propensity", "claim_action_rate",
                       "temporary_use_action_rate", "heavy_return_overlay", "power_user", "bracketer", "tenure_days"]
    truth = {
        "customer_profile": profiles[["customer_id"] + profile_columns].assign(world_id=world),
        "unit_truth": unit_truth,
        "campaign": campaign_truth.assign(campaign_date=_days(campaign_truth["campaign_date"]).to_numpy()),
        "relationship_truth": rel.truth,
        "unit_allocation": pd.DataFrame(reservations, columns=["world_id", "order_id", "order_line_no", "unit_index",
                                                               "reservation_kind", "event_id"]),
        "action_truth": action_truth,
        "customer_truth": customer_truth,
        "product_truth": product_truth,
        "sku_truth": pd.DataFrame({"world_id": world, "sku": cat.sku_master["sku"], "fit_issue": fit_issue}),
        "line_truth": line_truth,
        "order_truth": pd.DataFrame({"world_id": world, "order_id": orders["order_id"].to_numpy(),
                                     "layer": orders["layer"].to_numpy(), "campaign_id": orders["campaign_id"].to_numpy(),
                                     "household_co_order": orders["co_order"].to_numpy(dtype=bool)}),
        "address_truth": pd.DataFrame({"world_id": world, "address_id": list(g_address),
                                       "genuine_failure_multiplier": list(g_address.values())}),
    }
    return truth
