"""Structural validation of an operational world (final-spec components 03 and 04).

A world is seven CSV files plus manifest.json. Any structural failure rejects the whole world; nothing is
imputed, deleted or repaired. The report lists rule, table, example key and count for every violation.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema
import numpy as np
import pandas as pd
import yaml

from arai.catalog import load_catalog
from arai.paths import SPEC_ROOT

TABLES = ("customer_master", "sku_master", "reason_code", "sales_order", "sales_order_line", "return_order", "return_order_line")
OFFSET = "+05:30"
EPSILON = 0.005     # money is written to the paisa; comparisons allow half a paisa
MAX_UPLOAD_BYTES = 500_000_000     # final-spec component 11 resource limits
MAX_UPLOAD_ROWS = 2_000_000


@dataclass
class Report:
    world_id: str | None = None
    violations: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)

    @property
    def accepted(self) -> bool:
        return not self.violations

    def add(self, rule_id: str, table: str | None, message: str, keys=None, count: int | None = None):
        keys = [] if keys is None else list(keys)
        total = len(keys) if count is None else count
        if total:
            self.violations.append({"rule_id": rule_id, "table": table, "severity": "error", "count": int(total),
                                    "row_key": None if not keys else str(keys[0]), "message": message})

    def to_dict(self) -> dict:
        return {"accepted": self.accepted, "world_id": self.world_id, "row_counts": self.counts, "violations": self.violations}


def _keys(frame: pd.DataFrame, mask, columns) -> list:
    return ["|".join(map(str, row)) for row in frame.loc[np.asarray(mask, dtype=bool), columns].head(5).itertuples(index=False)]


def _flag(report: Report, rule: str, table: str, message: str, frame: pd.DataFrame, mask, columns):
    mask = np.asarray(mask, dtype=bool)
    if mask.any():
        report.add(rule, table, message, _keys(frame, mask, columns), int(mask.sum()))


def _parse(report: Report, name: str, raw: pd.DataFrame, spec: dict, key: list) -> pd.DataFrame:
    """Type, nullability, enum and bound checks; returns a typed copy (unparseable cells become null)."""
    typed = {}
    for column, rules in spec["columns"].items():
        text = raw[column]
        empty = text == ""
        if not rules.get("nullable", False):
            _flag(report, "T003", name, f"{column} is required but empty", raw, empty, key)
        kind = rules["type"]
        if kind == "date":
            values = pd.to_datetime(text.where(~empty), format="%Y-%m-%d", errors="coerce")
            bad = values.isna() & ~empty
        elif kind == "timestamp":
            has_offset = text.str.endswith(OFFSET)
            values = pd.to_datetime(text.str.slice(0, 19).where(~empty & has_offset), format="%Y-%m-%dT%H:%M:%S", errors="coerce")
            bad = values.isna() & ~empty
        elif kind in ("number", "integer"):
            values = pd.to_numeric(text.where(~empty), errors="coerce")
            bad = values.isna() & ~empty
            if kind == "integer":
                bad |= values.notna() & (values % 1 != 0)
            else:
                bad |= ~empty & ~text.str.fullmatch(r"-?\d+(\.\d{1,2})?")
        else:
            values = text.where(~empty, None)
            bad = pd.Series(False, index=raw.index)
        _flag(report, "T001", name, f"{column} is not a valid {kind}", raw, bad, key)
        if "enum" in rules:
            allowed = {str(v) for v in rules["enum"]}
            _flag(report, "T002", name, f"{column} outside its allowed values", raw, ~empty & ~text.isin(allowed), key)
        if "const" in rules:
            _flag(report, "T002", name, f"{column} must equal {rules['const']}", raw, text != str(rules["const"]), key)
        if kind in ("number", "integer"):
            if "minimum" in rules:
                _flag(report, "T004", name, f"{column} below minimum {rules['minimum']}", raw, values < rules["minimum"], key)
            if "exclusive_minimum" in rules:
                _flag(report, "T004", name, f"{column} must exceed {rules['exclusive_minimum']}", raw,
                      values <= rules["exclusive_minimum"], key)
        typed[column] = values
    return pd.DataFrame(typed)


def validate_world(directory: Path, spec_root: Path | None = None) -> Report:
    directory, spec_root = Path(directory), Path(spec_root or SPEC_ROOT)
    schema = yaml.safe_load((spec_root / "contracts" / "data-schema.yaml").read_text(encoding="utf-8"))["tables"]
    report = Report()

    # ---- manifest and files
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        report.add("M001", None, "manifest.json is missing", count=1)
        return report
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report.world_id = manifest.get("world_id")
    manifest_schema = json.loads((spec_root / "contracts" / "manifest.schema.json").read_text(encoding="utf-8"))
    errors = sorted(jsonschema.Draft202012Validator(manifest_schema).iter_errors(manifest), key=lambda e: list(e.path))
    for error in errors:
        report.add("M001", None, f"manifest: {error.message}", ["/".join(map(str, error.path))], 1)
    if errors:
        return report
    present = {p.name for p in directory.iterdir() if p.is_file()}
    expected = {f"{t}.csv" for t in TABLES} | {"manifest.json"}
    report.add("M003", None, "unexpected file in the upload (private or unknown)", sorted(present - expected))
    report.add("M003", None, "required file missing", sorted(expected - present))
    if present != expected:
        return report

    size = sum((directory / f"{t}.csv").stat().st_size for t in TABLES)
    if size > MAX_UPLOAD_BYTES:
        report.add("L001", None, "upload exceeds the size limit", [f"{size} bytes"], 1)
        return report

    raw = {}
    for name in TABLES:
        path = directory / f"{name}.csv"
        entry = manifest["files"][name]
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            report.add("M002", name, "file hash differs from the manifest", [path.name], 1)
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
        report.counts[name] = len(frame)
        if len(frame) != entry["row_count"]:
            report.add("M002", name, "row count differs from the manifest", [f"{len(frame)} != {entry['row_count']}"], 1)
        wanted = list(schema[name]["columns"])
        report.add("S001", name, "unknown or private column", [c for c in frame.columns if c not in wanted])
        report.add("S002", name, "required column missing", [c for c in wanted if c not in frame.columns])
        raw[name] = frame
    if sum(report.counts.values()) > MAX_UPLOAD_ROWS:
        report.add("L001", None, "upload exceeds the row limit", [f"{sum(report.counts.values())} rows"], 1)
    if report.violations:
        return report

    data = {}
    for name in TABLES:
        key = schema[name]["primary_key"]
        data[name] = _parse(report, name, raw[name], schema[name], key)
        _flag(report, "K001", name, "duplicate primary key", raw[name], raw[name].duplicated(key, keep=False), key)
    if report.violations:
        return report

    # ---- reference conformance: the codebook always, the bundled catalog for generated worlds
    codebook = pd.read_csv(spec_root / "assets" / "reason_codes.csv", dtype=str, keep_default_na=False)
    listed = raw["reason_code"].sort_values("reason_code").reset_index(drop=True)
    if not listed.equals(codebook[listed.columns].sort_values("reason_code").reset_index(drop=True)):
        differing = sorted(set(map(tuple, listed.to_numpy())) ^ set(map(tuple, codebook[listed.columns].to_numpy())))
        report.add("G001", "reason_code", "reason_code differs from the bundled codebook", [row[0] for row in differing][:5],
                   max(1, len(differing)))
    if manifest["purpose"] != "external":
        catalog = load_catalog(spec_root).sku_master.assign(launch_date=lambda f: pd.to_datetime(f["launch_date"]))
        compared = ["style_id", "brand", "category", "size", "colour", "unit_price", "price_band", "return_window_days",
                    "is_occasion_wear", "launch_date", "active_flag"]
        both = data["sku_master"].merge(catalog, on="sku", how="outer", suffixes=("", "_catalog"), indicator=True)
        wrong = both["_merge"] != "both"
        for column in compared:
            wrong |= ~(both[column].astype(str) == both[column + "_catalog"].astype(str)) & (both["_merge"] == "both")
        _flag(report, "G002", "sku_master", "sku_master differs from the bundled catalog", both, wrong, ["sku"])
    if report.violations:
        return report

    cutoff = pd.Timestamp(manifest["cutoff"][:19])
    cutoff_date = cutoff.normalize()
    history_start = pd.Timestamp(manifest["history_start"])
    customers, skus, reasons = data["customer_master"], data["sku_master"], data["reason_code"]
    orders, lines = data["sales_order"], data["sales_order_line"]
    headers, returns = data["return_order"], data["return_order_line"]
    line_key = ["order_id", "order_line_no"]
    return_key = ["return_order_id", "return_line_no"]

    # ---- references and ownership
    _flag(report, "F001", "sales_order", "customer_id not in customer_master", orders, ~orders["customer_id"].isin(customers["customer_id"]), ["order_id"])
    _flag(report, "F001", "sales_order_line", "order_id not in sales_order", lines, ~lines["order_id"].isin(orders["order_id"]), line_key)
    _flag(report, "F001", "sales_order_line", "sku not in sku_master", lines, ~lines["sku"].isin(skus["sku"]), line_key)
    _flag(report, "F001", "return_order", "customer_id not in customer_master", headers, ~headers["customer_id"].isin(customers["customer_id"]), ["return_order_id"])
    _flag(report, "F001", "return_order_line", "return_order_id not in return_order", returns, ~returns["return_order_id"].isin(headers["return_order_id"]), return_key)
    _flag(report, "F001", "return_order_line", "reason_code not in reason_code", returns, ~returns["reason_code"].isin(reasons["reason_code"]), return_key)
    _flag(report, "F001", "sales_order", "order has no lines", orders, ~orders["order_id"].isin(lines["order_id"]), ["order_id"])
    _flag(report, "F001", "return_order", "return header has no lines", headers, ~headers["return_order_id"].isin(returns["return_order_id"]), ["return_order_id"])
    if report.violations:
        return report

    order_view = orders.merge(customers[["customer_id", "signup_date"]], on="customer_id", how="left")
    sale = lines.merge(order_view[["order_id", "customer_id", "order_date", "signup_date"]], on="order_id", how="left") \
                .merge(skus[["sku", "launch_date"]], on="sku", how="left")
    ret = returns.merge(sale[line_key + ["sku", "quantity", "line_total", "line_status", "delivered_date", "return_window_days",
                                         "customer_id"]], on=line_key, how="left", suffixes=("", "_sale")) \
                 .merge(headers[["return_order_id", "customer_id", "available_at"]], on="return_order_id", how="left",
                        suffixes=("", "_header")) \
                 .merge(reasons[["reason_code", "requires_item_return"]], on="reason_code", how="left")
    _flag(report, "F001", "return_order_line", "referenced sale line does not exist", ret, ret["line_status_sale"].isna(), return_key)
    if report.violations:
        return report
    _flag(report, "F002", "return_order_line", "return customer differs from the order's customer", ret,
          ret["customer_id"] != ret["customer_id_header"], return_key)
    _flag(report, "F003", "return_order_line", "returned sku differs from the sale line", ret, ret["sku"] != ret["sku_sale"], return_key)
    _flag(report, "F003", "return_order_line", "referenced sale line is not delivered", ret, ret["line_status_sale"] != "delivered", return_key)

    # ---- chronology and sale-line state
    _flag(report, "C001", "sales_order", "order before signup", order_view, order_view["order_date"] < order_view["signup_date"], ["order_id"])
    _flag(report, "C001", "sales_order", "order outside the history window", orders,
          (orders["order_date"] < history_start) | (orders["order_date"] > cutoff_date), ["order_id"])
    _flag(report, "C001", "sales_order_line", "order before SKU launch", sale, sale["order_date"] < sale["launch_date"], line_key)
    no_ship = sale["line_status"].isin(["awaiting_dispatch", "cancelled"])
    _flag(report, "C002", "sales_order_line", "shipped_date must be empty exactly for awaiting_dispatch/cancelled", sale,
          no_ship != sale["shipped_date"].isna(), line_key)
    _flag(report, "C002", "sales_order_line", "delivered_date must be present exactly for delivered", sale,
          (sale["line_status"] == "delivered") != sale["delivered_date"].notna(), line_key)
    _flag(report, "C002", "sales_order_line", "shipping chronology broken", sale,
          (sale["shipped_date"] < sale["order_date"]) | (sale["delivered_date"] < sale["shipped_date"])
          | (sale["shipped_date"] > cutoff_date) | (sale["delivered_date"] > cutoff_date), line_key)

    # ---- money and quantity
    _flag(report, "A001", "sales_order_line", "line_total != quantity*unit_price - line_discount", lines,
          (lines["quantity"] * lines["unit_price"] - lines["line_discount"] - lines["line_total"]).abs() > EPSILON, line_key)
    subtotal = lines.groupby("order_id")["line_total"].sum().reindex(orders["order_id"]).to_numpy()
    _flag(report, "A001", "sales_order", "order_subtotal != sum of line totals", orders, np.abs(subtotal - orders["order_subtotal"]) > EPSILON, ["order_id"])
    _flag(report, "A001", "sales_order", "order_total != subtotal + shipping", orders,
          (orders["order_subtotal"] + orders["order_shipping"] - orders["order_total"]).abs() > EPSILON, ["order_id"])
    active = ret[ret["line_status"] != "withdrawn"]
    requested = active.groupby(line_key)["quantity_returned"].sum().reset_index().merge(lines[line_key + ["quantity"]], on=line_key)
    _flag(report, "Q001", "return_order_line", "non-withdrawn requested quantity exceeds purchased quantity", requested,
          requested["quantity_returned"] > requested["quantity"], line_key)
    net_unit = ret["line_total"] / ret["quantity"]
    _flag(report, "A002", "return_order_line", "refund on a line that is not refunded", ret,
          (ret["line_status"] != "refunded") & (ret["refund_amount"] > EPSILON), return_key)
    _flag(report, "A002", "return_order_line", "refund exceeds requested net value", ret,
          ret["refund_amount"] > ret["quantity_returned"] * net_unit + EPSILON, return_key)
    refunds = returns.groupby("return_order_id")["refund_amount"].sum().reindex(headers["return_order_id"]).to_numpy()
    _flag(report, "A002", "return_order", "refund_total != sum of line refunds", headers, np.abs(refunds - headers["refund_total"]) > EPSILON, ["return_order_id"])

    # ---- return timing, availability and state
    days = (ret["requested_at"].dt.normalize() - ret["delivered_date"]).dt.days
    _flag(report, "C003", "return_order_line", "request before delivery", ret, days < 0, return_key)
    _flag(report, "C003", "return_order_line", "request or availability after the cutoff", ret,
          (ret["requested_at"] > cutoff) | (ret["available_at"] > cutoff) | (ret["available_at"] < ret["requested_at"]), return_key)
    _flag(report, "C003", "return_order", "header after the cutoff", headers,
          (headers["available_at"] > cutoff) | (headers["return_created_at"] > cutoff), ["return_order_id"])
    _flag(report, "C003", "return_order_line", "header available before its latest line", ret,
          ret["available_at_header"] < ret["available_at"], return_key)
    _flag(report, "R001", "return_order_line", "out-of-window request was refunded", ret,
          (days > ret["return_window_days"]) & (ret["line_status"] == "refunded"), return_key)
    no_item = ret["requires_item_return"] == 0
    _flag(report, "R002", "return_order_line", "return_received_flag must be empty exactly for no-item reasons", ret,
          no_item != ret["return_received_flag"].isna(), return_key)
    needs_item = (~no_item).groupby(ret["return_order_id"]).any().reindex(headers["return_order_id"]).to_numpy(dtype=bool)
    _flag(report, "R003", "return_order", "return_channel must be not_applicable exactly when no line needs an item", headers,
          needs_item == (headers["return_channel"] == "not_applicable").to_numpy(), ["return_order_id"])
    return report


def write_report(report: Report, path: Path) -> None:
    Path(path).write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
