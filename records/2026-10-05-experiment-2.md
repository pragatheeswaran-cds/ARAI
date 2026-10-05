# Experiment 2 (EXP-20261005-02): gate dry run, selection and the final test (2026-10-05)

Contract: specification 2.0, decisions AM-45 to AM-48, recorded in commit a7b79aa before any world of this
experiment existed. Every record below carries that commit with no uncommitted change, the scoring-code hash
`b5a035cb34...`, the generator-code hash of the first experiment (the simulator is unchanged) and the manifest
hashes of the worlds it used.

What is new against EXP-20261002-01: fresh seeds for every world set; 43 features (the first 17 unchanged);
candidates that weight honest repeat genuine claimants in training; a fourth gate leg for that group. How these
were arrived at is in `2026-10-05-experiment-2-exploration.md`. No calibration lever was changed.

All figures are precision at the 5% review budget unless stated. "Repeat claimants" means honest eligible
customers with two or more genuinely failed units; the figure is the share of them sent for review.

## 1. Gate dry run (training worlds W3101-W3110, out of fold)

Recorded 2026-10-05T09:40:00Z, before any validation world existed.

| Ranking | Precision | Recall | Heavy returners | Defective buyers | Households | Repeat claimants | Gate |
|---|---|---|---|---|---|---|---|
| Return-rate rule | 0.259 | 0.222 | 44.6% | 5.9% | 3.9% | 6.6% | reference |
| logreg_c1 | 0.754 | 0.647 | 4.9% | 1.9% | 1.5% | 11.3% | fails the new leg |
| hgb_leaf15 | 0.793 | 0.680 | 4.2% | 1.7% | 1.3% | 9.6% | fails the new leg |
| hgb_leaf15_w4 | 0.781 | 0.670 | 4.9% | 1.4% | 1.2% | 5.2% | passes |
| hgb_leaf15_w6 | 0.767 | 0.658 | 5.2% | 1.5% | 1.3% | 4.5% | passes |
| hgb_leaf15_w8 | 0.759 | 0.651 | 5.5% | 1.5% | 1.2% | 4.0% | passes |
| iforest_256 (in sample) | 0.538 | 0.461 | 6.8% | 3.9% | 2.5% | 21.3% | fails the new leg |
| analyst rulebook (reference) | 0.375 | 0.322 | 37.0% | 5.5% | 3.8% | 11.4% | report only |
| volume only (reference) | 0.078 | 0.067 | 4.5% | 14.4% | 5.1% | 19.0% | report only |

**Development target (AM-45).** The target is defined on these scores: return-rate rule 0.20-0.30, best supervised
candidate 0.75-0.85. Achieved: rule 0.259, best supervised candidate 0.793. Both are inside the band, with no
calibration lever changed; the gain over the first experiment's 0.694 comes from the 26 new features. The best
candidate that also passes the gate is `hgb_leaf15_w4` at 0.781, also inside the band. These training worlds are
a little easier than the first experiment's (rule 0.259 against 0.237), which accounts for about two points.

## 2. What the result depends on (training worlds, out of fold, selected candidate)

| `hgb_leaf15_w6` with | Precision |
|---|---|
| all 43 features | 0.767 |
| only the 17 features of the first experiment | 0.676 |
| without any timing feature | 0.588 |
| without any claim feature | 0.630 |
| without any claim or timing feature | 0.376 |
| (return-rate rule) | 0.259 |

Honest groups sent for review, model against rule: repeat claimants 4.5% against 6.6%; one genuine failure 3.9%
against 5.0%; no genuine failure 0.5% against 3.5%; heavy returners 5.2% against 44.6%; defective buyers 1.5%
against 5.9%; households 1.3% against 3.9%. Repeat claimants are 27% of the model's false positives (12% of the
rule's); in the first experiment they were 73%.

## 3. Stress worlds (frozen estimators, diagnostic)

| World | Rule | hgb_leaf15 | w4 | w6 | w8 |
|---|---|---|---|---|---|
| W2501 ordinary propensity x1.2 | 0.227 | 0.762 fails | 0.734 | 0.720 | 0.720 |
| W2502 ordinary propensity x0.8 | 0.289 | 0.799 fails | 0.796 | 0.771 | 0.775 |
| W2503 defect incidence x2 | 0.254 | 0.764 fails | 0.761 | 0.754 | 0.754 |
| W2504 household share x2 | 0.223 | 0.753 fails | 0.739 | 0.735 | 0.725 |
| W2505 action rate x0.5 | 0.144 | 0.579 fails | 0.554 fails | 0.558 | 0.561 |
| W2506 action rate x2 | 0.441 | 0.899 | 0.874 | 0.871 | 0.860 |
| W2507 persona multipliers all 1 | 0.213 | 0.759 fails | 0.738 | 0.748 | 0.727 |

"fails" means the four-leg gate, always on the new leg. `w6` and `w8` pass on all seven worlds, `w4` on six. The
level still follows the simulated action rate (0.56 to 0.87 for `w6`).

## 4. Validation and selection (W3201-W3205)

Selection frozen 2026-10-05T09:44:55Z. The validation worlds were generated after the dry-run record, by the
generator and configuration of the training worlds (checked in code).

