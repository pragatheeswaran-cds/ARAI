"""The validator accepts a generated world and rejects each class of structural defect (VAL-AC-01, DATA-AC-01/02)."""
import hashlib
import json
import shutil

import pandas as pd
import pytest

from arai.validation import validate_world


def _rules(report):
    return {v["rule_id"] for v in report.violations}


@pytest.fixture
def copy(written, tmp_path):
    target = tmp_path / "operational"
    shutil.copytree(written["operational"], target)
    return target


def _rewrite(directory, table, change):
    """Apply `change` to one CSV and bring the manifest hash and row count back in line."""
    path = directory / f"{table}.csv"
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame = change(frame)
    frame.to_csv(path, index=False, lineterminator="\n", encoding="utf-8")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"][table].update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), row_count=len(frame))
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_generated_world_is_accepted(written):
    report = validate_world(written["operational"])
    assert report.accepted, report.violations
    assert report.world_id == "W2001" and len(report.counts) == 7


def test_changed_file_without_manifest_update_is_rejected(copy):
    with open(copy / "sales_order.csv", "a", encoding="utf-8") as handle:
        handle.write("\n")
    assert "M002" in _rules(validate_world(copy))


def test_extra_or_private_file_is_rejected(copy):
    (copy / "customer_truth.csv").write_text("customer_id,y_abuse\n", encoding="utf-8")
    assert "M003" in _rules(validate_world(copy))


def test_private_column_is_rejected(copy):
    _rewrite(copy, "customer_master", lambda f: f.assign(persona="Loyalist"))
    assert "S001" in _rules(validate_world(copy))


def test_missing_required_column_is_rejected(copy):
    _rewrite(copy, "sales_order", lambda f: f.drop(columns="device_id"))
    assert "S002" in _rules(validate_world(copy))


def test_duplicate_key_is_rejected(copy):
    _rewrite(copy, "sales_order", lambda f: pd.concat([f, f.head(1)], ignore_index=True))
    assert "K001" in _rules(validate_world(copy))


def test_bad_type_enum_and_null_are_rejected(copy):
    def change(frame):
        frame.loc[0, "quantity"] = "two"
        frame.loc[1, "line_status"] = "teleported"
        frame.loc[2, "sku"] = ""
        return frame
    _rewrite(copy, "sales_order_line", change)
    assert {"T001", "T002", "T003"} <= _rules(validate_world(copy))


def test_negative_money_is_rejected(copy):
    _rewrite(copy, "sales_order_line", lambda f: f.assign(line_discount=["-1.00"] + list(f["line_discount"][1:])))
    assert "T004" in _rules(validate_world(copy))


def test_unknown_customer_is_rejected(copy):
    _rewrite(copy, "sales_order", lambda f: f.assign(customer_id=["W2001-C99999"] + list(f["customer_id"][1:])))
    assert "F001" in _rules(validate_world(copy))


def test_cross_customer_return_is_rejected(copy):
    def change(frame):
        frame.loc[0, "customer_id"] = frame.loc[frame["customer_id"] != frame.loc[0, "customer_id"], "customer_id"].iloc[0]
        return frame
    _rewrite(copy, "return_order", change)
    assert "F002" in _rules(validate_world(copy))


def test_future_delivery_is_rejected(copy):
    def change(frame):
        row = frame.index[frame["line_status"] == "delivered"][0]
        frame.loc[row, "delivered_date"] = "2026-12-01"
        return frame
    _rewrite(copy, "sales_order_line", change)
    assert "C002" in _rules(validate_world(copy))


def test_excess_return_quantity_is_rejected(copy):
    def change(frame):
        row = frame.index[frame["line_status"] != "withdrawn"][0]
        frame.loc[row, "quantity_returned"] = "9"
        return frame
    _rewrite(copy, "return_order_line", change)
    assert "Q001" in _rules(validate_world(copy))


def test_refund_on_pending_line_is_rejected(copy):
    def change(frame):
        row = frame.index[frame["line_status"] == "pending"][0]
        frame.loc[row, "refund_amount"] = "10.00"
        return frame
    _rewrite(copy, "return_order_line", change)
    assert "A002" in _rules(validate_world(copy))


def test_request_after_cutoff_is_rejected(copy):
    def change(frame):
        frame.loc[0, ["requested_at", "available_at"]] = "2026-09-10T08:00:00+05:30"
        return frame
    _rewrite(copy, "return_order_line", change)
    assert "C003" in _rules(validate_world(copy))


def test_money_identity_is_checked(copy):
    def change(frame):
        frame.loc[0, "order_subtotal"] = f"{float(frame.loc[0, 'order_subtotal']) + 5:.2f}"
        return frame
    _rewrite(copy, "sales_order", change)
    assert "A001" in _rules(validate_world(copy))
