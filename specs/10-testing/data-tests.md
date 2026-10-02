# Data Tests

DRAFT ? verification specifications only, not implemented or executed tests. Sources: LLD ?5/?9 and referenced canonical specs.

| Test ID | Requirements | Level / concern | Fixture and expected result |
|---|---|---|---|
| DATA-TEST-001 | DATA-001/002/003; FR-009 | Contract and data quality | Complete seven-table fixture passes schema/keys; missing customer_master fails before join; each DQ-001?DQ-020 violation gets specified severity/code and redacted lineage. Assert no row multiplication, SKU/customer mismatch, duplicate return or silent retained-sale reclassification. Q-002/Q-003 block disputed cases. |
| DATA-TEST-002 | DATA-004/005; LEAK-001?LEAK-006; SEC-001/002 | Leakage and synthetic integrity | Poison operational inputs with population/base_return_rate and reject; detection has no sealed-data access. Rename identifier literals preserving equality and require unchanged graph evidence. Check population overlap, benign household links, 400-address cap fixture and no prefix interpretation. |
| DATA-TEST-003 | DATA-004/005; REPRO-001 | Generation contract regression | Future same-seed generation under pinned environment yields identical hashes, changed seed differs; compare CSV/Parquet values including blank text and loyalty none. Verify manifest covers all seven inputs plus ground-truth provenance. This task does not generate data. |
| DATA-TEST-004 | DATA-002/003; Q-002/Q-003 | Temporal and monetary boundary | Fixture includes partial refund, pending/rejected states, cancellation, date before delivery, consolidated line/header mismatch, late goodwill, open window at cutoff and policy change. Check pro-rata rounding, approved eligibility and exact as-of boundaries. Expected disputed outcomes require owner approval first. |
