# Feature engineering and explanatory evidence

Version 1.1 (amended 2026-10-02) | Implementation baseline | Component FEAT

## Requirements and boundary

Compute one row per customer/world. Complete population context required. Snapshot aggregates may recompute at inference; learned transforms may not refit.

On mature sales q=purchased units, r=non-withdrawn requested units (validated r<=q); N_c=sum(q), R_c=sum(r). Exclude self from category peers mu_cat=(R_cat-R_c,cat)/(N_cat-N_c,cat); no peers -> frozen training category mean. Unknown category rejects. mu_style=(R_style-R_c,style+20*mu_cat)/(N_style-N_c,style+20). p_cs=(R_s-R_cs+20*mu_style)/(N_s-N_cs+20). E=sum(q*p); V=sum(q*p*(1-p)); d=min(4,max(1,mean mature line count per customer/order/style)); residual_z=(R-E)/sqrt(d*V), null if V=0. This is heuristic, not significance.

features.yaml fixes order, observation sets, weights and nulls. Mature sets govern rates/residual/requested-value ratio. Composition/timing use all visible non-withdrawn delivered requests, including unmatured, so recent submitted actions remain visible without assuming retention. Trend delivery dates: cutoff-89..cutoff minus cutoff-179..cutoff-90 inclusive.

Graph: fanout=distinct accounts. Drop individual values with fanout>25; edge needs >=2 shared types. Weight value 1/log2(1+fanout); multiple values of one type still count once toward edge. supported_neighbor_count counts unique adjacent accounts. coordinated_claim_share applies the style-grain linked-claim rule below to the customer's own claim lines. Failure fails job; empty graph valid zeros. Membership is not guilt. Leave-linked-group-out sensitivity is diagnostic unless separately versioned.

Style evidence: rates and shares use mature sales/requests; claim linkage uses all visible non-withdrawn transaction-claim return lines on delivered lines of the style. Support >=20 mature sale lines, not units. damage_share=defective/poor_quality/not_as_described requested units over requested units (exclude carrier damage); claim_share uses the four claim codes. A claim line is linked iff a supported neighbor of the claimant has a transaction-claim line on the same style with requested local dates <=7 calendar days apart; the SKU need not match. linked_claim_share=linked claim lines/all claim lines, null without claims; linked_claimers=distinct claimants with >=1 linked line. Support<20 -> insufficient_support; supported with zero mature requested units and zero visible claim lines -> no_return_evidence. quality_signal=(damage_share>=.30); targeting_signal=(linked_claimers>=3 AND linked_claim_share>=.10). Both -> mixed_or_uncertain; quality only -> quality; targeting only -> targeting; neither -> no_elevated_signal. These thresholds are engineering defaults to confirm on development worlds before validation. The v1.0 induced returner graph and component_share are withdrawn: a linked group of 3-6 can never be half of a style's returners at 10,000 customers. Retain signal booleans/continuous axes. SKU drill-down has own support. Descriptive style shrunk rate=(R_style+20*training_category_rate)/(N_style+20), distinct from customer self-excluding formula.

Wardrobing signals: latency_z>=1, median_window_ratio>=.75, occasion_return_share>=.5, discretionary_share>=.5, bracketing_share<.1. Integer points 30/25/15/20/10, summed as integers (never floating point); indicator_score is the 0-100 total. A band requires >=1 timing signal (latency_z or median_window_ratio): then elevated>=65, possible>=45; without a timing signal the status is no_elevated_signal and the score is still shown. No returns -> insufficient_evidence; missing required measure -> incomplete with no band/score. Per-line z uses latency capped at twice captured window, centered by training category median and divided by max(1 day,IQR). Training quantiles use same capped latency. Customer z is unweighted mean across lines. Missing training category latency baseline means incomplete, not fabricated zero.

Fit median imputation and one missingness indicator per feature on training only; all-null -> 0+indicator. Logistic scales; others do not. Freeze feature shape/order. Exclude IDs, private truth, persona, targets, age, loyalty/status, free text and disposition. Evidence includes measured values, denominator and source keys, not causal attribution.

## Inputs, outputs and dependencies

- Inputs: Complete operational snapshot and frozen training fallbacks.
- Outputs: 18 ordered features, graph, style/SKU evidence, wardrobing indicators.
- Dependencies: contracts/features.yaml and reason-groups.yaml.

## Acceptance criteria

| ID | Pass condition and required evidence |
|---|---|
| FEAT-AC-01 | Hand-calculated partial quantity, two-level shrinkage, sole buyer, single-SKU style/no peers and V=0 fixtures match. |
| FEAT-AC-02 | Ordered 18-feature schema enforced; identity renaming preserving equality leaves features unchanged. |
| FEAT-AC-03 | Eligibility threshold exactly three mature lines; recent requests affect composition but not mature rate. |
| FEAT-AC-04 | One shared type no edge; two edge; fanout26 value removed; empty vs failed graph distinguished. |
| FEAT-AC-05 | All six style states and signal boundaries correct; claims 7 days apart link and 8 do not; different SKUs of one style link; unsupported neighbors never link; low-link misses reported. |
| FEAT-AC-06 | Wardrobing integer boundaries 45/65, a 45-point case without a timing signal (no band), zero-IQR, capped-latency and no-return fixtures match without mixing into model risk. |
| FEAT-AC-07 | Changing private labels with operational inputs fixed changes no features or predictions. |
| FEAT-AC-08 | coordinated_claim_share matches the style-grain linked-claim rule on a hand-built fixture and counts each own line once. |

Acceptance status: **NOT_RUN**. Record executed results and artifact hashes; prose requirements are not implementation evidence.
