# Independent review of the EDA and the generated worlds, 2026-10-02

Reviewer: an independent critic agent on the Fable model, briefed as a principal data scientist. It worked
read-only on commit `39213ec` (branch `v1`), read the specification, generator, exploration code, notebook and
reports, and ran its own analysis over the ten training worlds plus W2504 and W2001. The report below is the
critic's own text, lightly reformatted. "VERIFIED" means measured by the critic; "INFERRED" means from reading
code or the specification.

Claims 1, 2, 5 (same-day orders) and the header-numbering bug were re-checked by the project on worlds 2101,
2105 and 2110 and hold. The modelling numbers under "calibration targets" are the critic's approximation with a
hand-written logistic regression; no model exists in this repository yet.

## Verdict

The data is structurally clean and the EDA is competent on everything it chose to look at, but it is **not yet
fit to build the model story on**, for three reasons.

1. The abuse layer carries **mechanical signatures that are not behaviour**: coordinated claims use a
   different latency law than every honest claim (11.5% land in a latency range no honest claim can occupy),
   98% sit on single-line, quantity-1 orders versus 34% of honest claims, and abusive lines are numbered out of
   chronological order inside mixed return headers.
2. The simulated retailer is **implausible on its time axis**: base order volume triples between February and
   August with a flat established base, 16% of orders are same-day duplicates, new accounts order about four
   times a week, and ring campaigns pile into the last 90 days (70% of coordinated claims, 43% on unmatured
   lines).
3. The **calibration targets conflict**: a grouped-by-world out-of-fold logistic model on spec-like features
   reaches 0.60-0.69 precision at 5%, not 0.75-0.85, and the only permitted lever that lifts it (action rate)
   also lifts the baseline out of its band (W2506: 0.448).

Fix first: unify the claim-latency law and campaign-order basket composition (specification), fix header line
numbering (generator), and re-derive tenure and order intensity so volume and ring timing are stationary.

## Findings, ranked

### MAJOR: coordinated-claim latency is a deterministic leak (SPEC issue, implemented faithfully)

Component 02 mandates a Gamma(2,3)-day delay truncated at 30 for coordinated claims, while honest and solo
claims use uniform(0, min(10, window)) (`returns.py`, `abuse.py`). VERIFIED over ten worlds: honest claims max
10 days (24,043 lines), solo abuse max 10 (7,476), coordinated p99 = 18.8, max 30; **243 of 2,120 coordinated
claims (11.5%) exceed 10 days and 100% of claims with latency above 10 are abusive**. Claim window ratio: honest
max 0.333, coordinated up to 0.70, so `median_window_ratio` and `late_window_share` will encode it. The record's
sentence "deceptive claims and honest claims have the same timing (mean 0.14), by design" is wrong for
coordinated claims; pooling solo and coordinated hid the tail.

Fix: one latency law for all transaction claims (give honest claims the same Gamma tail, or draw the coordinated
delay from the solo law).

### MAJOR: campaign orders are structurally identifiable (SPEC issue)

Specification: campaign order = "one line, quantity 1". VERIFIED: 97.9% of coordinated claims are on single-line
orders against 34.1% honest and 50.3% solo; 2,831 of 2,901 attempts are campaign orders (70 reuse a purchase), so
the ring layer is almost entirely these orders; they are on price-weighted hot-list styles (claimed unit price
mean 2,820 against 2,278) and never multi-line. A hand rule ranking by "number of claimed single-line orders"
gets 0.475 precision at 5%, beating the claim-count rule (0.417): order composition, not behaviour.

Fix: give campaign orders the base basket law (hot-list line plus Poisson filler lines) and the base quantity
law.

### MAJOR: ring activity is concentrated at the end of the window (DATA; consequence of AM-15 and short tenures)

