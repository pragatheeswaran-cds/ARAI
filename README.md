# ARAI development

Start with the [final portable component specification](final-spec/README.md).
It contains separate component requirements, acceptance criteria, bundled contracts/assets and a revised clickable wireframe.

- [Clickable wireframe](final-spec/wireframe/index.html)
- [Acceptance register](final-spec/acceptance-register.csv)
- [Decision provenance](final-spec/DECISIONS.md)
- [Package verification](final-spec/verification/REPORT.md)

The folder is at version 1.1 (amended 2026-10-02; see the amendment section of the decision provenance).
Copy the entire final-spec folder or the ARAI-final-spec-v1.1.zip archive to another system.
ARAI-final-spec-v1.0.zip is the unamended 1.0 baseline, kept as a record.
Older specs/ versions and docs/ are historical evidence, not competing development contracts.
Existing code/synthetic-data assets remain preserved; the final package bundles the required inputs.

## Code (branch `v1`)

The project is managed with [uv](https://docs.astral.sh/uv/); every dependency lives in the project's `.venv`.

```
uv sync                                   # create .venv from uv.lock
uv run pytest                             # generator and validator tests
uv run arai generate --seed 2001          # generate, write and validate fixture world 2001
uv run arai validate data/artifacts/worlds/W2001/operational
uv run jupyter lab                        # then open notebooks/01_synthetic_data_generation.ipynb
```

- `src/arai/generator/` builds a synthetic world from the specification's contracts and assets.
- `src/arai/validation.py` checks an operational world against the data contract.
- `notebooks/01_synthetic_data_generation.ipynb` walks through generation stage by stage with checks and charts.
- `records/` holds dated development records, starting with the generator's open choices and first observations.
- `data/` (ignored by git) receives generated worlds: operational tables under `data/artifacts/`, private truth
  under `data/private/`.
