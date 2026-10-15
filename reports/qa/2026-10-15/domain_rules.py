"""Returns-domain integrity: feed the snapshot validator copies of W5401 that each break one rule of the returns process,
and report whether it rejects them. Read-only on the real world; copies live in a temporary folder."""
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

from arai.validation import validate_world

SRC = Path("/home/user/ARAI/data/EXP-20261005-04/artifacts/worlds/W5401/operational")
work = Path(tempfile.mkdtemp(prefix="arai-domain-"))

base = {name: pd.read_csv(SRC / f"{name}.csv", dtype=str, keep_default_na=False) for name in
        ("customer_master", "sku_master", "reason_code", "sales_order", "sales_order_line", "return_order", "return_order_line")}

print("== the real W5401 first")
print("  accepted:", validate_world(SRC).accepted)

# facts about the real data a returns analyst would ask about
sol = base["sales_order_line"].assign(quantity=lambda f: f["quantity"].astype(int))
rol = base["return_order_line"].assign(quantity_returned=lambda f: f["quantity_returned"].astype(int))
live = rol[rol["line_status"] != "withdrawn"]
cum = live.groupby(["order_id", "order_line_no"])["quantity_returned"].sum().rename("returned").reset_index()
over = cum.merge(sol[["order_id", "order_line_no", "quantity"]], on=["order_id", "order_line_no"])
over = over[over["returned"] > over["quantity"]]
refunded = rol[rol["line_status"] == "refunded"].groupby(["order_id", "order_line_no"])["quantity_returned"].sum().rename("refunded").reset_index()
double = refunded.merge(sol[["order_id", "order_line_no", "quantity"]], on=["order_id", "order_line_no"])
double = double[double["refunded"] > double["quantity"]]
print(f"  sale lines whose live requests exceed the purchased quantity: {len(over)}; whose refunded units exceed it: {len(double)}")
if len(double):
    print("   e.g.", double.head(3).to_dict("records"))
nr = rol[rol["reason_code"].isin(["item_not_received", "empty_package"])]
print("  non-receipt and empty-parcel lines with return_received_flag=1:", int((nr["return_received_flag"] == "1").sum()), "of", len(nr))
inr = rol[rol["reason_code"] == "item_not_received"].merge(sol[["order_id", "order_line_no", "line_status", "delivered_date"]], on=["order_id", "order_line_no"], suffixes=("", "_sale"))
print("  item_not_received on lines the carrier marked delivered:", int((inr["line_status_sale"] == "delivered").sum()), "of", len(inr))
hdr = base["return_order"].assign(refund_total=lambda f: f["refund_total"].astype(float))
sums = rol.assign(refund_amount=lambda f: f["refund_amount"].astype(float)).groupby("return_order_id")["refund_amount"].sum()
mismatch = (hdr.set_index("return_order_id")["refund_total"] - sums).abs() > 0.005
print("  return headers whose refund_total differs from the sum of line refunds:", int(mismatch.sum()))
paid = sol.assign(line_total=lambda f: f["line_total"].astype(float), quantity=lambda f: f["quantity"].astype(int))
r2 = rol.assign(refund_amount=lambda f: f["refund_amount"].astype(float)).merge(paid[["order_id", "order_line_no", "line_total", "quantity"]], on=["order_id", "order_line_no"])
r2["paid_per_unit"] = r2["line_total"] / r2["quantity"]
print("  refunds above the price paid for the units returned:", int((r2["refund_amount"] > r2["paid_per_unit"] * r2["quantity_returned"] + 0.01).sum()))
print("  refund_amount > 0 on rejected or withdrawn lines:", int(((r2["refund_amount"] > 0) & r2["line_status"].isin(["rejected", "withdrawn"])).sum()),
      "| refunded lines with refund 0:", int(((r2["refund_amount"] == 0) & (r2["line_status"] == "refunded")).sum()))


def mutate(label, change, expect=True):
    """Apply `change(frames)` to a copy, bring the manifest back in line, validate. `expect`: a returns expert expects rejection."""
    target = work / label.replace(" ", "_")[:60]
    shutil.copytree(SRC, target)
    frames = {k: v.copy() for k, v in base.items()}
    touched = change(frames)
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    for name in touched:
        path = target / f"{name}.csv"
        frames[name].to_csv(path, index=False, lineterminator="\n", encoding="utf-8")
        manifest["files"][name].update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), row_count=len(frames[name]))
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    report = validate_world(target)
    rules = sorted({v["rule_id"] for v in report.violations})
    verdict = "rejected " + ",".join(rules) if not report.accepted else "ACCEPTED"
    flag = "" if (not report.accepted) == expect else ("   <-- GAP" if expect else "   <-- unexpected rejection")
    print(f"  {label:<72} {verdict}{flag}")
    shutil.rmtree(target, ignore_errors=True)
    return report.accepted


