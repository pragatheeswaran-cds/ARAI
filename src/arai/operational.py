"""Read an operational world (seven CSV files plus manifest.json) into typed tables.

This is the only way data enters serving. It reads exactly the contract's columns; private truth has no place
in an operational directory and the validator rejects any extra file or column before this is called.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from arai.paths import SPEC_ROOT

TABLES = ("customer_master", "sku_master", "reason_code", "sales_order", "sales_order_line", "return_order", "return_order_line")


def _schema(spec_root: Path | None = None) -> dict:
    return yaml.safe_load((Path(spec_root or SPEC_ROOT) / "contracts" / "data-schema.yaml").read_text(encoding="utf-8"))["tables"]


def read_csv_table(path: Path, columns: dict) -> pd.DataFrame:
    """One validated CSV as a typed table: dates and timestamps as local naive datetimes, empty cells as nulls."""
    raw = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    out = {}
    for name, rules in columns.items():
        text, kind = raw[name], rules["type"]
        empty = text == ""
        if kind == "date":
            out[name] = pd.to_datetime(text.where(~empty), format="%Y-%m-%d").astype("datetime64[ms]")
        elif kind == "timestamp":                                   # written with the +05:30 offset; kept as local time
            out[name] = pd.to_datetime(text.str.slice(0, 19).where(~empty), format="%Y-%m-%dT%H:%M:%S").astype("datetime64[ms]")
        elif kind == "number":
            out[name] = pd.to_numeric(text.where(~empty)).astype("float64")
        elif kind == "integer":
            values = pd.to_numeric(text.where(~empty))
            out[name] = values.astype("Int64") if rules.get("nullable") else values.astype("int64")
        else:
            out[name] = text.where(~empty, None)
    return pd.DataFrame(out)


def read_csv_world(directory: Path, spec_root: Path | None = None) -> tuple:
    """(tables, manifest) from a directory that has already passed validation."""
    directory = Path(directory)
    schema = _schema(spec_root)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    tables = {name: read_csv_table(directory / f"{name}.csv", schema[name]["columns"]) for name in TABLES}
    return tables, manifest


def cutoff_date(manifest: dict):
    return pd.Timestamp(manifest["cutoff"][:10]).date()
