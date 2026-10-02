# Deterministic transformations

Canonical feature definitions: feature-spec.yaml; design values: ../00-governance/design-config.yaml. Status DRAFT; formulas with TBD are blocked, not implementation choices.

M04: N_s counts eligible sales lines and R_s eligible returned lines, once Q-002 fixes eligibility. Estimate category means from operational observations only. Shrunk SKU rate is (R_s+k*mu_cat)/(N_s+k), k>0. No-sale SKU yields category mean; empty category is Q-006.

M05: subtract own contributions before shrinkage, never from a shrunk rate. In pass 2 the mathematically necessary exclusion is U = {customer} union excluded_accounts. Subtract each member once from unexcluded SKU totals: (R_s-R_U,s+k*mu_cat)/(N_s-N_U,s+k). This clarifies set subtraction, not whether category means are recomputed or which communities belong to U (Q-006). Excluded accounts remain scored; exclusions affect reference baselines, not scored-population membership.

M06: E=sum(p_i), V=sum(p_i*(1-p_i)), unadjusted z=(R-E)/sqrt(V), adjusted residual_z=z/sqrt(deff). deff=min(4, mean lines per (order,style) group). Source mentions fallback 1.5 without defining thin-history trigger (Q-004). LLD numeric z examples are unadjusted; fixtures for adjusted z must state deff explicitly. A null residual is not an average-risk zero.

M07: five weighted booleans and band boundaries live in threshold-policy.yaml under 04-model. LLD single-line examples are reproducible; multi-return/multi-category customer aggregation is not specified. Do not implement majority/any/max logic without Q-004 approval.

M08: rule_score=min(1,sum weights of true configured predicates)), emitting each rule ID. Operators and exact boundary values come from design-config.yaml. Null predicate behaviour remains Q-004.

M09: rank-transform the exact eight-feature allow-list before fitting the batch. Tie convention, missing value policy, empty/constant batch and anomaly-score orientation/normalization are Q-004/Q-012. No standard scaler, imputer or new feature has been silently added.

M10: d(v)=number of distinct accounts sharing identifier v; drop v if d(v)>25; an account pair needs at least two distinct surviving identifier types. Edge weight=sum over shared surviving values of 1/log2(1+d(v)). Connected components followed by Louvain resolution=1 and seed=20250901. Graph score and giant-component limit remain Q-005.

M11: blended_raw=.40*rule_score+.35*iforest_score+.25*graph_score. risk_score=100*percentile_rank(blended_raw); percentiles/ties/eligible population are Q-012. For counterfactuals zero one component at a time and recompute; whether to hold the reference distribution fixed or rerank all customers requires Q-012. Wardrobing is displayed alongside and never contributes to this blend.

M12: see threshold-policy.yaml for explicit predicates. The no-item fifth signal has no decision threshold and is evidence-only until Q-016; quality_issue does not yet define customer flag suppression. M13 must use the same approved feature path; exact downstream recomputation/refitting is Q-006.
