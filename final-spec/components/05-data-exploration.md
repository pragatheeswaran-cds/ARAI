# Exploratory data analysis and diagnostics

Version 1.0 | Implementation baseline | Component EDA

## Requirements and boundary

Explore fixtures/training/stress before validation generation. Sealed test cannot guide fixes. Show counts/keys/nulls, time coverage, signup/launch feasibility, basket/quantity/order distributions, mature exposure, reason/latency/windows, currency and target-vs-realized deviations.

Report eligibility/excluded abuse, opportunities/blocks/completions, prevalence by persona/opportunity count, overlapping action/benign groups, style support, genuine/deceptive code overlap, assigned/observed relationships and graph fanout/connectivity. Distinguish units/lines/orders/customers.

Private exploration is offline only; never persist private fields in operational features. Persona/opportunity classifiers use held-out data, not training accuracy. All-1 propensity does not imply completed-action AUC=.5: more opportunities can lead to more completed actions. Normal-world persona AUC>.60 triggers investigation, not automatic failure/resampling. Stress 2507 checks allocation independence among actionable profiles.

Optional profile clustering measures structure, not detection success. Enrichment=(positive_subset/subset_size)/(positive_total/population). N1000/positive200/noise300/positive_noise40 gives .667 enrichment and .20 recall. Zero denominator null.

Record conclusions, limits and dated config changes before validation. Do not change households/gate/truth to make a model win.

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

Acceptance status: **NOT_RUN**. Record executed results and artifact hashes; prose requirements are not implementation evidence.
