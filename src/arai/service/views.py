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
from arai.service import attribution, scoring
from arai.service.store import NotFound, Store

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
TIER_MEDIUM_FROM = 90.0                            # decision D1: MEDIUM is a score at or above this and not selected; HIGH is the queue
# evidence tag -> (label under 40 characters, the signal code that carries its value, the measure of its denominator, unit)
PRIMARY_SIGNAL_LABELS = {
    "repeat_claims": ("Two or more transaction claims", "claim_lines", "timed_return_lines", "of return lines"),
    "linked_claims": ("Claims matched by a linked account", "coordinated_claim_share", "claim_lines", "share of claim lines"),
    "late_returns": ("Two or more late returns", "late_return_lines", "item_return_lines", "of item-return lines"),
    "returns_above_expected": ("Returns well above basket expectation", "residual_z", None, "score"),
    "supported_links": ("Shares identifiers with other accounts", "supported_neighbor_count", None, "accounts"),
}
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


def basket_expectation(row: dict) -> dict | None:
    """Actual against expected units with the normal band, for the queue's cleared rows and the case; None without mature lines."""
    measures = row.get("measures") or {}
    expected = measures.get("expected_units")
    if expected is None or not row["mature_purchased_units"]:
        return None
    return {"actual_units": int(row["mature_requested_units"]), "purchased_units": int(row["mature_purchased_units"]),
            "expected_units": float(expected), "sd": _number(measures.get("expected_sd")),
            "band_low": _number(measures.get("expected_band_low")), "band_high": _number(measures.get("expected_band_high")),
            "z": _number(measures.get("residual_z"))}


def community_summary(row: dict) -> dict | None:
    """The community a customer row belongs to, as the queue shows it; None for a customer with no supported edge.

    Also None when the run has no row for the community (result files of an earlier version imported without one).
    """
    if row.get("community_id") is None or row.get("community_size") is None:
        return None
    return {"id": row["community_id"], "kind": row["community_kind"], "size": int(row["community_size"])}


def community_detail(store: Store, run_id: str, row: dict) -> dict | None:
    """The customer's community with its members' own results and the edges between them; None without a supported edge.

    Everything is read from the stored rows: the members are the customers of the run that carry the community id,
    the edges and their coordinated claim matches were recorded when the run was scored. The kind follows the stated
    rule (ring: a coordinated claim match, two or more members selected, or a member with a coordinated claim share)
    and is evidence about the group, not a verdict on any member.
    """
    if row.get("community_id") is None:
        return None
    community = store.run_community(run_id, row["community_id"])
    if community is None:
        return None
    return {"id": community["community_id"], "kind": community["kind"], "method": community["method"], "size": int(community["size"]),
            "selected_count": int(community["selected_count"]), "requested_units": int(community["requested_units"]),
            "purchased_units": int(community["purchased_units"]), "coordinated_claim_matches": int(community["coordinated_claim_matches"]),
            "members": [{"customer_id": m["customer_id"], "risk_score": _number(m["risk_score"]), "rank": _integer(m["rank"]),
                         "selected_for_review": bool(m["selected_for_review"]), "eligibility_status": m["eligibility_status"],
                         "mature_requested_units": int(m["mature_requested_units"]), "mature_purchased_units": int(m["mature_purchased_units"]),
                         "evidence_tags": list(m["evidence_tags"])} for m in community["members"]],
            "edges": [{"a": e["a"], "b": e["b"], "types": list(e["types"]), "coordinated_claim_matches": int(e["coordinated_claim_matches"])}
                      for e in community["edges"]]}


def tier(row: dict) -> str | None:
    """Decision D1, anchored to the queue: HIGH is selected for review, MEDIUM scores at or above 90 and is not selected, LOW
    is every other eligible customer. None for a customer without a score. store.TIER_SQL is the same rule."""
    if row["eligibility_status"] != "eligible" or row["risk_score"] is None:
        return None
    if row["selected_for_review"]:
        return "HIGH"
    return "MEDIUM" if float(row["risk_score"]) >= TIER_MEDIUM_FROM else "LOW"


