# ARAI runbook: start, stop, validate

Commands are for PowerShell, run from the repository root
(`F:\projects\Adaptive_Return_Abuser_Intelliengence`), on branch `v4`.

The application serves experiment 4 (EXP-20261005-04). Its data, bundles and local database are in
`data\EXP-20261005-04\` (`artifacts`, `private`, `postgres`). The folders `data\artifacts`, `data\private` and
`data\postgres` belong to experiments 1 to 3 and are not used in this state of the branch; to demonstrate
experiment 2 again, check out commit `b157edf` and follow the runbook of that commit.

If `uv` is "not recognized", open a new terminal (it was installed with winget and older terminals do not have
it on PATH yet), or call it by its full path:
`C:\Users\<you>\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe`.

The demonstration narrative and click-by-click flow are in `docs\demo-script.md`.

There are two ways to run the application. **Use one at a time**, never both together: they would share the
`data\EXP-20261005-04\artifacts` folder.

| | Local (recommended for the demo) | Docker Compose (reference runtime) |
|---|---|---|
| Needs | uv, Node (only to build the UI once) | Docker Desktop running |
| Address | http://127.0.0.1:8000 | http://localhost:8080 |
| Database | embedded PostgreSQL in `data\EXP-20261005-04\postgres` | `postgres:16` container, volume `pgdata_exp_20261005_04` |
| Keeps datasets, runs and notes between restarts | yes | yes, until `down -v` |

---

## 1. First-time setup (once per machine)

```powershell
uv sync                      # creates .venv from uv.lock
cd web
npm install
npm run build                # builds the UI into web\dist
cd ..
```

Rebuild the UI (`npm run build`) only after changing something under `web\`.

The application needs the generated artifacts under `data\artifacts` (worlds, model bundles, the published
experiment). They are not in git. On this machine they already exist. On a fresh clone, either copy the `data`
folder across or reproduce it with the offline pipeline in `README.md`.

---

## 2. Local: start, stop, restart

### Start

```powershell
uv run arai local
```

It prints `ARAI local rehearsal on http://127.0.0.1:8000` and is ready in about 10 seconds. Leave the terminal
open: the server runs until you stop it. This one process is the database, the API, the scoring worker and the
UI.

To use another port: `uv run arai local --port 8010`.

### Stop

Press **Ctrl+C** in the terminal where it is running. That also stops the embedded PostgreSQL.

If the terminal is gone, or the server was started in the background, stop it by port and then stop the
database it left behind:

```powershell
# 1. stop the server listening on port 8000
$c = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($c) { Stop-Process -Id $c.OwningProcess -Force }

# 2. stop the embedded PostgreSQL if it is still running
.\.venv\Lib\site-packages\pgserver\pginstall\bin\pg_ctl.exe stop -D .\data\EXP-20261005-04\postgres -m fast
```

`pg_ctl` answers `server stopped`, or says no server is running, which is also fine.

### Restart

Stop, then start. Runs, their results and review notes are kept in the database (`data\EXP-20261005-04\postgres`);
registered snapshots and model bundles are kept as files in `data\EXP-20261005-04\artifacts`.

If a scoring run was in progress when the server stopped, it shows as **interrupted** after the restart and
publishes nothing. Use **Retry** on the Datasets & runs page.

### Start from an empty database (rarely needed)

Stop everything first, then:

```powershell
Remove-Item -Recurse -Force .\data\EXP-20261005-04\postgres, .\data\EXP-20261005-04\artifacts\datasets
uv run arai local
```

This deletes every registered dataset, run and review note. The model bundles and the experiment report are
not touched. Afterwards register and score the demonstration world again (section 4).

---

## 3. Docker Compose: start, stop

Stop the local server first (section 2).

```powershell
Copy-Item .env.example .env        # once; then set POSTGRES_PASSWORD in .env
docker compose up --build -d       # start in the background
docker compose ps                  # db, api, worker, web should be "Up"
docker compose logs -f worker      # follow the scoring worker (Ctrl+C stops following, not the stack)
```

Open http://localhost:8080.

```powershell
docker compose down                # stop; the database volume is kept
docker compose down -v             # stop and delete the database (datasets, runs, notes)
```

The Compose stack has its own database, so the demonstration world must be registered and scored in it
separately (section 4, using port 8080).

---

## 4. Load and score the demonstration world

Only needed on an empty database.

**In the browser:** open **Datasets & runs**, choose the eight files in
`data\EXP-20261005-04\artifacts\worlds\W5401\operational` (`manifest.json` and the seven `.csv` files), press
**Validate and register**, then **Score with the active bundle**. Scoring 10,000 customers takes about 12
seconds; the page updates by itself.

**From the terminal** (same thing through the API; change the port to 8080 for Docker):

```powershell
$d = "data\EXP-20261005-04\artifacts\worlds\W5401\operational"
curl.exe -s -X POST http://127.0.0.1:8000/api/v1/datasets `
  -F "manifest=<$d\manifest.json" `
  -F "customer_master=@$d\customer_master.csv" -F "sku_master=@$d\sku_master.csv" `
  -F "reason_code=@$d\reason_code.csv" -F "sales_order=@$d\sales_order.csv" `
  -F "sales_order_line=@$d\sales_order_line.csv" -F "return_order=@$d\return_order.csv" `
  -F "return_order_line=@$d\return_order_line.csv"

# use the dataset_id from the answer; the key can be any text you have not used for this dataset before
curl.exe -s -X POST http://127.0.0.1:8000/api/v1/runs -H "content-type: application/json" `
  -d '{\"dataset_id\":\"ds-27bd9b52167d935eaf7a\",\"idempotency_key\":\"demo-1\"}'
