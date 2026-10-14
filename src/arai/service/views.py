"""Read models: run results and experiment reports shaped as the API contract's schemas.

Everything here is read from PostgreSQL (decision AM-39); no file is opened to answer a request. Results are
written once when a run succeeds. Nothing is recomputed and no filter changes a score or a selection.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime

from arai import features as F
from arai.service import scoring
from arai.service.store import Store

WARDROBING_LIMITATION = ("Occasion wear returned late in its return window, counted only when what the customer returned supports "
                         "it. It cannot establish that an item was worn, and it is independent of the model score.")
# code -> (label, value, denominator, unit); value and denominator name measures of the customer's result row
WARDROBING_SIGNALS = {
    "late_occasion_return": ("Occasion wear returned in the last quarter of the return window (reaches no band alone)",
                             "late_occasion_return_lines", "item_return_lines", "of item-return lines"),
    "occasion_excess": ("Occasion-wear units returned, far above what this customer's other returns predict",
                        "occasion_returned_units", "occasion_units", "of occasion-wear units bought"),
    "clean_style_complaint": ("Quality complaints on styles other buyers do not complain about",
                              "clean_style_complaint_lines", "item_return_lines", "of item-return lines"),
}
OCCASION_EXPECTED = ("occasion_expected_units", "Occasion-wear returns this customer's other returns predict", "units")
CASE_STYLES, STYLE_CUSTOMERS, SOURCE_REFS = 12, 50, 20
SCORE_BINS, SCORE_TOP = 20, 100.0                 # the risk score is a percentile: twenty bins of five points
TIMELINE_FACTS = ("order_id", "order_line_no", "quantity", "size", "reason_code", "reason_group", "day_in_window", "window_days",
                  "line_status", "item_received", "linked_claim")


class BadCursor(Exception):
    """The cursor is malformed or belongs to another list (HTTP 422)."""


# ------------------------------------------------------------------ cursors
def _context(parts: dict) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def encode_cursor(context: dict, position) -> str:
    payload = json.dumps({"c": _context(context), "p": position}, default=str)
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _valid_position(position, kind: str) -> bool:
    if kind == "int":
        return isinstance(position, int) and not isinstance(position, bool) and position >= 0
    if kind == "text":
        return isinstance(position, str) and 0 < len(position) <= 200
    if kind == "time_id":
        if not (isinstance(position, list) and len(position) == 2 and all(isinstance(p, str) for p in position)):
            return False
        try:
            datetime.fromisoformat(position[0])
        except ValueError:
            return False
        return True
    return False


def decode_cursor(cursor: str | None, context: dict, kind: str):
    """The position stored in a cursor, after checking it was issued for this list and has the shape this list uses."""
    if cursor is None:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
        issued_for, position = payload["c"], payload["p"]
    except Exception:                                               # noqa: BLE001
        raise BadCursor("The cursor is not valid.") from None
    if issued_for != _context(context):
        raise BadCursor("The cursor belongs to a different list or filter set.")
    if not _valid_position(position, kind):
        raise BadCursor("The cursor is not valid.")
    return position


# ------------------------------------------------------------------ run results
def _number(value):
    return None if value is None else float(value)


def _integer(value):
    return None if value is None else int(value)


def _boolean(value):
    return None if value is None else bool(value)


def customer_item(row: dict, latest_disposition: str | None) -> dict:
    return {
        "customer_id": row["customer_id"], "eligibility_status": row["eligibility_status"],
        "raw_score": _number(row["raw_score"]), "risk_score": _number(row["risk_score"]), "rank": _integer(row["rank"]),
        "selected_for_review": bool(row["selected_for_review"]), "baseline_rank": _integer(row["baseline_rank"]),
        "baseline_selected": bool(row["baseline_selected"]),
        "support_counts": {name: int(row[name]) for name in scoring.SUPPORT},
        "evidence_tags": list(row["evidence_tags"]),
        "wardrobing_status": row["wardrobing_status"], "latest_disposition": latest_disposition,
    }


def customer_queue(store: Store, run: dict, filters: dict, after: int | None, limit: int) -> tuple:
    """(items, next position). Order: rank, then unranked customers by identifier. Filters only choose what is shown."""
    rows = store.run_customers(run["id"], run["world_id"], filters, after, limit + 1)
    items = [customer_item(row, row["latest_disposition"]) for row in rows[:limit]]
    return items, (rows[limit - 1]["queue_position"] if len(rows) > limit else None)


def _signal(code, label, value, denominator, unit, refs=()) -> dict:
    return {"code": code, "label": label, "value": _number(value), "denominator": _number(denominator), "unit": unit,
            "source_refs": list(refs)}


def _style_item(row: dict) -> dict:
    return {
        "style_id": row["style_id"], "category": row["category"], "state": row["state"],
        "mature_sale_lines": int(row["mature_sale_lines"]), "purchased_units": int(row["purchased_units"]),
        "requested_units": int(row["requested_units"]), "unique_returners": int(row["unique_returners"]),
        "raw_return_rate": _number(row["raw_return_rate"]), "shrunk_return_rate": _number(row["shrunk_return_rate"]),
        "damage_share": _number(row["damage_share"]), "claim_share": _number(row["claim_share"]),
        "linked_claim_share": _number(row["linked_claim_share"]), "linked_claimers": int(row["linked_claimers"]),
        "quality_signal": bool(row["quality_signal"]), "targeting_signal": bool(row["targeting_signal"]),
    }


def customer_case(store: Store, run_id: str, customer: dict) -> dict:
    """Evidence for one customer of the run: measured values with their denominators and source keys, no verdict.

    `customer` is the customer's result row; its `measures` hold every value that has no column of its own.
    """
    customer_id = customer["customer_id"]
    row = {**customer["measures"], **customer}
    events = store.run_timeline(run_id, customer_id)
    claims = [e["source_ref"] for e in events if e["event_type"] == "transaction_claim"]
    returns = [e["source_ref"] for e in events if e["event_type"] != "purchase"]
    signals = [
        _signal("mature_requested_units", "Units requested for return on mature sale lines", row["mature_requested_units"],
                row["mature_purchased_units"], "units of mature purchased units", returns[:SOURCE_REFS]),
        _signal("expected_requested_units", "Units a customer buying the same products would be expected to request",
                row["expected_units"], row["mature_purchased_units"], "units of mature purchased units"),
        _signal("raw_return_rate", "Return rate on mature sale lines", row["raw_return_rate"], None, "share"),
        _signal("expected_return_rate", "Expected return rate for the products bought", row["expected_return_rate"], None, "share"),
        _signal("residual_z", "Requested above expected, scaled by volume (heuristic, not a significance test)", row["residual_z"],
                None, "score"),
        _signal("claim_lines", "Transaction-claim lines (not received, wrong item, missing parts, empty package)", row["claim_lines"],
                row["timed_return_lines"], "of return lines", claims[:SOURCE_REFS]),          # withdrawn requests are not counted, as everywhere
        _signal("claim_share", "Share of requested units that are transaction claims", row["claim_share"], row["all_requested_units"],
                "share of requested units"),
        _signal("coordinated_claim_share", "Own claim lines matched by a linked account on the same style within 7 days",
                row["coordinated_claim_share"], row["claim_lines"], "share of claim lines"),
        _signal("requested_refund_ratio", "Requested value over purchased value on mature lines", row["requested_refund_ratio"], None, "share"),
        _signal("late_return_lines", "Item returns requested in the last quarter of the return window", row["late_return_lines"],
                row["item_return_lines"], "of item-return lines"),
        _signal("median_window_ratio", "Median point in the return window at which requests were made", row["median_window_ratio"],
                None, "share of window"),
        _signal("damage_reason_share", "Share of requested units with a quality or damage reason", row["damage_reason_share"],
                row["all_requested_units"], "share of requested units"),
        _signal("supported_neighbor_count", "Accounts sharing two or more identifier types (shown as evidence, not a model input)",
                row["supported_neighbor_count"], None, "accounts"),
        _signal("max_identifier_fanout", "Largest number of accounts using one of this customer's identifiers (evidence only)",
                row["max_identifier_fanout"], None, "accounts"),
        _signal("open_window_share", "Delivered units whose return window is still open", row["open_window_share"], None, "share"),
    ]
    wardrobing_signals = []
    for name in F.WARDROBING_POINTS:
        if not bool(row.get("fired_" + name)):
            continue
        label, value, denominator, unit = WARDROBING_SIGNALS[name]
        wardrobing_signals.append(_signal(name, label, row.get(value), row.get(denominator) if denominator else None, unit))
        if name == "occasion_excess":                       # the prediction the excess is measured against
            code, label, unit = OCCASION_EXPECTED
            wardrobing_signals.append(_signal(code, label, row.get(code), None, unit))
    return {
        "signals": signals,
        "timeline": [_timeline_event(e) for e in events],
        "neighbors": [{"customer_id": n["neighbor_id"], "shared_types": list(n["shared_types"]),
                       "shared_value_count": int(n["shared_value_count"]), "supported": bool(n["supported"]),
                       "max_value_fanout": int(n["max_value_fanout"]), "coordinated_claim_matches": int(n["coordinated_claim_matches"]),
                       # the neighbour's own result in this run; a link is evidence, the score is the neighbour's, not this customer's
                       "risk_score": _number(n["neighbor_risk_score"]), "rank": _integer(n["neighbor_rank"]),
                       "selected_for_review": bool(n["neighbor_selected_for_review"]),
                       "evidence_tags": list(n["neighbor_evidence_tags"] or [])}
                      for n in store.run_neighbors(run_id, customer_id)],
        "styles": [_style_item(style) for style in store.run_customer_styles(run_id, customer_id, CASE_STYLES)],
        "wardrobing": {"status": row["wardrobing_status"], "indicator_score": _integer(row["indicator_score"]),
                       "signals": wardrobing_signals, "limitation": WARDROBING_LIMITATION},
    }


def _timeline_event(e: dict) -> dict:
    """One timeline row as the contract's TimelineEvent: the sentence plus every fact behind it (null where it does not apply)."""
    casts = {"order_line_no": _integer, "quantity": _integer, "day_in_window": _integer, "window_days": _integer,
             "item_received": _boolean, "linked_claim": _boolean}
    event = {"source_ref": e["source_ref"], "event_type": e["event_type"], "observed_at": e["observed_at"],
             "description": e["description"], "amount_inr": _number(e["amount_inr"]), "style_id": e["style_id"], "sku": e["sku"]}
    for name in TIMELINE_FACTS:
        event[name] = casts.get(name, lambda value: value)(e.get(name))
    return event


