# Synthetic data specification

Q18/Q19 approval: new generation uses the [team apparel/INR policy](retail-simulation-policy.yaml) and twelve months of transaction history, with shorter new-account histories. Counts, categories, currencies and windows below describe historical artifacts and are not silently rewritten as current output.

Latest steering: the [ML development pipeline](../../docs/ml-development-workflow.md) is the current focus. Retain customer abuse and legitimate-counterexample generation requirements; the pending-item inspection expansion described in the historical update below is no longer a current generation prerequisite.

## Approved direction update - 2026-09-25

The user's Q11/Q12 decisions require revising volume-only `serial_returner` abuse labels and generating a separate as-of pending-return inspection scenario. See [customer and inspection demo data](customer-and-inspection-demo-data.md) for the approved objectives, proposed simulation design, demonstration walkthrough and remaining generation decisions. The archive counts and generator behaviours below describe historical artifacts, not the approved target for new data. No new data has been generated in this update.

DATA-005. Sources: schema.py categories/populations/profiles; generate.py; Dataset Build Steps ??1?6. Actual measurements are in observed-data-profile.json, not acceptance thresholds.

The archive contains 10,000 customer labels, 338 SKUs, 52,232 orders, 115,299 sales lines, 24,661 submissions, 30,694 return lines and 16 reasons. It has six CSV/Parquet input pairs and two ground-truth CSVs, but no customer_master. Current source adds that table after transaction generation. All three archived Python files differ from current copies. The six manifest hash prefixes match archived CSV bytes. New dataset generation is deferred to implementation; no dataset was generated here.

Business-realistic assumptions: size bracketing, SKU-specific 14/30/45/60/90-day windows, partial quantities, consolidated submissions, cancelled orders, pending/rejected returns, defective products and benign shared households. These are assumptions about the simulated world, not empirically validated retail distributions.

Artificial labels: population is assigned before behaviour; there is no fraud adjudication. Counts are normal 8080, serial_returner 250, refund_fraudster 100, collusion_ring 210, wardrober 180, legit_heavy_returner 650, defective_cluster_buyer 350, benign_household 180. Abuse totals 740 (7.4%); benign totals 9260. At k=625 the count-only maximum recall is 625/740 ? 0.8446, NOT the achievable statistical-separation ceiling requested by M16.

Randomness: numpy default_rng seed 20250901; category/style choices, uniform return multipliers, Beta latency plus normal noise, weighted reasons, 2% goodwill late returns, 1.5% cancellations, 4% pending and 2% rejected submissions. Per-line return probability is clip(base * customer_multiplier, .01, .95); bracketing overrides it to .15 for first line and .52 for later lines. Defect flags override base rates to sampled .55?.72; ordinary per-SKU true rate is the category constant. Sealed constants are never detector priors.

Intentional correlations: wardrobers choose occasion wear with probability .70 and late/discretionary returns; defect buyers choose defective SKUs with probability .55; fraudsters choose premium SKUs with probability .55; rings target selected premium SKUs with probability .45 and share a 90-day activity window. Rings are 35 groups of six; households share address/device and sometimes payment; 400 normal customers share one address. Customer status and marketing channel are population-conditioned; loyalty uses full-history volume.

Easy-task risks: identity prefixes PAY-R/DEV-R and PAY-H/DEV-H expose generator membership if parsed; deterministic hashing must preserve equality only. Reasons and inspection disposition share generator logic; free text comes from short templates. All seeds share the same behavioural law, so sealed-seed success does not establish real-world transfer. Known population sizes and static topology simplify recovery. Some ring members lack two shared types, so perfect graph recall is not guaranteed. Current account status and whole-history loyalty are post-outcome proxies in historical prediction; neither is on the forest allow-list.

Observed checks: 466 partial returns, 237 consolidated submissions, 25 injection strings, 9,715 blank reason_text values, 1,801 blank cancelled-line delivery dates. 5,140 latency mismatches and 2,389 open return windows require Q-002/Q-003 resolution. No receipt is not proof of abuse or non-defect. Physical wardrobing cannot be established from this dataset.

Acceptance requires schema and cross-table checks, same-seed reproducibility under a pinned environment, different-seed variation, overlap of heavy/serial raw rates and wardrober/exchanger latency, benign graph hard negatives, and independent blind recovery before label access. Existing historical precision figures have no accompanying scored artifacts; they are not validated results. Resolve Q-018/Q-021 before claiming evidence quality.
