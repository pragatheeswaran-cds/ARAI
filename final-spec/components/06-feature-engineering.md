# Feature engineering and explanatory evidence

Version 1.4 (amended 2026-10-02) | Implementation baseline | Component FEAT

## Requirements and boundary

Compute one row per customer/world. Complete population context required. Snapshot aggregates may recompute at inference; learned transforms may not refit.

On mature sales q=purchased units, r=non-withdrawn requested units (validated r<=q); N_c=sum(q), R_c=sum(r). Exclude self from category peers mu_cat=(R_cat-R_c,cat)/(N_cat-N_c,cat); no peers -> frozen training category mean. Unknown category rejects. mu_style=(R_style-R_c,style+20*mu_cat)/(N_style-N_c,style+20). p_cs=(R_s-R_cs+20*mu_style)/(N_s-N_cs+20). E=sum(q*p); V=sum(q*p*(1-p)); d=min(4,max(1,mean mature line count per customer/order/style)); residual_z=(R-E)/sqrt(d*V), null if V=0. This is heuristic, not significance.

features.yaml fixes order, observation sets, weights and nulls. Mature sets govern rates/residual/requested-value ratio. Composition/timing use all visible non-withdrawn delivered requests, including unmatured, so recent submitted actions remain visible without assuming retention. Trend delivery dates: cutoff-89..cutoff minus cutoff-179..cutoff-90 inclusive.

Graph: fanout=distinct accounts. Drop individual values with fanout>25; edge needs >=2 shared types. Weight value 1/log2(1+fanout); multiple values of one type still count once toward edge. supported_neighbor_count counts unique adjacent accounts. max_identifier_fanout and supported_neighbor_count are evidence shown to the analyst and are not model inputs (AM-26): the gate dry run showed that a model given raw link structure selects honest household members more often than the return-rate rule does. The model sees links only through coordinated_claim_share, which needs linked accounts to act. coordinated_claim_share applies the style-grain linked-claim rule below to the customer's own claim lines. Failure fails job; empty graph valid zeros. Membership is not guilt. Leave-linked-group-out sensitivity is diagnostic unless separately versioned.

Style evidence: rates and shares use mature sales/requests; claim linkage uses all visible non-withdrawn transaction-claim return lines on delivered lines of the style. Support >=20 mature sale lines, not units. damage_share=defective/poor_quality/not_as_described requested units over requested units (exclude carrier damage); claim_share uses the four claim codes. A claim line is linked iff a supported neighbor of the claimant has a transaction-claim line on the same style with requested local dates <=7 calendar days apart; the SKU need not match. linked_claim_share=linked claim lines/all claim lines, null without claims; linked_claimers=distinct claimants with >=1 linked line. Support<20 -> insufficient_support; supported with zero mature requested units and zero visible claim lines -> no_return_evidence. quality_signal=(damage_share>=.30); targeting_signal=(linked_claimers>=3 AND linked_claim_share>=.075). Both -> mixed_or_uncertain; quality only -> quality; targeting only -> targeting; neither -> no_elevated_signal. Both thresholds were checked on the ten regenerated training worlds on 2026-10-02 (AM-25): the quality threshold was kept and the linked-claim share was set to .075, the lowest value tried that lets no untargeted style through now that honest linked claims exist; they stay fixed from here unless a dated development record changes them before validation generation. The v1.0 induced returner graph and component_share are withdrawn: a linked group of 3-6 can never be half of a style's returners at 10,000 customers. Retain signal booleans/continuous axes. SKU drill-down has own support. Descriptive style shrunk rate=(R_style+20*training_category_rate)/(N_style+20), distinct from customer self-excluding formula.

Late returns: a late return is a visible non-withdrawn item-return line (any reason other than the four transaction-claim codes) requested at 75% to 100% of its captured return window; a request after the window is not a late return. late_return_lines counts them per customer and is the 17th model feature (AM-27): customer-level medians and shares hide a behaviour that shows on single lines.

Wardrobing signals (AM-28, superseding AM-12): repeat_late_returns (late_return_lines>=2) 50 points, late_return (>=1) 25, late_occasion_return (>=1 late return of occasion wear) 15, late_return_share (late_return_lines/item_return_lines>=.5) 10. Points are integers summed as integers (never floating point); indicator_score is the 0-100 total. elevated>=75, possible>=35, otherwise no_elevated_signal: two late returns are always elevated, one late return is possible only when it is occasion wear or at least half of the customer's item returns, and nothing else reaches a band. No item-return line with valid timing -> insufficient_evidence with no score. The rule needs no training reference; the status incomplete is reserved and not produced. The indicator cannot establish wear and never enters the model score.

Fit median imputation and one missingness indicator per feature on training only; all-null -> 0+indicator. Logistic scales; others do not. Freeze feature shape/order. Exclude IDs, private truth, persona, targets, age, loyalty/status, free text and disposition. Evidence includes measured values, denominator and source keys, not causal attribution.

## Inputs, outputs and dependencies

- Inputs: Complete operational snapshot and frozen training fallbacks.
- Outputs: 17 ordered model features, 2 evidence-only link measures, graph, style/SKU evidence, wardrobing indicators.
- Dependencies: contracts/features.yaml and reason-groups.yaml.

## Acceptance criteria

| ID | Pass condition and required evidence |
|---|---|
| FEAT-AC-01 | Hand-calculated partial quantity, two-level shrinkage, sole buyer, single-SKU style/no peers and V=0 fixtures match. |
| FEAT-AC-02 | Ordered 17-feature schema enforced, with the two link measures kept out of the model matrix; identity renaming preserving equality leaves features unchanged. |
| FEAT-AC-03 | Eligibility threshold exactly three mature lines; recent requests affect composition but not mature rate. |
| FEAT-AC-04 | One shared type no edge; two edge; fanout26 value removed; empty vs failed graph distinguished. |
| FEAT-AC-05 | All six style states and signal boundaries correct; claims 7 days apart link and 8 do not; different SKUs of one style link; unsupported neighbors never link; low-link misses reported. |
| FEAT-AC-06 | Wardrobing integer boundaries 35/75, one late return without occasion wear or a half share (25 points, no band), the 75%/100% window boundaries, a request after the window, a claim that is not an item return, and no-return fixtures match without mixing into model risk. |
| FEAT-AC-07 | Changing private labels with operational inputs fixed, or removing private truth altogether, changes no features or predictions. |
| FEAT-AC-08 | coordinated_claim_share matches the style-grain linked-claim rule on a hand-built fixture and counts each own line once. |

Acceptance status is recorded per criterion in acceptance-register.csv (status, evidence, date, reviewer). Prose requirements are not implementation evidence.
