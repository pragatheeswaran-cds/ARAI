# Experiment 4: what was explored before its contract (2026-10-05)

The owner's decisions after experiment 3, in their words: "rebuilt with new experiment" (the wardrobing
indicator); "go with recommendation" (a fifth gate leg for honest customers with one genuine failure, training
weights on both groups); "since experiment 3 is harsher, ignore it. but don't touch those data. Keep as-is. you
create new expermient with new data on separate folder for new data".

Everything below was measured on training worlds of experiments 2 and 3, which were already used as training
data, read-only. No validation or test world of any experiment was opened, and no world of experiment 4 existed.
The numbers chosen from it are the implementer's and are fixed in `final-spec/contracts/` (AM-51 to AM-54).

## 1. The simulator of experiment 4 is the simulator of experiment 2

"Ignore the harsher one" is implemented as generator-config 4.0: the three values that made generator-config 3.0
less generous are switched off (no honest late-return habit, no early temporary-use returns, action rate back to
Beta(1.2, 4.8), mean 0.20). The generator code is the code of experiment 3, so this had to be checked rather than
assumed: seed 3101 was regenerated in a scratch folder under these settings and compared with the stored world
W3101 of experiment 2. All seven operational tables are identical byte for byte, and all twelve truth tables are
equal (the profile table has one added column, `late_returner`, false for everybody).

Consequence to say aloud: the level of any result on these worlds is again a property of a generous simulation.
The ratio to the return-rate rule is the figure that carried across simulators.

Four extra stress worlds switch parts of generator-config 3.0 back on: 5508 the honest late-return habit, 5509
early temporary-use returns, 5510 both, and 5511 both with the lower action rate, which is 3.0 in full. The model,
the five-leg gate and the rebuilt indicator are therefore also read on fresh worlds where timing is blurred and
where the gate binds. They are diagnostic and select nothing. This is the implementer's addition, the last one at
the review's suggestion; experiment 3's own data is not used.

## 2. The wardrobing indicator: a late return that has to be supported

The old rule scored late item returns. Its "elevated" band was right 95% of the time on generator-config 1.3
(35% of temporary-use customers found) and 13% on 3.0, where honest customers also return late.

What else distinguishes a temporary-use customer in the operational tables (eligible customers, W3101-W3105):

| Per customer, mean | Honest and other | Temporary use |
|---|---|---|
| Share of occasion-wear units returned | 0.18 | 0.61 |
| Share of other units returned | 0.16 | 0.24 |
| Quality complaints on styles others do not complain about | 0.09 | 0.59 |

Two normalised measures were built from this:

- **Occasion excess.** Occasion-wear units returned, against the number the customer's own returns of other
  products predict (own rate, shrunk to the snapshot's, carried over by the snapshot's ratio of the two rates), in
  standard deviations.
- **Clean-style complaint.** A quality complaint on a style whose other buyers complain no more often than the
  snapshot as a whole.

**First design, dropped.** It scored these two alone and used a late return only as a bonus. Its headline looked
acceptable (elevated right 80% on 1.3 and 63% on 3.0). The independent review split the alerts by whether a late
return was present and found the design did not do what it claimed: without a late return its alerts were right
about one time in ten, and the pair "excess and complaint" alone 8% to 12% (its figures, for that design). The
same split with the definitions now in the code confirms it:

| Evidence present (ten training worlds each) | Right on 1.3 | Right on 3.0 |
|---|---|---|
| Excess only | 58 of 1,424 (4%) | 59 of 1,324 (4%) |
| Complaint only | 132 of 4,253 (3%) | 163 of 3,930 (4%) |
| Excess and complaint, no late return | 26 of 226 (12%) | 37 of 221 (17%) |
| Late occasion return only | 192 of 320 (60%) | 157 of 1,443 (11%) |
| Late occasion return and complaint | 120 of 154 (78%) | 93 of 411 (23%) |
| Late occasion return and excess | 135 of 158 (85%) | 79 of 269 (29%) |
| Late occasion return, excess and complaint | 185 of 192 (96%) | 95 of 127 (75%) |

So in this simulation timing is what tells temporary use apart, and nothing else comes close. The recommendation
I gave the owner, an indicator that "should not rest on timing", cannot be met with a transparent rule on this
data. What can be met is the reason for the rebuild: a late return alone must stop raising an alert.

**Design in the contract.** The signal is a late return of occasion wear. Alone it reaches no band. With one kind
of support (excess or complaint) the pattern is "possible"; with both it is "elevated". The supporting evidence
without a late return scores nothing. A snapshot with too few other customers to compare with gives "incomplete".

Measured with the implemented code on all twenty training worlds (eligible customers). Both tables in this
section come out of `scripts/exploration/experiment_4_indicator.py`, which reads only:

