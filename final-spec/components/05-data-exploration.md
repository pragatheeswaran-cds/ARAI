# Exploratory data analysis and diagnostics

Version 1.1 (amended 2026-10-02) | Implementation baseline | Component EDA

## Requirements and boundary

Explore fixtures/training/stress before validation generation. Sealed test cannot guide fixes. Show counts/keys/nulls, time coverage, signup/launch feasibility, basket/quantity/order distributions, mature exposure, reason/latency/windows, currency and target-vs-realized deviations.

Report eligibility/excluded abuse, opportunities/blocks/completions, prevalence by persona/opportunity count, overlapping action/benign groups, style support, genuine/deceptive code overlap, action-rate distribution, genuine claims per address, hot-list coverage, campaign-order versus reused-purchase claims, assigned/observed relationships and graph fanout/connectivity. Distinguish units/lines/orders/customers.

Private exploration is offline only; never persist private fields in operational features. Persona/opportunity classifiers use held-out data, not training accuracy. All-1 propensity does not imply completed-action AUC=.5: more opportunities can lead to more completed actions. Normal-world persona AUC>.60 triggers investigation, not automatic failure/resampling. Stress 2507 checks allocation independence among actionable profiles.

Optional profile clustering measures structure, not detection success. Enrichment=(positive_subset/subset_size)/(positive_total/population). N1000/positive200/noise300/positive_noise40 gives .667 enrichment and .20 recall. Zero denominator null.

Record conclusions, limits and dated config changes before validation. Do not change households/gate/truth to make a model win.

Difficulty calibration is a disclosed development step, not a hidden one. Targets at the 5% budget on pooled out-of-fold training-world scores: raw-return-rate baseline precision .20-.30; best supervised candidate .75-.85; above .90 difficulty must be raised. Permitted levers only: the action-rate Beta parameters, the address multiplier dispersion and the genuine claim rates. Never the gate, truth definitions, eligibility, benign segments or household generation. Calibrate on fixture/training/stress worlds before any validation manifest exists and record each dated change with before/after values. Targets are not acceptance gates: if they cannot be reached with the permitted levers, report the achieved values. Every evaluation report states that difficulty was calibrated and with which levers.

## Inputs, outputs and dependencies

- Inputs: Accepted development tables; separately joined private diagnostic truth.
- Outputs: Versioned reports and summary tables.
- Dependencies: Validation; split boundary in component 07.

## Acceptance criteria

| ID | Pass condition and required evidence |
|---|---|
| EDA-AC-01 | Reports include eligibility/excluded abuse and denominators per world. |
| EDA-AC-02 | Enrichment fixture yields .667/.20; undefined metrics are null. |
| EDA-AC-03 | Reports identify disjoint feature support and genuine/deceptive code overlap. |
| EDA-AC-04 | Equal propensity may coexist with unequal completed prevalence without false failure. |
| EDA-AC-05 | Configuration changes are justified on development data before validation manifests. |
| EDA-AC-06 | Dated calibration record precedes validation manifests, changes only permitted levers and reports achieved baseline and best-candidate precision against the targets. |

Acceptance status: **NOT_RUN**. Record executed results and artifact hashes; prose requirements are not implementation evidence.