Ring formation = latest signup among claim-capable members; 40% of propensity accounts are in rings and
New_Growth and High_Intensity tenures are at most 160 days. VERIFIED: campaign orders per world per month rise
from 2.8 (September 2025) to 92.6 (August 2026); coordinated claims sit on lines delivered a median 49 days
before the cutoff against 172 for honest; 70% in the last 90 days against 32%; **43% on unmatured lines against
13%**. `trend_90d` and `open_window_share` will learn "recent claim = ring", validation worlds will reproduce
it, and the explanation shown to a jury would be a generator artefact.

Fix: draw ring membership so rings exist across the window (for example, form rings only among members with
tenure of at least 180 days, or spread campaign dates from min(formation, history_start + k)).

### MAJOR: order volume and intensity are not retail-plausible (DATA / SPEC profile-config)

VERIFIED, ten worlds pooled: base orders August 2026 / February 2026 = 3.03; orders per day in the last eight
weeks 433 against 159 in January to March; the base older than 365 days is flat (about 123 per day), so **all
growth comes from new accounts**, which supply 58% of recent orders. 16.3% of orders are same-day duplicates by
the same customer (35% for tenure up to 60 days; 9,757 customer-days with three or more orders) because
`rng.choice(..., replace=True)` samples dates with replacement and the per-day cap is only on the target. Tenure
up to 14 days: median 4.4 orders a week; 4,211 customers average two or more a week. Signups jump from 230 a
month before the window to 328 a month inside it. A retail reviewer will not accept this; new-account recency
also correlates with the 1.5x and 2x persona multipliers (eligible prevalence 7.1% at up to 160 days against
5.2%).

Fix: scale order targets by eligible_days / 365, sample dates without replacement, and draw tenures from one
smooth hazard.

### MAJOR: return-header line numbering reveals abusive lines (GENERATOR BUG)

`assemble.build_return_tables` numbers honest lines first and abusive lines after them. VERIFIED: 364 headers
have a line whose `requested_at` precedes the previous line's; all 364 offending lines are abusive (145
contents, 140 nonreceipt, 79 temporary use), zero honest. Small (2.6% of abusive lines) but 100% precise.

Fix: number lines by `requested_at` only; keep honest-ID stability by testing content rather than line numbers
under abuse-off.

### MAJOR: the graph signal is noise-free, so `coordinated_claim_share` is a label (DATA / SPEC)

VERIFIED: eligible customers with at least one linked claim line: 525, of which **2 are honest** (W2504 with
doubled households: 73, 2 honest; W2001: 9, 0). P(abuse | ring member with a supported neighbour) = 0.844 against
0.064 for linked household members; no ungrouped account has any edge. Honest fulfilment failures are drawn
independently per unit, so two linked honest customers never claim the same style within seven days.
Consequence for the AM-17 decision: precision 1.0 "at every threshold" is not evidence about the 0.05 share;
`linked_claimers >= 3` does all the work (untargeted styles never exceed 2 claimers; 8 of 330 reach 2), and the
three misses at 0.05 all have 3-4 claimers. The threshold was set and evaluated on the same ten worlds; recall
37/40 has a 95% interval of 0.81-0.98 and 37/37 precision cannot exclude an 8% false-fire rate.

Fix: inject correlated honest claims (a shared address failure affects all packages to that address in a
window; household co-returns), then re-derive the thresholds and report intervals.

### MAJOR: calibration targets likely unreachable together; household gate leg at risk (SPEC / next stage)

VERIFIED with a numpy logistic regression, five folds grouped by world: 15 spec-like features give precision at
5% of 0.604 (per world 0.58-0.63), recall 0.54; with log and interaction terms 0.675; adding the shortcut
features above 0.693. Recall for temporary-use-only abusers (1,119 of 3,326 eligible positives) is 0.46 and for
one-action abusers (903) 0.24, which caps any model well below 0.85. The baseline is in band (0.216) but W2506
shows action rate x2 pushes it to 0.448, so the lever that lifts the model breaks the baseline target.
Approximate gate dry run: baseline household FPR 0.044-0.045; spec-like logistic 0.055-0.072 (fails the leg);
richer logistic 0.039-0.050 (passes under the broad "any shared identifier" definition, fails under "linked").
Nonacting ring members (296 eligible, labelled honest) are selected at 0.11-0.13. Report achieved values rather
than the band, and expect the household leg to decide selection.