def score_distribution(store: Store, run: dict) -> dict:
    """Eligible customers of a run in twenty five-point score bins, with the queue size at or above each bin's lower edge.

    `at_or_above` is how many eligible customers score at or above the bin's lower edge, which is the queue a
    threshold at that edge would produce; the budget cut itself is `threshold_score`. Nothing here is recomputed:
    every number is a count over the stored result rows.
    """
    width = SCORE_TOP / SCORE_BINS
    held = {int(row["bin"]): row for row in store.score_distribution(run["id"], SCORE_BINS, SCORE_TOP)}
    bins, above = [], 0
    for index in range(SCORE_BINS, 0, -1):                          # from the top bin down, so the cumulative count is a running sum
        row = held.get(index)
        count = int(row["count"]) if row else 0
        above += count
        bins.append({"lower": (index - 1) * width, "upper": index * width, "count": count,
                     "selected_count": int(row["selected_count"]) if row else 0, "at_or_above": above})
    summary = run["summary"] or {}
    return {"run_id": run["id"], "eligible_count": above, "review_budget": _integer(summary.get("review_budget_k")),
            "threshold_score": _number(summary.get("threshold_score")), "bin_width": width, "bins": bins[::-1]}


def style_queue(store: Store, run_id: str, state: str, after: str | None, limit: int) -> tuple:
    rows = store.run_styles(run_id, state, after, limit + 1)
    return [_style_item(row) for row in rows[:limit]], (rows[limit - 1]["style_id"] if len(rows) > limit else None)


