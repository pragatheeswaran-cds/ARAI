"""Base shopping: orders, lines, pricing, fulfilment and the sale-line state visible at the cutoff."""
from __future__ import annotations

import numpy as np
import pandas as pd

from arai.generator.context import DAY, Context
from arai.generator.relationships import Relationships
from arai.rng import stream, token

NAT = np.datetime64("NaT", "D")
FESTIVE_DISCOUNT_STEPS = (25, 30, 35, 40)   # generator-config: festive_discount


def _eligible_weights(ctx: Context, start_index: int, festive_share: float) -> np.ndarray:
    """Order-date weights over a customer's eligible days.

    The festive share is spread over eligible festive days in proportion to each window's multiplier and the
    rest is uniform. With no eligible festive day the realised festive share is zero.
    """
    multiplier = ctx.festive_multiplier[start_index:]
    festive = multiplier > 0
    if festive.any() and (~festive).any():
        weights = np.where(festive, festive_share * multiplier / multiplier[festive].sum(),
                           (1.0 - festive_share) / (~festive).sum())
    elif festive.any():
        weights = multiplier.copy()
    else:
        weights = np.ones(len(multiplier))
    return weights / weights.sum()


def _pick(u: np.ndarray, probabilities) -> np.ndarray:
    """Index of the category each uniform draw falls in."""
    return np.minimum(np.searchsorted(np.cumsum(probabilities), u, side="right"), len(probabilities) - 1)


def choose_skus(ctx: Context, style: np.ndarray, dates: np.ndarray, u: np.ndarray) -> np.ndarray:
    """Uniform SKU of each style among variants launched by the order date (-1 if none is launched yet)."""
    cat = ctx.catalog
    sku = np.full(len(style), -1)
    for index in np.unique(style):
        mask = style == index
        variants = np.flatnonzero(cat.sku_style == index)
        variants = variants[np.argsort(cat.sku_launch[variants], kind="stable")]
        launched = np.searchsorted(cat.sku_launch[variants], dates[mask], side="right")
        chosen = variants[np.minimum((u[mask] * np.maximum(launched, 1)).astype(int), np.maximum(launched, 1) - 1)]
        sku[mask] = np.where(launched > 0, chosen, -1)
    return sku


def price_lines(ctx: Context, sku: np.ndarray, quantity: np.ndarray, festive: np.ndarray,
                u_discount: np.ndarray, u_step: np.ndarray):
    """Line discount and total in integer paise. The discount is a line amount."""
    accepted = ctx.s.accepted
    steps = np.rint(np.array(accepted["discount_steps"]) * 100).astype(int)
    festive_steps = np.array(FESTIVE_DISCOUNT_STEPS)
    percent = np.where(festive, festive_steps[(u_step * len(festive_steps)).astype(int)],
                       steps[(u_step * len(steps)).astype(int)])
    percent = np.where(u_discount < accepted["no_discount_probability"], 0, percent)
    gross = quantity * ctx.catalog.sku_price_paise[sku]
    discount = (gross * percent + 50) // 100
    return discount, gross - discount