def gate_outcome(row: dict, summary: dict) -> str | None:
    """Decision D2, a presentation rule over stored results and never a model output: ESCALATE is selected and in a ring or with
    the wardrobing indicator elevated; HOLD is selected otherwise; WARNING is not selected and either MEDIUM or at or above
    the run's heavy-returner cutoff; LOW is the rest. None for a customer without a score. store.GATE_SQL is the same rule."""
    band = tier(row)
    if band is None:
        return None
    if row["selected_for_review"]:
        return "ESCALATE" if row.get("community_kind") == "ring" or row["wardrobing_status"] == "elevated" else "HOLD"
    cutoff, rate = summary.get("heavy_returner_cutoff"), (row.get("measures") or {}).get("raw_return_rate")
    heavy = cutoff is not None and rate is not None and float(rate) >= float(cutoff)
    return "WARNING" if band == "MEDIUM" or heavy else "LOW"


def workflow(row: dict, summary: dict) -> dict:
    """Where the case stands in the review workflow, derived from its reviews and never stored (store.STATE_SQL is the same rule).

    The latest open, request_approval, approve or reject decides: in_review, awaiting_approval, approved, rejected. With no
    such event a customer the gate leaves at LOW or WARNING is auto_logged (no reviewer is needed; it is still in the log),
    and every other customer is new. A note or feedback never moves the state.
    """
    kind = row.get("workflow_kind")
    if kind is None:
        state = "auto_logged" if gate_outcome(row, summary) in ("LOW", "WARNING") else "new"
    else:
        state = {"open": "in_review", "request_approval": "awaiting_approval", "approve": "approved", "reject": "rejected"}[kind]
    decided = kind in ("approve", "reject")
    return {"state": state, "opened_by": row.get("opened_by"), "opened_by_user_id": row.get("opened_by_user_id"),
            "opened_at": _iso(row.get("opened_at")),
            "decided_by": row.get("workflow_reviewer") if decided else None, "decided_at": _iso(row.get("workflow_at")) if decided else None}


def _iso(value) -> str | None:
    return None if value is None else value.isoformat().replace("+00:00", "Z")


def primary_signals(row: dict) -> list:
    """Up to three evidence tags in the order scoring ranked them (the family that moves the score most first), each as a
    plain phrase with the value and denominator of the signal behind it. The tags themselves are unchanged."""
    measures = row.get("measures") or {}
    ordered = [t for t in str(measures.get("primary_signals") or "").split("|") if t] or list(row["evidence_tags"])[:attribution.PRIMARY_SIGNALS]
    out = []
    for tag in ordered:
        label, code, denominator, unit = PRIMARY_SIGNAL_LABELS[tag]
        out.append({"tag": tag, "label": label, "family": attribution.TAG_FAMILY.get(tag), "value": _number(measures.get(code)),
                    "denominator": _number(measures.get(denominator)) if denominator else None, "unit": unit})
    return out


def previous_snapshot(store: Store, run: dict) -> dict | None:
    """The snapshot of the run's world just before the run's cutoff that has a succeeded run, with that reference run
    (decision AM-68); None when the run is on the world's first scored snapshot."""
    earlier = [s for s in store.snapshots(run["world_id"]) if s["cutoff"] < run["cutoff"]]
    return earlier[-1] if earlier else None


def page_history(store: Store, run: dict, customer_ids: list) -> dict:
    """What customer_item needs to place a page of customers against earlier snapshots: the previous snapshot, each
    customer's row in it, and each customer's latest decision in any earlier snapshot."""
    previous = previous_snapshot(store, run)
    rows = store.previous_rows(previous["run_id"], previous["dataset_id"], run["world_id"], customer_ids) if previous else {}
    return {"previous": previous, "rows": rows, "decisions": store.earlier_decisions(run["world_id"], run["cutoff"], customer_ids)}


def snapshot_comparison(store: Store, run: dict) -> dict | None:
    """The run's review set against the previous snapshot's (decision AM-68): customers in both queues, new to this one, gone
    from it, and how many of this queue were decided in an earlier snapshot. None on a world's first scored snapshot."""
    previous = previous_snapshot(store, run)
    if previous is None:
        return None
    counts = store.snapshot_comparison(run["id"], previous["run_id"], run["world_id"], run["cutoff"])
    return {"dataset_id": previous["dataset_id"], "run_id": previous["run_id"], "cutoff": _iso(previous["cutoff"]), **counts}


WORKFLOW_STATE = {"open": "in_review", "request_approval": "awaiting_approval", "approve": "approved", "reject": "rejected"}


