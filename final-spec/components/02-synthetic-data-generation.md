# Synthetic data generation

Version 1.1 (amended 2026-10-02) | Implementation baseline | Component GEN

## Requirements and boundary

Generate profiles -> base purchases/delivery/honest returns -> propensities/relationships/campaigns -> abuse-layer campaign orders -> compatible abusive actions -> immutable snapshot -> private labels. Reconstruct customer/transaction generation; retain supplied 300-SKU/37-style catalog with a named adapter. Do not claim reconstruction reproduces unavailable original code. Scalar shared_device_count is not an identity relationship.

Snapshot 2026-09-09T23:59:59+05:30; inclusive history 2025-09-10..2026-09-09; Asia/Kolkata; INR; 10,000 fresh profiles per full world. Opaque customer/relationship IDs are world-namespaced. Catalog fixed; defect/target truth redraws. No orders before signup or SKU launch. Current active_flag does not imply historical retirement.

Profiles are targets, not model fields. Use profile-config.yaml; Fraud_Proxy becomes label-neutral High_Intensity. Emit account_status=unknown. Honest return propensity is independent of abuse. Intersect festive windows with signup/history; no eligible festive date means realized festive share zero. Handle year-crossing windows. Observed order gap uses consecutive dates, null for fewer than two orders; target_days_per_order is only an intensity input. Optional clustering is exploratory.

Joint overlays: m_i=persona multiplier for positive-target accounts, otherwise zero; M=mean(m) across all accounts; w_i=m_i/M. Draw one category: claim-only .035w, temporary-only .025w, both .005w, neither 1-.065w. Expected whole-world rates are 4% claim/3% temporary/.5% overlap, not exact quotas. Invalid probabilities fail; no clipping. Multipliers 1 Occasional/Seasonal/Loyalist, 1.5 New_Growth, 2 High_Intensity. Stress 2507 sets actionable multipliers to 1. All-dormant boundary fixtures explicitly disable overlays.

Reserve private units (order_id,order_line_no,unit_index). Generate honest events first; reserve all honestly requested units, including withdrawn requests. Each positive-propensity account draws one private action_rate per enabled family from Beta(1.2,4.8) (mean .20), keyed per account and family. Solo opportunities are drawn at that rate per relevant base-layer delivered order. A relevant order has a unit compatible with the family before reservations; report blocked opportunities after reservations. Any delivered unit is compatible with temporary use, but its opportunity probability is clip(action_rate*m,0,1) with m=2.5 when the order has an unreserved delivered occasion-wear unit (that unit is then used) and m=0.55 otherwise, so occasion wear is favoured while the mean stays near the account rate. Choose compatible unreserved units; competing families use keyed random winner with no forced replacement. Disabling abuse preserves base sales and honest line event fields/IDs and removes every campaign order; derived totals may differ. Purpose/entity-keyed random streams prevent one phase advancing another.

Actions: deceptive_nonreceipt_claim requires actual receipt and knowingly false nonreceipt; deceptive_contents_claim knowingly false wrong/missing/empty content; temporary_use_return actual use beyond fitting followed by return. Intent/condition stay private. Submitted rejected/late abuse counts; unsubmitted, future, withdrawn honest requests or group membership alone do not. Abusive requests never withdraw. y_abuse=1 iff a completed action is on a delivered line with requested_at<=cutoff; maturity not required. Label every account; rank eligible only.

Households: 12% members, groups 2-5. Coordination groups: 40% of any-abuse-propensity accounts, sizes 3-6. Type-sharing probabilities per group independently: household address/device/payment 1/.7/.3; abuse .4/.8/.7. Per-member p=U(.6,.9) households or U(.7,1) groups; independent use per order/type. If overlapping memberships offer the same type, keyed equal-choice between offered values; report actual sharing. Add 1-2% address-only shared-location members in groups 26-60. No graph edge from high-fanout address alone.

Campaigns: each world draws a private hot list of 4 target styles without replacement, weighted by median catalog unit price, among styles with >=1 SKU launched by history_start. Each coordination group draws 1-2 hot-list styles (price-weighted) and 2-4 campaign dates uniform over the history window; each date is assigned one of the group's styles uniformly. Only deceptive claim types coordinate, so only claim-capable members take part; each participates per date with probability .60. A participant first reuses a compatible unreserved unit of that style delivered in the 14 days up to the campaign date; otherwise the participant places a campaign order: order_date=campaign_date+U{0,1,2} days, one line, quantity 1, uniform launched SKU of the style, with ordinary pricing, discount, shipping, identifier-usage and fulfilment rules. The coordinated claim is requested Gamma(shape 2, scale 3 days) after delivery, truncated at 30 days.

