# Status and open decisions (end of 2026-10-05)

## Update, later on 2026-10-05: experiment 4

The owner answered three of the decisions below: D1 "since experiment 3 is harsher, ignore it. but don't touch
those data. Keep as-is. you create new expermient with new data on separate folder for new data"; D2 "rebuilt
with new experiment"; D3 "go with recommendation". They were carried out as experiment 4 (EXP-20261005-04,
specification 4.0, AM-51 to AM-54). The rest of this record describes the state before it and is kept as written.

| | |
|---|---|
| Result | Final test passed: 0.766 against 0.218 for the return-rate rule, five legs met. `records/2026-10-05-experiment-4.md` |
| Where | `data/EXP-20261005-04/` (artifacts, private, postgres). Nothing in `data/artifacts`, `data/private` or `data/postgres` was modified |
| Served by this branch | Experiment 4: bundle `m-7f2dafb5f8101da88c6859e7`, demonstration world W5401. Experiment 2 stays published in the old folder and is demonstrated from commit `b157edf` |
| Tests | 189 Python tests and 14 front-end tests pass; browser walkthrough 47 of 47 |
| Package for the team | `data/exports/EXP-20261005-04/`: five archives (679 MB) with `DATA-GUIDE.md`, built by `scripts/package_experiment_data.py`; guide source `docs/experiment-4-data-guide.md` |

What the answers settled and what they opened:

- **D1, settled.** Experiment 3 is set aside; its data and records are kept unchanged.
- **D2, done differently from the recommendation.** The recommendation was an indicator that does not rest on
  timing. Measured, such an indicator is right about one time in ten in this simulation. The rebuilt indicator
  keeps a late return of occasion wear as its signal and requires support from what the customer returned.
  Elevated band: right for 99% on the test worlds and 76% to 93% on the stress worlds with honest late returns.
- **D3, done.** Fifth leg for customers with one genuine failure, weights on both groups. It works for that group
  (1.5% reviewed against 4.6%) and costs margin on the repeat claimants.

Decisions now open, in addition to D4 to D7 below:

- **D8. Confirm AM-54.** Experiment 4 was published in its own folder on passing. This is the implementer's
  reading of "you create new experiment". To undo it, delete nothing: check out `b157edf`, which serves experiment 2.
- **D9. The selection rule.** The selected model meets the repeat-claimant leg with little margin and misses it
  on training worlds and on the pooled stress worlds. Candidates weighted on repeat claimants only keep a clear
  margin on both claimant legs for about one point of precision less. Preferring margin on the protected groups
  within a precision tolerance would be a change of the selection rule and needs a new experiment on fresh seeds.
- **D10. What to claim about robustness.** A model trained on the generous simulator reaches only 35-46% on
  worlds where honest customers return late. "About three times the rule on both simulators" is true only when
  the model is trained on the behaviour it is scored on.
- **D4, new fact.** The 0.75-0.85 target is met on the out-of-fold training scores it is defined on (0.770 best,
  0.751 best that meets the gate) and, for the first time, on the test worlds (0.766). Validation was 0.743.

Written at the owner's request: everything is recorded here so the open decisions can be taken later. Branch `v3`,
specification 3.0, 183 Python tests and 13 front-end tests passing. Nothing is pushed: the repository has no
remote.

## 1. Where things stand

| Experiment | Simulator | Features / gate | Final test: model against rule | Status |
|---|---|---|---|---|
| EXP-20261002-01 | generator-config 1.3 | 17 / three legs | 0.715 / 0.239 | Passed. Demonstrable from branch `v2`. Its bundles do not load on `v3` (17 features against 43). |
| EXP-20261005-02 | generator-config 1.3 | 43 / four legs | 0.737 / 0.240 | Passed. **Published and active on `v3`** (bundle `m-8c0e069929f81739c1321e38`, demo world W3401). |
| EXP-20261005-03 | generator-config 3.0, less generous | 43 / four legs | 0.548 / 0.186 | Passed. Recorded, **not published**. |

Each final test was run once and may not be rerun. The validation and test worlds of all three are used.

What today established, in one place:

- The method finds about three times as many abusers per review as a return-rate rule, on every world set and
  on both simulators. That ratio is the result that travels; no single percentage does.
- The level depends on two behaviours the simulator controls: how often abusers claim, and when items come
  back. Experiment 3 blurred both and the level fell from 0.737 to 0.548.
- A claim-driven model reviews honest repeat claimants more often than the rule unless it is trained not to.
  The fourth gate leg and the training weight (experiment 2) fix that for customers with two or more genuine
  failures.

Records: `2026-10-05-principal-ml-review.md` (the review and its fixes), `2026-10-05-experiment-2-exploration.md`,
`2026-10-05-experiment-2.md`, `2026-10-05-experiment-3.md`. Decisions: `final-spec/DECISIONS.md`, AM-39 to AM-50.

## 2. Open decisions

Each is the owner's. None blocks the others.

### D1. Which experiment is the demonstration

- **Keep experiment 2** (the current state). Higher numbers, on the simulator the team already knows. The caveat
  that the level is generous must be said aloud.
- **Publish experiment 3.** Lower numbers on a simulator that is easier to defend. Needs
  `uv run arai generate --seed 4401` and `uv run arai publish --demo-world W4401`; it replaces the active model.
  The wardrobing indicator must be dealt with first (D2), because it is on every case page.
- **Show both.** Experiment 2 in the application, experiment 3 as one slide: "we made the simulation harder; the
  level fell, the ratio held."

