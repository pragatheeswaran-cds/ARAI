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


def test_unknown_category_and_changed_catalog_are_rejected_with_the_sku_key(copy):
    def change(frame):
        frame.loc[0, "category"] = "Sari"
        frame.loc[1, "unit_price"] = "1.00"
        return frame
    _rewrite(copy, "sku_master", change)
    report = validate_world(copy)
    assert "T002" in _rules(report)                    # the enum failure stops validation before the catalog comparison
    assert any(v["rule_id"] == "T002" and v["row_key"] == "SKU001" for v in report.violations)


def test_changed_catalog_price_is_rejected(copy):
    def change(frame):
        frame.loc[1, "unit_price"] = "1.00"
        return frame
    _rewrite(copy, "sku_master", change)
    report = validate_world(copy)
    assert any(v["rule_id"] == "G002" and v["row_key"] == "SKU002" for v in report.violations)


def test_changed_codebook_is_rejected(copy):
    _rewrite(copy, "reason_code", lambda f: f.assign(is_high_risk=["1"] + list(f["is_high_risk"][1:])))
    assert "G001" in _rules(validate_world(copy))


def test_violations_name_the_offending_key(copy):
    def change(frame):
        frame.loc[0, "customer_id"] = frame.loc[frame["customer_id"] != frame.loc[0, "customer_id"], "customer_id"].iloc[0]
        return frame
    first = pd.read_csv(copy / "return_order.csv", dtype=str).loc[0, "return_order_id"]
    _rewrite(copy, "return_order", change)
    report = validate_world(copy)
    ownership = [v for v in report.violations if v["rule_id"] == "F002"]
    assert ownership and ownership[0]["table"] == "return_order_line" and ownership[0]["row_key"].startswith(first)


def test_command_line_exits_nonzero_on_a_rejected_world(copy, capsys):
    from arai.cli import main
    assert main(["validate", str(copy)]) == 0
    (copy / "leak.csv").write_text("x\n", encoding="utf-8")
    assert main(["validate", str(copy)]) == 1
    assert '"accepted": false' in capsys.readouterr().out


def test_optional_evidence_may_be_empty_without_losing_customers(written, world):
    lines = pd.read_csv(written["operational"] / "return_order_line.csv", dtype=str, keep_default_na=False)
    assert (lines["reason_text"] == "").all() and (lines["disposition"] == "").all()
    report = validate_world(written["operational"])
    assert report.accepted and report.counts["customer_master"] == world.n_customers


def test_catalog_hash_and_adapter_transforms_are_recorded(written):
    import hashlib
    from arai.paths import SPEC_ROOT
    source = hashlib.sha256((SPEC_ROOT / "assets" / "sku_master_source.csv").read_bytes()).hexdigest()
    assert written["manifest"]["generator"]["catalog_sha256"] == source
    private = json.loads((written["private"] / "private-manifest.json").read_text(encoding="utf-8"))
    assert private["catalog_transforms"] == ["rename sku_id->sku", "rename color->colour", "rename color_id->colour_id",
                                             "is_occasion_wear True/False->1/0", "active_flag True/False->1/0"]