### MINOR: targeting and quality truths are degenerate (SPEC)

VERIFIED: `hot_listed == targeted` in 40 of 40 style-worlds; `sub_threshold` never occurs at 10,000 customers.
Damage share: defect-prone 0.369-0.448 against ordinary at most 0.039, a ten-fold gap, so the quality detector's
30 of 30 is trivial, not a demonstrated capability. Realistic quality-complaint shares on ordinary apparel are
far above 2%.

### MINOR: negative-only markers by design (DATA)

VERIFIED: all 4,155 out-of-window requests and all 8,263 withdrawn lines are honest; `quantity_returned > 1`
occurs on 5,226 honest lines and zero abusive; header `return_channel = not_applicable` is 63% for coordinated
against 3.3% honest (implied by the reason-code mix, not an independent leak). None is fatal, but a model with
access to request-level data would exploit them; `features.yaml` mostly shields the 18 features.

### MINOR: honest repeat-claimant volume (DATA, disclosed lever)

VERIFIED: 4,510 eligible honest customers (8.1%) have two or more genuine fulfilment-failure units in a year,
2,135 have three or more. The record flags this; it is the main source of model false positives (633 of 1,187
in the critic's out-of-fold top 5%).

### EDA gaps against component 05 and good practice

- No audit of operational artefacts (latency law, header order, order composition, quantities, status); the
  shortcut table stops at persona and order count. This is the gap that let the three major leaks through.
- No label-free gate dry-run approximation; segment false-positive rates of the two rules were computable now
  and would have shown the household leg.
- "Prevalence by opportunity count" (specification wording) is replaced by order-count buckets; opportunities
  drawn per account are in `action_truth` and unused.
- Distributions, relationships, hot-list coverage and fan-out are shown for W2101 only; no per-world dispersion
  or intervals anywhere (style recall, rule precision, segment sizes).
- The order-volume trend is plotted and mentioned as "to watch" but never quantified or tied to persona or
  abuse; campaign timing is never examined.
- The record sentence "431-493 honest customers with 2+ genuine claims against 366-402 abusers" mixes
  all-customer counts with a rule evaluated on eligible customers (eligible: 4,417 honest against 1,875 abusers
  with two or more claim lines); the conclusion survives, the numbers do not support the sentence.
- Grouped cross-validation across worlds from one configuration is a stability check, not generalization (the
  notebook says so; the record should too).
- The analyst rulebook as specified (the critic's approximation: 0.32) underperforms the trivial claim-count
  rule (0.417); the "rule misranks" story is strong only against raw return rate.

## Checked and found sound (VERIFIED unless noted)

All 20 worlds validate; no orders before signup or launch, no requests after the cutoff. IDs are SHA-derived
tokens and tables are sorted by primary key (INFERRED: customer index is random with respect to persona).
Request hour-of-day, status, received-flag, refund-method and channel distributions are near-identical across
honest, solo and coordinated requests. Every deceptive code has honest use in every world. Realised
4.0% / 3.1% / 0.6% propensity, action rate 0.198, and claim, damage and cancel rates match their targets; W2507
independence holds. Delivery timing (order to delivery 2-9 days, tail to 14), category return rates 17-21%,
festive share 27% of orders in 16% of days, and refund logic are plausible. Eligibility accounting reconciles;
the raw-return-rate baseline is 0.216 as reported. The temporary-use reason mix differs from honest but is not
deterministic.

## Not checked

Actual gradient-boosting or isolation-forest performance (no scikit-learn in the environment); the exact
component-08 segment definitions (defective-buyer unit join not cached; household approximated two ways); stress
worlds other than W2504 and fixtures other than W2001 with the critic's own probes; notebook 01 and the
acceptance register.