def build_base_orders(ctx: Context, profiles: pd.DataFrame, rel: Relationships):
    """Every account's base purchases. Abuse never changes these rows or their identifiers."""
    s, seed, cat = ctx.s, ctx.seed, ctx.catalog
    accepted, impl = s.accepted, s.impl
    target = profiles["target_order_count"].to_numpy()
    festive_share = profiles["target_festive_share"].to_numpy()
    start_index = ((profiles["eligible_start"].to_numpy() - ctx.history_start) / DAY).astype(int)
    d_lo, d_hi = accepted["dispatch_days"]
    r_lo, r_hi = accepted["carrier_regular_days"]
    t_lo, t_hi = accepted["carrier_tail_days"]

    order_parts, line_parts = [], []
    for i in np.flatnonzero(target > 0):
        cid = ctx.customer_ids[i]
        rng = stream(seed, cid, "orders")
        n_orders = int(rng.poisson(target[i]))
        if n_orders == 0:
            continue
        days = start_index[i] + np.sort(rng.choice(len(ctx.history) - start_index[i], size=n_orders,
                                                   p=_eligible_weights(ctx, start_index[i], festive_share[i])))
        n_lines = np.minimum(6, 1 + rng.poisson(0.6, n_orders))           # generator-config: basket
        total = int(n_lines.sum())
        line_u = rng.random((total, 5))
        order_u = rng.random((n_orders, 3))

        ship = stream(seed, cid, "fulfilment")
        dispatch = ship.integers(d_lo, d_hi + 1, n_orders)
        tail = ship.random(n_orders) < accepted["carrier_tail_probability"]
        transit = np.where(tail, ship.integers(t_lo, t_hi + 1, n_orders), ship.integers(r_lo, r_hi + 1, n_orders))
        lost = ship.random(n_orders) < accepted["loss_probability_of_shipped"]
        cancel_u = ship.random((total, 2))

        used = rel.draw_identifiers(stream(seed, cid, "identifiers"), i, n_orders)
        sequence = np.arange(n_orders)
        order_parts.append({
            "cust": np.full(n_orders, i), "seq": sequence, "day": days, "n_lines": n_lines,
            "u_bracket": order_u[:, 0], "u_sibling": order_u[:, 1], "u_channel": order_u[:, 2],
            "dispatch_days": dispatch, "transit_days": transit, "lost": lost,
            "address_id": used["address"], "device_id": used["device"], "payment_id": used["payment"],
            "order_id": np.array([f"{ctx.world_id}-O{token(seed, cid, 'order:' + str(k))}" for k in sequence], dtype=object),
        })
        line_parts.append({
            "order_pos": np.repeat(sequence, n_lines),
            "order_line_no": np.concatenate([np.arange(1, k + 1) for k in n_lines]),
            "u_style": line_u[:, 0], "u_sku": line_u[:, 1], "u_quantity": line_u[:, 2],
            "u_discount": line_u[:, 3], "u_step": line_u[:, 4],
            "u_cancel": cancel_u[:, 0], "u_cancel_day": cancel_u[:, 1],
        })

    if not order_parts:
        return None, None
    orders = pd.DataFrame({k: np.concatenate([p[k] for p in order_parts]) for k in order_parts[0]})
    offsets = np.concatenate([[0], np.cumsum([len(p["seq"]) for p in order_parts])[:-1]])
    lines = pd.DataFrame({k: np.concatenate([p[k] for p in line_parts]) for k in line_parts[0]})
    lines["order_row"] = lines.pop("order_pos") + np.repeat(offsets, [len(p["order_line_no"]) for p in line_parts])

    orders["order_date"] = ctx.history[orders.pop("day").to_numpy()]
    orders["festive"] = ctx.festive_multiplier[((orders["order_date"].to_numpy() - ctx.history_start) / DAY).astype(int)] > 0
    channels = list(s.amendment["emitted_constants"]["order_channel"])
    orders["channel"] = np.array(channels, dtype=object)[
        _pick(orders.pop("u_channel").to_numpy(), list(s.amendment["emitted_constants"]["order_channel"].values()))]
    orders["layer"] = "base"
    orders["campaign_id"] = None

    row = lines["order_row"].to_numpy()
    line_date = orders["order_date"].to_numpy()[row]
    # uniform style among styles with a launched variant, then uniform launched SKU of that style
    available = cat.styles["first_launch"].to_numpy().astype("datetime64[D]")[None, :] <= line_date[:, None]
    wanted = (lines["u_style"].to_numpy() * available.sum(axis=1)).astype(int)
    style = (np.cumsum(available, axis=1) > wanted[:, None]).argmax(axis=1)
    sku = choose_skus(ctx, style, line_date, lines["u_sku"].to_numpy())

    # bracketers sometimes make the second line another size of the first line's style and colour
    bracketed = np.zeros(len(lines), dtype=bool)
    bracketer = profiles["bracketer"].to_numpy()[orders["cust"].to_numpy()]
    wants = bracketer & (orders["n_lines"].to_numpy() >= 2) & (orders["u_bracket"].to_numpy() < impl["bracket_line_probability"])
    first_line = np.flatnonzero(lines["order_line_no"].to_numpy() == 1)
    u_sibling = orders["u_sibling"].to_numpy()
    for order_row in np.flatnonzero(wants):
        first = first_line[order_row]
        siblings = np.flatnonzero((cat.sku_style == cat.sku_style[sku[first]]) & (cat.sku_colour == cat.sku_colour[sku[first]])
                                  & (cat.sku_size != cat.sku_size[sku[first]]) & (cat.sku_launch <= line_date[first]))
        if len(siblings):
            sku[first + 1] = siblings[int(u_sibling[order_row] * len(siblings))]
            style[first + 1] = style[first]
            bracketed[[first, first + 1]] = True

    quantity = np.array(accepted["quantity_values"])[_pick(lines["u_quantity"].to_numpy(), accepted["quantity_probabilities"])]
    discount, total_paise = price_lines(ctx, sku, quantity, orders["festive"].to_numpy()[row],
                                        lines["u_discount"].to_numpy(), lines["u_step"].to_numpy())
    dispatch_line = orders["dispatch_days"].to_numpy()[row]
    lines = lines.assign(
        order_id=orders["order_id"].to_numpy()[row], cust=orders["cust"].to_numpy()[row], order_date=line_date,
        sku_idx=sku, style_idx=style, quantity=quantity, unit_price_p=cat.sku_price_paise[sku],
        discount_p=discount, total_p=total_paise, window=cat.sku_window[sku], bracketed=bracketed,
        cancel=lines["u_cancel"].to_numpy() < accepted["cancel_probability"],
        cancel_offset=(lines["u_cancel_day"].to_numpy() * (dispatch_line + 1)).astype(int),
        dispatch_days=dispatch_line, transit_days=orders["transit_days"].to_numpy()[row],
        lost=orders["lost"].to_numpy()[row], address_id=orders["address_id"].to_numpy()[row], layer="base",
    ).drop(columns=["u_style", "u_sku", "u_quantity", "u_discount", "u_step", "u_cancel", "u_cancel_day", "order_row"])
    orders = orders.drop(columns=["u_bracket", "u_sibling", "n_lines"])
    return orders, lines


