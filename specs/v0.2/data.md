# Synthetic data and contracts

Existing team artifacts must pass the [reuse and repair requirements](existing-generator-disposition.md). The [separate assessment](../../docs/generator-reuse-assessment.md) finds the SKU catalog reusable, customer profiles useful but incomplete for ML, and generator source missing. Retain working assets; recover/repair before conditional reconstruction.

## Time, scale and provenance

Engineering default snapshot: 2026-09-09 23:59:59 Asia/Kolkata. Simulate calendar dates 2025-09-10 through 2026-09-09 inclusive. Persist dates as ISO dates; timestamp fields as ISO timestamps with offset. Every record used by a snapshot has available_at <= cutoff. Store start/end/timezone in the manifest; do not infer them from the filename.

Use 10,000 independently generated customer profiles per world and the team's 300-SKU catalog. Twelve months is the maximum transaction window, not a minimum customer age. No orders before signup or SKU launch. For the initial simulation, active_flag is current metadata, not evidence that a SKU was inactive historically. Generate no retirement event unless an explicit effective date is supplied. Never infer an unobserved retirement date from active_flag.

Catalog currency/category/windows follow [retail policy](../02-data/retail-simulation-policy.yaml). Fix catalog attributes across worlds; redraw private defects and targeting so SKU identity cannot encode truth. Customer and relationship identifiers are world-namespaced opaque identifiers with no persona prefix. SKU IDs, customer IDs and relationship strings are join keys, not model features.

Every world manifest records schema/generator/config versions and hashes, RNG seed, source catalog hash, exact date boundaries, output counts, dependency lock hash and SHA-256 hashes of operational and private files. Seed reproducibility means equal canonical table content after stable sorting; compressed file bytes are not assumed equal across unpinned libraries.

## Profile-first generation

Preserve the team's intended sequence: customer profiles -> optional exploratory clustering -> transactions -> observed features. Clustering evaluates encoded profile structure only; it is not independent detection performance.

The team profile fields actual_orders, return_rate, festive_order_ratio and avg_days_between_orders are simulation inputs. Rename internally to target_order_count, target_return_propensity, target_festive_share and target_days_per_order. Do not export these targets, customer_segment, persona-conditioned account_status or full-history loyalty as model inputs. The operational customer table contains factual signup and approved reference fields; missing legacy loyalty/channel values use explicit unknown, not truth-derived values.

Use profile targets as expectations, not an obligation to reproduce rates exactly. Sample monthly demand from customer intensity with seasonality; cap by available signup days. Generate basket size, SKU/style/size and quantities before return actions. Recompute realised counts and ratios from events and report deviation from targets. Do not tune worlds to make a model pass.

Intersect festive calendars with the customer's actual eligible dates before allocating orders. If that intersection is empty, realised festive share must be0 regardless of the private preference target; record the target deviation. In the reviewed current profiles5,810 nonzero-order rows have positive targets with no eligible festive date, so direct target-to-count allocation is prohibited. These are simulation calendar windows, not verified actual festival dates.

The legacy avg_days_between_orders value is approximately tenure_days/actual_orders, an intensity proxy. Name the private input target_days_per_order; compute observed mean_inter_order_gap_days from consecutive actual order timestamps, null for fewer than two orders. A one-order customer has no observed inter-order gap.

## Actions define labels

Private action events have world_id, customer_id, source line key, action_time, action_type, completed_action and private evidence. y_abuse=1 iff at least one completed intentional abusive action occurs by cutoff on an included transaction; otherwise 0. Attempted-but-not-submitted behaviour is not positive. Success in obtaining a refund is not required. Future intent/persona alone is not a positive label.

Action types:

- deceptive_nonreceipt_claim: the simulated customer knowingly claims nonreceipt after actually receiving the item; observed delivery records can be incomplete and legitimate nonreceipt also exists.
- deceptive_contents_claim: a knowingly false empty/missing/wrong-item claim; genuine fulfilment failures share the same public reason codes.
- temporary_use_return: the customer uses the garment for an occasion beyond ordinary fitting and submits it as an ordinary return. Actual use remains private truth, never a detector field.

Coordination is an additional private relationship on abusive actions, not an abuse action by itself. collusion_type=true requires participation in a coordinated abusive action; shared addresses/devices or membership without an action cannot make y_abuse positive. Overlapping action types are retained for evaluation while the model target is binary.

Preserve non-abusive high-return profiles. For evaluation, benign groups are y_abuse=0 AND respectively heavy_return_profile, defective_product_exposure or shared_household. Groups may overlap; report their denominators separately and never sum them as disjoint totals. Mixed cases (abusive customer + defective purchase, abusive household member) are reported separately, not included in benign error denominators.

## Generation defaults and hard cases