| Ranking | Precision | Recall | Heavy returners | Defective buyers | Households | Repeat claimants | Gate |
|---|---|---|---|---|---|---|---|
| Return-rate rule | 0.265 | 0.235 | 43.0% | 5.5% | 3.6% | 6.0% | reference |
| logreg_c1 | 0.740 | 0.655 | 5.7% | 1.9% | 1.7% | 11.6% | rejected |
| hgb_leaf15 | 0.760 | 0.673 | 4.9% | 1.7% | 1.2% | 10.5% | rejected |
| hgb_leaf15_w4 | 0.745 | 0.660 | 5.7% | 1.7% | 1.5% | 6.04% | rejected (rule 5.99%) |
| **hgb_leaf15_w6** | **0.737** | 0.652 | 6.3% | 1.8% | 1.5% | 5.1% | **passed, selected** |
| hgb_leaf15_w8 | 0.726 | 0.643 | 6.0% | 1.8% | 1.5% | 4.5% | passed |
| iforest_256 | 0.545 | 0.482 | 6.9% | 3.7% | 2.8% | 22.0% | rejected |

`hgb_leaf15_w4` missed the new leg by one customer in two thousand, as the exploration warned it might. The gate
is a point rule; it was applied as written.

Selected model per world: 0.727, 0.785, 0.703, 0.748, 0.721 (rule 0.290, 0.278, 0.241, 0.230, 0.286). Spread over
resampled worlds: 0.715 to 0.765; difference from the rule 0.441 to 0.502. Recall by kind of abuse: non-receipt
0.70, contents 0.66, temporary use 0.75, coordinated 0.89. At the 1% budget every reviewed customer is an abuser
(precision 1.000); at 10%, precision 0.456 and recall 0.807. 181 of 1,786 abusers have too little history to rank.

## 5. The final test (W3301-W3305), run once

Recorded 2026-10-05T09:47:30Z. The test worlds were generated after the selection was frozen; the model file was
verified against the hash frozen at selection.

| Ranking | Precision | Recall | Heavy returners | Defective buyers | Households | Repeat claimants | Gate |
|---|---|---|---|---|---|---|---|
| Return-rate rule | 0.240 | 0.217 | 43.1% | 5.5% | 3.8% | 5.3% | reference |
| **hgb_leaf15_w6** | **0.737** | 0.668 | 5.8% | 1.6% | 1.3% | 4.5% | **passed** |

**Final test status: passed.** Per world 0.777, 0.721, 0.770, 0.729, 0.687 (rule 0.286, 0.236, 0.240, 0.214, 0.222).
Spread 0.709 to 0.765; difference from the rule 0.478 to 0.516. Recall by kind: non-receipt 0.73, contents 0.66,
temporary use 0.76, coordinated 0.88. 169 of 1,724 abusers are outside the ranking.

Errors on the test worlds: 371 false positives, of which 90 are repeat genuine claimants (24%; 72% in the first
experiment), 145 heavy returners, 87 defective buyers, 44 household members, 130 in none of these groups. Abusers
missed: 293 of 461 with one completed action, 163 of 574 with two or three, 60 of 520 with four or more.

In one of the five test worlds taken alone (W3304) the model reviews repeat claimants more often than the rule
(6.5% against 5.9%); pooled, which is what the gate reads, it does not.

## 6. Against the first experiment

| | EXP-20261002-01 | EXP-20261005-02 |
|---|---|---|
| Test precision, model / rule | 0.715 / 0.239 | 0.737 / 0.240 |
| Test recall | 0.617 | 0.668 |
| Temporary-use recall (test) | 0.67 | 0.76 |
| Repeat claimants reviewed, model / rule (test) | not gated; 15.8% / 6.7% on training worlds | 4.5% / 5.3% |
| Repeat claimants among false positives (test) | 72% | 24% |
| Gate legs | 3 | 4 |
| Development target on training worlds (0.75-0.85) | 0.694, not met | 0.793 best candidate, 0.767 selected: met |

The two experiments ran on different worlds, so differences of a point or two are world-to-world variation. The
gain in precision is modest; the change that matters is whom the model wrongly reviews.

## 7. What may and may not be said

- The model passed a stricter gate than before, on untouched worlds, once.
- The development target is met on the scores it is defined on (out-of-fold training). On validation and test
  the selected model is at 0.737, below 0.75. Say both.
- The weighting uses simulation truth in training. Real data has no such truth; a real deployment would need
  adjudicated claims or would have to accept the unweighted model's behaviour toward this group.
- Two signal families still carry the model (0.376 without claims and timing), and the level still follows the
  simulated action rate. Quote the gap to the rule, not the level.
- Simulated data from one generator. Nothing here is a claim about real returns.

## 8. Publication

`arai publish --demo-world W3401` on 2026-10-05: the current feature code reproduced the frozen features of
W3101 value for value; bundle `m-8c0e069929f81739c1321e38` (candidate `hgb_leaf15_w6`) is active, pointer version
4, baseline `b-5cd41d54f17679082398fafa`. Bundles of the first experiment remain on disk and are refused by this
feature contract, as recorded in AM-47.
