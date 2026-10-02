# Validation and model selection, 2026-10-02

Experiment `EXP-20261002-01`, specification v1.5 (components 08 and 09). Machine-readable results:
`data/artifacts/experiments/EXP-20261002-01/reports/validation.json` and `selection.json` (frozen
2026-10-02T16:49:15Z at commit `4da2cbd`, clean tree). Simulated data only.

**This record was written before the final test was run**, so that the test cannot colour how validation is
described. The final test has its own record.

## What was done

The five validation worlds (seeds 2201-2205, 10,000 customers each) were generated after the gate dry run was
recorded, by the same generator code and configuration as the training worlds. Their features were built with
the reference frozen from training worlds. The five frozen estimators and the two frozen references scored
them; nothing was fitted. The gate was applied once and the selection frozen.

## Scorecard at the 5% review budget (1,420 reviews over five worlds; 28,353 eligible customers, 1,599 abusers)

| Ranking | Role | Correct | Precision | Per world | Recall | Heavy returners | Defective buyers | Households | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| Raw return rate | baseline | 345 | 0.243 | 0.22-0.27 | 0.216 | 0.452 | 0.060 | 0.030 | comparison |
| Analyst rulebook | reference | 501 | 0.353 | 0.34-0.38 | 0.313 | 0.382 | 0.055 | 0.034 | report only |
| Volume only | reference | 91 | 0.064 | | 0.057 | 0.053 | 0.116 | 0.057 | report only |
| Logistic regression | candidate | 904 | 0.637 | 0.62-0.66 | 0.565 | 0.093 | 0.029 | 0.024 | passed |
| **Boosted trees, 15 leaves** | candidate | 1,004 | **0.707** | 0.68-0.73 | 0.628 | 0.075 | 0.023 | 0.020 | **passed, selected** |
| Boosted trees, 31 leaves | candidate | 1,002 | 0.706 | 0.68-0.73 | 0.627 | 0.077 | 0.024 | 0.019 | passed |
| Isolation forest, 256 | candidate | 314 | 0.221 | | 0.196 | 0.041 | 0.009 | 0.038 | rejected: precision, households |
| Isolation forest, 1,024 | candidate | 343 | 0.242 | | 0.215 | 0.041 | 0.010 | 0.039 | rejected: precision, households |

Segment sizes: 2,379 heavy returners, 5,418 defective-product buyers, 3,487 household members (each needs 200).
Spread over 1,000 resamples of whole worlds: boosted 15 leaves 0.692-0.722, rule 0.229-0.257, difference
0.448-0.480. This is spread between simulated worlds, not a significance test.

**Selection: `hgb_leaf15`.** It leads the 31-leaf model by two correct reviews, so the two are equivalent; the
rule is highest precision, then smallest worst-segment rate, then registered order.

Validation is where the dry run said it would be (0.69-0.71 was expected). The selected model's file hash is
recorded in `selection.json`; it is the training fit and was not refitted on validation.

## What the selected model gets wrong (validation)

- **416 false positives.** 74% are honest repeat claimants (two or more genuine fulfilment failures), 43% honest
  heavy returners, 31% defective-product buyers, 16% household members; 11% are in none of these groups. Groups
  overlap.
- **595 missed abusers of 1,599.** By completed actions: 321 of 451 abusers with one action are missed (71%),
  231 of 610 with two or three (38%), 43 of 538 with four or more (8%). 58% of the missed made a deceptive
  contents claim, 33% a temporary-use return, 28% a deceptive non-receipt claim.
- **Model against rule.** 1,042 customers are selected by the model and not by the rule; 728 of them (70%) are
  abusers. 1,042 are selected by the rule and not by the model; 973 of them (93%) are honest, all of them heavy
  returners.
- **Outside the ranking.** 177 of 1,776 abusers (10%) have fewer than three mature sale lines.

## Report-only evidence (validation)

| Signal | Fired or flagged | Correct | Precision | Recall |
|---|---|---|---|---|
| Style targeting | 19 styles | 19 | 1.00 | 0.95 (19 of 20 targeted) |
| Style quality | 15 styles | 15 | 1.00 | 1.00 |
| Wardrobing, elevated | 211 customers | 199 | 0.94 | 0.32 |
| Wardrobing, elevated or possible | 498 customers | 366 | 0.73 | 0.59 |

Wardrobing alerts among honest customers with any late request (including after the window): 124 of 2,159;
among honest size bracketers: 45 of 5,605. The targeting and wardrobing figures are as sharp as they are because
of how the simulation generates rings and return timing; they are not capabilities demonstrated on real data.

## How to state the result

Say: "On five held-out simulated worlds the selected model is right about 71% of the customers it sends for
review, against 24% for a return-rate rule and 35% for a hand-written rulebook. Without any timing feature the
same model family is at 56% on training worlds. This is a result about this simulation, not about real returns."

Do not say: significant; that the 0.75-0.85 target was met (it was not); that the heavy-returner comparison is
evidence (that group is defined on the rule's own quantity).

## Before the final test

An independent review (`records/2026-10-02-evaluation-critic-review.md`) reproduced every row of this scorecard
from the frozen estimators and private truth, and asked for these changes to the test routine, all made before
the test worlds were generated:

- the check that the selected model is the one frozen at selection now hashes the model file itself, before
  anything is scored;
- records are written through a temporary file and a rename; if the process dies after the test report and
  before the selection record is updated, the next call completes the record without scoring again; a missing
  report with a tested selection does not allow a second run;
- test worlds must be generated after the freeze and by the same generator code and configuration;
- the timing-feature ablation (AM-31) is recorded in `reports/timing_ablation.json` and published with the
  experiment report.

**Stated before the run:** the gate on the test worlds is the same point-estimate rule. On validation the
model's household rate was above the rule's in one world of five (W2204: 0.034 against 0.031) while the pooled
rate was well below (0.020 against 0.030). Resampling the five validation worlds gives the pooled household leg
a chance of about 1 in 140 of failing; precision and the other legs never fail. If the test fails, the model is
not promoted, no runner-up takes its place, and the return-rate baseline serves.