Use configured stochastic populations, not fixed exact positive counts. Initial propensity allocation: 4% claim-abuse propensity, 3% temporary-use propensity, with 0.5% overlapping; within those accounts randomly form coordinated groups of 3-6. Propensity is private and does not guarantee an action. Benign overlays target 8% heavy shoppers and 5% household members; select 8% of styles for increased latent defect incidence. These are simulation design choices, not Indian prevalence estimates.

Ordinary item returns use a logistic probability from SKU quality/fit, customer preference, size bracketing and latent noise. Keep category ordinary rates configurable initially in 0.10-0.30. Defect-prone styles increase latent defective-unit probability rather than forcing every buyer to return. Heavy buyers increase purchase volume and fit-related returns without intentional misuse. Genuine delivery/content problems occur in every propensity group.

For enabled abusive propensities, sample action opportunities per relevant order (initial rate 0.20, configurable); temporary-use opportunities favour occasion wear but must not be restricted to it. Choose a return-request time from overlapping distributions: ordinary fitting returns often early, temporary-use returns often late, but both have exceptions. Include honest late returns, benign occasion wear, low-volume abusive accounts, shared payment methods and large shared addresses. Never force all positives above a detector threshold.

Run diagnostics on action counts, missingness, feature overlap and case coverage. Flag absent required scenarios as coverage failures. Fix generator defects on development worlds; never repeatedly regenerate final-test worlds until their outcomes look favourable. Keep curated demo worlds separate.

## Operational schema and adapters

Base fields/keys are in [schema.yaml](../02-data/schema.yaml); use its team category/INR updates. Apply these v0.2 amendments explicitly:

| Table | Amendment / semantics |
|---|---|
| customer_master | customer_id, signup_date required; status/loyalty/channel nullable unknown reference fields, excluded from model allow-list |
| sku_master | sku_id -> sku; color -> colour; boolean occasion flag -> 0/1; team categories/price bands retained; no private defect/target flags |
| reason_code | fixed declared codebook; reasons are claims, not adjudications; public flags never assigned from private customer persona |
| sales_order | order date, customer and opaque device/address/payment references; monetary totals in INR |
| sales_order_line | quantity, delivery date and historical return_window_days captured at sale; cancelled lines have no delivery |
| return_order | submission/status snapshot, current refund total, header available_at; header date is not line latency |
| return_order_line | add requested_at and available_at; retain source order/line, quantity, reason, receipt/refund data as available at cutoff |

Consolidated return headers may contain different line request times. days_to_return = calendar days from line delivery to requested_at; derive it, never copy inconsistent legacy values. Return window is the policy captured on the sale, not a later catalog lookup. Permit partial quantities and multiple return lines per sale, with cumulative accepted/requested quantity <= purchased quantity after removing cancelled requests. New schema permits these one-to-many joins; feature code aggregates quantities before joining to avoid duplicate sales exposure.

For the initial snapshot, one immutable snapshot per world avoids reconstructing status changes from final-state CSVs. Additional snapshot dates require event logs or independently constructed as-of fields, never filtering final-state tables solely by order date.

Physical inspection disposition, free text, future refunds and private item condition are not model inputs in v0.2. Preserve optional operational values for evidence only if observed by cutoff. This keeps image-free wardrobing honest and avoids solving abuse detection by handing it simulated inspection truth.

## Observations, censoring and eligibility

Include delivered sales in the history window; cancelled/undelivered sales contribute no exposure. A sale is mature only when delivery_date + captured return_window_days <= snapshot date. Rate/residual denominators use mature sales only; count requests on those lines recorded by cutoff whether pending/refunded/rejected, because the outcome is return behaviour, not retailer approval. Record rejected and pending counts separately. Unmatured lines remain visible with open-window counts and never become implicit retained items.

The primary customer ranking includes customers with at least three mature sale lines; all others receive insufficient_history, nullable risk and an unranked UI row. Report their counts, action prevalence and excluded-abuse coverage separately; do not describe ranked-population recall as whole-population recall. Exact positive label counts are derived from actions, never promised in advance.

Private data live outside operational upload bundles: profiles, action_truth, customer_truth, product_truth, relationship_truth. The supervised training assembler can join customer_truth only after the feature artifact is frozen. Inference has no path to private directories.

## Validation contract

Reject the complete world for missing/duplicate primary keys, broken references, currency/policy violations, impossible dates, negative monetary values, excess return quantity, future-visible fields or private columns in an operational file. Do not silently quarantine label-correlated rows and change evaluation composition. Emit a structured report with rule ID, table, row key and counts. Harmless optional-field absence uses declared null handling.

Check header totals against lines, rounded to INR paise; verify CSV/Parquet logical parity; compare world hashes. Confirm at least one example of every required scenario in development/demo, with coverage statistics reported for test. Structural validity is not evidence of behavioural realism.
