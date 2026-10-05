# Principal ML engineer review of the specification and the codebase (2026-10-05)

Requested by the project owner. Reviewed at commit 60b556a (branch `v2`, specification 1.7).

**Read:** all 16 component specifications, `experiment.yaml`, `features.yaml`, `reason-groups.yaml`, the decision
log and the acceptance register; all of `src/arai` except the two exploration modules (`eda.py`,
`feature_eda.py`, skimmed); the service tests in full and the other test files by name; the API client, three
of the six UI pages in full and two in part; Docker and Compose files. **Not read:** the notebooks, the Styles
page, `generator-config.yaml` line by line, the OpenAPI document beyond what the tests validate.

**Measured (read-only, nothing written under `data/`):** the frozen validation and test reports; a refit of the
selected model; out-of-fold permutation importance, feature-family ablations, a learning curve and false-positive
groups on the ten training worlds; the promoted bundle on the seven stress worlds and three fixture worlds. No
validation or test world was scored again.

## Verdict

The experiment is sound and the result is real for this simulator: the protocol (grouped folds, frozen
selection, one test) was followed and is enforced in code, the selected model refits to identical scores, and
validation (0.707), test (0.715) and out-of-fold training (0.694) agree. I found no leakage.

Three things should change how the result is presented, and one of them should change the next experiment:

1. The promotion gate does not see the group the model harms most (A1).
2. The headline level is set by one simulator knob, and the published caveat names only half of the
   dependence (A2, A3).
3. Several specification requirements have no acceptance criterion and were not built (B1).

## A. What the model does (measured)

Figures are out of fold on the ten training worlds at the 5% budget unless stated. Prevalence among eligible
customers is 5.6%, so the budget is about the number of abusers and precision and recall move together.

### A1. Honest repeat claimants are reviewed 2.4 times as often by the model as by the rule, and the gate has no leg for them

| Honest group | Customers | Reviewed by model | Reviewed by rule |
|---|---|---|---|
| Two or more genuinely failed units (repeat genuine claimant) | 4,015 | 15.8% | 6.7% |
| Exactly one genuinely failed unit | 6,440 | 1.2% | 4.8% |
| No genuine failure | 42,979 | 0.4% | 3.7% |
| Heavy returner (gate leg) | 4,894 | 7.6% | 44.2% |
| Household member (gate leg) | 6,981 | 2.0% | 3.9% |
| Defective-product buyer (gate leg) | 10,987 | 2.5% | 6.0% |

73% of the model's false positives (636 of 867) are repeat genuine claimants, against 12% of the rule's (270 of
2,165). The frozen reports show the same: 308 of 416 on validation and 291 of 404 on the test. The model sends
far fewer honest customers to review overall, but for customers whose parcels really did go missing more than
once it is worse than the rule it replaces. The gate was written to stop exactly this kind of shift and checks
three groups; this fourth group is reported in the error account and gated nowhere.

The gate cannot be changed for this experiment. For the next one: add the group as a gate leg, or at least
publish its review rate beside the rule's. Today: add the sentence to the published limitations and to the
evaluation page. A feature that separates the two cases would need information the model does not have (how
other parcels to the same address fared); in the simulator an address is mostly one account, so part of this
error is irreducible by design.

### A2. Two signals carry the model

Drop in precision when one feature is shuffled within its world (baseline 0.694): `claim_share` 0.359,
`late_return_lines` 0.173, `residual_z` 0.072, `coordinated_claim_share` 0.040, `median_window_ratio` 0.031,
`raw_return_rate` 0.028; each of the other eleven is under 0.02.

| Feature set | Precision | Recall non-receipt / contents / temporary use |
|---|---|---|
| All 17 | 0.694 | 0.74 / 0.65 / 0.64 |
| Without the two claim features | 0.552 | 0.51 / 0.43 / 0.67 |
| Without the three timing features | 0.561 | 0.79 / 0.71 / 0.21 |
| Without both families | 0.384 | 0.51 / 0.43 / 0.25 |
| Return-rate rule | 0.237 | |

The published caveat (AM-31) says the figure without timing features, 0.561, is the one to quote as robust. That
figure still rests on `claim_share`, which is as much a simulator setting as the timing law: it works because a
deceptive claimant claims on about a fifth of orders while a genuine failure strikes about 1.5% of lines. The
claim dependence deserves the same disclosure as the timing dependence. `ablation.py` should report all four
rows above.

