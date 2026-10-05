# Experiment 3 (EXP-20261005-03): the same method on a less generous simulator (2026-10-05)

Contract: specification 3.0, decisions AM-49 and AM-50, recorded in commit c78dcda before any world of this
experiment existed. Every record carries that commit with no uncommitted change.

**Question.** Experiment 2 passed at 0.737 against 0.240. Its caveat was that the level depends on how sharply the
simulation separates abusers on two behaviours. How much survives when the simulation is less generous?

**What changed, and only this.** The simulator (generator-config 3.0):

- 12% of active accounts are late returners, an honest habit independent of abuse. Half of their item returns
  follow the timing law of temporary-use abuse; so does one in twenty of everyone else's.
- 30% of temporary-use returns come back as early as honest returns do.
- Abusers act less often: the per-account action rate has mean 0.143 instead of 0.20.

The 43 features, the six candidates and the four-leg gate are those of experiment 2, unchanged. All worlds are
new (train 4101-4110, validation 4201-4205, test 4301-4305, stress 4501-4507). The numbers of the change were
chosen as plausible before any world existed and were not adjusted afterwards.

**Data safety.** Everything of experiments 1 and 2 was copied to `data/backups/2026-10-05-experiments-1-and-2`
(2.2 GB) before any change. No earlier world was regenerated: `arai generate` now refuses to overwrite a world of
another simulator or contract. Experiment 2 stays the published result and its model stays active; experiment 3
has not been published.

All figures are precision at the 5% review budget unless stated.

## 1. Result

| Stage | Model `hgb_leaf15_w6` | Return-rate rule | Ratio | Repeat claimants reviewed, model / rule |
|---|---|---|---|---|
| Training worlds, out of fold | 0.536 | 0.196 | 2.7 | 6.1% / 6.4% |
| Validation (W4201-W4205) | 0.543 | 0.171 | 3.2 | 6.0% / 7.1% |
| **Final test (W4301-W4305), run once** | **0.548** | **0.186** | **2.9** | 4.3% / 5.5% |

**Final test status: passed**, all four legs. Per world 0.582, 0.535, 0.527, 0.547, 0.549 (rule 0.161, 0.165, 0.199,
0.221, 0.182). Spread over resampled worlds 0.534 to 0.566; difference from the rule 0.335 to 0.393. Recall 0.521.
At the 1% budget precision is 0.996; at 10%, 0.347 with recall 0.659.

Selection on validation, as the gate reads it:

| Candidate | Precision | Repeat claimants (rule 7.1%) | Gate |
|---|---|---|---|
| logreg_c1 | 0.563 | 19.5% | rejected |
| hgb_leaf15 | 0.586 | 17.6% | rejected |
| hgb_leaf15_w4 | 0.562 | 7.6% | rejected |
| **hgb_leaf15_w6** | **0.543** | 6.0% | **passed, selected** |
| hgb_leaf15_w8 | 0.533 | 4.6% | passed |
| iforest_256 | 0.429 | 26.8% | rejected |
| analyst rulebook (reference) | 0.270 | 13.0% | report only |

The same candidate was selected as in experiment 2, for the same reason.

## 2. Against experiment 2

| | Experiment 2 | Experiment 3 |
|---|---|---|
| Test precision, model | 0.737 | 0.548 |
| Test precision, rule | 0.240 | 0.186 |
| Model over rule | 3.1 times | 2.9 times |
| Test recall | 0.668 | 0.521 |
| Recall, deceptive non-receipt claims | 0.73 | 0.71 |
| Recall, deceptive contents claims | 0.66 | 0.63 |
| Recall, coordinated claims | 0.88 | 0.89 |
| Recall, temporary-use returns | 0.76 | 0.37 |
| Wardrobing indicator "elevated", precision / recall | 0.95 / 0.34 | 0.135 / 0.28 |
| Style targeting signal, precision / recall | 1.00 / 0.90 | 1.00 / 1.00 |
| Four-leg gate | passed | passed |
| Stress worlds passed (selected model) | 7 of 7 | 7 of 7 |

**The level fell by a quarter; the ratio to the rule did not move.** That is the answer to the question: 0.737 was
a statement about one simulator, and "about three times the rule" was not.