def _previous_field(row: dict, history: dict | None) -> dict | None:
    """The customer in the previous snapshot: absent from it (a later account), or its rank, score, place in that queue
    and where its review ended there. None when the run has no previous snapshot."""
    previous = (history or {}).get("previous")
    if previous is None:
        return None
    before = history["rows"].get(row["customer_id"])
    return {"cutoff": _iso(previous["cutoff"]), "run_id": previous["run_id"], "present": before is not None,
            "rank": _integer(before["rank"]) if before else None, "risk_score": _number(before["risk_score"]) if before else None,
            "selected_for_review": bool(before["selected_for_review"]) if before else None,
            "workflow_state": WORKFLOW_STATE.get(before["workflow_kind"]) if before else None}


def _earlier_decision(row: dict, history: dict | None) -> dict | None:
    decision = (history or {}).get("decisions", {}).get(row["customer_id"])
    if decision is None:
        return None
    return {"state": WORKFLOW_STATE[decision["kind"]], "decided_by": decision["reviewer_name"],
            "decided_at": _iso(decision["created_at"]), "cutoff": _iso(decision["cutoff"])}


def customer_item(row: dict, latest_disposition: str | None, summary: dict | None = None, refunds: dict | None = None,
                  history: dict | None = None) -> dict:
    """A customer as the queue shows it. `summary` is what scoring recorded for the run (the gate reads its heavy-returner cutoff).
    `refunds` maps customer ids to their refund totals (Store.refund_totals); None leaves the refund fields null. `history`
    is page_history for the page; None leaves the history fields null."""
    summary = summary or {}
    paid = None if refunds is None else refunds.get(row["customer_id"], {"refunded": 0, "claim_refunded": 0, "known": True})
    if paid is not None and not paid["known"]:
        paid = None
    outside = row["eligibility_status"] == "eligible" and not row["selected_for_review"]
    return {
        "basket_expectation": basket_expectation(row), "cleared_reason": (row.get("measures") or {}).get("cleared_reason"),
        "community": community_summary(row), "tier": tier(row), "gate_outcome": gate_outcome(row, summary),
        "primary_signals": primary_signals(row), "workflow": workflow(row, summary),
        "customer_id": row["customer_id"], "eligibility_status": row["eligibility_status"],
        "raw_score": _number(row["raw_score"]), "risk_score": _number(row["risk_score"]), "rank": _integer(row["rank"]),
        "selected_for_review": bool(row["selected_for_review"]), "baseline_rank": _integer(row["baseline_rank"]),
        "baseline_selected": bool(row["baseline_selected"]),
        "support_counts": {name: int(row[name]) for name in scoring.SUPPORT},
        "evidence_tags": list(row["evidence_tags"]),
        "wardrobing_status": row["wardrobing_status"], "latest_disposition": latest_disposition,
        # contract 1.14.0: observed refunds, and for a customer outside the queue the evidence it does not carry
        "refunded_inr": None if paid is None else round(float(paid["refunded"]), 2),
        "claim_refunded_inr": None if paid is None else round(float(paid["claim_refunded"]), 2),
        "absent_signals": [tag for tag in scoring.TAGS if tag not in set(row["evidence_tags"])] if outside else None,
        # contract 1.15.0 (AM-68): the same customer in the previous snapshot of its world, and its latest earlier decision
        "previous": _previous_field(row, history), "earlier_decision": _earlier_decision(row, history),
    }


EXPORT_COLUMNS = ["rank", "customer_id", "score", "tier", "recommendation", "primary_signals", "rule_rank", "rule_selected",
                  "mature_requested_units", "mature_purchased_units", "refunded_inr", "claim_refunded_inr", "linked_accounts",
                  "community_id", "wardrobing", "cleared_reason", "not_observed", "status", "opened_by", "decided_by",
                  "latest_reading", "previous_cutoff", "previous_rank", "previous_in_queue", "earlier_decision", "run_id",
                  "world_id", "cutoff"]


