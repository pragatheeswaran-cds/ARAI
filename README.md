# ARAI development

Start with the [final portable component specification](final-spec/README.md).
It contains separate component requirements, acceptance criteria, bundled contracts/assets and a revised clickable wireframe.

- [Clickable wireframe](final-spec/wireframe/index.html)
- [Acceptance register](final-spec/acceptance-register.csv)
- [Decision provenance](final-spec/DECISIONS.md)
- [Package verification](final-spec/verification/REPORT.md)

The folder is at version 1.6 (amended 2026-10-02; see the amendment sections of the decision provenance).
Copy the entire final-spec folder or the ARAI-final-spec-v1.6.zip archive to another system.
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
uv run arai generate --seed 2001 2002 2003 2101 ... 2110 2501 ... 2507   # development worlds
uv run arai train                          # freeze features, fit five candidates and two references
uv run arai dry-run                        # gate dry run and calibration check, before any validation world
uv run arai generate --seed 2201 ... 2205  # validation worlds
uv run arai select                         # apply the gate, freeze the selection
uv run arai generate --seed 2301 ... 2305  # test worlds
uv run arai test                           # the final test: runs once
uv run arai generate --seed 2401           # demonstration world
uv run arai publish --demo-world W2401     # bundles, active pointer, published experiment report
uv run arai register data/artifacts/worlds/W2401/operational   # or upload through the UI
```

The order is enforced in code: training and the dry run refuse to run once validation worlds exist, selection
needs a recorded dry run, and the test needs a frozen selection and runs once.

### Tests

```
uv run pytest                              # 150+ tests; storage and API tests start their own PostgreSQL
cd web && npm test                         # front-end unit tests
uv run python tests/e2e/walkthrough.py     # browser walkthrough against a running `arai local`
```

### Where things are

- `src/arai/generator/` builds a synthetic world; `validation.py` checks an operational snapshot against the contract.
- `src/arai/features.py` computes the 17 model features and the evidence; `modeling.py`, `evaluation.py`,
  `selection.py`, `experiment.py` train, evaluate and select; `ablation.py` measures the timing dependence.
- `src/arai/bundles.py`, `publishing.py` and `src/arai/service/` are the serving side: immutable bundles, PostgreSQL
  metadata, batch scoring, the worker and the API (`final-spec/contracts/openapi.yaml` is the contract).
- `web/` is the analyst UI.
- `notebooks/` walk through generation, exploration and features. `records/` holds the dated development records,
  including the independent reviews and what was done about each. `reports/` holds summary tables and UI screenshots.
- `data/` (ignored by git) receives generated worlds and artifacts: operational data under `data/artifacts/`,
  private truth under `data/private/`.

### Results in one paragraph

On five untouched simulated test worlds the selected model (boosted trees) is right about 71.5% of the customers
it sends for review at a 5% review budget, against 23.9% for a return-rate rule and about 35% for a hand-written
rulebook (validation). Without any timing feature the same model family reaches 56% on training worlds; the
development target of 75-85% was not met. This is a result about one simulation, not about real returns. See
`records/2026-10-02-final-test.md` and `records/2026-10-02-gate-dry-run.md`.