**Where the loss is.** Almost all of it is temporary use: recall fell from 0.76 to 0.37 because a late return is no
longer evidence of anything. Deceptive claims are found as well as before although abusers claim less often,
because claim behaviour is measured against what a customer bought. Coordinated claims are unaffected.

**The wardrobing indicator does not survive.** It scores customers on late item returns alone. With honest late
returners in the population, 86 of 100 customers it marks "elevated" are honest (precision 0.135). It was always
report-only and outside the model, but it is shown on every case page. It should not be shown with this wording on
data where honest customers return late, which real data is.

## 3. What the result depends on now (training worlds, out of fold)

| `hgb_leaf15_w6` with | Experiment 2 | Experiment 3 |
|---|---|---|
| all 43 features | 0.767 | 0.536 |
| only the first experiment's 17 features | 0.676 | 0.456 |
| without any timing feature | 0.588 | 0.494 |
| without any claim feature | 0.630 | 0.400 |
| without any claim or timing feature | 0.376 | 0.275 |
| (return-rate rule) | 0.259 | 0.196 |

Timing features now add four points instead of eighteen. Claims carry the model. The 26 features added in
experiment 2 are still worth eight points.

## 4. Whom the model wrongly reviews

Honest groups, model against rule, training worlds out of fold: repeat genuine claimants 6.1% against 6.4%; heavy
returners 8.9% against 44.7%; defective buyers 4.2% against 6.3%; households 2.6% against 4.2%; no genuine failure
1.3% against 3.9%.

**One group is reviewed more often than under the rule and is not gated:** honest customers with exactly one
genuinely failed delivery, 7.7% against 5.2%. In experiment 2 it was 3.9% against 5.0%. With weaker signals the
weighted model moves its false positives from customers with two genuine failures, whom the gate protects, to
customers with one, whom it does not. The gate did what it was written to do; the harm moved next door.

Test worlds: 640 false positives (371 in experiment 2), of which 235 heavy returners, 224 defective buyers, 106
household members, 87 repeat genuine claimants (14%) and 204 in none of these groups. Abusers missed: 370 of 511
with one completed action, 260 of 617 with two or three, 85 of 364 with four or more.

## 5. Stress worlds (frozen estimators, diagnostic)

| World | Rule | hgb_leaf15 | w6 | w8 |
|---|---|---|---|---|
| W4501 ordinary propensity x1.2 | 0.170 | 0.604 fails | 0.544 | 0.519 |
| W4502 ordinary propensity x0.8 | 0.233 | 0.583 fails | 0.537 | 0.519 |
| W4503 defect incidence x2 | 0.160 | 0.557 fails | 0.504 | 0.493 |
| W4504 household share x2 | 0.192 | 0.515 fails | 0.519 | 0.505 |
| W4505 action rate x0.5 | 0.120 | 0.403 fails | 0.385 | 0.371 |
| W4506 action rate x2 | 0.331 | 0.730 fails | 0.691 | 0.655 |
| W4507 persona multipliers all 1 | 0.179 | 0.561 fails | 0.546 | 0.521 |

## 6. Gate dry run and the development target

Recorded 2026-10-05T10:43:21Z before any validation world existed, with the action-rate lever disclosed as
changed. Return-rate rule 0.196 (target 0.20-0.30: just below). Best supervised candidate 0.577 (target 0.75-0.85:
not met, and not expected to be; AM-50). AM-45 stands: the target was met on experiment 2's training worlds and is
not met on this simulator. Which simulator the target is about is the owner's decision.

## 7. What may and may not be said

- Across three experiments and two simulators the method finds about three times as many abusers per review as
  the return-rate rule, and passes the gate each time. That is the result that travels.
- No single percentage travels. 0.72, 0.74 and 0.55 are all true, each of its own simulation.
- Detection of temporary use rests on return timing. Where honest customers return late it is weak, and the
  wardrobing indicator misleads.
- The weighting needs simulation truth, and it relocates harm to an ungated neighbour group. A fifth leg, or a
  leg defined on "any genuine failure", would be the next step if this line is pursued.
- The numbers of the less generous simulator are assumptions. Real behaviour could be gentler or harsher.

## 8. Not done

Experiment 3 is not published: a valid active model is not replaced automatically, and its demonstration world
(seed 4401) has not been generated. To publish it: `uv run arai generate --seed 4401`, then
`uv run arai publish --demo-world W4401`. To keep experiment 2 as the demonstration, do nothing.