def _cell(value) -> str:
    """A CSV cell that a spreadsheet will not run: free text that starts like a formula gets a leading quote."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def export_row(item: dict, run: dict) -> list:
    """One queue row for the CSV export, from the item the list serves (so the two never disagree)."""
    community = item["community"] or {}
    workflow = item["workflow"]
    score = item["risk_score"]
    previous = item["previous"] or {}
    decision = item["earlier_decision"]
    in_previous = previous.get("selected_for_review")
    return [_cell(v) for v in (
        item["rank"], item["customer_id"], None if score is None else f"{score:.2f}", item["tier"], item["gate_outcome"],
        "; ".join(s["label"] for s in item["primary_signals"]), item["baseline_rank"], "yes" if item["baseline_selected"] else "no",
        item["support_counts"]["mature_requested_units"], item["support_counts"]["mature_purchased_units"],
        item["refunded_inr"], item["claim_refunded_inr"],
        f"{community['kind']} of {community['size']}" if community else "", community.get("id"), item["wardrobing_status"],
        item["cleared_reason"], "; ".join(item["absent_signals"] or []), workflow["state"], workflow["opened_by"],
        workflow["decided_by"], item["latest_disposition"], (previous.get("cutoff") or "")[:10] or None, previous.get("rank"),
        None if not previous else "not in snapshot" if not previous["present"] else "yes" if in_previous else "no",
        f"{decision['state']} on the {decision['cutoff'][:10]} snapshot by {decision['decided_by']}" if decision else None,
        run["id"], run["world_id"], _iso(run["cutoff"])[:10])]


def customer_queue(store: Store, run: dict, filters: dict, after: int | None, limit: int) -> tuple:
    """(items, next position). Order: rank, then unranked customers by identifier. Filters only choose what is shown."""
    summary = run["summary"] or {}
    rules = {"medium_from": TIER_MEDIUM_FROM, "heavy_cutoff": summary.get("heavy_returner_cutoff")}
    previous = previous_snapshot(store, run)
    rules.update(previous_run=previous["run_id"] if previous else None, world_id=run["world_id"], cutoff=run["cutoff"])
    rows = store.run_customers(run["id"], run["world_id"], filters, after, limit + 1, rules, run["dataset_id"])
    page = [row["customer_id"] for row in rows[:limit]]
    refunds = store.refund_totals(run["id"], page)
    history = page_history(store, run, page)
    items = [customer_item(row, row["latest_disposition"], summary, refunds, history) for row in rows[:limit]]
    return items, (rows[limit - 1]["queue_position"] if len(rows) > limit else None)


def _signal(code, label, value, denominator, unit, refs=()) -> dict:
    return {"code": code, "label": label, "value": _number(value), "denominator": _number(denominator), "unit": unit,
            "source_refs": list(refs)}


def _style_item(row: dict, reasons: list = ()) -> dict:
    unique = int(row["unique_returners"])
    flagged = row.get("flagged_returners")
    return {
        "style_id": row["style_id"], "category": row["category"], "state": row["state"],
        # the SKU screen's extras (contract 1.9.0); null for runs scored before it
        "name": row.get("name") or row["style_id"], "median_return_day": _number(row.get("median_return_day")),
        "share_in_last_five_days": _number(row.get("share_in_last_five_days")),
        "flagged_returner_share": None if flagged is None else {
            "numerator": int(flagged), "denominator": unique, "share": int(flagged) / unique if unique else None},
        "ring_returners": _integer(row.get("ring_returners")), "median_returner_score": _number(row.get("median_returner_score")),
        "reason_codes": [{"code": r["reason_code"], "group": r["reason_group"], "lines": int(r["lines"]), "units": int(r["units"])} for r in reasons],
        "mature_sale_lines": int(row["mature_sale_lines"]), "purchased_units": int(row["purchased_units"]),
        "requested_units": int(row["requested_units"]), "unique_returners": int(row["unique_returners"]),
        "raw_return_rate": _number(row["raw_return_rate"]), "shrunk_return_rate": _number(row["shrunk_return_rate"]),
        "damage_share": _number(row["damage_share"]), "claim_share": _number(row["claim_share"]),
        "linked_claim_share": _number(row["linked_claim_share"]), "linked_claimers": int(row["linked_claimers"]),
        "quality_signal": bool(row["quality_signal"]), "targeting_signal": bool(row["targeting_signal"]),
    }


def score_breakdown(store: Store, run: dict, customer: dict) -> dict | None:
    """The score with each feature family at typical values (decision D6): the honest reading is "the score with this family
    at typical values", never parts that sum to the score. Each row is also the counterfactual for that family removed:
    in_queue_without compares the re-scored raw score with the raw score at rank k, everyone else unchanged. None for a
    customer without a score and for runs scored before contract 1.7.0."""
    rows = store.run_attributions(run["id"], customer["customer_id"])
    if not rows:
        return None
    summary = run["summary"] or {}
    basis = summary.get("attribution") or {}
    read = set(summary.get("feature_order") or [])                      # the baseline reads one feature, a model all 43
    feature_count = {family: len(read.intersection(names)) for family, _, names in attribution.FAMILIES}
    by_family = {row["family"]: row for row in rows}
    families = []
    for family, label, _ in attribution.FAMILIES:
        row = by_family[family]
        score = float(row["score_without"])
        families.append({"family": family, "label": label, "feature_count": feature_count[family],
                         "raw_score_without": float(row["raw_score_without"]), "score_without": score,
                         "delta_points": float(row["delta_points"]), "in_queue_without": bool(row["in_queue_without"]),
                         "tier_without": "HIGH" if row["in_queue_without"] else "MEDIUM" if score >= TIER_MEDIUM_FROM else "LOW"})
    return {"method": "family_at_typical_values", "typical_from": basis.get("typical_from"),
            "threshold_raw_score": _number(basis.get("threshold_raw_score")), "families": families}


def rules_fired(customer: dict) -> list:
    """The analyst rulebook's five rules as they stand for this customer: report-only, never part of the score. `fired` is null
    when the rule's training threshold is not in the bundle, an input is missing, or the run predates contract 1.7.0."""
    measures = customer.get("measures") or {}
    return [{"rule_id": rule_id, "label": label, "fired": _boolean(measures.get("rule_" + rule_id))} for rule_id, label in attribution.RULES]


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
        _signal("expected_band_low", "Low edge of the normal band: expected units less two standard deviations",
                row.get("expected_band_low"), row["mature_purchased_units"], "units of mature purchased units"),
        _signal("expected_band_high", "High edge of the normal band: expected units plus two standard deviations",
                row.get("expected_band_high"), row["mature_purchased_units"], "units of mature purchased units"),
        _signal("bracketing_units", "Units bought as two or more sizes of one style in one order (size bracketing)",
                row.get("bracket_units_ordered"), row["mature_purchased_units"], "units of mature purchased units"),
        _signal("bracketing_kept_units", "Of the bracketed units, the ones kept", row.get("bracket_units_kept"),
                row.get("bracket_units_ordered"), "units of bracketed units"),
        _signal("median_return_day", "Median day after delivery at which this customer's return requests were made",
                row.get("median_return_day"), None, "days"),
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
        "styles": _style_items(store, run_id, store.run_customer_styles(run_id, customer_id, CASE_STYLES)),
        "wardrobing": {"status": row["wardrobing_status"], "indicator_score": _integer(row["indicator_score"]),
                       "signals": wardrobing_signals, "limitation": WARDROBING_LIMITATION},
        "community": community_detail(store, run_id, customer),
        "rules_fired": rules_fired(customer),
    }