| | Simulator 1.3: right / found | Simulator 3.0: right / found |
|---|---|---|
| New, elevated | 96% (185 of 192) / 15% | 75% (95 of 127) / 9% |
| New, possible | 82% (255 of 312) / 20% | 25% (172 of 680) / 16% |
| New, either band | 87% / 35% | 33% / 24% |
| Old, elevated | 95% (438 of 462) / 35% | 13% (290 of 2,196) / 26% |
| Old, either band | 72% / 59% | 11% / 46% |

The choice was made on the first five worlds of each simulator and held on the other five (elevated: 97% and 96%
on 1.3, 79% and 72% on 3.0). Honest customers alerted: 0.12% on 1.3 and 0.95% on 3.0. The 43 model features
computed by the changed code are identical to the stored ones on all twenty worlds.

What this costs: the rebuilt indicator finds fewer temporary-use customers than the old rule (35% against 59% in
either band on this simulator). What it buys: when honest customers return late, its elevated band is right three
times in four where the old one was right one time in eight. Per world the elevated band holds only 10 to 24
customers, so a single world's figure moves a lot (59% to 100% on 3.0).

Two caveats that stay with it. The excess score is a heuristic, not a calibrated test. And the clean-style test
works here because the catalogue has 37 styles with a marked defect truth; most clean-style complaints are
genuine defects reported by honest customers.

## 3. Weights for both honest claimant groups

Out of fold on ten training worlds, boosted trees with the settings of the registered candidates. The two legs
are the share of each honest group sent for review; the rule's share is the limit. The tables come out of
`scripts/exploration/experiment_4_claimant_weights.py --all`, which reads only.

Generator-config 1.3 (W3101-W3110). Rule: precision 0.259, repeat claimants 6.6%, one failure 5.0%.

| Weight repeat / one failure | Precision | Repeat claimants | One failure | Legs met (of 5) |
|---|---|---|---|---|
| none | 0.793 | 9.6% | 1.5% | 4 |
| 6 / 0 (experiment 2's selected model) | 0.767 | 4.5% | 3.9% | 5 |
| 6 / 2 | 0.774 | 5.3% | 2.3% | 5 |
| 6 / 3 | 0.781 | 5.6% | 1.5% | 5 |
| 6 / 4 | 0.778 | 5.9% | 1.3% | 5 |
| 6 / 6 | 0.778 | 6.3% | 0.9% | 5 |
| 4 / 2 | 0.787 | 6.2% | 2.0% | 5 |
| 4 / 4 | 0.783 | 7.0% | 1.0% | 4 |
| 8 / 3 | 0.771 | 5.0% | 1.9% | 5 |
| 8 / 4 | 0.770 | 5.4% | 1.4% | 5 |
| 3 / 3 | 0.789 | 7.4% | 1.1% | 4 |

Generator-config 3.0 (W4101-W4110). Rule: precision 0.196, repeat claimants 6.4%, one failure 5.2%.

| Weight repeat / one failure | Precision | Repeat claimants | One failure | Legs met (of 5) |
|---|---|---|---|---|
| none | 0.577 | 17.5% | 3.5% | 4 |
| 6 / 0 | 0.536 | 6.1% | 7.7% | 4 |
| 6 / 2 | 0.547 | 7.5% | 4.1% | 4 |
| 6 / 3 | 0.543 | 7.9% | 2.6% | 4 |
| 8 / 3 | 0.539 | 7.0% | 2.8% | 4 |
| 8 / 4 | 0.535 | 6.9% | 2.2% | 4 |

Read together:

- The two groups trade against each other. Weight on one-failure customers lowers their review rate and raises
  the repeat claimants', and the other way round. This is why the fifth leg is separate and not a widening of
  the fourth.
- On the generous simulator the fifth leg is met by every weighted candidate, including the one with no weight
  on the group. It is there to keep it met, and it is not expected to change which kind of model is selected.
- On the harsher simulator none of the explored weights meets both claimant legs at once. A five-leg gate there
  would have selected nothing with these candidates; heavier weights would be needed.

The contract registers three candidates with both weights (6/2, 6/3, 8/3) beside the six of experiment 2. The
thinner margins (4/2, 6/6) were left out: a leg met by a third of a percentage point out of fold is a coin toss on
five validation worlds, as experiment 2's weight-4 candidate showed.

The independent review reproduced the 1.3 table and rehearsed selection on every split of the ten training
worlds into five and five: the weight-4 candidate of experiment 2 was selected 151 times and the 6/3 candidate
101 times, on a pooled precision difference of 0.0004, and the selected model then met the gate on the other
five worlds 248 times of 252. Which weighted candidate is selected is therefore not a finding, and the experiment
is in effect a replication of experiment 2 with one more leg. The contract says so in its `expectation`. The
selection rule itself is left as in the earlier experiments; preferring the larger margin on the claimant legs
within a precision tolerance is an option for the owner.

## 4. A data folder of its own

The contract names its data folder (`data_root: data/EXP-20261005-04`). Worlds, features, records, bundles, the
active pointer and the local database of experiment 4 live there. Nothing under `data/artifacts`, `data/private`
or `data/postgres` is read or written by this contract, so experiments 1 to 3, the published experiment 2 and its
database stay exactly as they are.
