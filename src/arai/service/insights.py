"""Aggregates a scored run carries for the dashboard and the product screen (Penpot decisions 3, 9 and 10; AM-77).

Everything here is a count or a sum over the snapshot's own rows, made once at scoring time and stored in the run's
summary: orders, returns and refunds by day, returns by channel and by category, and, per style, the category's return
rate, how concentrated the returns are among the returners, and the return rate by month. "Flagged" means the rows of
customers the run selected for review; it is a description of the review set, never a finding about a return.
Nothing here reads private truth, and nothing changes a score, a rank or a selection.
"""
from __future__ import annotations

import pandas as pd

CONCENTRATION_SHARES = (0.01, 0.05, 0.10)      # the top 1%, 5% and 10% of a style's returners, by units requested


def _dates(series: pd.Series) -> pd.Series:
    """Local calendar dates as ISO strings; timestamps keep their own offset (Asia/Kolkata in every snapshot)."""
    return pd.to_datetime(series).dt.strftime("%Y-%m-%d")


def _records(frame: pd.DataFrame, integers: tuple, amounts: tuple) -> list:
    out = frame.copy()
    for name in integers:
        out[name] = out[name].fillna(0).astype(int)
    for name in amounts:
        out[name] = out[name].fillna(0.0).astype(float).round(2)
    return out.to_dict("records")


def _requests(tables: dict, requests: pd.DataFrame, flagged: set) -> pd.DataFrame:
    out = requests[["return_order_id", "customer_id", "style_id", "category", "quantity_returned", "requested_at", "line_status",
                    "refund_amount", "mature"]].copy()
    out["date"] = _dates(out["requested_at"])
    out["flagged"] = out["customer_id"].isin(flagged)
    out["refunded"] = out["refund_amount"].where(out["line_status"] == "refunded", 0.0).fillna(0.0)
    out["flagged_refunded"] = out["refunded"].where(out["flagged"], 0.0)
    channel = tables["return_order"].drop_duplicates("return_order_id").set_index("return_order_id")["return_channel"]
    out["channel"] = out["return_order_id"].map(channel).fillna("unknown").astype(str)
    return out


def run_insights(tables: dict, lines: pd.DataFrame, requests: pd.DataFrame, customers: pd.DataFrame) -> dict:
    """{daily, channels, categories} for one scored snapshot."""
    flagged = set(customers.loc[customers["selected_for_review"], "customer_id"])
    req = _requests(tables, requests, flagged)
    sold = lines[["order_date", "quantity", "line_total", "category", "mature", "requested_units"]].copy()
    sold["date"] = _dates(sold["order_date"])

    orders = sold.groupby("date").agg(order_lines=("quantity", "size"), ordered_units=("quantity", "sum"), order_value_inr=("line_total", "sum"))
    returns = req.groupby("date").agg(return_lines=("quantity_returned", "size"), returned_units=("quantity_returned", "sum"),
                                      refunded_inr=("refunded", "sum"), flagged_return_lines=("flagged", "sum"),
                                      flagged_refunded_inr=("flagged_refunded", "sum"))
    daily = orders.join(returns, how="outer").sort_index().reset_index().rename(columns={"index": "date"})
    integers = ("order_lines", "ordered_units", "return_lines", "returned_units", "flagged_return_lines")
    amounts = ("order_value_inr", "refunded_inr", "flagged_refunded_inr")

    channels = req.groupby("channel").agg(return_lines=("quantity_returned", "size"), flagged_return_lines=("flagged", "sum"),
                                          refunded_inr=("refunded", "sum"), flagged_refunded_inr=("flagged_refunded", "sum")) \
        .sort_values(["return_lines", "channel"], ascending=[False, True]).reset_index()

    mature = sold[sold["mature"]]
    categories = mature.groupby("category").agg(purchased_units=("quantity", "sum"), requested_units=("requested_units", "sum")).reset_index()
    categories["return_rate"] = (categories["requested_units"] / categories["purchased_units"]).where(categories["purchased_units"] > 0)
    categories = categories.sort_values(["return_rate", "category"], ascending=[False, True])
    category_rows = [{"category": str(r.category), "purchased_units": int(r.purchased_units), "requested_units": int(r.requested_units),
                      "return_rate": None if pd.isna(r.return_rate) else float(r.return_rate)} for r in categories.itertuples()]
    return {"daily": _records(daily, integers, amounts),
            "channels": _records(channels, ("return_lines", "flagged_return_lines"), ("refunded_inr", "flagged_refunded_inr")),
            "categories": category_rows}


def style_insights(lines: pd.DataFrame, requests: pd.DataFrame) -> dict:
    """style_id -> {category_return_rate, concentration, monthly}, over mature sale lines and the requests on them.

    category_return_rate is the pooled rate of the style's category (requested over purchased units); concentration is
    the share of the style's requested units that came from its top 1%, 5% and 10% of returners (cumulative, at least
    one account) and from everyone outside the top 10%; monthly is purchased and requested units by the month of the order.
    """
    mature = lines[lines["mature"]]
    by_category = mature.groupby("category").agg(purchased=("quantity", "sum"), requested=("requested_units", "sum"))
    category_rate = (by_category["requested"] / by_category["purchased"]).where(by_category["purchased"] > 0)
    style_category = mature.drop_duplicates("style_id").set_index("style_id")["category"]

    months = mature.assign(month=pd.to_datetime(mature["order_date"]).dt.strftime("%Y-%m"))
    monthly = months.groupby(["style_id", "month"]).agg(purchased_units=("quantity", "sum"), requested_units=("requested_units", "sum")).reset_index()

    asked = requests[requests["mature"]]
    per_returner = asked.groupby(["style_id", "customer_id"])["quantity_returned"].sum()

    out = {}
    for style_id, category in style_category.items():
        rate = category_rate.get(category)
        units = per_returner.xs(style_id, level="style_id").sort_values(ascending=False) if style_id in per_returner.index.get_level_values(0) else pd.Series(dtype=float)
        total, returners = float(units.sum()), len(units)
        bands, taken = [], 0
        for share in CONCENTRATION_SHARES:
            count = max(1, int(round(returners * share))) if returners else 0
            taken = max(count, taken)
            part = float(units.iloc[:taken].sum())
            bands.append({"band": f"top_{int(share * 100)}", "returners": int(taken), "share": part / total if total else None})
        rest = float(units.iloc[taken:].sum())
        bands.append({"band": "others", "returners": int(returners - taken), "share": rest / total if total else None})
        rows = monthly[monthly["style_id"] == style_id].sort_values("month")
        out[str(style_id)] = {
            "category_return_rate": None if rate is None or pd.isna(rate) else float(rate),
            "concentration": bands,
            "monthly": [{"month": r.month, "purchased_units": int(r.purchased_units), "requested_units": int(r.requested_units)}
                        for r in rows.itertuples()],
        }
    return out