def customer_history(store: Store, run: dict, customer_id: str, reviews: list) -> list:
    """The customer in every scored snapshot of its world, oldest cutoff first (decision AM-68): its place in that snapshot's
    reference run (this run for this run's snapshot), how its review ended there and how many notes were written under it.
    Every value is read from that snapshot's stored results; nothing is recomputed or carried between snapshots."""
    notes = {}
    for review in reviews:
        notes[review["dataset_id"]] = notes.get(review["dataset_id"], 0) + 1
    out = []
    for snapshot in store.snapshots(run["world_id"]):
        current = snapshot["dataset_id"] == run["dataset_id"]
        source = run if current else store.get_run(snapshot["run_id"])
        entry = {"dataset_id": snapshot["dataset_id"], "cutoff": _iso(snapshot["cutoff"]), "run_id": source["id"],
                 "model_kind": source["model_kind"], "current": current, "present": False, "eligibility_status": None,
                 "rank": None, "risk_score": None, "tier": None, "gate_outcome": None, "selected_for_review": None,
                 "mature_requested_units": None, "mature_purchased_units": None, "refunded_inr": None, "evidence_tags": [],
                 "community_kind": None, "workflow": None, "notes": notes.get(snapshot["dataset_id"], 0)}
        try:
            row = store.run_customer(source["id"], customer_id, run["world_id"], snapshot["dataset_id"])
        except NotFound:                                              # an account that did not exist yet at that cutoff
            out.append(entry)
            continue
        item = customer_item(row, None, source["summary"], store.refund_totals(source["id"], [customer_id]))
        entry.update(present=True, eligibility_status=item["eligibility_status"], rank=item["rank"], risk_score=item["risk_score"],
                     tier=item["tier"], gate_outcome=item["gate_outcome"], selected_for_review=item["selected_for_review"],
                     mature_requested_units=item["support_counts"]["mature_requested_units"],
                     mature_purchased_units=item["support_counts"]["mature_purchased_units"], refunded_inr=item["refunded_inr"],
                     evidence_tags=item["evidence_tags"], community_kind=(item["community"] or {}).get("kind"), workflow=item["workflow"])
        out.append(entry)
    return out


