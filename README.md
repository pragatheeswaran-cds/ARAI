# ARAI development

Start with the [final portable component specification](final-spec/README.md).
It contains separate component requirements, acceptance criteria, bundled contracts/assets and a revised clickable wireframe.

- [Clickable wireframe](final-spec/wireframe/index.html)
- [Acceptance register](final-spec/acceptance-register.csv)
- [Decision provenance](final-spec/DECISIONS.md)
- [Package verification](final-spec/verification/REPORT.md)

The folder is at version 4.1 (amended 2026-10-14; see the amendment sections of the decision provenance).
Copy the entire final-spec folder to another system; ARAI-final-spec-v4.0.zip is the last packaged archive (4.1 amends the API contract only).
After any edit to final-spec, run `uv run python scripts/spec_package.py` to rebuild its register and hashes.
ARAI-final-spec-v1.0.zip is the unamended 1.0 baseline, kept as a record.
Older specs/ versions and docs/ are historical evidence, not competing development contracts.
Existing code/synthetic-data assets remain preserved; the final package bundles the required inputs.

## Code (branch `v4`)

The Python side is managed with [uv](https://docs.astral.sh/uv/); every dependency lives in the project's `.venv`.
The web side is a React/Vite app under `web/`.

**Day-to-day operation (start, stop, validate, troubleshoot) is in [RUNBOOK.md](RUNBOOK.md).**

### Run the demonstration locally (no Docker)

```
uv sync                                    # create .venv from uv.lock
cd web && npm install && npm run build     # build the UI once
cd .. && uv run arai local                 # embedded PostgreSQL + API + worker + UI on http://127.0.0.1:8000
uv run arai baseline-rehearsal             # optional second instance serving the return-rate rule only, http://127.0.0.1:8011
uv run arai db-clean --all --dry-run       # housekeeping for either demo database: notes, runs, datasets or a full reset
```

`arai local` needs the artifacts of the current experiment (worlds, bundles, the published experiment). They are
not in git; the offline pipeline below reproduces them from seeds, the specification and `uv.lock`.

Each experiment contract names its data folder (`data_root` in `final-spec/contracts/experiment.yaml`). The current
one, experiment 4, keeps everything under `data/EXP-20261005-04/`: `artifacts/`, `private/` and the local database
`postgres/`. The data of experiments 1 to 3 stays in `data/artifacts`, `data/private` and `data/postgres` and is
neither read nor written; check out an earlier experiment's commit to work with it.

### Reference runtime (Docker Compose)

```
cp .env.example .env                       # set POSTGRES_PASSWORD
docker compose up --build                  # PostgreSQL, API, one worker, UI on http://localhost:8080
```

Only the experiment's `artifacts` folder is mounted into the containers (`ARAI_ARTIFACTS` in `.env` to point elsewhere).
Its `private` folder (simulation truth) is never visible to serving.

### Offline pipeline, in order

```
uv run arai generate --seed 5101 ... 5110 5501 ... 5510   # development worlds of the current contract (experiment 4)
uv run arai train                          # freeze features, fit nine candidates and two references
uv run arai dry-run                        # gate dry run and calibration check, before any validation world
uv run arai ablation                       # what the result depends on, and which honest groups are reviewed (training worlds)
uv run arai stress                         # the frozen models on the stress worlds; diagnostic, selects nothing
uv run arai generate --seed 5201 ... 5205  # validation worlds
uv run arai select                         # apply the gate, freeze the selection
uv run arai generate --seed 5301 ... 5305  # test worlds
uv run arai test                           # the final test: runs once
uv run arai generate --seed 5401           # demonstration world
uv run arai publish --demo-world W5401     # bundles, active pointer, published experiment report
uv run arai register data/EXP-20261005-04/artifacts/worlds/W5401/operational   # or upload through the UI
```

Every command defaults to the experiment named in `final-spec/contracts/experiment.yaml` (now EXP-20261005-04) and
to its data folder. An experiment recorded under an earlier contract is a closed record: train, dry-run, ablation,
stress, select and test refuse to run for it, and `arai generate` refuses to overwrite a world that an earlier
simulator or contract produced.

The order is enforced in code: training and the dry run refuse to run once validation worlds exist, selection
needs a recorded dry run, and the test needs a frozen selection and runs once. `ablation` and `stress` read only
training and stress worlds, so they can be run or rerun at any point; `publish` puts their figures in the report.
`publish` first proves that the current feature code still reproduces the features the model was trained on, and
points serving at the new bundle only after the report is written.

### Tests

```
uv run pytest                              # 185+ tests, including the whole offline pipeline on small worlds; PostgreSQL starts itself
cd web && npm test                         # front-end unit tests
uv run python tests/e2e/walkthrough.py     # browser walkthrough against a running `arai local`
```

### Where things are

- `src/arai/generator/` builds a synthetic world; `validation.py` checks an operational snapshot against the contract.
- `src/arai/features.py` computes the 43 model features and the evidence; `modeling.py`, `evaluation.py`,
  `selection.py`, `experiment.py` train, evaluate and select; `ablation.py` measures what the result depends on
  and which honest groups are sent for review; `contract.py` reads the numbers the specification fixes.
- `src/arai/bundles.py`, `publishing.py` and `src/arai/service/` are the serving side: immutable bundles, PostgreSQL,
  batch scoring, the worker and the API (`final-spec/contracts/openapi.yaml` is the contract). Everything the API
  serves is read from PostgreSQL: a run's results are written there in the transaction that marks it succeeded
  (`run_customers`, `run_styles`, `run_skus`, `run_neighbors`, `run_timeline`, `run_customer_styles`,
  `run_communities`, `run_attributions`, `run_style_reasons`, `run_memos`), and the worker
  loads the published experiment report and truth export at startup. Registered snapshots and model bundles stay files.
- `web/` is the analyst UI.
- `notebooks/` walk through generation, exploration and features. `records/` holds the dated development records,
  including the independent reviews and what was done about each. `reports/` holds summary tables and UI screenshots.
- `data/` (ignored by git) receives generated worlds and artifacts, one folder per experiment from experiment 4 on
  (`data/EXP-20261005-04/artifacts`, `private`, `postgres`); experiments 1 to 3 share `data/artifacts` and
  `data/private`. Scoring results are not files: they are rows in PostgreSQL.

### Results in short

Four experiments have been run, each with a single final test that it passed. The fourth (EXP-20261005-04) is the
one this branch serves.

| Experiment | Simulator | Gate | Final test: model against rule | State |
|---|---|---|---|---|
| 1, EXP-20261002-01 | generous (1.3) | three legs | 71.5% / 23.9% | recorded; branch `v2` |
| 2, EXP-20261005-02 | generous (1.3) | four legs | 73.7% / 24.0% | published in `data/artifacts`; commit `b157edf` |
| 3, EXP-20261005-03 | less generous (3.0) | four legs | 54.8% / 18.6% | recorded, set aside by the owner |
| 4, EXP-20261005-04 | generous (4.0, generates as 1.3) | five legs | 76.6% / 21.8% | published in `data/EXP-20261005-04` |

Experiment 4: on five untouched simulated test worlds the selected model (boosted trees, 43 features) is right
about 76.6% of the customers it sends for review at a 5% review budget, against 21.8% for a return-rate rule. It
passed a five-leg gate: it reviews honest heavy returners, defective-product buyers, household members, customers
whose deliveries genuinely failed more than once (5.8% against 7.5%) and customers with exactly one genuine
failure (1.5% against 4.6%) no more often than the rule does.

Read it with three caveats, all measured (`records/2026-10-05-experiment-4.md`):

- **The level belongs to this simulator.** On stress worlds where honest customers return late, the same frozen
  model falls to 35-46% against 18-24% for the rule. A model trained where a late return is a tell does not carry
  over; experiment 3, trained on that behaviour, reached 54.8%.
- **The repeat-claimant leg is met with little margin.** The model reviews about 6% of that group everywhere,
  while the rule's rate moves between 5.9% and 7.5% from one set of worlds to the next, so the leg is met on
  validation and test and missed on training worlds and on the pooled stress worlds.
- **The model was trained with weights that use simulation truth** (which delivery failures were genuine). Real
  data has no such label.

The wardrobing indicator was rebuilt with this experiment. It is still built on a late return, now of occasion
wear only, and it reaches a band only when what the customer returned supports it. On the test worlds its
elevated band is right for 89 of 90 customers and holds 15% of the customers with a temporary-use return; on the
stress worlds with honest late returns it is right for 76% to 93%, where the timing rule it replaces was right
13.5% of the time in experiment 3. An indicator that does not use timing at all was tried first and dropped:
without a late return its alerts were right about one time in ten.

Earlier records: `records/2026-10-05-experiment-2.md`, `records/2026-10-05-experiment-3.md`,
`records/2026-10-02-final-test.md`, and the review in `records/2026-10-05-principal-ml-review.md`. All data of
experiments 1 to 3 is kept untouched, with a copy of experiments 1 and 2 under `data/backups/`.

### Sharing data and where the project stands

- `docs/experiment-2-data-guide.md` and `docs/experiment-4-data-guide.md` explain the synthetic data of experiments 2
  and 4: the worlds, the seven operational tables, the truth tables, the configuration that produced them and
  where the simulation is kinder than reality. The experiment 4 data also has four stress worlds with the less
  generous behaviour.
- `uv run python scripts/package_experiment_data.py --experiment EXP-20261005-04 --guide docs/experiment-4-data-guide.md`
  (or `EXP-20261005-02` with its guide) writes the data, its truth, its configuration and the guide as zip
  archives under `data/exports/<experiment>/` (not in git), after checking every file against the hashes recorded
  when the world was written. Both packages have been built.
- `records/2026-10-05-status-and-open-decisions.md` is the current state of the four experiments and the decisions
  still to be taken.
- `docs/experiment-4-verification-guide.md` says what was done in experiment 4 and how to check it;
  `uv run --no-sync python scripts/verify_experiment.py` runs the checks (read-only, half a minute).