def apply_fulfilment(ctx: Context, lines: pd.DataFrame) -> pd.DataFrame:
    """Sale-line state as observed at the cutoff. Plans that complete after the cutoff stay private."""
    loss_days = ctx.s.impl["loss_confirmation_days"]
    order_date = lines["order_date"].to_numpy().astype("datetime64[D]")
    shipped = order_date + lines["dispatch_days"].to_numpy() * DAY
    delivered = shipped + lines["transit_days"].to_numpy() * DAY
    cancel_seen = lines["cancel"].to_numpy() & (order_date + lines["cancel_offset"].to_numpy() * DAY <= ctx.snapshot)
    not_dispatched = lines["cancel"].to_numpy() | (shipped > ctx.snapshot)
    lost = lines["lost"].to_numpy()
    status = np.select(
        [cancel_seen, not_dispatched, lost & (shipped + loss_days * DAY <= ctx.snapshot), lost, delivered <= ctx.snapshot],
        ["cancelled", "awaiting_dispatch", "lost_in_transit", "shipped", "delivered"], default="shipped").astype(object)
    in_hand = ~np.isin(status, ["cancelled", "awaiting_dispatch"])
    return lines.assign(line_status=status,
                        shipped_date=np.where(in_hand, shipped, NAT),
                        delivered_date=np.where(status == "delivered", delivered, NAT))


def expand_units(lines: pd.DataFrame) -> pd.DataFrame:
    """One private row per delivered unit, keyed (order_id, order_line_no, unit_index)."""
    delivered = lines[lines["line_status"] == "delivered"]
    repeat = delivered["quantity"].to_numpy()
    units = delivered.loc[delivered.index.repeat(repeat),
                          ["order_id", "order_line_no", "cust", "sku_idx", "style_idx", "quantity", "total_p", "window",
                           "bracketed", "delivered_date", "address_id", "layer"]].reset_index(drop=True)
    units["unit_index"] = np.concatenate([np.arange(1, q + 1) for q in repeat]) if len(repeat) else np.array([], dtype=int)
    return units.sort_values(["cust", "order_id", "order_line_no", "unit_index"], kind="stable").reset_index(drop=True)
