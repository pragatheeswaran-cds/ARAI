# Feature engineering and evidence

Feature unit: one customer at one immutable world snapshot. All candidates use the same ordered numeric feature allow-list. IDs and truth fields never enter X. Deterministic snapshot aggregates can be recomputed for each input batch; this is distinct from refitting a learned transformer or model. Scoring requires a complete declared population snapshot, not an arbitrary customer subset with missing SKU/relationship context.

## Quantities and SKU expectations

For each mature sale line l let q_l be purchased quantity and r_l=min(q_l, submitted return quantity by cutoff). N_c=sum(q_l), R_c=sum(r_l); raw_return_rate=R_c/N_c. Document both units and line counts. Never join raw return rows directly onto sales and then count duplicated exposure.

Let N_s,R_s be mature SKU totals. For customer c compute peer totals N_s-N_cs and R_s-R_cs, and category peer mean mu_cat=(R_cat-R_c,cat)/(N_cat-N_c,cat). If no category peers exist, use the frozen training category mean; if unseen category, reject schema. The shrinkage k=20 is a versioned engineering default:

p_cs=(R_s-R_cs+20*mu_cat)/(N_s-N_cs+20).

Expected returned units E_c=sum_l(q_l*p_cs). Variance V_c=sum_l(q_l*p_cs*(1-p_cs)). Let d=min(4,max(1,mean number of sale lines per (order,style) group)). residual_z=(R_c-E_c)/sqrt(d*V_c); null if V_c=0. This is a heuristic standardization, not a calibrated statistical test because return units need not be independent. Test against hand-computed examples and report its limitations.

This basket adjustment is the first protection for defective-product buyers. Keep refund/coordination signals intact. Do not automatically clear customers when a SKU is flagged. An optional leave-linked-group-out sensitivity check recomputes both SKU and category peer totals excluding the union of self and group; no member is subtracted twice. It is diagnostic unless included in a versioned candidate definition before comparison.

## Numeric model allow-list

| Feature | Definition |
|---|---|
| mature_sale_lines | Count of mature delivered sale lines |
| log_order_count | log1p(unique delivered orders by cutoff) |
| raw_return_rate | R_c/N_c over mature exposure |
| expected_return_rate | E_c/N_c |
| residual_z | Formula above |
| claim_share | Transaction-claim requested units / all requested units; null if no requests |
| requested_refund_ratio | Requested value on mature sales / net value of those sales; net unit value times requested units, independent of eventual payout |
| damage_reason_share | Damage/defect-reason requested units / requested units; claims, not confirmed damage |
| bracketing_share | Mature purchased units in orders containing >=2 distinct sizes of the same style / mature units |
| late_window_share | Requested units with request latency/window >=0.75 / requested units with valid delivered timing |
| median_window_ratio | Median per-return-line latency/captured window, not quantity-weighted; null without valid returns |
| occasion_return_share | Occasion-wear requested units / requested units |
| discretionary_share | Discretionary-reason requested units / requested units |
| trend_90d | Raw return rate on mature deliveries in last90 calendar days minus preceding90; null if either denominator0 |
| open_window_share | Units on unmatured delivered lines / all delivered units |
| max_identifier_fanout | Max distinct account count for any shared device/address/payment; count only equality, cap at25 for numeric feature |
| supported_neighbor_count | Distinct neighbors linked by >=2 different identifier types after dropping values shared by >25 accounts |
| coordinated_claim_share | Fraction of own transaction-claim requests sharing SKU and a +/-7day request window with a supported neighbor; null without own claims |

Counts/values use only available records. Age, persona, loyalty, marketing channel, operational flagged/suspended status, free text, raw identity/SKU strings and disposition are excluded. Return-rate inclusion is permitted because it is contextualized and tested against legitimate controls; no feature alone establishes abuse.

Fit median imputation plus missing indicators on training data only; all-null training columns get0 with an indicator. Freeze feature order and fitted medians. Do not learn a fresh per-batch quantile transform. If a candidate needs scaling, freeze its training scaler. Save training means and category baselines needed for fallbacks with the artifact.

## Graph and SKU evidence

Edges require >=2 shared identifier types; value weight=1/log2(1+fanout). Drop individual values with fanout>25. Use graph support as evidence and numeric neighbor features, never membership-as-guilt. A graph construction failure fails the job rather than silently feeding zeros into a model trained with graph features. A legitimate empty graph yields zeros and a valid no-links explanation.

For SKU with <20 mature sale lines, state insufficient_support. Otherwise show raw rate, shrunk rate, damage-reason share, unique returners and largest connected-component share among returners. With no returns, state no_return_evidence; undefined denominators remain null. Compute quality_signal=(damage_share>=0.50 and component_share<=0.15); targeting_signal=(component_share>=0.50 and transaction_claim_share>=0.40). These draft engineering thresholds are fixed before evaluation. If targeting_signal and damage_share>=0.50, display mixed_or_uncertain; otherwise display the sole fired signal, or mixed_or_uncertain if neither fires. Keep both continuous axes visible. A failed predicate is not proof of no quality problem. Independent SKU truth, not the evidence predicate, defines synthetic quality labels.

## Wardrobing evidence

Separate explanatory indicator uses late-window share, occasion-return share, discretionary share and bracketing context. Preserve the original five-signal formulation as a documented reference; for v0.2 calculate category-relative latency from training return-line median and IQR (floor scale1day). Aggregate customer/category latency z by valid return count. Five booleans are latency_z>=1, median_window_ratio>=0.75, occasion_return_share>=0.5, discretionary_share>=0.5, bracketing_share<0.1. Weighted sum=(.30,.25,.15,.20,.10); elevated>=.65, possible>=.45, otherwise no_elevated_signal. No returns -> insufficient_evidence rather than presumed legitimate. Missing any required measure -> incomplete indicator with available signals, no numeric band.

These thresholds describe a heuristic, not truth or a forced addition to model risk. Explain each fired signal with measured value, denominator and source keys. Include legitimate late-return and size-shopping counterexamples. A model's global feature importance is not a causal explanation for an individual case; evidence tags are explicitly supporting observations.
