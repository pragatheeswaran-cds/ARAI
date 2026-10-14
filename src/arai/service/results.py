"""Run results as database rows (final-spec components 11 and 14, decision AM-39).

Scoring produces data frames; the store copies rows. This module is the only place that knows how one becomes
the other, and its column lists mirror migrations/0002_results_in_postgres.sql.
"""
from __future__ import annotations

import pandas as pd
from psycopg.types.json import Jsonb

from arai.service.scoring import SUPPORT, RunOutput

CUSTOMERS = (("queue_position", "int"), ("customer_id", "text"), ("eligibility_status", "text"), ("raw_score", "float"),
             ("risk_score", "float"), ("rank", "int"), ("baseline_rank", "int"), ("selected_for_review", "bool"),
             ("baseline_selected", "bool"), *((name, "int") for name in SUPPORT), ("wardrobing_status", "text"),
             ("indicator_score", "int"))
STYLES = (("style_id", "text"), ("category", "text"), ("state", "text"), ("mature_sale_lines", "int"), ("purchased_units", "int"),
          ("requested_units", "int"), ("unique_returners", "int"), ("quality_units", "int"), ("claim_units", "int"),
          ("claim_lines", "int"), ("linked_claim_lines", "int"), ("linked_claimers", "int"), ("raw_return_rate", "float"),
          ("shrunk_return_rate", "float"), ("damage_share", "float"), ("claim_share", "float"), ("linked_claim_share", "float"),
          ("quality_signal", "bool"), ("targeting_signal", "bool"))
SKUS = (("sku", "text"), ("style_id", "text"), ("size", "text"), ("colour", "text"), ("unit_price", "float"),
        ("mature_sale_lines", "int"), ("purchased_units", "int"), ("requested_units", "int"), ("support_status", "text"))
NEIGHBORS = (("customer_id", "text"), ("neighbor_id", "text"), ("shared_value_count", "int"), ("supported", "bool"),
             ("max_value_fanout", "int"), ("coordinated_claim_matches", "int"))
TIMELINE = (("customer_id", "text"), ("source_ref", "text"), ("event_type", "text"), ("observed_at", "text"),
            ("description", "text"), ("amount_inr", "float"), ("style_id", "text"), ("sku", "text"),
            # the facts of the event as columns (migration 0004); a column that does not apply to an event kind is null
            ("order_id", "text"), ("order_line_no", "int"), ("quantity", "int"), ("size", "text"), ("reason_code", "text"),
            ("reason_group", "text"), ("day_in_window", "int"), ("window_days", "int"), ("line_status", "text"),
            ("item_received", "bool"), ("linked_claim", "bool"))
CUSTOMER_STYLES = (("customer_id", "text"), ("style_id", "text"), ("requested_units", "int"), ("claim_lines", "int"),
                   ("linked_claim_lines", "int"))
CASTS = {"int": int, "float": float, "bool": bool, "text": str}


def _values(series: pd.Series, kind: str | None = None) -> list:
    """Plain Python values of a column, every kind of missing value as None, cast to the column's type."""
    cast = CASTS.get(kind, lambda value: value)
    return [None if value is None or value is pd.NA or (isinstance(value, float) and value != value) else cast(value)
            for value in series.tolist()]


def _rows(frame: pd.DataFrame, spec: tuple) -> list:
    """Rows in the spec's column order. A column the frame lacks (a run scored before it existed) is null throughout."""
    if not len(frame):
        return []
    absent = pd.Series([None] * len(frame), index=frame.index, dtype=object)
    return list(zip(*[_values(frame[name] if name in frame else absent, kind) for name, kind in spec]))


def _split(series: pd.Series) -> list:
    return [[part for part in str(value or "").split("|") if part] for value in _values(series)]


def tables(output: RunOutput) -> dict:
    """{table: (columns, rows)} for one scored run, ready to be copied. The run identifier is added by the store."""
    customers = output.customers
    typed = {name for name, _ in CUSTOMERS} | {"evidence_tags", "eligible"}
    rest = [name for name in customers.columns if name not in typed]
    measures = [Jsonb(dict(zip(rest, row))) for row in zip(*[_values(customers[name]) for name in rest])]
    customer_rows = [(*row, tags, measured) for row, tags, measured in
                     zip(_rows(customers, CUSTOMERS), _split(customers["evidence_tags"]), measures)]
    neighbor_rows = [(*row, shared) for row, shared in zip(_rows(output.neighbors, NEIGHBORS), _split(output.neighbors["shared_types"]))]
    timeline_rows = [(seq, *row) for seq, row in enumerate(_rows(output.timeline, TIMELINE), start=1)]
    names = lambda spec: [name for name, _ in spec]  # noqa: E731
    return {
        "run_customers": ([*names(CUSTOMERS), "evidence_tags", "measures"], customer_rows),
        "run_styles": (names(STYLES), _rows(output.styles, STYLES)),
        "run_skus": (names(SKUS), _rows(output.skus, SKUS)),
        "run_neighbors": ([*names(NEIGHBORS), "shared_types"], neighbor_rows),
        "run_timeline": (["seq", *names(TIMELINE)], timeline_rows),
        "run_customer_styles": (names(CUSTOMER_STYLES), _rows(output.customer_styles, CUSTOMER_STYLES)),
    }


def counts(summary: dict) -> dict:
    return {name: summary[name] for name in ("eligible_count", "excluded_count", "selected_count", "model_only_count",
                                             "baseline_only_count")}