def style_detail(store: Store, run_id: str, style_id: str) -> dict:
    row = store.run_style(run_id, style_id)
    signals = [
        _signal("requested_units", "Units requested for return on mature sale lines", row["requested_units"], row["purchased_units"],
                "units of mature purchased units"),
        _signal("damage_share", "Requested units with a quality reason (defective, poor quality, not as described)",
                row["quality_units"], row["requested_units"], "units of requested units"),
        _signal("claim_share", "Requested units that are transaction claims", row["claim_units"], row["requested_units"],
                "units of requested units"),
        _signal("linked_claim_share", "Claim lines matched by a linked account's claim on this style within 7 days",
                row["linked_claim_lines"], row["claim_lines"], "of claim lines"),
        _signal("linked_claimers", "Distinct customers with a linked claim on this style", row["linked_claimers"], None, "customers"),
    ]
    return {"style": _style_item(row),
            "skus": [{"sku": s["sku"], "style_id": s["style_id"], "size": str(s["size"]), "colour": str(s["colour"]),
                      "unit_price_inr": float(s["unit_price"]), "mature_sale_lines": int(s["mature_sale_lines"]),
                      "purchased_units": int(s["purchased_units"]), "requested_units": int(s["requested_units"]),
                      "support_status": s["support_status"]} for s in store.run_style_skus(run_id, style_id)],
            "customer_ids": store.run_style_customers(run_id, style_id, STYLE_CUSTOMERS), "signals": signals}


# ------------------------------------------------------------------ experiment truth (published offline, synthetic only)
def truth_page(store: Store, experiment: dict, after: int | None, limit: int) -> tuple:
    """(items, next position, world) of the demonstration world's synthetic truth, for the evaluation page only."""
    rows = store.experiment_truth(experiment["id"], after, limit + 1)
    items = [{"customer_id": r["customer_id"], "y_abuse": int(r["y_abuse"]), "action_types": list(r["action_types"])} for r in rows[:limit]]
    return items, (rows[limit]["position"] if len(rows) > limit else None), experiment["truth_world_id"]