### A3. The headline level follows the action-rate setting

The promoted bundle on the stress worlds (not used in training; gate passes on all seven):

| World | Change | Model | Rule |
|---|---|---|---|
| W2505 | action rate x0.5 | 0.523 | 0.144 |
| W2501-04, W2507 | other mechanisms | 0.68-0.71 | 0.21-0.29 |
| W2506 | action rate x2 | 0.846 | 0.441 |

The 0.75-0.85 development target (AM-30, not met) is therefore a statement about one permitted calibration
lever, not about the model: doubling the action rate gives 0.85 with the same model. What is stable across all
seven is the ordering and the gap (the model finds two to four times as many abusers per review as the rule).
Present the gap and the ordering; do not present 71.5% as a level. I would close AM-30 as "not a model property"
instead of leaving it open.

### A4. More data or a bigger model will not move it

Training on 1, 2, 4 and 8 worlds and scoring the last two training worlds gives 0.639, 0.683, 0.681, 0.690: flat
after two worlds. `hgb_leaf15` and `hgb_leaf31` tie on validation (0.707 and 0.706, inside a spread of 0.69 to
0.72), so the choice between them is noise and harmless. In-sample precision of the final fit is 0.733 against
0.694 out of fold: little overfitting. The ceiling is signal: 29% of eligible abusers completed exactly one
action, and the model finds 27% of those against 76% of the rest. One deceptive claim looks like one genuine
failure.

### A5. Other observations

- Reproducible: refitting `hgb_leaf15` on the training frame reproduces every stored score exactly.
- The isolation forests (0.22 and 0.24 on validation) do not beat the return-rate rule and fail the household
  leg. The supervised/unsupervised comparison the goals ask for is delivered, and its answer is that the
  unsupervised candidates add nothing here. Say so in the walkthrough.
- The analyst rulebook reaches 0.353: five hand-written rules get a third of the way from the rule to the model.
- Fixture worlds (1,000 customers, about 28 reviews each) give 0.54 to 0.63 with one defect-leg failure; at that
  size the figure is too noisy to conclude anything. The small-population warning fires below 500 eligible
  customers; the fixtures have about 550 and get none.
- The share of a snapshot scoring above the training 95th percentile moved from 4.0% (action rate halved) to
  5.7% (doubled). That one number is a usable drift signal (see B1).
- About 10% of abusers have fewer than three mature lines and are never ranked (177 of 1,776 on validation).
- Features and labels share one cutoff: this is retrospective triage of a closed year, not a forecast. The
  specification never claims otherwise; the walkthrough should not either.

## B. The specification

The package is unusually disciplined: decisions carry provenance, the experiment order is written down and then
enforced, and limitations are part of the contract. The problems are at its edges.

### B1. Requirements with no acceptance criterion were not built

- **Drift reports** (component 15: "compare input/score distributions to training"). Nothing computes one. Now
  that results are rows in PostgreSQL, a first version is one query per run (A5).
- **Monitoring of queue depth and duration** (component 15). `Store.queue_depth` exists and nothing calls it.
- **The timing ablation in every report** (component 08, AM-31). `ablation.py` has no command, no test and is
  not in the documented pipeline; the published limitation text refers to its figure whether or not the file
  exists. A rerun of the README pipeline produces a report without the disclosure.
- **Stress reports** (component 08). The only stress evaluation of the models is a paragraph in a review
  record; no command produces it. The table in A3 should be a pipeline output.
- **The bundle's cutoff** (component 10 lists it among the bundle contents). The manifest has none.
- **The calibration disclosure** (component 05: every report states whether difficulty was calibrated and with
  which levers). `publishing.py` hard-codes `calibrated: False, levers: []` and a dated record path.

Each needs either an acceptance criterion and an implementation, or a dated decision to drop it.

### B2. The contract and the code can drift apart silently

- `reason-groups.yaml` defines the code groups; no code reads it. `features.py` carries its own copies. They
  agree today and no test ties them together.
- The eligibility minimum, the 5% budget, the sensitivity budgets and the bootstrap settings are in
  `experiment.yaml` and again as constants in code. The feature order, by contrast, is read from the contract;
  do the same for these.