```

---

## 5. Validate that it is working

### Quick check (30 seconds)

```powershell
curl.exe -s http://127.0.0.1:8000/api/v1/health
```

Expected:

```json
{"alive":true,"scoring_ready":true,"promoted_model_ready":true,"model_kind":"supervised","queue_depth":0,"worker_seconds_since_seen":1.2}
```

| You see | Meaning |
|---|---|
| no answer | the server is not running |
| `scoring_ready: false` | no valid model bundle, or the worker has stopped: restart; if it persists run `uv run arai publish --demo-world W5401` |
| `promoted_model_ready: false`, `model_kind: baseline_fallback` | only the return-rate baseline is active; the UI shows a banner saying why |
| `worker_seconds_since_seen` is `null` or keeps growing while `queue_depth` is above 0 | no scoring worker is running: restart (local), or `docker compose restart worker` |

```powershell
curl.exe -s http://127.0.0.1:8000/api/v1/runs       # the latest run should be "succeeded"
```

Then open http://127.0.0.1:8000: the Overview should show 5,676 eligible customers and 284 selected for world
W5401.

### Full check before a demonstration

Run these in order. Each line says what a good result looks like.

```powershell
# 1. Python tests. They start their own temporary PostgreSQL; the running server is not touched.
uv run --no-sync pytest -q                          # "206 passed" in about 9 minutes

# 2. Front-end tests and type check
cd web; npm test; npx tsc --noEmit; cd ..            # "21 passed"; tsc prints nothing

# 3. Browser walkthrough of the running application (needs the server up with a scored run; uses Edge, headless)
uv run --no-sync python tests\e2e\walkthrough.py     # "54 of 54 checks passed"

# 4. Baseline-fallback check (starts its own temporary instance on port 8011)
uv run --no-sync python tests\e2e\fallback_check.py  # "11 of 11 checks passed"
```

Use `uv run --no-sync` while the server is running: plain `uv run` may try to refresh the environment and fail
with "file is being used by another process".

The walkthrough writes one review note on the top-ranked customer each time it runs and stages the second-reviewer
refusal, so it also opens that case. Notes are append only, so they accumulate; that is expected. The fallback check
scores W2001 where that world exists and W5401 otherwise (or the world named on its command line).

Screenshots and results from steps 3 and 4 are written to `reports\ui\<today's date>\`.

### Validate data

```powershell
# an operational snapshot against the data contract; exit code 0 and "accepted": true mean it passed
uv run --no-sync arai validate data\EXP-20261005-04\artifacts\worlds\W5401\operational
```

Uploading through the UI or the API runs the same validation; a snapshot that fails is rejected whole and the
answer lists each broken rule.

### Validate the specification package

```powershell
uv run --no-sync python final-spec\tools\verify_package.py     # "result": "PASS"
```

After editing anything under `final-spec\`, rebuild its register and hashes first:
`uv run --no-sync python scripts\spec_package.py`.

### Validate the model results

The numbers are frozen records, not something to re-run:

- `data\EXP-20261005-04\artifacts\experiments\EXP-20261005-04\selection.json`: selected model and
  `final_test_status`.
- `data\EXP-20261005-04\artifacts\experiments\EXP-20261005-04\reports\`: `dry_run.json`, `validation.json`,
  `test.json`, `ablation.json` and `stress.json`.
- The same figures are on the **Evaluation** page and in `records\2026-10-05-experiment-4.md`.
- The records of experiments 1 to 3 are closed and stay in `data\artifacts\experiments\`; the offline steps
  refuse to run for an experiment of an earlier contract.

**Do not run `arai train`, `arai dry-run`, `arai select` or `arai test` again for this experiment.** The code
refuses most of these, and the final test is designed to run exactly once. Do not regenerate worlds 5201-5205
or 5301-5305, and never a world of an earlier experiment (the command refuses those seeds).

---

## 6. When something goes wrong

| Symptom | Likely cause | What to do |
|---|---|---|
| `uv` not recognized | terminal opened before uv was installed | new terminal, or the full path at the top |
| "port 8000 already in use" / address in use | a server is still running | stop it by port (section 2) |
| "file is being used by another process" from `uv run` | the server holds the environment | add `--no-sync`, or stop the server first |
| UI opens but says the API cannot be reached | server stopped | start it (section 2) |
| A run shows **failed / output_missing** | it was scored by an earlier version and its result files were deleted before they were loaded into the database | press **Retry**; it creates a new run with the same dataset and model |
| A run shows **interrupted** | the server stopped while scoring | press **Retry** |
| A run carries a warning that scores or inputs are outside training | the snapshot differs from the training worlds | expected for unusual data; treat percentiles and the review list with caution |
| A run warns that the scoring code differs from the published bundle | code changed after `arai publish` | `uv run --no-sync arai publish --demo-world W5401`, restart, score again |
| `arai publish` says the feature code no longer reproduces the training features | `features.py` changed in a way that changes values | restore the code, or train a new experiment on fresh seeds |
| Banner: baseline only | no promoted model is active | `uv run --no-sync arai publish --demo-world W5401`, then restart |
| Evaluation page is empty after `arai publish` | the report is loaded into the database when the worker starts | restart (local), or `docker compose restart worker` |
| `web/dist is missing` at start | UI not built | `cd web; npm install; npm run build` |
| Docker: `POSTGRES_PASSWORD is missing a value` | no `.env` | copy `.env.example` to `.env` and set it |
| Walkthrough or fallback check fails on "msedge" | Microsoft Edge not installed | install Edge, or set `ARAI_BROWSER` to a Chromium executable (both scripts read it) |

Server logs are in the terminal where `arai local` runs (or `docker compose logs api worker`). Every error the
API returns carries a `request_id`; search the log for it.
