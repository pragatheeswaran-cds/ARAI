# Independent re-review of the regenerated worlds, 2026-10-02

Reviewer: an independent critic agent on the Fable model, briefed as a chief data scientist. It worked read-only
on the v1.3 worlds (commit `a5024dc`; the manifests' code hash matched the generator under review) and ran its own
scripts over training worlds W2101-W2110 and several stress worlds. The text below is the critic's report, lightly
reformatted. All numbers are the critic's measurements unless marked INFERRED.

Action taken on this report is recorded in `final-spec/DECISIONS.md` (amendment 1.4) and
`records/2026-10-02-gate-dry-run.md`.

## Verdict

The three mechanical leaks the first review named are gone in the request-level data (claim timing, header
order, same-day orders), order intensity is now stationary per account, and the link signal carries some honest
noise. The data is **fit to start building the features and candidates on, with two things to fix first** because
they will shape what the models learn and what the gate decides:

1. a new positional artefact: the claimed unit of a campaign order is always `order_line_no == 1`, so on
   multi-line orders a line-1 claim is 78 times more likely to be a ring claim than a later-line claim;
2. the graph features (`supported_neighbor_count`, `coordinated_claim_share`) are positive for exactly two
   populations, rings and households, so a spec-feature logistic model already **fails the household gate leg**
   (false-positive rate 0.068 against a baseline of 0.043) while passing the other two.

Neither blocks feature engineering; both should be decided before validation worlds exist. The calibration
target of 0.75-0.85 remains unreachable with the permitted levers: a grouped-by-world out-of-fold logistic model
on the 18 specification features gives 0.552 (per world 0.51-0.58).

## Earlier findings, re-measured (ten training worlds pooled)

| Finding | Status | Evidence |
|---|---|---|
| Coordinated-claim latency law | **FIXED** | One Gamma law: honest / solo / ring median 5 days, 95th percentile 14 / 14 / 14, maximum 30 / 30 / 27; share after day 10: 13.7 / 12.8 / 14.2%. |
| Campaign orders structurally identifiable | **PARTLY** | Baskets are now ordinary (campaign single-line 57.9% against 54.8% base; quantities, discounts, channel and fulfilment identical). But claims on multi-line orders sit on line 1 for 98.5% of ring claims against 43.0% honest and 45.1% solo. |
| Return-header line numbering | **FIXED** | No out-of-order line in 235,000 request lines; 1,137 mixed honest and abusive headers now exist. |
| Same-day orders and volume stationarity | **PARTLY** | No same-day customer-day in 813,406 orders. Established accounts are flat outside the festive season (August / February = 1.10). But signups per world-month step from about 250 (October to March) to about 500 (April to August); 61% of those later signups are New_Growth, whose tenure is capped at 160 days. The 1.39 times growth in base orders is this persona artefact, not a smooth hazard. |
| Ring activity end-loaded | **PARTLY** | Ring claims in the last 90 days 32.2% against 22.8% honest; on unmatured lines 13.3% against 8.4%. Ring claims per month double from October to August. Weak likelihood ratio, so `trend_90d` and `open_window_share` carry little (AUC 0.49 and 0.53). |
| Linked-claim signal noise-free | **PARTLY** | 566 linked claimants, 68 honest. P(abuse given an eligible customer with a linked claim) = 0.868 (was about 0.996). All 68 honest are household members. Noise exists but comes from one mechanism (co-order plus shared-fate pairs). |
| Calibration and gate conflict | **NOT FIXED** (not a generator item) | See the model section. Baseline 0.207-0.213 in band; W2506 0.423 out of band. |

## New findings

**MAJOR: campaign claim always on line 1 (GENERATOR / SPEC).** `abuse.draw_basket` puts the target style at index
0 and `run_campaigns` claims `order_line_no = 1`. Among claims on multi-line orders: honest 5,629 on line 1 and
7,465 later; solo 1,399 and 1,701; ring 731 and 11. A hand rule "count claims on single-line orders or on line 1"
reaches 0.470 precision at 5% against 0.415 for plain claim count: position, not behaviour. Not read by the
features, but anyone touching request-level data will see it. Fix: place the target line at a uniform random
position in the basket and claim that line.

**MAJOR: graph features and the household leg (DATA / SPEC).** Households are the only honest source of supported
edges (49% of household members have a supported neighbour; 0% of ungrouped accounts; 66% of ring members). The
specification-feature logistic coefficient on `supported_neighbor_count` is +0.42; its out-of-fold household
false-positive rate is 0.068 against a baseline of 0.043 (fails), and nonacting ring members are selected at
8.8%. Dropping the two graph features passes the leg (0.033) at a cost of 5 points of precision. This is
structural, not a bug: the model learns "has an edge" is about the same as "ring". Options: add honest edge
sources outside households, or accept that the gate will select non-graph candidates and say so in the plan.

**MINOR: whole-order non-receipt is honest-only (DATA).** Delivery incidents lose whole parcels; abusers claim one
unit per order. Whole-order `item_not_received` on multi-line orders: 1,018 honest against 5 abusive. Fix: let a
share of deceptive non-receipt claims cover the whole parcel.

**MINOR: header-level markers implied by the reason mix (DATA).** Abusive claims are 49% `item_not_received`
against 32% honest; `return_channel = not_applicable` 61.7% ring, 35.6% solo, 3.2% honest. Fix: draw the
deceptive claim code with the honest code mix.

**MINOR: signup step at April 2026 (DATA).** About 250 to about 500 signups per world-month, from the New_Growth
160-day tenure cap. Fix: give New_Growth a smooth tenure hazard or lower its share.

**MINOR: campaign filler lines (DATA).** Honest request rate on campaign filler lines 17.5% against 20.6% on base
delivered lines (986 lines, about 2.4 standard errors); campaign orders never bracket.

**MINOR: EDA gap and record.** `reports/eda/2026-10-02/summary.json` says specification 1.2 for v1.3 worlds. The
record attributes volume growth to the growing customer base without saying the base grows because of a signup
step. It does not report that ring claims double through the year, nor a line-position check.

## Residual differences the team kept, against the features

Order size under a claim: not read by any feature; acceptable, but line position (above) is a different thing.
Recency of ring claims: harmless. Withdrawn, late and multi-unit honest-only: features exclude withdrawn lines;
`late_window_share` reads the band where 48% of temporary-use requests sit against 2.2% of honest item returns,
which is the intended wardrobing behaviour, not a mechanical leak. Acceptable.

## Label quality and difficulty (5 folds grouped by world; 53,024 eligible, 2,876 positives)

- Baseline raw return rate 0.207-0.213; claim count 0.415; linked-claim count 0.464.
- Logistic on the 18 specification features with missing indicators: precision 0.552 (0.511-0.576 per world),
  recall 0.509; false-positive rate heavy returners 0.112 (pass), defective buyers 0.034 (pass), households 0.068
  (**fail**).
- Hard positives: 819 eligible abusers (28.5%) have exactly one completed action, recall 0.28; temporary-use-only
  955, recall 0.34; ring participants 875, recall 0.83. Honest look-alikes: 3,746 eligible honest customers with
  two or more claim lines against 1,593 abusers.
- `coordinated_claim_share` is null for 80% of honest customers against 25% of abusers; the missing-value
  indicator matters.

## The targeting threshold (AM-25)

Re-derived identically: 38 targeted style-worlds; fired and correct at 0.05 / 0.075 / 0.10 = 36 and 34, 33 and 33,
30 and 30. Untargeted maximum share 0.0548, maximum four claimants. Leave-one-world-out, choosing the lowest
zero-false-fire threshold on nine worlds, picks 0.055 every time and gets 34 of 34 with no false positive on the
held-out world. Stress world W2506 (action rate doubled): untargeted maximum 0.059 with three untargeted styles at
three or more linked claimants, so the margin to 0.075 is only 0.016. Verdict: defensible as an engineering
default on these worlds, with the caveats that honest noise is structurally bounded because only households
create supported edges, that 0.06 performs identically, and that the claimant-count condition does most of the
work.

## Checked and found sound

Customer index against label AUC 0.499; tenure against label 0.507; hour of day, refund method and refund
arithmetic identical across kinds; `available_at == requested_at` everywhere; address co-claims carry no leak;
household co-orders are recognisable but leak nothing beyond already-visible identifiers and barely move
household metrics; High_Intensity is now established; per-account rates and target realisations match the
record; the quantitative claims in the record's change table all reproduce.

## Not checked

Gradient boosting and isolation forests (no scikit-learn when the review started); the project's `features.py`
against the critic's approximations; fixtures and stress worlds W2502 / W2507; the wardrobing indicator; the
abuse-off equivalence; the acceptance register.