- The benign-segment definitions exist twice (`evaluation.benign_segments` and `eda.benign_segments`), and the
  tie-break twice (`ranking.py` and `diagnostics.py`).

### B3. Fold-local fitting is specified and not done

Component 07 and `experiment.yaml` require each fold to fit its fallbacks on eight worlds. The category
fallback is fitted once on all ten. The register already records this as PARTIAL (TRAIN-AC-02), and it has no
effect because no development world ever used the fallback. Either fit it per fold or amend the sentence, and
assert in training that the fallback count is zero.

### B4. Housekeeping

- Every component ends with "Acceptance status: NOT_RUN" while the register shows 91 PASS, 9 PARTIAL and 3
  NOT_RUN. Remove the footer or generate it from the register.
- Version labels differ by file (components 1.0 to 1.7, `experiment.yaml` 1.1, `features.yaml` 1.4). They mean
  "last amended in"; say so once in the README.
- The gate is a point-estimate rule with a leg that cannot fail (heavy returners). Both are disclosed. With A1
  in mind, the next gate should be designed from the error account instead of from the list of groups that
  seemed at risk beforehand.
- Still open with the demonstration four weeks away: target-machine rehearsal (TEST-AC-04), database backup and
  restore (STORE-AC-05), the optional VM (OPS-AC-05).

## C. The codebase

The same-day code review stands. Fixed since: results, the experiment report and the truth export are served
from PostgreSQL (AM-39). Still open, in order of importance:

1. The bundle records the scoring-code hash at publish time, not at training time, and nothing compares it with
   the running code (`bundles.py:143`).
2. The upload route runs validation on the event loop and blocks every other request (`api.py`,
   `register_dataset`).
3. `experiment.train` and `evaluation.private_counts` drop the artifact root they are given; no test runs the
   pipeline end to end.
4. `publishing.publish` activates the model before the report is built.
5. Labels are joined without checking that the truth belongs to the world (`dataset.labelled`, `load_world`).
6. Validation worlds are not checked for the generator hash; test worlds are.
7. Operations: no restart policy and no worker heartbeat in Compose; the login check returns 500 on a
   non-ASCII header; no git remote.

New in this review:

8. The Evaluation page finds metrics by display text assembled in `publishing.py`; give `Metric` a stable code.
9. `sqlalchemy` is still a runtime dependency that nothing imports.

## D. Recommended order

1. Disclose A1, A2 and A3 in the published report and on the evaluation page (text only; no model, world or
   gate changes, so the experiment stays valid).
2. Make the ablation and the stress table pipeline commands with tests (B1), so the disclosures reproduce.
3. Fix C1 to C6; add one end-to-end pipeline test on small worlds.
4. Add the per-run drift figure and expose queue depth (B1).
5. Rehearse on the presentation machine; back up and restore the database once; push the repository to a remote.
6. Next experiment (fresh validation and test seeds): a gate leg for repeat genuine claimants, contract-driven
   constants, fold-local fallbacks.

## Follow-up, same day

The project owner asked for every item to be fixed. Done and recorded as specification 1.8 (AM-40 to AM-44):

- A1 to A3 are disclosed in the published report and lead the evaluation page; `arai ablation` and `arai stress`
  produce the figures and reproduce the tables above exactly.
- B1: drift report per run, worker heartbeat and queue depth in health, the ablation and stress commands, the
  bundle's cutoff, the calibration disclosure recorded with the dry run. B2: contract values are read from the
  contracts; one definition of the segments, the tie-break and the table list. B3: training refuses a world that
  needs the all-worlds fallback, and component 07 says so. B4: footers and version labels.
- C1 to C9, including an end-to-end pipeline test on small worlds, a database dump-and-restore test, stable metric
  codes (API contract 1.3.0) and the removal of `sqlalchemy`. The generator is byte-identical: its code hash still
  matches every world on disk.
- The experiment was republished: same estimator, new bundle identifier, and the feature code was proved to
  reproduce the frozen training features value for value.

Not done, because they are not mine to do or belong to a new experiment: the gate leg for honest repeat
claimants (it needs a revised `experiment.yaml`, fresh validation and test seeds and a new final test); the
rehearsal on the presentation machine; the optional VM; a git remote. Left as they were, by judgement: a new
database connection per query, and three unused store methods.
