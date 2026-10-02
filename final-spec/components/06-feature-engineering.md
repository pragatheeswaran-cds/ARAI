# Feature engineering and explanatory evidence

Version 1.0 | Implementation baseline | Component FEAT

## Requirements and boundary

Compute one row per customer/world. Complete population context required. Snapshot aggregates may recompute at inference; learned transforms may not refit.

On mature sales q=purchased units, r=non-withdrawn requested units (validated r<=q); N_c=sum(q), R_c=sum(r). Exclude self from category peers mu_cat=(R_cat-R_c,cat)/(N_cat-N_c,cat); no peers -> frozen training category mean. Unknown category rejects. mu_style=(R_style-R_c,style+20*mu_cat)/(N_style-N_c,style+20). p_cs=(R_s-R_cs+20*mu_style)/(N_s-N_cs+20). E=sum(q*p); V=sum(q*p*(1-p)); d=min(4,max(1,mean mature line count per customer/order/style)); residual_z=(R-E)/sqrt(d*V), null if V=0. This is heuristic, not significance.

features.yaml fixes order, observation sets, weights and nulls. Mature sets govern rates/residual/requested-value ratio. Composition/timing use all visible non-withdrawn delivered requests, including unmatured, so recent submitted actions remain visible without assuming retention. Trend delivery dates: cutoff-89..cutoff minus cutoff-179..cutoff-90 inclusive.

Graph: fanout=distinct accounts. Drop individual values with fanout>25; edge needs >=2 shared types. Weight value 1/log2(1+fanout); multiple values of one type still count once toward edge. supported_neighbor_count counts unique adjacent accounts. Failure fails job; empty graph valid zeros. Membership is not guilt. Leave-linked-group-out sensitivity is diagnostic unless separately versioned.

Style evidence uses mature sales/requests. Support >=20 sale lines, not units. Returner graph is induced by that style's returners; singletons count. component_share=largest component/all unique returners. damage_share uses defective/poor_quality/not_as_described requested units (exclude carrier damage); claim_share uses four codes. Support<20 -> insufficient_support; supported+zero returns -> no_return_evidence. quality=(damage>=.50 AND component<=.15); targeting=(component>=.50 AND claim>=.40). targeting+damage>=.50 -> mixed_or_uncertain; otherwise sole predicate or mixed_or_uncertain if neither. Retain predicate booleans/continuous axes. SKU drill-down has own support. Descriptive style shrunk rate=(R_style+20*training_category_rate)/(N_style+20), distinct from customer self-excluding formula.

Wardrobing booleans: latency_z>=1, median_window_ratio>=.75, occasion_return_share>=.5, discretionary_share>=.5, bracketing_share<.1. Weights .30/.25/.15/.20/.10; elevated>=.65, possible>=.45. No returns -> insufficient_evidence; missing required measure -> incomplete with no band/score. Per-line z uses latency capped at twice captured window, centered by training category median and divided by max(1 day,IQR). Training quantiles use same capped latency. Customer z is unweighted mean across lines. Missing training category latency baseline means incomplete, not fabricated zero.

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
| FEAT-AC-05 | All five style states and threshold boundaries correct; diluted/multi-group misses reported. |
| FEAT-AC-06 | Wardrobing boundary/zero-IQR/capped-latency/no-return fixtures match without mixing into model risk. |
| FEAT-AC-07 | Changing private labels with operational inputs fixed changes no features or predictions. |

Acceptance status: **NOT_RUN**. Record executed results and artifact hashes; prose requirements are not implementation evidence.