def case_body(store: Store, run: dict, customer: dict, review_body) -> dict:
    """The Case as the contract shows it: the customer row, its evidence, the group, the breakdown, the memo, the notes of
    every snapshot and the customer's history across the snapshots of its world."""
    case = customer_case(store, run["id"], customer)
    reviews = store.list_reviews(run["world_id"], customer["customer_id"])
    latest = reviews[-1]["disposition"] if reviews else None
    return {"run_id": run["id"], "dataset_id": run["dataset_id"], "world_id": run["world_id"], "model_id": run["model_id"],
            "model_kind": run["model_kind"], "cutoff": _iso(run["cutoff"]),
            "customer": customer_item(customer, latest, run["summary"], store.refund_totals(run["id"], [customer["customer_id"]]),
                                      page_history(store, run, [customer["customer_id"]])),
            "signals": case["signals"], "timeline": case["timeline"], "neighbors": case["neighbors"], "styles": case["styles"],
            "wardrobing": case["wardrobing"], "community": case["community"],
            "score_breakdown": score_breakdown(store, run, customer), "rules_fired": case["rules_fired"],
            "memo": memo_body(store, run, customer), "reviews": [review_body(r) for r in reviews],
            "history": customer_history(store, run, customer["customer_id"], reviews)}


def memo_body(store: Store, run: dict, customer: dict) -> dict:
    """The customer's investigation memo as the contract shows it. A memo exists only for a customer selected for review and only
    with status ok; pending means the run has succeeded and its memos are still being drafted; unavailable carries the reason.
    not_selected is every customer outside the queue. The content fields are null unless the status is ok."""
    empty = {"summary": None, "key_evidence": [], "alternative_explanations": [], "recommended_action": None,
             "attempts": 0, "reason": None, "model": None, "generated_at": None}
    if not customer["selected_for_review"]:
        return {"status": "not_selected", **empty}
    row = store.run_memo(run["id"], customer["customer_id"])
    if row is None:
        return {"status": "pending", **empty}
    content = row["memo"] or {}
    return {"status": row["status"], "summary": content.get("summary"), "key_evidence": list(content.get("key_evidence") or []),
            "alternative_explanations": list(content.get("alternative_explanations") or []),
            "recommended_action": content.get("recommended_action"), "attempts": int(row["attempts"]), "reason": row["reason"],
            "model": row["model"], "generated_at": _iso(row["generated_at"])}


def memo_progress(store: Store, run: dict) -> dict | None:
    """How far a succeeded run's memos are: {selected, ok, unavailable, complete}; None until the run succeeded."""
    if run["status"] != "succeeded":
        return None
    counts = store.memo_counts(run["id"])
    selected = int(run["selected_count"] or 0)
    return {"selected": selected, "ok": counts["ok"], "unavailable": counts["unavailable"],
            "complete": counts["ok"] + counts["unavailable"] >= selected}


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


def _style_items(store: Store, run_id: str, rows: list) -> list:
    """Style rows with their reason codes, fetched for the page in one query."""
    reasons = store.run_style_reasons(run_id, [row["style_id"] for row in rows])
    return [_style_item(row, reasons.get(row["style_id"], [])) for row in rows]


def style_queue(store: Store, run_id: str, state: str, after: str | None, limit: int) -> tuple:
    rows = store.run_styles(run_id, state, after, limit + 1)
    return _style_items(store, run_id, rows[:limit]), (rows[limit - 1]["style_id"] if len(rows) > limit else None)