def first_return(frames, reason=None, status="refunded"):
    r = frames["return_order_line"]
    mask = r["line_status"].eq(status) if status else pd.Series(True, index=r.index)
    if reason:
        mask &= r["reason_code"].eq(reason)
    return r.index[mask][0]


def sale_of(frames, i):
    r = frames["return_order_line"].loc[i]
    s = frames["sales_order_line"]
    return s.index[(s["order_id"] == r["order_id"]) & (s["order_line_no"] == r["order_line_no"])][0]


print("\n== one rule broken per copy (expected: rejected)")


def over_return(f):
    i = first_return(f); j = sale_of(f, i)
    f["return_order_line"].loc[i, "quantity_returned"] = str(int(f["sales_order_line"].loc[j, "quantity"]) + 1)
    return ["return_order_line"]
mutate("returned quantity above the purchased quantity", over_return)


def second_refund(f):
    r = f["return_order_line"]; i = first_return(f, "wrong_size")
    dup = r.loc[[i]].copy(); dup["return_line_no"] = "9"
    f["return_order_line"] = pd.concat([r, dup], ignore_index=True)
    return ["return_order_line"]
mutate("the same unit refunded twice (second refunded line, qty-1 sale line)", second_refund)


def before_delivery(f):
    i = first_return(f, "wrong_size"); j = sale_of(f, i)
    d = pd.Timestamp(f["sales_order_line"].loc[j, "delivered_date"]) - pd.Timedelta(days=3)
    stamp = d.strftime("%Y-%m-%dT10:00:00+05:30")
    f["return_order_line"].loc[i, ["requested_at", "available_at"]] = stamp
    rid = f["return_order_line"].loc[i, "return_order_id"]
    f["return_order"].loc[f["return_order"]["return_order_id"] == rid, ["return_created_at", "available_at"]] = stamp
    return ["return_order_line", "return_order"]
mutate("item return requested before the item was delivered", before_delivery)


def refund_above_paid(f):
    i = first_return(f); j = sale_of(f, i)
    new = float(f["sales_order_line"].loc[j, "line_total"]) * 3
    f["return_order_line"].loc[i, "refund_amount"] = f"{new:.2f}"
    rid = f["return_order_line"].loc[i, "return_order_id"]
    lines_ = f["return_order_line"][f["return_order_line"]["return_order_id"] == rid]
    f["return_order"].loc[f["return_order"]["return_order_id"] == rid, "refund_total"] = f"{lines_['refund_amount'].astype(float).sum():.2f}"
    return ["return_order_line", "return_order"]
mutate("refund three times the price paid", refund_above_paid)


def header_mismatch(f):
    f["return_order"].loc[f["return_order"].index[0], "refund_total"] = "1.00"
    return ["return_order"]
mutate("return header refund_total not the sum of its lines", header_mismatch)


def foreign_customer(f):
    i = first_return(f); rid = f["return_order_line"].loc[i, "return_order_id"]
    h = f["return_order"]; owner = h.loc[h["return_order_id"] == rid, "customer_id"].iloc[0]
    other = f["customer_master"]["customer_id"][f["customer_master"]["customer_id"] != owner].iloc[0]
    h.loc[h["return_order_id"] == rid, "customer_id"] = other
    return ["return_order"]
mutate("return filed by a customer who did not place the order", foreign_customer)


def received_on_nonreceipt(f):
    r = f["return_order_line"]; i = r.index[(r["reason_code"] == "item_not_received") & (r["return_received_flag"].isin(["0", ""]))][0]
    r.loc[i, "return_received_flag"] = "1"
    return ["return_order_line"]
mutate("item_not_received claim with the item marked received back", received_on_nonreceipt)


def unknown_sale_line(f):
    f["return_order_line"].loc[first_return(f), "order_line_no"] = "99"
    return ["return_order_line"]
mutate("return against a sale line that does not exist", unknown_sale_line)


def duplicate_key(f):
    r = f["return_order_line"]
    f["return_order_line"] = pd.concat([r, r.iloc[[0]]], ignore_index=True)
    return ["return_order_line"]
mutate("duplicate return line key", duplicate_key)


def negative_qty(f):
    f["return_order_line"].loc[first_return(f), "quantity_returned"] = "-1"
    return ["return_order_line"]