### D2. The wardrobing indicator

Under generator-config 3.0 its "elevated" band is right 13.5% of the time (95% under 1.3), because it scores late
item returns and honest customers now return late. It is report-only and outside the model, but it is shown on
every case page. Options: leave it and say it is only meaningful under the first simulator; hide it when the
snapshot's honest late-return share is high; rebuild it on something other than timing (occasion wear, repeat
purchase-and-return of the same style); remove it.

### D3. The gate leg for honest claimants

The fourth leg protects honest customers with two or more genuinely failed units. In experiment 3 the weighted
model moved false positives to customers with exactly one (7.7% reviewed against 5.2% for the rule), who are not
gated. Options: widen the leg to any genuine failure; add a fifth leg; leave it and disclose. Any change is a new
experiment on fresh seeds.

### D4. The 0.75-0.85 development target (AM-45)

Kept open at the owner's instruction "until we reach the target". Facts: on the out-of-fold training scores the
target is defined on, experiment 2 reached 0.793 (best candidate, which fails the gate) and 0.767 (selected), with
no calibration lever changed. On validation and test the selected model is at 0.737. On the less generous
simulator the best is 0.577. To decide: whether "reached" means the definition (met in experiment 2), or
validation and test (not met), and on which simulator.

### D5. The numbers of the less generous simulator (AM-49)

Chosen by the implementer as plausible, not fitted: 12% late returners with half their returns late, 5% of other
honest returns late, 30% of temporary-use returns early, action rate mean 0.143. The owner may revise them; that
is a new simulator version and a new experiment.

### D6. Earlier implementation decisions still awaiting confirmation

AM-26 to AM-38 (2026-10-02) were taken during the build and never confirmed one by one. The ones that shape
results: link features are evidence only (AM-26); the late-return feature (AM-27); the rebuilt wardrobing
indicator (AM-28, now in question under D2); generator realism fixes (AM-29).

### D7. Training weights need simulation truth (AM-48)

The selected models of experiments 2 and 3 were trained knowing which honest customers had genuine failures.
Real data has no such truth. To decide before any claim about applicability: accept it as a simulation device and
say so, or require a model that passes the fourth leg without it.

## 3. Not done, and not the implementer's to do

- A rehearsal on the presentation machine (TEST-AC-04, OPS-AC-06).
- A git remote, or any copy of the repository off this disk.
- The optional VM deployment (OPS-AC-05).
- Owner sign-off in the acceptance register (99 pass, 7 partial, 3 not run of 112, all "sign-off pending").

## 4. Where the data is

| What | Where | Note |
|---|---|---|
| Worlds of all three experiments | `data/artifacts/worlds/`, truth in `data/private/` | 79 worlds. Seeds 21xx-25xx: generator-config 1.3, experiment 1 (stress worlds also used by experiment 2). 31xx-34xx: experiment 2. 41xx-45xx: experiment 3. |
| Experiment records | `data/artifacts/experiments/<id>/` | Reports, selection, candidates. Closed records. |
| Bundles and the active pointer | `data/artifacts/bundles/`, `active/` | Pointer version 4: experiment 2. |
| Backup of experiments 1 and 2 | `data/backups/2026-10-05-experiments-1-and-2/` | Complete copy (2.2 GB) taken before the simulator changed. Same disk. |
| Package for the team | `data/exports/EXP-20261005-02/` | Five archives, see below. |
| Local database | `data/postgres/` | Upgrades itself on the next `uv run arai local`. |

`data/` is ignored by git. The worlds can be regenerated from their seeds at the commits named in their records;
the experiment records, which include the single final tests, cannot.

## 5. The data package shared with the team

Experiment 2's data, packaged by `scripts/package_experiment_data.py` into `data/exports/EXP-20261005-02/`:

1. `ARAI-EXP-20261005-02-1-operational-csv.zip`: the seven tables of 28 worlds as CSV with manifests.
2. `ARAI-EXP-20261005-02-2-operational-parquet.zip`: the same as typed Parquet.
3. `ARAI-EXP-20261005-02-3-private-truth.zip`: the twelve truth tables of each world.
4. `ARAI-EXP-20261005-02-4-configuration.zip`: contracts, assets, component specifications and generator code as
   of commit a7b79aa, and the experiment's records.
5. `ARAI-EXP-20261005-02-5-features-and-results.zip`: the 43 features per customer and the experiment's reports.

The guide inside every archive is `docs/experiment-2-data-guide.md`. Truth is in its own archive so it is never
unpacked beside the tables a model reads. The validation and test worlds in the package have been used; the guide
says so and says how to generate untouched ones.

## 6. Rules to keep

- Never rerun a final test, and never regenerate a world of a finished experiment. The commands now refuse both
  for experiments of an earlier contract, and `arai generate` refuses to overwrite a world of another simulator.
- `features.py`, `dataset.py`, `modeling.py`, `bundles.py` and `ranking.py` are hashed into the active bundle. An
  edit makes every new run carry a warning until the experiment is republished.
- `src/arai/generator/`, `settings.py`, `catalog.py` and `rng.py` are hashed into every world. An edit means new
  worlds no longer match old ones: it is a new simulator and belongs with a new experiment.
- The contract in the repository names one experiment (now experiment 3). To work on an earlier one, check out
  its commit: a7b79aa for experiment 2, cfa1e37 on `v1`/`v2` history for experiment 1.
- A new idea is tested on new seeds.