def _returner(row: dict) -> dict:
    """A customer with a request on the style, with its own result in the run; the score is the customer's, not the style's."""
    return {"customer_id": row["customer_id"], "risk_score": _number(row["risk_score"]), "rank": _integer(row["rank"]),
            "selected_for_review": bool(row["selected_for_review"]), "tier": tier(row), "community": community_summary(row),
            "requested_units": int(row["requested_units"]), "claim_lines": int(row["claim_lines"]), "linked_claim_lines": int(row["linked_claim_lines"]),
            "return_lines": _integer(row.get("return_lines")), "purchased_lines": _integer(row.get("purchased_lines")),
            "last_reason_code": row.get("last_reason_code")}


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
    returners = [_returner(r) for r in store.run_style_returners(run_id, style_id, STYLE_CUSTOMERS)]
    return {"style": _style_items(store, run_id, [row])[0],
            "skus": [{"sku": s["sku"], "style_id": s["style_id"], "size": str(s["size"]), "colour": str(s["colour"]),
                      "unit_price_inr": float(s["unit_price"]), "mature_sale_lines": int(s["mature_sale_lines"]),
                      "purchased_units": int(s["purchased_units"]), "requested_units": int(s["requested_units"]),
                      "support_status": s["support_status"]} for s in store.run_style_skus(run_id, style_id)],
            "customer_ids": [r["customer_id"] for r in returners], "returners": returners, "signals": signals}


# ------------------------------------------------------------------ experiments (published offline, synthetic only)
SEED_KEYS = ("train_seeds", "validation_seeds", "test_seeds", "demo_seeds", "stress_seeds")
CURVE_POINTS = 200


def experiment_summary(report: dict) -> dict:
    """The published summary as the contract shows it; a report published before contract 1.10.0 lacks the manifest fields."""
    summary = dict(report["summary"])
    summary.setdefault("git_sha", None)
    for name in SEED_KEYS:
        summary[name] = [int(seed) for seed in (summary.get(name) or [])]
    return summary


def curves(store: Store, experiment: dict, run: dict, max_points: int) -> dict:
    """Abusers caught and legitimate heavy returners reviewed by the model's first k and the return-rate rule's first k, for a
    run on the experiment's truth world (synthetic truth; the evaluation page only).

    Every k from 1 to the eligible count is counted; at most `max_points` are returned, thinned evenly, always keeping
    k = 1, the review budget and the last k. The last point carries the totals.
    """
    summary = run["summary"] or {}
    rows = store.curve_points(experiment["id"], run["id"], summary.get("heavy_returner_cutoff"))
    budget = summary.get("review_budget_k")
    keep = set()
    if rows:
        step = max(1, len(rows) / max(1, max_points - 1))
        keep = {rows[min(len(rows) - 1, int(round(i * step)))]["k"] for i in range(max_points)} | {rows[0]["k"], rows[-1]["k"]}
        if budget:
            keep.add(budget)
    points = [{"k": int(r["k"]), "model_abusers_caught": int(r["model_abusers"]), "model_legitimate_heavy_reviewed": int(r["model_heavy"]),
               "baseline_abusers_caught": int(r["baseline_abusers"]), "baseline_legitimate_heavy_reviewed": int(r["baseline_heavy"])}
              for r in rows if r["k"] in keep]
    last = rows[-1] if rows else None
    return {"synthetic_only": True, "experiment_id": experiment["id"], "run_id": run["id"], "world_id": experiment["truth_world_id"],
            "eligible_count": int(last["k"]) if last else 0, "review_budget": _integer(budget),
            "heavy_returner_cutoff": _number(summary.get("heavy_returner_cutoff")),
            "abusers": int(last["model_abusers"]) if last else 0, "legitimate_heavy_returners": int(last["model_heavy"]) if last else 0,
            "points": points}


# ------------------------------------------------------------------ experiment truth (published offline, synthetic only)
def truth_page(store: Store, experiment: dict, after: int | None, limit: int) -> tuple:
    """(items, next position, world) of the demonstration world's synthetic truth, for the evaluation page only."""
    rows = store.experiment_truth(experiment["id"], after, limit + 1)
    items = [{"customer_id": r["customer_id"], "y_abuse": int(r["y_abuse"]), "action_types": list(r["action_types"])} for r in rows[:limit]]
    return items, (rows[limit]["position"] if len(rows) > limit else None), experiment["truth_world_id"]
