# Experiment 4 design: independent critic review and what was done (2026-10-05)

An independent reviewer (chief data scientist brief, read-only, own measurements) reviewed the uncommitted design
of EXP-20261005-04 before its contract was committed and before any of its data existed. Its verdict was "do not
commit yet". This record lists each finding, whether I confirmed it, and what was done. The reviewer's
measurements are quoted as it reported them; `[M]` is measured, `[R]` is read.

The reviewer disclosed that it opened `selection.json` of experiment 2 while looking for stored scores and saw
that experiment's validation scorecard; none of its findings use it, and that experiment is closed.

## Findings and dispositions

| # | Severity | Finding | Confirmed | Done |
|---|---|---|---|---|
| 1 | BLOCKER [M] | The rebuilt wardrobing indicator was described as resting on what was returned, not when. Measured, a late return carried 83-90% of its true positives; alerts without one were right about 10% of the time; "excess and complaint" alone 8-12%; precision was not ordered by score | Yes, on my own tables (see the exploration record) | Design dropped. The indicator now needs a late return of occasion wear, which alone reaches no band; one kind of support gives "possible", both give "elevated"; support without a late return scores nothing. Contract, docstrings, case-page text and decision AM-52 say that timing remains the discriminator. Re-measured: elevated right 96% (1.3) and 75% (3.0) |
| 2 | SHOULD FIX [M] | On this simulator the final test is in effect a replication of experiment 2: the fifth leg is slack, the weighted candidates are within noise of each other (selection rehearsal: 151 against 101 wins on a 0.0004 precision gap), and no stress world shows the five-leg gate where it binds | Reproduced the out-of-fold table; the rehearsal is the reviewer's | Contract gained an `expectation` that says this before any world exists. Stress world 5511 added: generator-config 3.0 in full. The selection rule is unchanged, for comparability with the earlier experiments; preferring claimant-leg margin within a precision tolerance is left to the owner |
| 3 | SHOULD FIX [R] | The contract is hashed into every world and into the training record, so it cannot be edited once training worlds exist | Yes, by design | Every change below was made before the contract commit |
| 4 | SHOULD FIX [R] | Isolation gaps: one Compose database volume for all experiments; `.env.example` pointing `ARTIFACT_ROOT` at the old folder; RUNBOOK still naming the old folder, W3401 and experiment 2; the Compose default hard-coding the experiment with no test | Yes | Compose volume named per experiment and tested against the contract; `.env.example` corrected; RUNBOOK rewritten with the result of the experiment. Refusing roots outside the data folder was not done: tests and scratch checks pass explicit roots on purpose |
| 5 | SHOULD FIX [M] | No minimum support: in a three-customer snapshot the excess score reaches 14 and gives "possible"; more units returned than delivered gives 30 | Yes | Returned units are capped at delivered units. Fewer than 200 peer units of occasion wear or of other products gives the status `incomplete`, with no score and no fired signal |
| 6 | SHOULD FIX [M] | `feature_eda.wardrobing_report` raised `KeyError: 'late_return_lines'` | Yes | Fixed: the count is read from the feature frame |
| 7 | SHOULD FIX [M] | The contract quoted only the elevated band and omitted the possible band, either band, and the old rule's recall | Yes | `features.yaml` now carries all bands for both simulators beside the old rule, the per-world spread and the limits |
| 8 | NOTE | The excess score is not calibrated (5.5% of honest occasion buyers at z >= 2 against 2.3% nominal); the clean-style test is a simulator artefact (37 styles); elevated recall is capped by the generator's 15% false-quality share; per-world figures are noisy on 14-32 flags; the stress sentence named only the action rate; a chained `!=` in a test compared less than it read; `stress_timing` in the generator configuration is not read by code; `arai generate` did not refuse retired seeds | Yes | Calibration and artefact stated in the contract's `limits`; stress sentence reworded; the test compares five distinct hashes; the configuration note says it documents `settings.STRESS_OVERRIDES`; a retired seed is refused, with a test |

## What the reviewer verified as sound

- Seed 3101 regenerated under generator-config 4.0 matches stored W3101: seven operational tables identical, truth
  identical apart from the added `late_returner` column. Seed 4101 with both 3.0 timing parts and the 3.0 action
  rate matches stored W4101, so the stress overrides apply 3.0 exactly.
- The 43 ordered features are bit-identical to the stored ones on W3106 and W4106.
- Weight flags equal the evaluation segments on all 56,467 and 56,429 training rows, with zero overlap; neither is
  a model feature. A refit of the weight-6 candidate equals experiment 2's stored out-of-fold scores.
- No truth or identifier is read by the indicator, and the customer is excluded from every snapshot statistic.
- Nothing under `src/` hardcodes the old data folders, and the protocol guards hold in the new folder.

## The reviewer's measurements of the first design (now dropped)

Eligible customers, ten training worlds per simulator.

| Simulator | Band or slice | Flagged | Right | Precision | Found |
|---|---|---|---|---|---|
| 1.3 | Elevated | 248 | 197 | 79.4% | 15.6% |
| 1.3 | Possible only | 559 | 204 | 36.5% | 16.1% |
| 1.3 | Elevated, late return present | 192 | 185 | 96.4% | 14.6% |
| 1.3 | Elevated, no late return | 56 | 12 | 21.4% | 0.9% |
| 1.3 | Possible, late return present | 207 | 177 | 85.5% | 14.0% |
| 1.3 | Possible, no late return | 352 | 27 | 7.7% | 2.1% |
| 1.3 | Old rule, elevated | 462 | 438 | 94.8% | 34.6% |
| 1.3 | Old rule, either band | 1,027 | 744 | 72.4% | 58.8% |
| 3.0 | Elevated | 177 | 112 | 63.3% | 10.2% |
| 3.0 | Possible only | 663 | 125 | 18.9% | 11.4% |
| 3.0 | Elevated, late return present | 127 | 95 | 74.8% | 8.6% |
| 3.0 | Elevated, no late return | 50 | 17 | 34.0% | 1.5% |
| 3.0 | Possible, late return present | 344 | 101 | 29.4% | 9.2% |
| 3.0 | Possible, no late return | 319 | 24 | 7.5% | 2.2% |
| 3.0 | Old rule, elevated | 2,196 | 290 | 13.2% | 26.3% |
| 3.0 | Old rule, either band | 4,452 | 506 | 11.4% | 46.0% |

The elevated band of the design in the contract is exactly the reviewer's "elevated, late return present" slice
(185 of 192 and 95 of 127), which my own measurement of the implemented code reproduces.
