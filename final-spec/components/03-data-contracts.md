# Operational and private data contracts

Version 1.3 (amended 2026-10-02) | Implementation baseline | Component DATA

## Requirements and boundary

Seven tables: customer_master, sku_master, reason_code, sales_order, sales_order_line, return_order, return_order_line. Full columns/types/keys/enums are bundled. Metadata rules require an implemented validator. Unknown/private columns reject. Required columns cannot be omitted; nullable evidence may be empty.

CSV: UTF-8 header, ISO dates/timestamps with offsets, dot decimals; empty cell means null only if nullable. Decimal paise arithmetic. SKU policy T-shirt/Shirt/Jeans 30 days, Jacket 45, Dress 60, captured at sale. Discount is a line amount. IDs are join keys, never numeric/model inputs.

Sales: awaiting_dispatch/cancelled have no shipment/delivery dates; shipped/lost_in_transit have observed shipping only; delivered has carrier scan. Status must be observed by cutoff. Mature iff delivered_date+captured_window<=cutoff local date. Genuine misdelivery and deceptive nonreceipt both can follow scan.

Returns reference delivered sale and same customer across header/order. Pending/refunded/rejected count; withdrawn excluded from all features and quantity cap. Sum active quantities<=purchased. Preserve line requested_at under consolidated headers. The generator consolidates every request by one rule (a header covers its first request date and the next day) and numbers lines by request time, so header structure cannot reveal intent. Generator available_at=requested_at per line; header created/available time is latest included request. Derived header state common or mixed. Mixed physical/no-item header uses physical channel, all-no-item uses not_applicable.

Refund zero unless refunded and <=requested net unit value; header equals sum current refunds. Order subtotal includes subsequently cancelled lines; total adds shipping. Optional disposition is observed evidence only.

Operational manifest: schema_version=1.0, world_id, cutoff, history_start, timezone, currency, purpose, exactly seven basenames/hashes/counts. Generated worlds also require generator/code/config/catalog/lock hashes and seed. Private manifest never uploaded. world_id binds immutable content: same content re-registration stable, changed content conflicts. Notes cannot cross unrelated regenerated worlds.

Private profiles/action rates/unit facts/order layer (base or campaign)/address failure multipliers/campaigns/memberships/allocations/actions/customer/style truth live outside inference mounts. Amendment 1.1 changes private truth only: the seven operational tables and manifest schema_version stay 1.0, and no operational field distinguishes a campaign order. Required fields and joins in private-truth.yaml reconstruct labels. Supervised labels join only after feature artifact freeze.

## Inputs, outputs and dependencies

- Inputs: Canonical CSV tables and manifest.
- Outputs: Immutable dataset identity and separate private artifacts.
- Dependencies: contracts/data-schema.yaml, manifest.schema.json, private-truth.yaml.

## Acceptance criteria

| ID | Pass condition and required evidence |
|---|---|
| DATA-AC-01 | Duplicate/missing keys, bad ownership, excess quantities and impossible chronology reject complete upload with table/key diagnostics. |
| DATA-AC-02 | Exactly seven file hashes/counts validate; unknown columns/private files reject. |
| DATA-AC-03 | Two request dates under one header retain separate latency. |
| DATA-AC-04 | Future evidence never survives; IST dates and paise values round-trip. |
| DATA-AC-05 | Same world+content registration is stable; changed world content conflicts. |
| DATA-AC-06 | Every customer/style label reconstructs privately; no truth columns occur operationally. |

Acceptance status is recorded per criterion in acceptance-register.csv (status, evidence, date, reviewer). Prose requirements are not implementation evidence.
