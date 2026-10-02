"""Hand-built operational tables for feature fixtures: small enough to calculate by hand."""
import pandas as pd

CUTOFF = "2026-09-09"


def make_tables(skus, orders, lines, returns=(), customers=None) -> dict:
    """Seven operational tables from compact tuples.

    skus:    (sku, style_id, category, size, is_occasion_wear, return_window_days)
    orders:  (order_id, customer_id, order_date, address_id, device_id, payment_id)
    lines:   (order_id, order_line_no, sku, quantity, line_status, delivered_date)
    returns: (return_order_id, return_line_no, order_id, order_line_no, quantity_returned, reason_code, requested_at, line_status)
    """
    sku = pd.DataFrame(skus, columns=["sku", "style_id", "category", "size", "is_occasion_wear", "return_window_days"])
    sku = sku.assign(brand="B", colour="Black", colour_id="C1", unit_price=1000.0, price_band="Mid",
                     launch_date=pd.Timestamp("2024-01-01"), active_flag=1)
    order = pd.DataFrame(orders, columns=["order_id", "customer_id", "order_date", "address_id", "device_id", "payment_id"])
    order["order_date"] = pd.to_datetime(order["order_date"])
    order = order.assign(channel="web", currency="INR", order_subtotal=0.0, order_shipping=0.0, order_total=0.0)
    line = pd.DataFrame(lines, columns=["order_id", "order_line_no", "sku", "quantity", "line_status", "delivered_date"])
    line["delivered_date"] = pd.to_datetime(line["delivered_date"])
    line = line.merge(sku[["sku", "return_window_days"]], on="sku")
    line = line.assign(unit_price=1000.0, line_discount=0.0, line_total=lambda f: f["quantity"] * 1000.0,
                       shipped_date=lambda f: f["delivered_date"] - pd.Timedelta(days=2))
    ret = pd.DataFrame(list(returns), columns=["return_order_id", "return_line_no", "order_id", "order_line_no",
                                               "quantity_returned", "reason_code", "requested_at", "line_status"])
    ret["requested_at"] = pd.to_datetime(ret["requested_at"])
    ret = ret.merge(line[["order_id", "order_line_no", "sku"]], on=["order_id", "order_line_no"], how="left")
    ret = ret.assign(available_at=ret["requested_at"], refund_amount=0.0, return_received_flag=pd.NA, reason_text=None, disposition=None)
    owner = order.set_index("order_id")["customer_id"]
    header = ret.groupby("return_order_id").agg(order_id=("order_id", "first"), return_created_at=("requested_at", "max")).reset_index()
    header = header.assign(customer_id=header["order_id"].map(owner), return_channel="courier_pickup",
                           refund_method="original_payment", refund_total=0.0, available_at=header["return_created_at"])
    ids = customers if customers is not None else sorted(set(order["customer_id"]))
    customer = pd.DataFrame({"customer_id": ids, "signup_date": pd.Timestamp("2024-01-01"), "account_status": "unknown",
                             "loyalty_tier": "unknown", "marketing_channel": "unknown"})
    return {"customer_master": customer, "sku_master": sku, "reason_code": pd.DataFrame({"reason_code": []}),
            "sales_order": order, "sales_order_line": line, "return_order": header.drop(columns="order_id"), "return_order_line": ret}


def simple_order(order_id, customer, address=None, device=None, payment=None, date="2026-01-01"):
    """An order whose identifiers default to values unique to the customer."""
    return (order_id, customer, date, address or f"A-{customer}", device or f"D-{customer}", payment or f"P-{customer}")
