# Experiment 4 (EXP-20261005-04): result (2026-10-05)

The selected model passed its single final test: 76.6% of the customers it sends for review are abusers, against
21.8% for the return-rate rule, with all five gate legs met. It is published in the experiment's own data
folder. The pass comes with three caveats that matter more than the headline; they are in section 5.

Contract: `final-spec/contracts/experiment.yaml` 4.0, committed as `0b0bf29` before any world existed. What was
explored first and why each number was chosen: `2026-10-05-experiment-4-exploration.md`. The independent design
review and what was done about it: `2026-10-05-experiment-4-design-critic-review.md`.

## 1. What this experiment is

The owner's decisions after experiment 3: set the harsher simulator aside and keep its data untouched; run a new
experiment on new data in a separate folder; rebuild the wardrobing indicator; add a fifth gate leg for honest
customers with exactly one genuine delivery failure, with training weights on both honest claimant groups.

- **Simulator.** Generator-config 4.0, which generates exactly as generator-config 1.3 did (experiments 1 and 2).
- **Data.** New seeds: training W5101-W5110, validation W5201-W5205, test W5301-W5305, demonstration W5401,
  stress W5501-W5511. Everything is under `data/EXP-20261005-04/`. No file in `data/artifacts`, `data/private` or
  `data/postgres` was modified (checked by modification time against the last commit before this work).
- **Features.** The 43 of experiment 2, unchanged.
- **Gate.** Five legs: heavy returners, defective-product buyers, household members, repeat genuine claimants,
  and customers with one genuine failure.
- **Candidates.** Nine: the six of experiment 2 and three boosted-tree candidates weighting both claimant groups.

The contract stated its expectation before any world existed: on this simulator this is in effect a replication
of experiment 2 with one more leg, and which of the weighted candidates is selected is not a finding.

## 2. Training worlds: gate dry run (out of fold, ten worlds)

| Ranking | Precision | Repeat claimants reviewed | One failure reviewed | Gate |
|---|---|---|---|---|
| Return-rate rule | 0.234 | 5.9% | 5.0% | |
| Boosted trees, no weight | 0.770 | 10.7% | 1.6% | fails the repeat leg |
| Repeat x4 | 0.759 | 6.1% | 3.2% | fails the repeat leg |
| Repeat x6 | 0.751 | 4.9% | 3.7% | passes |
| Repeat x8 | 0.740 | 4.6% | 4.2% | passes |
| Repeat x6, one failure x2 | 0.753 | 6.0% | 2.2% | fails the repeat leg |
| Repeat x6, one failure x3 | 0.755 | 6.3% | 1.6% | fails the repeat leg |
| Repeat x8, one failure x3 | 0.748 | 5.8% | 1.7% | passes |
| Logistic regression | 0.743 | 12.0% | 2.6% | fails the repeat leg |
| Isolation forest (in sample) | 0.544 | 21.7% | 6.8% | fails both claimant legs |

Development target (AM-45, 0.75 to 0.85 for the best supervised candidate, measured here): 0.770, inside the
band; the best candidate that also meets the gate is at 0.751. The rule is at 0.234, inside its band. The
action-rate law is disclosed as a changed lever because it differs from the previous contract; it was restored to
the generator-config 1.3 value by the owner's decision and was not tuned towards the target.

## 3. Validation worlds: selection (five worlds)

Rule 0.227. Six candidates met all five legs, within 1.5 points of each other:

| Candidate | Precision | Repeat claimants (rule 7.1%) | One failure (rule 4.8%) |
|---|---|---|---|
| Repeat x6, one failure x3 (**selected**) | 0.743 | 6.4% | 1.3% |
| Repeat x4 | 0.742 | 6.1% | 2.6% |
| Repeat x6, one failure x2 | 0.742 | 6.3% | 1.7% |
| Repeat x8, one failure x3 | 0.739 | 5.9% | 1.2% |
| Repeat x6 | 0.736 | 4.7% | 3.4% |
| Repeat x8 | 0.728 | 4.3% | 3.8% |

The unweighted boosted trees reached 0.760 and were rejected (repeat claimants 11.0%). The analyst rulebook
reached 0.324 and the volume-only model 0.074, both report-only.

The selected candidate had failed the repeat leg in the dry run on training worlds (6.3% against 5.9%). It passed
here because the rule's own rate on that group was higher on these worlds (7.1%). This is the noise the contract
warned about.

## 4. Test worlds: the single final test (five worlds, run once)

| | Model | Return-rate rule |
|---|---|---|
| Precision at the 5% review budget | **0.766** (1,081 of 1,411) | 0.218 (307 of 1,411) |
| Spread over resampled whole worlds | 0.740 to 0.792 | 0.205 to 0.229 |
| Recall | 67.2% | 19.1% |
| Honest heavy returners reviewed | 4.1% | 45.3% |
| Honest defective-product buyers reviewed | 1.5% | 6.1% |
| Honest household members reviewed | 1.3% | 3.8% |
| Honest repeat genuine claimants reviewed | 5.8% | 7.5% |
| Honest customers with one genuine failure reviewed | 1.5% | 4.6% |

Status: **passed**. The model is 3.5 times as precise as the rule.

- By kind of abuse, the model finds 75% of customers with a deceptive non-receipt claim, 68% with a deceptive
  contents claim, 75% with a temporary-use return and 89% of ring members.
- Per world its precision runs from 0.723 to 0.799. In one of the five worlds (W5301) it reviewed repeat
  claimants more often than the rule (8.5% against 6.9%); the gate is on the pooled worlds.