Campaign orders are abuse-layer events. Private order_truth marks them and no operational field does. They take no honest events, draw no solo opportunities, and take IDs from a separate keyed stream so base IDs never shift. An attempt that is pre-signup, pre-launch, after cutoff, cancelled, lost, undelivered by cutoff or whose claim falls after cutoff stays uncompleted with a recorded reason; there are no retries and no quotas. planned_targeted_by differs from completed_targeted_by. A style is targeted iff >=1 group has >=3 distinct accounts with completed coordinated claims on it visible at cutoff; fewer is sub_threshold coordination, reported separately. Truth never depends on detector thresholds or +/-7-day matching.

Ordinary logistic return probability incorporates preference, fit, bracketing, latent quality and noise; initial category range .10-.30. Randomly mark 8% styles defect-prone then sample units; not every exposed buyer returns. Benign heavy-return overlay 6%, honest .28-.48 range; power users 8% affect volume, not gate membership. Genuine delivered-line claims: nonreceipt .5%, wrong item .4%, missing parts .4%, empty .2%; carrier damage .5% independently. Each delivery address has a private keyed multiplier g=Z^2 (Z standard normal; mean 1, variance 2) applied to all four genuine claim rates for lines delivered there (probability clipped at 1), so honest repeat claimants cluster at a few addresses while population rates stay near the stated values and independent of abuse propensity. Carrier damage is not address-scaled. Resolve multiple honest causes once per unit, retain latent causes privately. Temporary-use reasons 85% fit/discretionary and 15% false poor_quality/not_as_described.

generator-config.yaml specifies numeric operational settings and explicitly identified consolidation defaults. These are simulation assumptions, not Indian market statistics. Freeze expanded config/lock before accepted generation. Change only on development worlds with dated rationale before validation. Never resample sealed worlds for attractive results. Order channel is mobile_app .60/web .30/marketplace .10, independent of all other draws; loyalty_tier and marketing_channel emit unknown; reason_text and disposition emit null. Difficulty calibration (component 05) may change only the action-rate Beta parameters, the address multiplier dispersion and the genuine claim rates.

Development/demo scenarios: five sale states; genuine and deceptive claim codes; linked/unlinked households; low-link abuse; high-fanout addresses; heavy returns; defective buyers; honest late returners; bracketers; low-volume abusers; mixed cases; nonacting group members; campaign orders and reused purchases; sub-threshold groups; one-off abusers; honest repeat claimants at high-failure addresses. Deterministic boundary fixtures supplement rare random coverage, never alter sealed worlds. No pending inspection expansion.

## Inputs, outputs and dependencies

- Inputs: Bundled catalog/profile/festival inputs, seed and generation config.
- Outputs: Seven operational tables/manifest plus isolated truth and diagnostics.
- Dependencies: Data contracts, validation and experiment contracts.

## Acceptance criteria

| ID | Pass condition and required evidence |
|---|---|
| GEN-AC-01 | Pinned seed/config/lock reproduces canonical sorted tables; different seeds vary; CSV/Parquet values match. |
| GEN-AC-02 | Adapter preserves 300 SKUs/37 styles, prices/windows/variants/launch dates and source hash. |
| GEN-AC-03 | Abuse-off preserves base/honest events and IDs and removes every campaign order; quantity-three fixture with one honest/one abusive request yields two requested units. |
| GEN-AC-04 | Five sale states and all cutoff chronology pass; future plans do not enter snapshot. |
| GEN-AC-05 | Population-average probabilities equal .04/.03/.005; invalid allocation fails; no forced realized quotas. |
| GEN-AC-06 | Labels reconstruct from action/request/unit joins; nonacting group members and planned-only targets are not positive; a style is targeted iff one group has >=3 accounts with completed coordinated claims. |
| GEN-AC-07 | Assigned sharing and realized links differ legitimately; one-order usage may be 0%/100%. |
| GEN-AC-08 | Coverage, eligibility, excluded abuse, segment support and blocked-campaign reports precede full generation. |
| GEN-AC-09 | Campaign orders obey signup/launch/cutoff chronology and are marked only in private order_truth; coordinated claims occur only on world hot-list styles; uncompleted attempts keep a reason. |
| GEN-AC-10 | Per-account action rates and per-address genuine-failure multipliers reproduce from keyed streams; realized means versus .20 and the configured claim rates are reported; the temporary-use occasion weighting matches a fixture. |

Acceptance status: **NOT_RUN**. Record executed results and artifact hashes; prose requirements are not implementation evidence.
