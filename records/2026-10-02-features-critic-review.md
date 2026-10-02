# Independent review of feature engineering (component 06), 2026-10-02

Reviewer: an independent critic agent on the Fable model, briefed as a chief data scientist. It worked read-only
on commit `952e846` (18 model features, v1.3 worlds) and re-derived every feature with its own code. While it
ran, the working tree moved to the 16-feature contract (AM-26) and the feature artifacts were rebuilt; the critic
confirmed the 18 column values it measured are identical under both. The text below is the critic's report,
lightly reformatted. All numbers are the critic's measurements.

Action taken on each finding is recorded in `records/2026-10-02-features.md` (section "Review findings and
what was done") and in `final-spec/DECISIONS.md` (amendment 1.4).

## Verdict

The 18 features are implemented exactly as the v1.3 specification and contract describe, are deterministic, do
not read private truth, and are invariant to row order and to return identifiers. All 18 were re-derived for
every W2101 customer and matched the frozen artifact to the last bit. They are fit to train on: a simple
grouped-by-world logistic model (median imputation plus missing indicators) reaches out-of-fold AUC 0.926 and
precision 0.531 at the 5% budget against 0.213 for raw return rate, and beats the baseline on all three segment
false-positive rates. Fix before or alongside training, in this order:

1. `residual_z` is confounded with volume by its square-root-of-N scaling and selects defective-product buyers
   at nearly twice the rate of the raw-rate rule;
2. the two raw graph features encode household membership far more than ring membership (the AM-26 change that
   makes them evidence-only is supported by these measurements);
3. the wardrobing indicator has a design defect that a per-line late-request count fixes (measured);
4. the exploration is missing the analyses that matter for the error account: honest look-alikes, detectability
   per abuse type, and a multivariate dry run.

## Major findings

**M1. `residual_z` is a volume-weighted rate, not a product-adjusted rate, and it hurts the defective-buyer gate
leg (DESIGN).** Pooled over ten worlds, 53,024 eligible: `expected_return_rate` has standard deviation 0.016 (1st
to 99th percentile 0.164 to 0.249), so the adjustment is almost constant; Spearman(raw, z) = 0.925. What z adds
is the square root of N: among honest customers Spearman(|z|, mature sale lines) = 0.245. Defective buyers
average 38.4 mature lines (honest overall 20.6). At the 5% budget: raw rate precision 0.213, false-positive rate
heavy 0.446 / defective 0.061 / household 0.042; `residual_z` precision 0.233, heavy 0.376 / **defective 0.109** /
household 0.040. The record's claim that "defective-product buyers come down from a raw rate of 0.22 to a
residual of 0.09" compares a rate with a z-score; in rank terms the mean percentile moves only 0.637 to 0.612,
and at the budget z selects them more. `excess_rate = raw - expected` and `z / sqrt(N)` both restore the
defective false-positive rate to 0.058-0.060 with identical AUC (0.786). The overdispersion factor `d` is inert:
in W2101 80% of customers have d = 1, 99th percentile 1.33, maximum 2.0. Fix: keep `residual_z` only if the gate
dry run shows the boosted model does not lean on it for high-volume honest customers; otherwise replace it or
add `excess_rate` (dated record needed), and say in the record that the residual is not a de-volumed signal. The
explanation screen should never present z as "adjusted for defective styles" for high-volume customers.

**M2. Graph features are mostly household detectors (DESIGN / SPEC).** Edges across the ten training worlds:
6,884 household against 2,406 ring. Eligible customers with a supported neighbour: 6,292, of which 5,064
household-only, 1,029 ring-only, 199 both. 77% of the benign-household segment has a supported neighbour. Ring
abuser against honest household AUC: `supported_neighbor_count` 0.611, `max_identifier_fanout` 0.712.
`max_identifier_fanout` alone at the 5% budget gives household false-positive rate 0.190 (raw-rate rule 0.042).
The identifier type separates them better than the count: rings share device and payment (69% of ring abusers
share a payment identifier), households share address and device (30% share a payment identifier). AM-26 is
consistent with this; if a link feature is wanted in the model, "shares a payment instrument with 2-25 other
accounts" (AUC 0.696 ring against household) is the better-grounded candidate, through a dated record.
`coordinated_claim_share > 0` is strong where defined (435 abusers against 66 honest, all 66 household members;
precision 0.868).

**M3. Label-adjacent look-alikes the exploration never examined (EDA GAP).** (a) 285 eligible ring members have
y = 0 (no completed action yet) and carry ring-like links; they are honest by label and will be scored as
abusers. (b) Repeat genuine claimants: 3,857 honest eligible customers requested two or more genuine
fulfilment-failure units against 958 solo-claim abusers. Between those groups `claim_share` AUC is 0.656 and the
claim-line count AUC is 0.503. In the critic's logistic selection, 639 of 1,244 false positives are repeat
genuine claimants. The record should name this as the dominant honest look-alike, ahead of heavy returners. (c)
Per abuse type (AUC against all honest): temporary-use-only abusers (955) are invisible to `claim_share` (0.518)
and rely on `late_window_share` (0.834), `median_window_ratio` (0.831) and raw rate (0.760); solo claimants rely
entirely on `claim_share` (0.940). The logistic recalls 669 of 875 ring, 387 of 958 solo and 290 of 955
temporary-use-only abusers at 5%. 28.5% of eligible abusers have exactly one completed action; 634 of the
logistic's misses are single-action abusers.

**M4. Wardrobing indicator: design defect, with a measured fix (DESIGN).** The per-line window ratio on item
returns is a clean signal (P(ratio >= .75 | temporary use) = 0.467 against 0.022 honest). The indicator throws
it away by aggregating to customer medians and means: `median_window_ratio >= .75` fires for 8.6% of
temporary-use customers and `latency_z >= 1` for 37%. Current: elevated precision 0.239, recall 0.129; elevated
or possible 0.167 / 0.252. Alternatives on the same population: **two or more item-return lines with ratio
>= .75: precision 0.466, recall 0.362** (862 flagged); two or more late lines or (one late line and late share
>= .5): 0.352 / 0.469. 90% of current elevated false alerts have two or fewer item-return lines. Fix: re-specify
the band on late-line count and share with a dated record. The implementation matches the specification; the
specification is the problem.

**M5. Working tree and artifacts out of sync with the reviewed commit (PROCESS).** The uncommitted AM-26 edits
and the rebuilt 16-feature artifacts must be committed together with the decision and the dry-run numbers
before the 16-feature matrix is used; `features.yaml` at the reviewed commit said version 1.1.

## Minor findings

- **Small uploads.** Features depend on the uploaded population: on random subsets of W2101, `residual_z` moves
  by a median of 0.756 for 100 customers, 0.100 for 500 and 0.053 for 2,000; `supported_neighbor_count` changes
  for 10-13% of eligible customers at every size. Component 11 sets only maximum sizes. Fix: a minimum
  eligible-population check or a fallback warning on the inference report.
- **`claim_share` is mostly a has-claim indicator.** 72% of defined values are exactly 0; "has any claim line"
  AUC 0.777 against 0.783. The 20% of honest eligible customers with no requests make six composition features
  null for honest customers only, which is legitimate.
- **Specification deviations that do not change values.** "Unknown category rejects" is implemented as unknown
  SKU rejects; "empty versus failed graph" has no failure path; the reference was fitted on all ten training
  worlds while component 07 says fold-local (harmless while no fallback is used and wardrobing is not a model
  input); `bracketing_share` counts sizes over mature lines only.
- **Record wording.** The defective-buyer sentence (M1). "Features are stable" is true for means, but the
  relative range of `trend_90d` is 2.7 and of `residual_z` 0.66. "Three of the four strongest features are
  near-duplicates" should be stated as a tree-model risk.

## Test coverage

Exercised: FEAT-AC-01 to 06 and 08 by fixtures. Not genuinely exercised: FEAT-AC-07 (the test checks column names
only; it never changes private labels and recomputes), the style-signal boundaries at exactly .30 / .075 / three
claimants, "counts each own line once" with two matching neighbours, the exclusion of withdrawn requests, d > 1,
the `trend_90d` windows, `late_window_share` / `median_window_ratio` from real tables, negative-day requests,
and `requested_refund_ratio` with discounts.

## Risks for training and the gate

Trees will split on `mature_sale_lines` / `log_order_count` and on the volume part of `residual_z`; the
volume-only reference will look weak while volume still drives selection inside the model. Expect the
heavy-returner leg to pass easily, the defective leg to be the tight one, and the household leg to fail for any
model given raw link counts. The 0.75-0.85 target is not reached by a logistic model (0.53). Honest ring members
and repeat genuine claimants will be the visible false positives in the demo.

## Checked and found sound

All 18 feature values (independent derivation, 10,000 customers, zero mismatches including null patterns);
determinism; row-order invariance; invariance to renumbered return identifiers and to dropping refund,
disposition, header and customer-attribute columns; model features invariant to the reference when no fallback
is used; truth never read; null rules; empty-returns and empty-orders worlds; style evidence against product
truth (targeting precision 1.0, recall 0.868 over 38 targeted style-worlds; quality 1.0 / 1.0 over 30
defect-prone styles); thresholds in code match the specification; integer wardrobing points.

## Not checked

Whether excluding abusers' requests from `fit_reference` would move the latency baseline; fixture and stress
worlds beyond artifact integrity; performance at the 2,000,000-row limit; the uncommitted v1.4 code beyond the
diff summary; the modeling and evaluation modules.
