# Final test, 2026-10-02

Experiment `EXP-20261002-01`, specification v1.5 (component 09). Machine-readable result:
`data/artifacts/experiments/EXP-20261002-01/reports/test.json` (recorded 2026-10-02T17:06:34Z at commit
`62bb9aa`, clean tree); `selection.json` now carries `final_test_status: passed`. Simulated data only.

**The test was run once.** The five test worlds (seeds 2301-2305) were generated after the selection was
frozen, by the same generator code and configuration as the training worlds, and were scored once with the
frozen `hgb_leaf15` estimator and the return-rate rule. Nothing was fitted, no other candidate was scored, and
the routine cannot be run again for this experiment.

## Result at the 5% review budget (1,417 reviews over five worlds; 1,643 eligible abusers)

| Ranking | Correct | Precision | Per world | Recall | Heavy returners | Defective buyers | Households |
|---|---|---|---|---|---|---|---|
| Raw return rate | 339 | 0.239 | 0.22-0.27 | 0.206 | 0.445 | 0.060 | 0.041 |
| **Boosted trees, 15 leaves (selected)** | 1,013 | **0.715** | 0.66-0.76 | 0.617 | 0.073 | 0.023 | 0.021 |

**Gate: passed.** Precision is higher than the rule's and the review rate is lower in each honest group.
Segment sizes: 2,422 heavy returners, 5,650 defective-product buyers, 3,446 household members; none is below
200, so there is no coverage limitation. Spread over 1,000 resamples of whole worlds: model 0.686-0.743, rule
0.224-0.255, difference 0.446-0.498. This is spread between simulated worlds, not a significance test.

The three measurements agree: 0.694 out of fold on training worlds, 0.707 on validation, 0.715 on test.

**Other budgets.** Top 1%: model 0.979 precision (recall 0.17), rule 0.333. Top 10%: model 0.464 precision
(recall 0.80), rule 0.211.

**Recall by kind of abuse at 5% (model against rule).** Deceptive non-receipt 0.70 against 0.28; deceptive
contents 0.65 against 0.25; temporary use 0.67 against 0.17; coordinated 0.78 against 0.30.

## Errors on the test worlds

- **404 false positives**: 72% honest repeat claimants, 44% heavy returners, 32% defective-product buyers, 18%
  household members, 9% in none of these groups (groups overlap).
- **630 missed abusers of 1,643**: 328 of 452 with one completed action (73%), 239 of 638 with two or three
  (37%), 63 of 553 with four or more (11%).
- **Model against rule**: 1,029 customers are selected by the model and not by the rule, 728 of them abusers
  (71%); 1,029 by the rule and not by the model, 975 of them honest (95%).
- **Outside the ranking**: 211 of 1,854 abusers (11%) have fewer than three mature sale lines.

## Report-only evidence on the test worlds

| Signal | Fired or flagged | Correct | Precision | Recall |
|---|---|---|---|---|
| Style targeting | 18 styles | 18 | 1.00 | 0.95 (18 of 19 targeted) |
| Style quality | 15 styles | 15 | 1.00 | 1.00 |
| Wardrobing, elevated | 227 customers | 210 | 0.93 | 0.34 |
| Wardrobing, elevated or possible | 545 customers | 382 | 0.70 | 0.61 |

## What follows

- The selected model is eligible for promotion. `arai publish` builds its bundle from the training fit and points
  serving at it.
- The 0.75-0.85 development target was not met (AM-30). The result that survives without any timing feature is
  0.56 on training worlds out of fold (AM-31).
- This is a result about one simulation. Passing here is not readiness for real returns.
- Any change to features, models, the generator or the gate that is prompted by these test results needs a new
  experiment with untouched test worlds; this experiment and its records stay as they are.
