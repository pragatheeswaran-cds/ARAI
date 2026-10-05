# ARAI development

Start with the [final portable component specification](final-spec/README.md).
It contains separate component requirements, acceptance criteria, bundled contracts/assets and a revised clickable wireframe.

- [Clickable wireframe](final-spec/wireframe/index.html)
- [Acceptance register](final-spec/acceptance-register.csv)
- [Decision provenance](final-spec/DECISIONS.md)
- [Package verification](final-spec/verification/REPORT.md)

The folder is at version 3.0 (amended 2026-10-05; see the amendment sections of the decision provenance).
Copy the entire final-spec folder or the ARAI-final-spec-v3.0.zip archive to another system.
After any edit to final-spec, run `uv run python scripts/spec_package.py` to rebuild its register and hashes.
ARAI-final-spec-v1.0.zip is the unamended 1.0 baseline, kept as a record.
Older specs/ versions and docs/ are historical evidence, not competing development contracts.
Existing code/synthetic-data assets remain preserved; the final package bundles the required inputs.

## Code (branch `v1`)

The Python side is managed with [uv](https://docs.astral.sh/uv/); every dependency lives in the project's `.venv`.
The web side is a React/Vite app under `web/`.

**Day-to-day operation (start, stop, validate, troubleshoot) is in [RUNBOOK.md](RUNBOOK.md).**

### Run the demonstration locally (no Docker)

```
uv sync                                    # create .venv from uv.lock
cd web && npm install && npm run build     # build the UI once
cd .. && uv run arai local                 # embedded PostgreSQL + API + worker + UI on http://127.0.0.1:8000
```

`arai local` needs the artifacts under `data/artifacts/` (worlds, bundles, the published experiment). They are
not in git; the offline pipeline below reproduces them from seeds, the specification and `uv.lock`.

### Reference runtime (Docker Compose)

```
cp .env.example .env                       # set POSTGRES_PASSWORD
docker compose up --build                  # PostgreSQL, API, one worker, UI on http://localhost:8080
```

Only `data/artifacts` is mounted into the containers. `data/private` (simulation truth) is never visible to serving.

### Offline pipeline, in order

```
uv run arai generate --seed 4101 ... 4110 4501 ... 4507   # development worlds of the current contract (experiment 3)
uv run arai train                          # freeze features, fit five candidates and two references
uv run arai dry-run                        # gate dry run and calibration check, before any validation world
uv run arai ablation                       # what the result depends on, and which honest groups are reviewed (training worlds)
uv run arai stress                         # the frozen models on the stress worlds; diagnostic, selects nothing
uv run arai generate --seed 4201 ... 4205  # validation worlds
uv run arai select                         # apply the gate, freeze the selection
uv run arai generate --seed 4301 ... 4305  # test worlds
uv run arai test                           # the final test: runs once
uv run arai generate --seed 4401           # demonstration world
uv run arai publish --demo-world W4401     # bundles, active pointer, published experiment report
uv run arai register data/artifacts/worlds/W4401/operational   # or upload through the UI
```

Every command defaults to the experiment named in `final-spec/contracts/experiment.yaml` (now EXP-20261005-03). An
experiment recorded under an earlier contract is a closed record: train, dry-run, ablation, stress, select and
test refuse to run for it, and `arai generate` refuses to overwrite a world that an earlier simulator or contract
produced. `arai publish --experiment EXP-20261005-02 --demo-world W3401` republishes the published experiment
from its records.

The order is enforced in code: training and the dry run refuse to run once validation worlds exist, selection
needs a recorded dry run, and the test needs a frozen selection and runs once. `ablation` and `stress` read only
training and stress worlds, so they can be run or rerun at any point; `publish` puts their figures in the report.
`publish` first proves that the current feature code still reproduces the features the model was trained on, and
points serving at the new bundle only after the report is written.

### Tests

```
uv run pytest                              # 170+ tests, including the whole offline pipeline on small worlds; PostgreSQL starts itself
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
  (`run_customers`, `run_styles`, `run_skus`, `run_neighbors`, `run_timeline`, `run_customer_styles`), and the worker
  loads the published experiment report and truth export at startup. Registered snapshots and model bundles stay files.
- `web/` is the analyst UI.
- `notebooks/` walk through generation, exploration and features. `records/` holds the dated development records,
  including the independent reviews and what was done about each. `reports/` holds summary tables and UI screenshots.
- `data/` (ignored by git) receives generated worlds and artifacts: operational data under `data/artifacts/`,
  private truth under `data/private/`. Scoring results are not there: they are rows in PostgreSQL.

### Results in one paragraph

Three experiments have been run. The second (EXP-20261005-02) is the published one; the third reran the same method on a
less generous simulator.

On five untouched simulated test worlds its selected model (boosted trees, 43 features) is right about 73.7% of
the customers it sends for review at a 5% review budget, against 24.0% for a return-rate rule and about 37% for a
hand-written rulebook (validation). It passed a four-leg gate: it reviews honest heavy returners, defective-product
buyers, household members and customers whose deliveries genuinely failed more than once no more often than the
rule does. That last group is the one the first experiment's model reviewed more than twice as often as the rule
(15.8% against 6.7%); here it is 4.5% against 5.3% on the test worlds.

The gap is the result, not the level: the level follows how often simulated abusers act (56% to 87% across the
stress worlds, with the rule at 14% to 44%). Two signal families carry the model, claims and return timing; on
training worlds it reaches 63% without the claim features, 59% without the timing features and 38% without both.
The model was trained to weigh honest repeat claimants more heavily, which uses simulation truth that real data
would not have. The development target of 75-85% is met on the out-of-fold training scores it is defined on (79%
best candidate, 77% selected) and not on validation or test (73.7%). This is a result about one simulation, not
about real returns. See `records/2026-10-05-experiment-2.md`; the first experiment (71.5% against 23.9%, three-leg
gate) is in `records/2026-10-02-final-test.md` and its review in `records/2026-10-05-principal-ml-review.md`.

The third experiment (EXP-20261005-03) asked how much of this survives a less generous simulation, in which honest
customers often return late and abusers act less often. With the same features, candidates and gate it passed its
final test at 54.8% against 18.6% for the rule. The level fell by a quarter; the ratio to the rule stayed at about
three. Temporary-use detection lost most of its recall (76% to 37%) and the wardrobing indicator stopped being
usable (13.5% precision), because a late return no longer tells honest customers from abusers. It is recorded and
not published: `records/2026-10-05-experiment-3.md`. All data of the first two experiments is kept untouched and
copied under `data/backups/`.

### Sharing data and where the project stands

- `docs/experiment-2-data-guide.md` explains the synthetic data of experiment 2: the worlds, the seven operational
  tables, the truth tables, the configuration that produced them and where the simulation is kinder than reality.
- `uv run python scripts/package_experiment_data.py --experiment EXP-20261005-02 --guide docs/experiment-2-data-guide.md`
  writes the data, its truth, its configuration and the guide as zip archives under `data/exports/` (not in git),
  after checking every file against the hashes recorded when the world was written.
- `records/2026-10-05-status-and-open-decisions.md` is the current state of the three experiments and the decisions
  still to be taken.