- Of its 330 false positives, 112 are repeat genuine claimants, 100 heavy returners, 84 defective-product buyers,
  49 customers with one genuine failure and 46 household members (groups overlap); 83 are in none of these.
- 9.3% of abusers have fewer than three mature sale lines and are outside the ranking.

## 5. What to say with the result

**The level is a property of this simulator.** It is the generous one. On the four stress worlds that blur
return timing the same frozen model is much weaker:

| Stress world (one world each) | Model | Rule | Gate |
|---|---|---|---|
| W5509: temporary-use returns come back early | 0.728 | 0.258 | fails the repeat leg |
| W5508: honest customers return late | 0.460 | 0.228 | fails the defective-buyer leg |
| W5510: both timing changes | 0.414 | 0.241 | fails the defective-buyer leg |
| W5511: generator-config 3.0 in full | 0.348 | 0.181 | fails two legs; no candidate passes |

A model trained where a late return is a tell does not carry over to a world where honest customers return late:
about twice the rule instead of three and a half times, and below experiment 3's model, which was trained on
that behaviour (0.548). The ratio of about three "on both simulators" holds only when the model is trained on
the behaviour it is scored on.

**The repeat-claimant leg is met with little margin.** The selected model reviews about 6% of honest repeat
claimants on every set of worlds; the rule's rate on that group moves between 5.9% and 7.5%. So the leg was
failed on training worlds out of fold (6.3% against 5.9%), met on validation (6.4% against 7.1%) and test (5.8%
against 7.5%), and narrowly missed on the seven generous stress worlds pooled (6.2% against 5.9%; five of the
seven fail it one by one). The candidates weighted on repeat claimants only, the kind experiment 2 selected, keep
a clear margin on both claimant legs (pooled stress: 4.6% and 3.9% against 5.9% and 5.1%) at about one point of
precision less. The fifth leg did what it was added for: one-failure customers are reviewed about a third as
often as under the rule everywhere. But adding weight for them cost margin on the repeat claimants, which is the
trade the exploration showed. Whether selection should prefer margin on the protected groups over the last
fraction of precision is a decision for the owner; the rule was applied as registered. The pooled figures come out of
`scripts/exploration/experiment_4_stress_pooled.py`.

**The training weights use simulation truth** (which customers' failures were genuine). Real data has no such
label (AM-48).

Stress worlds 5501 to 5507, which vary the simulation without touching timing: the model's precision runs from
0.633 to 0.877 and the rule's from 0.134 to 0.400.

What the result depends on (selected model, training worlds, out of fold): 0.755 with all features, 0.609 without
the claim features, 0.569 without the timing features, 0.347 without both, against 0.234 for the rule.

## 6. The rebuilt wardrobing indicator on new worlds

Report-only, outside the model. A late return of occasion wear, counted only when what the customer returned
supports it (see the exploration record for why the first, timing-free design was dropped).

| Worlds | Elevated: right / found | Possible: right | Either band: right / found |
|---|---|---|---|
| Validation (five) | 78 of 81 (96%) / 13% | 113 of 144 (78%) | 191 of 225 (85%) / 31% |
| Test (five) | 89 of 90 (99%) / 15% | 122 of 145 (84%) | 211 of 235 (90%) / 35% |
| W5508, honest late returns (one world) | 16 of 21 (76%) / 12% | 29 of 74 (39%) | 45 of 95 (47%) / 34% |
| W5510, both timing changes (one world) | 19 of 21 (90%) / 15% | 22 of 74 (30%) | 41 of 95 (43%) / 32% |
| W5511, generator-config 3.0 in full (one world) | 14 of 15 (93%) / 13% | 19 of 73 (26%) | 33 of 88 (38%) / 31% |

"Found" is the share of customers with a temporary-use return that the band contains. On the worlds where honest
customers return late the elevated band stays right three times in four or better, where the timing rule it
replaces was right 13.5% of the time in experiment 3. The possible band there is right about one time in three.
It finds fewer customers than the old rule did on this simulator (35% against 59% in either band on training
worlds). On the test worlds 18 of the 84 honest customers with a late occasion-wear return were alerted.

Style signals, unchanged and report-only: targeting 18 of 19 right with 18 of 19 targeted styles found; quality
15 of 15 with all 15 found (test worlds).

## 7. Published state

- Bundle `m-7f2dafb5f8101da88c6859e7` (baseline `b-69c7b2ca43edd34744ffb3c7`), active pointer version 1 in
  `data/EXP-20261005-04/artifacts/active/`. Publication proved that the feature code reproduces the frozen
  training features.
- Demonstration world W5401: registered and scored through the API in a new database
  (`data/EXP-20261005-04/postgres`): 5,676 eligible customers, 284 selected, no warning.
- Browser walkthrough against it: 47 of 47 checks passed; screenshots in `reports/ui/2026-10-05/` (they replace
  experiment 2's of the same date).
- Experiment 2 is untouched: its bundle, pointer (version 4), database and worlds are where they were. To
  demonstrate it, check out commit `b157edf`.

Publishing on a pass is decision AM-54, which is the implementer's reading of "you create new experiment" and
awaits the owner's confirmation. Nothing was replaced by it.

How to check all of this: `docs/experiment-4-verification-guide.md` and `scripts/verify_experiment.py`.

## 8. Rules that now apply to this experiment

The final test has been run and is not run again. Worlds W52xx and W53xx are used. `features.py`, `dataset.py`,
`modeling.py`, `bundles.py` and `ranking.py` are hashed into the active bundle; the contract and the generator
are hashed into every world of this experiment.