mutate("negative returned quantity", negative_qty)


def unknown_reason(f):
    f["return_order_line"].loc[first_return(f), "reason_code"] = "fraud"
    return ["return_order_line"]
mutate("reason code outside the codebook", unknown_reason)


def after_cutoff(f):
    i = first_return(f)
    f["return_order_line"].loc[i, ["requested_at", "available_at"]] = "2026-09-20T10:00:00+05:30"
    return ["return_order_line"]
mutate("return requested after the snapshot cutoff", after_cutoff)


def delivered_before_shipped(f):
    s = f["sales_order_line"]; j = s.index[s["line_status"] == "delivered"][0]
    s.loc[j, "delivered_date"] = (pd.Timestamp(s.loc[j, "shipped_date"]) - pd.Timedelta(days=2)).strftime("%Y-%m-%d")
    return ["sales_order_line"]
mutate("sale line delivered before it shipped", delivered_before_shipped)


def return_on_cancelled(f):
    s = f["sales_order_line"]
    cancelled = s.index[s["line_status"].isin(["cancelled", "undelivered", "lost"])]
    if not len(cancelled):
        print("  (no cancelled sale line in W5401; skipped)"); return []
    j = cancelled[0]; i = first_return(f, "wrong_size")
    f["return_order_line"].loc[i, ["order_id", "order_line_no", "sku"]] = s.loc[j, ["order_id", "order_line_no", "sku"]].to_numpy()
    return ["return_order_line"]
print("  sale line statuses in W5401:", base["sales_order_line"]["line_status"].value_counts().to_dict())
mutate("item return (wrong size) on a line that was never delivered", return_on_cancelled)


def refund_on_rejected(f):
    i = first_return(f, status="rejected")
    f["return_order_line"].loc[i, "refund_amount"] = "999.00"
    rid = f["return_order_line"].loc[i, "return_order_id"]
    lines_ = f["return_order_line"][f["return_order_line"]["return_order_id"] == rid]
    f["return_order"].loc[f["return_order"]["return_order_id"] == rid, "refund_total"] = f"{lines_['refund_amount'].astype(float).sum():.2f}"
    return ["return_order_line", "return_order"]
mutate("money refunded on a rejected return line", refund_on_rejected)


def wrong_sku(f):
    i = first_return(f); r = f["return_order_line"]
    r.loc[i, "sku"] = "SKU300" if r.loc[i, "sku"] != "SKU300" else "SKU001"
    return ["return_order_line"]
mutate("returned SKU differs from the SKU sold on that line", wrong_sku)


def free_text(f):
    f["return_order_line"].loc[first_return(f), "reason_text"] = "customer said the parcel was stolen from the porch"
    return ["return_order_line"]
mutate("free-text reason supplied (privacy: the product never shows free text)", free_text)


print("\n== allowed by design (expected: accepted)")


def late_beyond_window(f):
    i = first_return(f, "wrong_size", status="rejected") if len(f["return_order_line"][(f["return_order_line"]["reason_code"] == "wrong_size") & (f["return_order_line"]["line_status"] == "rejected")]) else first_return(f, "wrong_size")
    j = sale_of(f, i)
    d = pd.Timestamp(f["sales_order_line"].loc[j, "delivered_date"]) + pd.Timedelta(days=int(f["sales_order_line"].loc[j, "return_window_days"]) + 5)
    if d > pd.Timestamp("2026-09-09"):
        print("  (line too recent for an out-of-window request; skipped)"); return []
    stamp = d.strftime("%Y-%m-%dT10:00:00+05:30")
    f["return_order_line"].loc[i, ["requested_at", "available_at"]] = stamp
    f["return_order_line"].loc[i, ["line_status", "refund_amount"]] = ["rejected", "0.00"]
    rid = f["return_order_line"].loc[i, "return_order_id"]
    h = f["return_order"]; lines_ = f["return_order_line"][f["return_order_line"]["return_order_id"] == rid]
    h.loc[h["return_order_id"] == rid, "refund_total"] = f"{lines_['refund_amount'].astype(float).sum():.2f}"
    created = min(lines_["requested_at"])
    h.loc[h["return_order_id"] == rid, ["return_created_at"]] = created
    h.loc[h["return_order_id"] == rid, ["available_at"]] = max(lines_["available_at"])
    return ["return_order_line", "return_order"]
mutate("request five days after the window closed, rejected with no refund", late_beyond_window, expect=False)

shutil.rmtree(work, ignore_errors=True)
