# Training, gate dry run and difficulty calibration, 2026-10-02

Experiment `EXP-20261002-01`, specification v1.4 (components 05, 07, 09). Source: `src/arai/modeling.py`,
`src/arai/selection.py`, `src/arai/experiment.py`; machine-readable result in
`data/artifacts/experiments/EXP-20261002-01/reports/dry_run.json` (recorded 2026-10-02T16:09:15Z).

**This is a diagnostic on training worlds. It selects nothing.** It was recorded before any validation, test or
demo world was generated. The gate rule, the review budget, the tie rule and the segment definitions used here
are the ones validation will use, unchanged. Simulated data only.

## What was trained

Five registered candidates and two report-only references, on the 56,615 eligible customers (3,181 abusers) of
the ten training worlds, 17 ordered features, exact parameters from `contracts/experiment.yaml`.

- Preprocessing: training-median imputation plus one missing-value indicator per feature; a scaler for the
  logistic model only. Everything learned is fitted inside each fold on that fold's eight training worlds.
- Supervised reference scores are out of fold, five folds grouped by world (two worlds held out per fold). The
  final estimator of each candidate is fitted once on all ten worlds and is the only one stored.
- Isolation forests never see a label; their training scores are in-sample and therefore optimistic.
- All seven fits converged with no warning. Durations: logistic 3 s, boosted 15 s and 20 s, forests 3-4 s.

## Gate dry run at the 5% review budget (2,836 reviews, pooled over ten worlds)

| Ranking | Role | Correct | Precision | Per world | Recall | Heavy returners | Defective buyers | Households | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| Raw return rate | baseline | 671 | 0.237 | 0.19-0.28 | 0.211 | 0.442 | 0.060 | 0.039 | comparison |
| Analyst rulebook | reference | 957 | 0.337 | 0.31-0.38 | 0.301 | 0.380 | 0.056 | 0.041 | report only |
| Volume only | reference | 212 | 0.075 | 0.04-0.09 | 0.067 | 0.057 | 0.117 | 0.053 | report only |
| Logistic regression | candidate | 1,742 | 0.614 | 0.57-0.65 | 0.548 | 0.092 | 0.028 | 0.026 | would pass |
| **Boosted trees, 15 leaves** | candidate | 1,969 | **0.694** | 0.66-0.72 | 0.619 | 0.076 | 0.026 | 0.020 | would pass |
| Boosted trees, 31 leaves | candidate | 1,954 | 0.689 | 0.66-0.71 | 0.614 | 0.077 | 0.026 | 0.021 | would pass |
| Isolation forest, 256 | candidate | 588 | 0.207 | 0.17-0.25 | 0.185 | 0.039 | 0.012 | 0.043 | would fail |
| Isolation forest, 1,024 | candidate | 667 | 0.235 | 0.19-0.27 | 0.210 | 0.040 | 0.012 | 0.043 | would fail |

The three right-hand rate columns are the share of each honest segment that the ranking would send for review.
Segment sizes over ten worlds: 4,894 heavy returners, 10,987 defective-product buyers, 6,981 household members.
Both isolation forests fail on precision and on the household leg.

Whole-world bootstrap (1,000 paired resamples of the ten worlds): boosted trees 0.683-0.705, return-rate rule
0.222-0.252, difference 0.44-0.47. With ten worlds from one generator this measures spread between worlds; it
is not a significance claim.

**Other budgets (boosted trees, 15 leaves):** top 1%: 0.979 precision, recall 0.18; top 10%: 0.447 precision,
recall 0.80. The return-rate rule gives 0.298 and 0.204.

**Recall by kind of abuse at 5% (boosted trees against the rule):** deceptive non-receipt 0.74 against 0.28;
deceptive contents 0.65 against 0.25; temporary use 0.64 against 0.16; coordinated 0.80 against 0.28.

**Coverage.** 336 of 3,517 abusers (9.6%) have fewer than three mature sale lines and are outside the ranking
whatever the model does.

## Why the rule fails and the model does better

This is the explanation the demonstration rests on; the numbers are from the tables above and from
`records/2026-10-02-features.md`.

1. **The rule reads one number.** A high return rate is mostly honest: 44% of honest heavy returners land in
   the rule's review list, and they fill it. The models send 8-9% of them.
2. **Abuse shows in what is returned and how, not how much.** Claims without an item (non-receipt, missing
   parts), returns in the last days of the window, and claims made alongside linked accounts on the same style.
   No single one of these sees every kind of abuse, so a single-number rule cannot either.
3. **A hand-written rulebook gets part of the way** (0.34): it reads the same signals, but with fixed
   thresholds and equal weights. The model learns how the signals combine and how much evidence is enough.
4. **Volume is not the answer.** A model given only order volume is worse than the rule (0.07).
5. **What nobody finds.** 29% of abusers acted exactly once, and more than twice as many honest customers have
   repeat genuine claims (bad delivery addresses) as abusers have repeat claims. These set the ceiling.

## Difficulty calibration: disclosed outcome

`contracts/experiment.yaml` set development targets, not acceptance gates: return-rate rule 0.20-0.30, best
supervised candidate 0.75-0.85, raise difficulty above 0.90.

| Measure | Target | Achieved (out of fold, ten training worlds) | In band |
|---|---|---|---|
| Return-rate rule | 0.20-0.30 | 0.237 | yes |
| Best supervised candidate | 0.75-0.85 | 0.694 | **no, 0.056 below** |
| Ceiling | below 0.90 | 0.694 | yes |

**No calibration lever was changed.** The three permitted levers (action-rate distribution, address failure
dispersion, genuine claim rates) were left at their specified values. Reasons: (1) the gap is explained by
one-action abusers and honest repeat claimants, which are the two things the levers control, so closing it
would mean making abusers act more often or honest deliveries fail less until the number fits; (2) the purpose
of the comparison is the explanation above, and 0.69 against 0.24 carries it; (3) the generator changes of
amendments 1.2 to 1.4 were all made to remove artefacts, each of which had made the task easier, and the result
should be reported as it came out.

This closes the calibration window: the specification allows lever changes only before a validation manifest
exists. The 0.75-0.85 target is reported as **not met** and stays an open point for the project owner. Reaching
it later needs a new dated amendment and a new experiment on fresh seeds.

History of the best out-of-fold figure today: 18 features on the v1.3 worlds failed the household leg (0.063
against 0.042 for the rule); 16 features (AM-26) gave 0.63 on the v1.3 worlds and 0.65 on the v1.4 worlds; 17
features (AM-27) give 0.69.

## Known deviations and limits

- The frozen feature reference (category return rates) is fitted on all ten training worlds, not per fold. No
  development world uses the fallback, so no feature value depends on it; if that ever changes, the reference
  must become fold-local.
- Isolation-forest reference scores are in-sample.
- All worlds come from one generator and one configuration. Cross-validation grouped by world shows the result
  is stable across simulated worlds, not that it would hold on real returns.
- The timing-based features depend on the simulation's timing laws (see the features record).
