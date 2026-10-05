# Experiment 4: what was done and how to verify it

Written on 2026-10-05 for the project owner, to check the work later without having to trust the summary.
Everything here can be checked from the repository at commit `696ab2d` or later, on branch `v3`. Commands are for
PowerShell from the repository root; `uv run --no-sync` avoids touching the environment.

## 1. What you asked for and what was done

Your three answers on 2026-10-05, in your words:

1. "since experiment 3 is harsher, ignore it. but don't touch those data. Keep as-is. you create new expermient
   with new data on separate folder for new data"
2. "rebuilt with new experiment" (the wardrobing indicator)
3. "go with recommendation" (a fifth gate leg for honest customers with one genuine failure, with training
   weights on both honest claimant groups)

| Asked | Done | Where to see it |
|---|---|---|
| Ignore experiment 3, keep its data | Experiment 3 is set aside; nothing of it was changed | Section 4, checks 20 to 22 |
| New experiment, new data, separate folder | EXP-20261005-04, everything under `data\EXP-20261005-04\` | `final-spec\contracts\experiment.yaml` (`data_root`) |
| Rebuild the indicator | Rebuilt, but not as I had recommended: see section 3 | `final-spec\contracts\features.yaml` (`wardrobing_indicator`) |
| Fifth leg and weights on both groups | Leg `one_genuine_failure`; three candidates weight both groups | `experiment.yaml` (`selection.segments`, `candidates`) |

Result: the selected model passed its single final test, 76.6% against 21.8% for the return-rate rule, with all
five legs met. It is published in the new folder.

## 2. Decisions I took that are yours to confirm or change

These were not in your answers. Each is recorded where it can be found again.

| My decision | Why | Recorded in |
|---|---|---|
| "Ignore the harsher one" means: use experiment 2's simulator | It is the only other simulator; the new settings reproduce an experiment 2 world byte for byte | AM-51; exploration record, section 1 |
| The indicator still uses a late return | A timing-free indicator was right about one time in ten | AM-52; exploration record, section 2 |
| Seeds, thresholds, points, the three weight pairs | Chosen on earlier training worlds, before any new world existed | AM-52, AM-53; exploration record |
| Four extra stress worlds that switch the harsher behaviour back on | To see the model and indicator where timing is blurred, without using experiment 3's data | AM-51 |
| Publishing experiment 4 when it passed | The new folder has its own pointer and database, so nothing was replaced | AM-54, marked as awaiting your confirmation |
| The selection rule left as in earlier experiments | Changing it is a design decision; see open decision D9 | Experiment record, section 5 |

## 3. Where my recommendation was wrong

I recommended an indicator that "should not rest on timing". I built one. The independent review measured it and
found that without a late return its alerts were right about one time in ten. I confirmed that on my own tables
and dropped the design before the contract was committed.

The indicator in the contract keeps a late return of occasion wear as the signal. A late return alone raises no
alert. It needs support from what the customer returned: occasion wear returned far more than their other
returns predict, or a quality complaint on a style nobody else complains about. One kind of support gives
"possible", both give "elevated".

| | This simulator | Honest customers return late |
|---|---|---|
| Rebuilt, elevated: how often right | 96% on old training worlds; 89 of 90 on the new test worlds | 75% on old training worlds; 76% to 93% on three new stress worlds |
| Old timing rule, elevated: how often right | 95% | 13% |
| Rebuilt, either band: share of temporary-use customers found | 35% | 24% |
| Old timing rule, either band: share found | 59% | 46% |

So the rebuild finds fewer customers and no longer collapses when honest customers return late. It does not
make the indicator independent of timing.

## 4. Verify in one command

```powershell
uv run --no-sync python scripts\verify_experiment.py
```

It reads only, takes about half a minute, and should end with `ALL CHECKS PASSED`. It ran clean on 2026-10-05.
What each line establishes:

| # | Check | What it rules out |
|---|---|---|
| 1 | The contract in the repository is the one the experiment was trained under | The contract being edited after the fact |
| 2-3 | Dry run, selection and test were made from one commit with no uncommitted change, and that commit holds this contract | Results produced by code that is not in git |
| 4 | The contract was committed before any training world was generated | Choosing the design after seeing the data |
| 5 | The gate dry run was recorded before any validation world was generated | Tuning on validation worlds |
| 6 | The selection was frozen before any test world was generated | Choosing the model after seeing test worlds |
| 7 | The test was run after the freeze and recorded once | A second attempt at the final test |
| 8 | All 32 worlds and their truth match the hashes written with them | Data or labels changed after generation |
| 9-11 | One generator and configuration for training, validation, test and demonstration worlds; it is the code in the repository; each stress world records its own configuration | Sealed worlds coming from a different simulator than training |
| 12 | The selected model's file is the one frozen at selection | The model being swapped after selection |
| 13-14 | The test is recorded as passed, and the recorded figures meet the gate | A "passed" label that the numbers do not support |
| 15 | The frozen model scoring the stored test features gives the recorded figures again | Recorded numbers that cannot be reproduced |
| 16-19 | The active pointer, the published bundle, the scoring code and the published report all agree with the record | Serving a different model than the one tested |
| 20 | The earlier data folder still serves experiment 2 | Experiment 2 having been replaced |
| 21 | All 79 worlds of experiments 1 to 3 match their hashes | Earlier data having been altered |
| 22 | Every file of experiments 1 and 2 is identical to the backup taken before experiment 3 (1,894 files) | Any change to their records, features, bundles or truth |

Two limits of these checks. Checks 4 to 6 compare recorded times with the file times of the world manifests, as
the pipeline's own guard does; copying the data folder with a tool that resets file times would make them fail
without anything being wrong. Check 15 re-scores the test worlds read-only; it is a check of the record, not a
second test, and it cannot change the recorded outcome.

Further checks:

```powershell
uv run --no-sync python final-spec\tools\verify_package.py     # the specification package: "result": "PASS"
uv run --no-sync pytest                                        # 189 tests, about 7 minutes
cd web; npm test; cd ..                                        # 14 front-end tests
git log --oneline -3                                           # 696ab2d result, 0b0bf29 contract
```

## 5. Verify the numbers by hand

Every figure in the records comes from a file under
`data\EXP-20261005-04\artifacts\experiments\EXP-20261005-04\`.

| Claim | File | Where in it |
|---|---|---|
| Final test 0.766 against 0.218; the five legs | `reports\test.json` | `scorecard` |
| Passed, selected model, when | `selection.json` | `final_test_status`, `selected_model_id`, `frozen_at`, `tested_at` |
| Spread 0.740 to 0.792; per-world precision | `reports\test.json` | `bootstrap`, `per_world` |
| Who the false positives are | `reports\test.json` | `error_account` |
| Validation: six candidates passed, which was selected | `reports\validation.json` | `scorecard` |
| The selected candidate failed the dry run on the repeat leg | `reports\dry_run.json` | `scorecard`, `would_pass` |
| 0.35 to 0.46 where honest customers return late | `reports\stress.json` | worlds W5508, W5510, W5511 |
| Precision without claim or timing features | `reports\ablation.json` | `variants` |
| Indicator on validation and test worlds | `reports\validation.json`, `reports\test.json` | `evidence_report_only` |
| Indicator on stress worlds | `reports\stress.json` | `wardrobing` of each world |

To print the test scorecard:

```powershell
uv run --no-sync python -c "import json; r=json.load(open(r'data\EXP-20261005-04\artifacts\experiments\EXP-20261005-04\reports\test.json')); [print(x['ranking'], round(x['precision'],4), x['true_positives'], x['k'], x['status']) for x in r['scorecard']]"
```

Two sets of figures in the records are not in those files and come out of read-only scripts instead.

The pooled stress figures of the experiment record, section 5 (for example the repeat-claimant leg over the seven
generous stress worlds, 6.2% for the model against 5.9% for the rule):

```powershell
uv run --no-sync python scripts\exploration\experiment_4_stress_pooled.py      # about a minute
```

The measurements made before the contract, on the training worlds of experiments 2 and 3:

```powershell
uv run --no-sync python scripts\exploration\experiment_4_indicator.py           # the indicator tables; several minutes
uv run --no-sync python scripts\exploration\experiment_4_claimant_weights.py    # the weights tables; about 40 minutes
```

On 2026-10-05 the first two were run in full and gave the recorded figures. The third was written after the
exploration from the script used for it, and was stopped after its first four rows, which matched the record
(for example weight 6 on repeat claimants only: 0.7674, 4.5% and 3.9%); the rest of its output has not been
compared.

## 6. See it in the application

```powershell
uv run --no-sync arai local        # http://127.0.0.1:8000, serves experiment 4
```

The demonstration world W5401 is already registered and scored in the new database.

- **Evaluation page.** Final test "passed"; the scorecard has five gate columns, the last being "One genuine
  failure"; the limits at the bottom state the three caveats in plain words.
- **A case with the rebuilt indicator.** Open customer `W5401-C07624` from the queue: the indicator is
  "elevated", score 100, with the late occasion-wear return, the excess (4 of 4 occasion-wear units returned
  where about 1.6 were predicted) and the complaint listed as separate lines.
- **Browser walkthrough.** `uv run --no-sync python tests\e2e\walkthrough.py http://127.0.0.1:8000 W5401` with
  the server running: 47 of 47 checks passed on 2026-10-05; screenshots are in `reports\ui\2026-10-05\`.

Stop the server as the runbook describes (section 2 of `RUNBOOK.md`).

To see experiment 2 instead: `git checkout b157edf`, then `uv run --no-sync arai local`. Its folder and database
are untouched.

## 7. What to read, in order

1. `records\2026-10-05-experiment-4.md`: the result and its three caveats.
2. `records\2026-10-05-experiment-4-exploration.md`: what was measured before the contract and why each number
   was chosen, including the dropped indicator design.
3. `records\2026-10-05-experiment-4-design-critic-review.md`: the independent review, each finding and what was
   done about it.
4. `final-spec\DECISIONS.md`, Amendment 4.0: decisions AM-51 to AM-54 and the recorded result.
5. `records\2026-10-05-status-and-open-decisions.md`: all four experiments and the open decisions.

## 8. What cannot be redone, and what is still open

- The final test of experiment 4 has been run. It is not run again, and worlds W5201-W5205 and W5301-W5305 are
  used. A new idea needs a new experiment on new seeds.
- The backup of experiments 1 and 2 is on the same disk as the data, and the repository has no remote. A disk
  failure would lose the worlds (reproducible from seeds) and the experiment records (not reproducible).

Open decisions, detailed in the status record:

- **D8.** Confirm that experiment 4 should be the published result of this branch (AM-54).
- **D9.** Whether a later experiment should prefer margin on the protected groups over the last fraction of
  precision. The selected model meets the repeat-claimant leg narrowly: met on validation and test, missed on
  training worlds and on the pooled stress worlds.
- **D10.** What to claim about robustness, given 0.35 to 0.46 on worlds where honest customers return late.
- **D4 to D7**, unchanged: the 0.75-0.85 target, the harsher simulator's numbers, the earlier unconfirmed
  decisions AM-26 to AM-38, and the training weights that need simulation truth.
