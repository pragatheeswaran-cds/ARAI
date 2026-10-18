# ARAI runbook: start, stop, validate

Commands are for PowerShell, run from the repository root
(`F:\projects\Adaptive_Return_Abuser_Intelliengence`), on branch `year-of-snapshots`, which contains every earlier
branch (`git fetch origin; git checkout year-of-snapshots`).

The application serves experiment 4 (EXP-20261005-04). Its data, bundles and local database are in
`data\EXP-20261005-04\` (`artifacts`, `private`, `postgres`). The folders `data\artifacts`, `data\private` and
`data\postgres` belong to experiments 1 to 3 and are not used in this state of the branch; to demonstrate
experiment 2 again, check out commit `b157edf` and follow the runbook of that commit.

If `uv` is "not recognized", open a new terminal (it was installed with winget and older terminals do not have
it on PATH yet), or call it by its full path:
`C:\Users\<you>\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe`.

The demonstration narrative and click-by-click flow are in `docs\demo-script.md`. A guided end-to-end lab, from
generating the data to every screen as each role, is in `HANDS-ON.md`.

## Start here: a fresh clone on a new machine

**What a clone has, and what it does not.** Git holds the code, the specification, the baseline rehearsal fixture
and the development Keycloak realm. It does not hold the experiment's data (`data\` is ignored: the synthetic
worlds, the trained model bundles, the published report and the local database) or your `.env`. So a fresh clone
cannot show anything until the data is there: copy it from a machine that has it, or generate it from the seeds,
which reproduces the same worlds and the same selected model (step 3).

```powershell
# 1. the branch with all the work (main does not have it yet)
git fetch origin
git checkout year-of-snapshots

# 2. the environment and the UI (section 1)
uv sync
cd web; npm install; npm run build; cd ..

# 3. the data: EITHER copy the folder data\EXP-20261005-04 from the machine that has it into data\ (then skip to 4),
#    OR generate it from the seeds: the eleven commands of section 1.3, in order (about 40 minutes); after that,
#    also rebuild the rehearsal fixture once, because publishing gives the bundles new ids (section 1.4):
uv run arai baseline-rehearsal --fresh            # Ctrl+C once it says the run succeeded; only for the rehearsal

# 4. W5401 month by month for a year (9 Oct 2025 to 9 Aug 2026; the world itself is 9 Sep 2026), for the
#    customer-history screens (section 4.1); about 3 minutes
uv run arai snapshot W5401 --as-of 2025-10-09 2025-11-09 2025-12-09 2026-01-09 2026-02-09 2026-03-09 2026-04-09 2026-05-09 2026-06-09 2026-07-09 2026-08-09

# 5. start the instance (terminal 1; leave it running)
uv run arai local                                  # http://127.0.0.1:8000

# 6. in terminal 2: register and score the twelve monthly snapshots (about 10 minutes), then record the August
#    review outcomes (safe to rerun)
uv run --no-sync python scripts\history_demo.py --load
```

Then open http://127.0.0.1:8000 and choose a person. The Overview should show W5401 with 5,676 customers scored
and 284 in the queue. To check everything: section 5 ("Full check before a demonstration").

**Who you can sign in as.** Two ways, with the same six people and roles:

| Development login (default on a laptop; no password) | Keycloak development realm (`AUTH_MODE=oidc`, section 2.6) | Roles in ARAI |
|---|---|---|
| Asha, Ravi, Meera | `asha`, `ravi`, `meera`, password `arai-dev` | reviewer, approver |
| Arjun | `arjun`, password `arai-dev` | reviewer |
| Priya | `priya`, password `arai-dev` | viewer |
| Admin | `admin`, password `arai-dev` | admin (registers and scores snapshots, People & access; does not review) |

The Keycloak side, all defined in `deploy\keycloak\arai-realm.json` and `docker-compose.yml`:

| What | Value |
|---|---|
| Start it | `docker compose --profile sso up -d keycloak` (needs Docker and `POSTGRES_PASSWORD` set in `.env`: `Copy-Item .env.example .env`) |
| Realm | `arai`, at http://127.0.0.1:8081/realms/arai |
| Admin console (to add people or change groups) | http://127.0.0.1:8081/admin, user `kcadmin`, password `kcadmin-dev` (`KEYCLOAK_ADMIN_USER`, `KEYCLOAK_ADMIN_PASSWORD` in `.env` change them before the first start) |
| Client ARAI signs in with | `arai`, secret `arai-dev-secret` |
| Groups that give ARAI roles | `arai-viewers`, `arai-reviewers`, `arai-approvers`, `arai-admins` |
| ARAI settings for it | the five `$env:` lines of section 2.6, then `uv run arai local` |

These passwords and the secret are for a rehearsal on one machine only; they are in git on purpose and must never be
used on a shared deployment. Keycloak keeps nothing between restarts here: the realm is imported afresh each start.

## 0. Every command in one place

Every command that manages the environment, with the section that explains it. Run them from the repository root;
add `--no-sync` after `uv run` while an instance is running (section 5).

| Purpose | Command | Section |
|---|---|---|
| **Set up** | | |
| Python environment from the lock | `uv sync` | 1.1 |
| Build the UI (after any change under `web\`) | `cd web; npm install; npm run build; cd ..` | 1.2 |
| UI development server with live reload (API on 8000) | `cd web; npm run dev` (http://127.0.0.1:5173) | 1.2 |
| Regenerate the UI's API types after a contract change | `cd web; npm run api-types; cd ..` | 1.2 |
| Generate the synthetic data and reproduce the experiment from seeds (fresh clone only) | the eleven commands of section 1.3, in order | 1.3 |
| One more synthetic world from a new seed | `uv run arai generate --seed <seed no experiment has used>` | 1.3 |
| Rebuild the rehearsal fixture after bundles changed | `uv run arai baseline-rehearsal --fresh` then commit `rehearsal\baseline` | 1.4 |
| **Start and stop** | | |
| Start the product instance (port 8000) | `uv run arai local` | 2.1 |
| Start it on another port | `uv run arai local --port 8010` | 2.1 |
| Stop it | Ctrl+C; by port: the two lines in 2.1 (`Stop-Process`, then `pg_ctl.exe stop -D .\data\EXP-20261005-04\postgres -m fast`) | 2.1 |
| Start the baseline rehearsal (port 8011) | `uv run arai baseline-rehearsal` | 2.2 |
| Its options | `--port 8012`, `--demo-world W5401`, `--fresh` | 2.2 |
| Stop it | Ctrl+C; by port: the two lines in 2.2 (`Stop-Process`, then `pg_ctl.exe stop -D .\rehearsal\baseline\postgres -m fast`) | 2.2 |
| Both for a demonstration | terminal 1 `uv run arai baseline-rehearsal`, terminal 2 `uv run arai local` | 2.3 |
| Docker Compose up, status, logs | `docker compose up --build -d`; `docker compose ps`; `docker compose logs -f worker` | 3 |
| API and worker against your own PostgreSQL, without Docker | `uv run arai db-migrate`; `uv run arai serve`; `uv run arai worker` (with `DATABASE_URL`) | 3.1 |
| API and worker against Supabase Postgres (database `arai_local_db`) | `$env:DATABASE_URL` from `.env`, then the three commands of 3.1 | 3.2 |
| Docker Compose down, keep or drop the database | `docker compose down`; `docker compose down -v` | 3 |
| **Clean up** | | |
| Look before cleaning | `uv run arai db-clean --all --dry-run` | 2.4 |
| Remove notes, runs or datasets | `uv run arai db-clean --notes --yes`; `--runs --yes`; `--datasets --yes` | 2.4 |
| Everything demo state holds, all worlds or one | `uv run arai db-clean --all --yes`; `--all --world W5401 --yes` | 2.4 |
| The rehearsal's database | `uv run arai db-clean --instance rehearsal --all --yes` | 2.4 |
| Full reset of a stopped instance | `uv run arai db-clean --reset --yes`; `--instance rehearsal --reset --yes` | 2.4 |
| **Sign in** | | |
| Sign in on a laptop | the first page of http://127.0.0.1:8000: choose a person of the development login | 2.5 |
| Other people or roles | `$env:AUTH_DEV_USERS = "Asha=reviewer,approver;Kabir=reviewer;Admin=admin"` before `uv run arai local` | 2.5 |
| Sign in from a script or `curl.exe` | `curl.exe -c arai-cookies.txt -X POST .../api/v1/auth/dev-login` with `{"user":"Admin"}`, then the CSRF token on every POST | 2.5 |
| Sign in through Keycloak (single sign-on), rehearse it with the development Keycloak | `AUTH_MODE=oidc` and the `OIDC_*` settings; `docker compose --profile sso up -d keycloak` | 2.6 |
| See who has signed in, disable a person, end their sessions, read the sign-in log (admin) | **People & access** in the navigation | 2.7 |
| **Load data** | | |
| Register and score W5401 in the browser | Datasets & runs: choose the eight files, Validate and register, Score with the active bundle | 4 |
| The same from the terminal | the two `curl.exe` calls in section 4; or `uv run arai register data\EXP-20261005-04\artifacts\worlds\W5401\operational` | 4 |
| W5401 month by month for a year (the same customers on eleven earlier cutoffs) | `uv run arai snapshot W5401 --as-of 2025-10-09 2025-11-09 2025-12-09 2026-01-09 2026-02-09 2026-03-09 2026-04-09 2026-05-09 2026-06-09 2026-07-09 2026-08-09` | 4.1 |
| Only some months (any dates after 10 Sep 2025 and before 9 Sep 2026) | `uv run arai snapshot W5401 --as-of 2026-07-09 2026-08-09` | 4.1 |
| Register and score every snapshot on disk, then record the August review outcomes (instance up) | `uv run --no-sync python scripts\history_demo.py --load` | 4.1 |
| Only the August review outcomes | `uv run --no-sync python scripts\history_demo.py` | 4.1 |
| Validate a snapshot without registering it | `uv run arai validate <folder>` | 5 |
| Export the queue as CSV (any filters of the list; reviewers and above) | queue page **Export this view as CSV**, or `curl.exe -s -b arai-cookies.txt -o queue.csv "http://127.0.0.1:8000/api/v1/runs/<run_id>/customers/export?review_only=true"` after signing in (2.5) | 5 |
| **Check** | | |
| Health of an instance | `curl.exe -s http://127.0.0.1:8000/api/v1/health` (8011 for the rehearsal) | 5 |
| Latest run | `curl.exe -s http://127.0.0.1:8000/api/v1/runs` | 5 |
| Python tests | `uv run --no-sync pytest -q` | 5 |
| Front-end tests and type check | `cd web; npm test; npx tsc --noEmit; cd ..` | 5 |
| Python lint | `uvx ruff@0.16.8 check src tests scripts` | 5 |
| Browser walkthrough (instance up, run scored) | `uv run --no-sync python tests\e2e\walkthrough.py` | 5 |
| Baseline-fallback check (port 8011 free) | `uv run --no-sync python tests\e2e\fallback_check.py` | 5 |
| Specification package | `uv run --no-sync python final-spec\tools\verify_package.py`; after edits `uv run --no-sync python scripts\spec_package.py` | 5 |
| Wireframe opens offline (acceptance OPS-AC-02) | `uv run --no-sync python tests\e2e\wireframe_offline_check.py` | 5 |
| Re-check experiment 4 against its records (read-only, about half a minute) | `uv run --no-sync python scripts\verify_experiment.py` | 7 |
| Linked-account communities on generated worlds (offline diagnostics) | `uv run --no-sync python scripts\community_check.py --seed 5101 5102`; `uv run --no-sync python scripts\community_rule_check.py --world W5201 W5202 W5203 W5204 W5205 W5401` | 7 |
| Package the synthetic data with its truth and guide for sharing | `uv run --no-sync python scripts\package_experiment_data.py --experiment EXP-20261005-04 --guide docs\experiment-4-data-guide.md` | 7 |
| Re-publish the bundles after a code change the run warns about | `uv run --no-sync arai publish --demo-world W5401`, then restart | 6 |

On macOS or Linux the same commands work with forward slashes, `curl` for `curl.exe`, and the `pg_ctl` binary under
`.venv/lib/python3.12/site-packages/pgserver/pginstall/bin/pg_ctl`.

---

There are three ways to bring the application up. The **local** instance and the **baseline rehearsal** are meant
to run together for a demonstration; the Docker Compose stack is the reference runtime and must not run beside the
local instance, because the two would share the `data\EXP-20261005-04\artifacts` folder.

| | Local (the product, recommended for the demo) | Baseline rehearsal (the return-rate rule only) | Docker Compose (reference runtime) |
|---|---|---|---|
| Command | `uv run arai local` | `uv run arai baseline-rehearsal` | `docker compose up --build -d` |
| Needs | uv, Node (only to build the UI once), the experiment artifacts | the same, plus the fixture in `rehearsal\baseline` (in git) | Docker Desktop running |
| Address | http://127.0.0.1:8000 | http://127.0.0.1:8011 | http://localhost:8080 |
| Database | embedded PostgreSQL in `data\EXP-20261005-04\postgres` | embedded PostgreSQL in `rehearsal\baseline\postgres` | `postgres:16` container, volume `pgdata_exp_20261005_04` |
| Artifacts | `data\EXP-20261005-04\artifacts` | `rehearsal\baseline\artifacts` | `data\EXP-20261005-04\artifacts` (mounted) |
| Keeps datasets, runs and notes between restarts | yes | yes | yes, until `down -v` |
| Can run beside | the baseline rehearsal | the local instance | nothing else |

---

## 1. First-time setup (once per machine)

### 1.1 Tools and the Python environment

| Tool | Version this was built and checked with | Pinned in |
|---|---|---|
| uv | 0.11 | (install it once: https://docs.astral.sh/uv/) |
| Python | 3.12, installed by uv | `.python-version`, `pyproject.toml`; every library in `uv.lock` |
| Node.js and npm | Node 22, npm 10 | `web/.nvmrc`; every package in `web/package-lock.json` |
| PostgreSQL | 16 (embedded by `arai local` through pgserver; the `postgres:16` image under Docker) | `uv.lock`, `docker-compose.yml` |
| Keycloak (optional) | 26.0 | `docker-compose.yml`, realm in `deploy/keycloak/arai-realm.json` |

```powershell
uv sync                      # creates .venv from uv.lock (Python 3.12 and every dependency, pinned)
```

What is not in git, and how each is rebuilt: `.venv` (`uv sync`), `web/node_modules` and `web/dist` (`npm install`,
`npm run build`), `data/` (the generator, section 1.3, from seeds and the tracked configuration in `final-spec/`), the
rehearsal's database and registered datasets (rebuilt on its first start), and `.env` (copy `.env.example`; every
setting the code reads is listed there with its default). `code/synthetic-data/` is a teammate's separate repository;
nothing here reads it.

### 1.2 Build the UI

```powershell
cd web
npm install
npm run build                # builds the UI into web\dist; both local instances serve it from there
cd ..
```

Rebuild the UI (`npm run build`) only after changing something under `web\`. Without `web\dist` the instances
start as API only and say so.

While changing the UI, a development server reloads on every save and forwards `/api` to the instance on port 8000
(`$env:ARAI_API = "http://127.0.0.1:8010"` first to use another one):

```powershell
cd web
npm run dev                  # http://127.0.0.1:5173; Ctrl+C stops it
npm run api-types            # after a change to final-spec\contracts\openapi.yaml: regenerates src\api-types.ts
cd ..
```

### 1.3 The experiment artifacts

Both local instances read the experiment's artifacts from `data\EXP-20261005-04\artifacts`: the worlds (the
demonstration world W5401 among them), the model and baseline bundles, and the published experiment report. They
are not in git. On this machine they already exist. On a fresh clone, either copy the `data` folder across or
reproduce it from the seeds with the offline pipeline in `README.md` (about 40 minutes; it reproduces the selected
model and the final test exactly, with new bundle ids).

To generate the synthetic data and reproduce the experiment on a fresh clone, run these in order (a
10,000-customer world takes about 15 seconds; the whole sequence about 40 minutes). The order is enforced:
training and the dry run refuse to run once validation worlds exist, selection needs the dry run, and the test
runs once.

```powershell
uv run arai generate --seed 5101 5102 5103 5104 5105 5106 5107 5108 5109 5110 5501 5502 5503 5504 5505 5506 5507 5508 5509 5510 5511   # training and stress worlds
uv run arai train                     # freeze features, fit nine candidates and two references
uv run arai dry-run                   # gate dry run and calibration check, before any validation world
uv run arai ablation                  # what the result depends on (training worlds; can run at any point)
uv run arai stress                    # the frozen models on the stress worlds; diagnostic
uv run arai generate --seed 5201 5202 5203 5204 5205   # validation worlds
uv run arai select                    # apply the gate, freeze the selection
uv run arai generate --seed 5301 5302 5303 5304 5305   # test worlds
uv run arai test                      # the final test: runs once
uv run arai generate --seed 5401      # demonstration world W5401
uv run arai publish --demo-world W5401   # bundles, active pointer, published experiment report
```

Every command uses the experiment named in `final-spec\contracts\experiment.yaml` and its data folder. A world's
seed and the commit reproduce it byte for byte. One more world for your own exploration takes a seed no experiment
has used (the command refuses the seeds of earlier experiments). A seed outside the contract gives 1,000 customers;
`--customers 10000` gives the full size and names the world with it (`W9001N10000`):

```powershell
uv run arai generate --seed 9001                         # about 3 seconds; writes data\EXP-20261005-04\artifacts\worlds\W9001
uv run arai validate data\EXP-20261005-04\artifacts\worlds\W9001\operational   # "violations": [] and exit code 0, or nonzero if rejected
uv run arai generate --seed 9001 --customers 10000       # the same simulator at full size, as W9001N10000
```

Register it like any snapshot (section 4) to see it in the workbench.

The earlier monthly snapshots of W5401 used by the history screens are written by `arai snapshot` (section 4.1).

Check that they are there:

```powershell
Get-ChildItem data\EXP-20261005-04\artifacts                      # active, bundles, experiments, worlds (and datasets once registered)
Get-ChildItem data\EXP-20261005-04\artifacts\worlds\W5401\operational   # manifest.json and seven .csv files
```

### 1.4 The baseline rehearsal fixture

`rehearsal\baseline\artifacts` is in git: the baseline bundle, the published report rewritten as if no candidate
had passed the gate, and the active pointer (its README explains each file). Nothing to do on a clone. If the
experiment's bundles were regenerated on this machine (the pipeline in `README.md` gives new bundle ids), rebuild
the fixture once so it carries the current baseline bundle, and commit the result:

```powershell
uv run arai baseline-rehearsal --fresh      # rebuilds the fixture and starts the instance; Ctrl+C once it says the run succeeded
git status rehearsal\baseline                # commit the changed fixture if bundles/, experiments/ or active/ changed
```

`--fresh` also empties the rehearsal's own database and registered snapshot (section 2.4); it never touches
`data\`.

---

## 2. Local: start, stop, restart

### 2.1 The product instance (port 8000)

**Start**

```powershell
uv run arai local
```

It prints `ARAI local rehearsal on http://127.0.0.1:8000` and is ready in about 10 seconds. Leave the terminal
open: the server runs until you stop it. This one process is the database, the API, the scoring worker and the
UI. To use another port: `uv run arai local --port 8010`.

On an empty database (first start on a machine, or after a clean-up in section 2.4) register and score the demonstration world
once (section 4). Afterwards the Overview shows 5,676 eligible customers and 284 selected for world W5401.

**Stop**

Press **Ctrl+C** in the terminal where it is running. That also stops the embedded PostgreSQL.

If the terminal is gone, or the server was started in the background, stop it by port and then stop the database
it left behind:

```powershell
# 1. stop the server listening on port 8000
$c = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($c) { Stop-Process -Id $c.OwningProcess -Force }

# 2. stop the embedded PostgreSQL if it is still running
.\.venv\Lib\site-packages\pgserver\pginstall\bin\pg_ctl.exe stop -D .\data\EXP-20261005-04\postgres -m fast
```

`pg_ctl` answers `server stopped`, or says no server is running, which is also fine.

**Restart**

Stop, then start. Runs, their results and review notes are kept in the database (`data\EXP-20261005-04\postgres`);
registered snapshots and model bundles are kept as files in `data\EXP-20261005-04\artifacts`.

If a scoring run was in progress when the server stopped, it shows as **interrupted** after the restart and
publishes nothing. Use **Retry** on the Datasets & runs page. A run you cancelled yourself shows as **cancelled**
and offers no retry.

### 2.2 The baseline rehearsal instance (port 8011)

A second instance that serves the return-rate rule only, the way the product behaves when no model has passed the
gate: the banner says so, the score column becomes a return-rate percentile, and the comparison views disappear.
It is the demo's optional cold open (`docs\demo-script.md`, section 1d) and can run beside the product instance.

**Start**

```powershell
uv run arai baseline-rehearsal
```

It prints `ARAI baseline rehearsal (return-rate rule only) on http://127.0.0.1:8011`. On the first start on a
machine it registers W5401 (read from `data\EXP-20261005-04\artifacts\worlds`, like the product instance) and scores
it with the rule, about 20 seconds; the log then says `scoring W5401 with the return-rate rule`. Later starts say
`W5401 is already scored here` and are ready at once. Nothing is shared with the product instance: the fixture is
`rehearsal\baseline\artifacts`, the database `rehearsal\baseline\postgres`.

Options: `--port 8012` for another port, `--demo-world W5401` for another world from the artifacts, `--fresh` to
rebuild the fixture from the current bundles and start with an empty database.

**Check**

```powershell
curl.exe -s http://127.0.0.1:8011/api/v1/health
# {"alive":true,"scoring_ready":true,"promoted_model_ready":false,"model_kind":"baseline_fallback", ...}
curl.exe -s http://127.0.0.1:8011/api/v1/runs       # the latest run should be "succeeded" with "model_kind":"baseline_fallback"
```

Then open http://127.0.0.1:8011: the banner reads that no candidate passed the validation gate and the return-rate
ranking is active, and the queue shows 284 names ranked by a return-rate percentile.

**Stop**

Press **Ctrl+C** in its terminal. By port, if the terminal is gone:

```powershell
$c = Get-NetTCPConnection -LocalPort 8011 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($c) { Stop-Process -Id $c.OwningProcess -Force }
.\.venv\Lib\site-packages\pgserver\pginstall\bin\pg_ctl.exe stop -D .\rehearsal\baseline\postgres -m fast
```

### 2.3 Running both for a demonstration

Two terminals, in this order:

```powershell
# terminal 1
uv run arai baseline-rehearsal          # wait for "W5401 is already scored here" or for the run to succeed

# terminal 2
uv run arai local                       # wait for the health line in section 5
```

Open http://127.0.0.1:8011 in one browser tab and http://127.0.0.1:8000 in another. The demo script starts on the
8011 tab (cold open, ninety seconds) and switches to 8000 for the rest. Sign in on the 8000 tab (development login,
section 2.5) before the audience arrives. Stop both with Ctrl+C in each terminal; the order does not matter.

If only one terminal is available, start the rehearsal in the background and the product in the foreground; stop
the rehearsal by port afterwards (section 2.2):

```powershell
Start-Process -NoNewWindow uv -ArgumentList "run arai baseline-rehearsal"
uv run arai local
```

### 2.4 Clean the demo database

`arai db-clean` removes demo state from either embedded database and leaves the models, the active pointer and the
experiment report alone. It does nothing without `--yes`; with `--dry-run` (or without `--yes`) it only reports what
it would remove. It may run while the instance is up: the pages show the change on their next load.

```powershell
uv run arai db-clean --notes --dry-run                 # what the product instance holds, and what --notes would remove
uv run arai db-clean --notes --yes                     # remove every review note (the walkthrough's notes among them)
uv run arai db-clean --runs --yes                      # remove runs with their results and memos, and the notes written under them
uv run arai db-clean --datasets --yes                  # remove registered datasets no run refers to, with their files
uv run arai db-clean --all --yes                       # notes, runs and datasets: the product instance as on first start
uv run arai db-clean --all --world W5401 --yes         # the same, for one world only
uv run arai db-clean --instance rehearsal --runs --yes # the baseline rehearsal's database instead (it re-scores on its next start)
```

After `--runs` or `--all` on the product instance, register and score the demonstration world again (section 4); the
rehearsal does that by itself on start.

**Full reset** (the database folder and the registered snapshots are deleted; the instance must be stopped):

```powershell
uv run arai db-clean --reset --yes                      # product instance: data\EXP-20261005-04\postgres and ...\artifacts\datasets
uv run arai db-clean --instance rehearsal --reset --yes # rehearsal: rehearsal\baseline\postgres and ...\artifacts\datasets
uv run arai baseline-rehearsal --fresh                  # rehearsal reset plus a rebuilt fixture, in one step
```

The next start rebuilds an empty database. Nothing under `data\EXP-20261005-04\artifacts` except `datasets` is
touched by any of these: bundles, worlds and the experiment report stay.

### 2.5 Signing in (development login)

Since API contract 1.16.0 (decision AM-69, `docs/design/authentication-and-roles.md`) every page and API call needs a
signed-in person; only `/api/v1/health` stays open. On a laptop the instance uses the **development login**: the
first page lists the people below, and choosing one signs in. Every note and decision is recorded under that person,
and the second-reviewer rule compares people, not typed names.

| Person | Roles | May |
|---|---|---|
| Asha, Ravi, Meera | reviewer, approver | read, export, write notes, open cases, request approval, approve or reject cases they did not open |
| Arjun | reviewer | read, export, write notes, open cases, request approval |
| Priya | viewer | read every screen |
| Admin | admin | read, export, register and delete snapshots, start and cancel runs (no reviewing) |

- **Session:** signed out after 60 minutes without a request, and after 10 hours in any case; **Sign out** is at the top
  right. Change with `SESSION_IDLE_MINUTES` and `SESSION_MAX_HOURS`.
- **Other people or roles:** `AUTH_DEV_USERS="Asha=reviewer,approver;Kabir=reviewer;Admin=admin"` before `uv run arai local`.
- **Shared deployments** (`APP_PROFILE=vm`) refuse the development login and use Keycloak single sign-on
  (`AUTH_MODE=oidc`, section 2.6).
- **Scripts and `curl.exe`** sign in through the same login and send the session's CSRF token on every POST and DELETE:

```powershell
$me = curl.exe -s -c arai-cookies.txt -X POST http://127.0.0.1:8000/api/v1/auth/dev-login -H "content-type: application/json" `
  -d '{\"user\":\"Admin\"}' | ConvertFrom-Json
curl.exe -s -b arai-cookies.txt http://127.0.0.1:8000/api/v1/me                         # who is signed in
# every POST and DELETE: -b arai-cookies.txt -H "X-CSRF-Token: $($me.csrf_token)"
```

Reviews written before sign-in existed keep their typed name and show **unverified name**; nothing is rewritten.

### 2.6 Single sign-on with Keycloak

Since API contract 1.17.0 (decision AM-70) ARAI signs people in through Keycloak when `AUTH_MODE=oidc` (the default on
the vm profile). The server does the whole sign-in: the browser is sent to Keycloak, comes back with a one-time code,
and the server exchanges it for an ID token, checks that token against the realm's published keys, and gives the
browser ARAI's own session cookie (the same session as section 2.5: 60 minutes idle, 10 hours at most). Roles come
from the person's **Keycloak groups**, read again at every sign-in:

| Keycloak group | ARAI role |
|---|---|
| `arai-viewers` | viewer |
| `arai-reviewers` | reviewer |
| `arai-approvers` | approver |
| `arai-admins` | admin |

Someone in none of these groups is refused with a message saying so. `ARAI_BOOTSTRAP_ADMINS=you@example.org` makes the
listed e-mail addresses admin before any group exists.

**Settings** (environment variables, also in `.env.example`):

| Variable | Example | Meaning |
|---|---|---|
| `AUTH_MODE` | `oidc` | single sign-on (empty: dev on local, oidc on vm) |
| `OIDC_ISSUER` | `https://keycloak.example.org/realms/arai` | the realm; must be https unless `OIDC_ALLOW_HTTP=1` |
| `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` | `arai`, (from Keycloak) | the confidential client ARAI signs in with |
| `OIDC_REDIRECT_URI` | `https://arai.example.org/api/v1/auth/callback` | registered on the client in Keycloak |
| `AUTH_ROLE_MAP` | `arai-viewers=viewer,...` | group to role, the table above by default |
| `AUTH_ROLE_CLAIM` | `groups` | the token claim holding the groups |
| `OIDC_API_AUDIENCE` | `arai-api` | the audience a script's bearer token must carry |
| `ARAI_BOOTSTRAP_ADMINS` | `you@example.org` | admin without a group |

The instance refuses to start in `oidc` mode when the issuer, client id, client secret or redirect address is missing.

**Setting up Keycloak:** a realm `arai`; a confidential OpenID Connect client `arai` with standard flow, PKCE method
S256 and the redirect address above; a *Group Membership* mapper on the client with token claim name `groups` and
"Full group path" off; an *Audience* mapper adding `arai-api` to access tokens; the four groups. Multi-factor
authentication, password rules and lockout are Keycloak's realm settings. `deploy/keycloak/arai-realm.json` is a
complete example of this realm.

**Rehearsing on a laptop with the development Keycloak.** The Compose profile `sso` starts Keycloak 26 on
http://127.0.0.1:8081 with that realm: six people with the same roles as section 2.5 (`asha`, `ravi`, `meera`,
`arjun`, `priya`, `admin`; password `arai-dev` for all) and the client secret `arai-dev-secret`. These credentials
are for this local rehearsal only. Needs Docker and `POSTGRES_PASSWORD` set in `.env` (Compose reads it for every
service); only Keycloak is started.

```powershell
docker compose --profile sso up -d keycloak       # first start takes about a minute; http://127.0.0.1:8081
$env:AUTH_MODE = "oidc"; $env:OIDC_ISSUER = "http://127.0.0.1:8081/realms/arai"; $env:OIDC_ALLOW_HTTP = "1"
$env:OIDC_CLIENT_ID = "arai"; $env:OIDC_CLIENT_SECRET = "arai-dev-secret"
$env:OIDC_REDIRECT_URI = "http://127.0.0.1:8000/api/v1/auth/callback"
uv run arai local                                  # open http://127.0.0.1:8000 and choose "Sign in with Keycloak"
docker compose --profile sso down                  # afterwards; the realm is imported afresh at the next start
```

Open ARAI at `127.0.0.1:8000` (not `localhost`), so the address matches the redirect address. **Sign out** ends the
ARAI session and the Keycloak session, then returns to the sign-in page.

**Scripts** send a Keycloak access token instead of a cookie; no CSRF token is needed. The token must be meant for
`arai-api` and the person must be in an ARAI group. With the development realm (its client allows the password grant
for scripts; a company realm would use a service account or a device sign-in instead):

```powershell
$t = (curl.exe -s -X POST http://127.0.0.1:8081/realms/arai/protocol/openid-connect/token `
  -d grant_type=password -d client_id=arai -d client_secret=arai-dev-secret -d username=admin -d password=arai-dev `
  -d scope=openid | ConvertFrom-Json).access_token
curl.exe -s -H "Authorization: Bearer $t" http://127.0.0.1:8000/api/v1/me
```

Behind the vm profile's shared login a bearer request passes the shared login and is checked by ARAI itself.

### 2.7 People & access (admins)

Since API contract 2.0.0 (decision AM-71) an admin sees **People & access** in the navigation (sign in as Admin on a
laptop). It lists everyone who has signed in, each role with where it comes from (Keycloak group, bootstrap admin or
the development list), status, last sign-in, last activity and open sessions. **Roles are not edited here**: they come
from Keycloak groups (or `AUTH_DEV_USERS` on a laptop) and are read at every sign-in.

| Action | What it does |
|---|---|
| **Disable** | Ends every session of the person now, stops their bearer tokens and refuses their next sign-in. Use it when someone leaves or a laptop is lost. An admin cannot disable themselves. |
| **Enable** | Lets a disabled person sign in again; the sessions ended by the disable stay ended. |
| **End sessions** | Signs the person out everywhere now; they may sign in again, with their roles read afresh. Use it after changing someone's Keycloak groups so the change applies at once. |

Each action asks first and takes an optional reason. Below the list is the **sign-in log**: sign-ins, sign-outs,
ended sessions, refused requests, exports, role changes and these admin actions, newest first, filtered by kind and
person. The same is available to scripts as `GET /api/v1/admin/users` and `GET /api/v1/admin/auth-events`.

Contract 2.0.0 also removed two typed-name fields that 1.16.0 already ignored: a review that still sends
`reviewer_name`, or a queue request with `exclude_reviewer`, now gets a 422 that names the field (use the signed-in
session, and `exclude_mine=true`).

---

## 3. Docker Compose: start, stop

Stop the local server first (section 2.1); the baseline rehearsal may keep running, it shares nothing with Compose.

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

### 3.1 API and worker against your own PostgreSQL (no Docker)

For a server with PostgreSQL already installed. `arai local` does all of this in one process with an embedded
database; these commands keep the parts separate, as the Compose stack does. Set the environment first (the full
list is in `.env.example`):

```powershell
$env:DATABASE_URL = "postgresql://arai:<password>@127.0.0.1:5432/arai"
$env:ARTIFACT_ROOT = "data\EXP-20261005-04\artifacts"    # the default already
uv run arai db-migrate                  # applies the schema; "applied: nothing new" when it is current
uv run arai serve --port 8000           # the API only (terminal 1); --with-worker also runs the worker in it
uv run arai worker                      # the single scoring worker (terminal 2)
```

`arai serve` serves the API, not the UI: put `web\dist` behind a web server that forwards `/api` (as
`deploy\nginx.conf` does), or use `npm run dev` (section 1.2). On a shared server set `APP_PROFILE=vm`, the
`BASIC_AUTH_*` settings and single sign-on (section 2.6).

### 3.2 API and worker against Supabase Postgres (no Docker)

Section 3.1 with the database on Supabase instead of a server of your own. ARAI gets a database of its own on the
project, `arai_local_db`, so it never touches the project's `postgres` database or the tables other applications
keep there. The `postgres` role of a Supabase project may create databases. Done once on 18 October 2026 for
project `ndrkejdmaiisdtttsdky`; a new project needs steps 1 and 2 again.

Supabase offers two connection strings (Dashboard, Project Settings, Database). Use the **direct** one,
`db.<project-ref>.supabase.co:5432`: the **pooler** (`*.pooler.supabase.com`) only serves the `postgres`
database, not `arai_local_db`. The direct host resolves to an IPv6 address only; from a network without IPv6
(an AWS VM by default) enable the project's IPv4 add-on, or keep ARAI's tables in the `postgres` database and
use the pooler.

```powershell
# 1. once per project: create the database (no psql needed; the environment has psycopg)
$env:DATABASE_URL = "postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres?sslmode=require"
uv run python -c "import os,psycopg; c=psycopg.connect(os.environ['DATABASE_URL'], autocommit=True); c.execute('create database arai_local_db'); print('created')"

# 2. once per machine: put the string in .env (gitignored; never commit it), pointing at the new database.
#    URL-encode special characters in the password: $ is %24, @ is %40, # is %23, ! may stay.
#    DATABASE_URL=postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/arai_local_db?sslmode=require

# 3. every terminal: the commands read the environment, not .env, so export it first
$env:DATABASE_URL = (Get-Content .env | Where-Object { $_ -like 'DATABASE_URL=*' }) -replace '^DATABASE_URL=', ''

# 4. as in 3.1
uv run arai db-migrate                  # first time: applied: ['0001_initial', ... '0013_single_sign_on']; later: nothing new
uv run arai serve --port 8000           # terminal 1; --with-worker also runs the worker in it
uv run arai worker                      # terminal 2
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health   # alive, scoring_ready and promoted_model_ready: True
```

Stop with Ctrl+C in each terminal; there is no embedded PostgreSQL to stop. If a terminal is gone, stop the server
by port with the first two lines of section 2.1 and skip the `pg_ctl` line. Runs, results and notes live on
Supabase; `arai db-clean` works against it through the same `DATABASE_URL`.

---

## 4. Load and score the demonstration world

Only needed on an empty database of the product instance; the baseline rehearsal registers and scores the world by itself.

**In the browser:** open **Datasets & runs**, choose the eight files in
`data\EXP-20261005-04\artifacts\worlds\W5401\operational` (`manifest.json` and the seven `.csv` files), press
**Validate and register**, then **Score with the active bundle**. Scoring 10,000 customers takes about 12
seconds; the page updates by itself.

**From the terminal** (same thing through the API, signed in as Admin as in section 2.5; change the port to 8080 for
Docker):

```powershell
$me = curl.exe -s -c arai-cookies.txt -X POST http://127.0.0.1:8000/api/v1/auth/dev-login -H "content-type: application/json" `
  -d '{\"user\":\"Admin\"}' | ConvertFrom-Json
$d = "data\EXP-20261005-04\artifacts\worlds\W5401\operational"
curl.exe -s -b arai-cookies.txt -H "X-CSRF-Token: $($me.csrf_token)" -X POST http://127.0.0.1:8000/api/v1/datasets `
  -F "manifest=<$d\manifest.json" `
  -F "customer_master=@$d\customer_master.csv" -F "sku_master=@$d\sku_master.csv" `
  -F "reason_code=@$d\reason_code.csv" -F "sales_order=@$d\sales_order.csv" `
  -F "sales_order_line=@$d\sales_order_line.csv" -F "return_order=@$d\return_order.csv" `
  -F "return_order_line=@$d\return_order_line.csv"

# use the dataset_id from the answer; the key can be any text you have not used for this dataset before
curl.exe -s -b arai-cookies.txt -H "X-CSRF-Token: $($me.csrf_token)" -X POST http://127.0.0.1:8000/api/v1/runs -H "content-type: application/json" `
  -d '{\"dataset_id\":\"ds-27bd9b52167d935eaf7a\",\"idempotency_key\":\"demo-1\"}'
```

### 4.1 Earlier monthly snapshots of W5401 (customer history)

A world is one population of customers; each upload of it is a **snapshot** at its cutoff, and a customer keeps the
same identifier in every snapshot (decision AM-68). Registering W5401 again with another cutoff therefore adds a
snapshot of the same world instead of being refused, and the queue, the case and the Overview show each customer's
history across the snapshots. Different worlds are never linked.

**On a laptop, from this branch** (everything below is regenerated, nothing is copied from another machine; rehearsed
on an empty database: same numbers, about two minutes):

```powershell
# 0. the branch, its environment and its UI (see "Start here" at the top)
git fetch origin; git checkout year-of-snapshots; git pull
uv sync
cd web; npm install; npm run build; cd ..

# 1. write W5401 as it stood on the 9th of each month from October 2025 to August 2026 (10 to 18 seconds each). Needs
#    W5401 itself on disk (data\EXP-20261005-04\artifacts\worlds\W5401, as section 1.3 generates it). The command
#    replays the generator for seed 5401, so nothing is copied; it checks each snapshot is a prefix of your W5401,
#    and stops (removing that snapshot) if it is not. Rerunning it changes nothing that is already right.
uv run arai snapshot W5401 --as-of 2025-10-09 2025-11-09 2025-12-09 2026-01-09 2026-02-09 2026-03-09 2026-04-09 2026-05-09 2026-06-09 2026-07-09 2026-08-09

# 2. start the instance (terminal 1); the database moves to schema version 11 by itself on the first start
uv run arai local

# 3. in terminal 2: register and score every snapshot of W5401 on disk (the ones already registered or scored are
#    skipped; about a minute each), then record the three August review outcomes. Safe to run again.
uv run --no-sync python scripts\history_demo.py --load
```

The last line it prints must read `Since the previous snapshot (2026-08-09): 249 in both queues, 35 new, 22 left,
2 decided before`. To confirm that your snapshot files are byte for byte the ones this branch was built with, compare
two hashes (every file of every month is in `records/2026-10-16-monthly-snapshots.md`):

```powershell
Get-FileHash data\EXP-20261005-04\artifacts\worlds\W5401.as-of-2026-07-09\operational\customer_master.csv   # BD1D31D933D73B34...
Get-FileHash data\EXP-20261005-04\artifacts\worlds\W5401.as-of-2026-08-09\operational\customer_master.csv   # 372D98CD2CAF3E63...
```

Step 3 by hand instead: register and score each folder as in section 4 (browser or `curl.exe`), using
`worlds\W5401.as-of-2026-07-09\operational` and `worlds\W5401.as-of-2026-08-09\operational`, then run
`uv run --no-sync python scripts\history_demo.py` without `--load`.

The order does not matter: the workspace always opens on the newest run of the latest snapshot (9 September).
Expected, month by month (customers in the snapshot / eligible, that is ranked / selected for review):

| 9 Oct 25 | 9 Nov | 9 Dec | 9 Jan 26 | 9 Feb | 9 Mar | 9 Apr | 9 May | 9 Jun | 9 Jul | 9 Aug | 9 Sep |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 6,210 / 0 / 0 | 6,585 / 621 / 32 | 6,953 / 2,467 / 124 | 7,319 / 3,210 / 161 | 7,709 / 3,670 / 184 | 8,067 / 3,955 / 198 | 8,447 / 4,272 / 214 | 8,802 / 4,555 / 228 | 9,152 / 4,840 / 242 | 9,502 / 5,119 / 256 | 9,791 / 5,408 / 271 | 10,000 / 5,676 / 284 |

In October nobody is ranked yet: after one month of history no customer has the three mature sale lines the model
needs, and the queue says so. The case's History tab lists every month. On the September Overview a panel **Since the
previous snapshot of W5401 (09 Aug 2026)** reading 249 also in the previous queue, 35 new, 22 left, 2 decided on an
earlier snapshot. The review workflow runs per snapshot: a case decided in August is a new case in September, with
the August decision shown on it. `db-clean --all --world W5401` removes every snapshot's runs and notes together.

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

Then open http://127.0.0.1:8000, sign in (section 2.5, for example as Ravi): the Overview should show 5,676 eligible customers and 284 selected for world
W5401 (the 9 September snapshot), and with the snapshots of section 4.1 the panel comparing it with 9 August.

### Full check before a demonstration

Run these in order. Each line says what a good result looks like.

```powershell
# 1. Python tests. They start their own temporary PostgreSQL; the running server is not touched.
uv run --no-sync pytest -q                          # "237 passed" in about 10 minutes

# 2. Front-end tests and type check
cd web; npm test; npx tsc --noEmit; cd ..            # "30 passed"; tsc prints nothing

#    Python lint (rules in pyproject.toml; the version is pinned here because each ruff release changes its default rules)
uvx ruff@0.16.8 check src tests scripts              # "All checks passed!"

# 3. Browser walkthrough of the running application (needs the server up with W5401 and its snapshots of section 4.1
#    scored; uses Edge, headless; it signs in as Admin, Ravi and Arjun through the development login)
uv run --no-sync python tests\e2e\walkthrough.py     # "71 of 71 checks passed"

# 4. Baseline-fallback check (starts its own temporary instance on port 8011: stop the baseline rehearsal first)
uv run --no-sync python tests\e2e\fallback_check.py  # "11 of 11 checks passed"

# 5. The demonstration VM's sign-in path (AM-74): starts its own API on port 8010 against DATABASE_URL (or the .env line)
#    on the vm profile with the development login, and walks through the shared login, the personas and the refusals
uv run --no-sync python tests\e2e\vm_devlogin_check.py  # "14 of 14 checks passed"
```

Use `uv run --no-sync` while the server is running: plain `uv run` may try to refresh the environment and fail
with "file is being used by another process".

The walkthrough writes one review note on the top-ranked customer each time it runs (as Ravi), and stages the
second-reviewer refusal on the first case still marked New, which it opens as Ravi; so each run leaves one more case in
review. Notes are append only, so they accumulate; that is expected. The fallback check
scores W2001 where that world exists and W5401 otherwise (or the world named on its command line).

Screenshots and results from steps 3 to 5 are written to `reports\ui\<today's date>\`.

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
| "port 8000 already in use" / address in use | a server is still running | stop it by port (section 2.1) |
| "port 8011 already in use" | a baseline rehearsal or the fallback check is still running | stop it by port (section 2.2), or start with `--port 8012` |
| The rehearsal says `model_not_ready` or the health shows `scoring_ready: false` on port 8011 | the fixture names a bundle that is not in `rehearsal\baseline\artifacts\bundles` | `uv run arai baseline-rehearsal --fresh`, then commit the rebuilt fixture |
| The rehearsal starts but its log shows no `scoring W5401` line and the queue stays empty | `data\EXP-20261005-04\artifacts\worlds\W5401` is missing, so the world could not be registered | restore the artifacts (section 1.3), then start again |
| "file is being used by another process" from `uv run` | the server holds the environment | add `--no-sync`, or stop the server first |
| UI opens but says the API cannot be reached | server stopped | start it (section 2.1 or 2.2) |
| A run shows **failed / output_missing** | it was scored by an earlier version and its result files were deleted before they were loaded into the database | press **Retry**; it creates a new run with the same dataset and model |
| A run shows **interrupted** | the server stopped while scoring | press **Retry** |
| A run carries a warning that scores or inputs are outside training | the snapshot differs from the training worlds | expected for unusual data; treat percentiles and the review list with caution |
| A run warns that the scoring code differs from the published bundle | code changed after `arai publish` | `uv run --no-sync arai publish --demo-world W5401`, restart, score again |
| `arai publish` says the feature code no longer reproduces the training features | `features.py` changed in a way that changes values | restore the code, or train a new experiment on fresh seeds |
| Banner: baseline only, on port 8000 | no promoted model is active | `uv run --no-sync arai publish --demo-world W5401`, then restart (on port 8011 the banner is the point) |
| Evaluation page is empty after `arai publish` | the report is loaded into the database when the worker starts | restart (local), or `docker compose restart worker` |
| `web/dist is missing` at start | UI not built | `cd web; npm install; npm run build` |
| Docker: `POSTGRES_PASSWORD is missing a value` | no `.env` | copy `.env.example` to `.env` and set it |
| `DATABASE_URL is not set` from `arai db-migrate`, `serve` or `worker` | the commands read the environment, not `.env` | export it first (section 3.2, step 3) |
| Supabase: `could not translate host name` or a connection timeout to `db.<project-ref>.supabase.co` | the direct host is IPv6 only and this network has no IPv6 | the IPv4 add-on, or the pooler with the `postgres` database (section 3.2) |
| Walkthrough or fallback check fails on "msedge" | Microsoft Edge not installed | install Edge, or set `ARAI_BROWSER` to a Chromium executable (both scripts read it) |

Server logs are in the terminal where `arai local` or `arai baseline-rehearsal` runs (or `docker compose logs api worker`). Every error the
API returns carries a `request_id`; search the log for it.

---

## 7. Offline checks and sharing the synthetic data

None of these needs a running instance; each reads the experiment's data folder and changes nothing in it.

```powershell
# Re-check experiment 4 against its records: hashes, seeds, the order of events, the final test re-scored
# (docs\experiment-4-verification-guide.md says what each check means)
uv run --no-sync python scripts\verify_experiment.py                  # every check, about half a minute
uv run --no-sync python scripts\verify_experiment.py --no-recompute   # without re-scoring the test worlds

# Linked-account communities (rings and households) on generated worlds: the community-kind checks of
# records\2026-10-15-community-kind-check.md and records\2026-10-16-community-kind-rule-revision.md
uv run --no-sync python scripts\community_check.py --seed 5101 5102
uv run --no-sync python scripts\community_rule_check.py --world W5201 W5202 W5203 W5204 W5205 W5401

# Package the synthetic data, its truth, its configuration and the guide as zip archives under
# data\exports\<experiment>\ (not in git), after checking every file against the hashes recorded at generation
uv run --no-sync python scripts\package_experiment_data.py --experiment EXP-20261005-04 --guide docs\experiment-4-data-guide.md
```

The exploration scripts of experiment 4 (`scripts\exploration\`) are explained, with their commands, in
`docs\experiment-4-verification-guide.md`.

## 8. AWS demonstration VM (Phase 4)

Design and decisions: `docs/design/aws-deployment.md` (section 2.9 is the variant that is built; decision row AM-72).
Account 819717422656, region ap-south-1, worked from the IAM user `arai-admin` through `aws login` (never root).
Claude Code runs the same steps through the AWS MCP tools; the commands are here so a person can do it by hand.

### 8.1 What exists

| Piece | Where | Made by |
|---|---|---|
| EC2 instance `arai-demo` (t3.small: the Free plan allows only Free Tier eligible types; Ubuntu 24.04, 16 GB root, 30 GB `/data` volume, no SSH, SSM only; always on until mid January 2027, then stopped between sessions) | CloudFormation stack `arai-demo` | `deploy/aws/stack.yaml` |
| S3 bucket `arai-819717422656-ap-south-1` (release, seed data, backups, evidence) | same stack | same |
| Instance role `arai-demo-instance` (SSM, that bucket, `/arai/*` parameters); security group `arai-demo-web` (80, 443) | same stack | same |
| Budget `arai-monthly`, 45 USD (20 until 18 Oct 2026), e-mail at 50 and 80 percent actual and 100 percent forecast | AWS Budgets | created directly with the Budgets API on 17 Oct 2026 |
| Configuration and secrets | Parameter Store `/arai/config/*` and `/arai/secret/*` | section 8.2 |
| On the VM: Compose stack (nginx with TLS, api, worker, db), DuckDNS timer, certificate renewal, nightly backup | `/opt/arai` | `deploy/aws/bringup.sh` |

One hostname (DuckDNS, free): `APP_HOST` is the UI and the API, public, no IP allowlist (D-044 as amended on 18 Oct
2026, AM-73). No Keycloak on the VM (AM-74): people sign in with the development login's personas (section 8.5).
What protects the instance: TLS, the shared login checked inside the API, the personas' roles for every action, and
nginx request limits (sign-in 10 a minute per address, API 20 a second).

### 8.2 Parameter Store

`/arai/config/<NAME>` (String) and `/arai/secret/<NAME>` (SecureString). `bringup.sh` turns each into a shell variable.
A value that must be empty is written as `-`.

| Name | Kind | Meaning |
|---|---|---|
| APP_HOST | config | the DuckDNS name, e.g. `arai-demo.duckdns.org` |
| DUCKDNS_DOMAINS | config | the subdomain without `.duckdns.org`, e.g. `arai-demo` |
| LE_EMAIL | config | Let's Encrypt expiry notices |
| AUTH_DEV_USERS | config | optional: the personas and roles of the development login, `Asha=reviewer,approver;Admin=admin` (section 8.5); the six defaults when absent |
| POSTGRES_PASSWORD, BASIC_AUTH_USER, BASIC_AUTH_PASSWORD | secret | generated once at setup |
| DUCKDNS_TOKEN | secret | from duckdns.org after signing in |
| ANTHROPIC_API_KEY | secret | optional; without it every memo is unavailable by design |

```powershell
aws ssm put-parameter --name /arai/config/APP_HOST --type String --overwrite --value "arai-demo.duckdns.org"
aws ssm put-parameter --name /arai/secret/DUCKDNS_TOKEN --type SecureString --overwrite --value "<token>"
```

### 8.3 Create or update the stack, publish a release, bring the VM up

```powershell
# 1. the stack (once; the same command changes a parameter later)
$vpc = aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query "Vpcs[0].VpcId" --output text
$subnet = aws ec2 describe-subnets --filters Name=vpc-id,Values=$vpc Name=map-public-ip-on-launch,Values=true --query "Subnets[0].SubnetId" --output text
aws cloudformation deploy --stack-name arai-demo --template-file deploy\aws\stack.yaml --capabilities CAPABILITY_NAMED_IAM --parameter-overrides VpcId=$vpc SubnetId=$subnet
aws cloudformation describe-stacks --stack-name arai-demo --query "Stacks[0].Outputs" --output table

# 2. the release: an archive of the committed tree (the VM never needs GitHub credentials)
git archive --format=tar.gz -o $env:TEMP\arai.tar.gz HEAD
aws s3 cp $env:TEMP\arai.tar.gz s3://arai-819717422656-ap-south-1/release/arai.tar.gz

# 3. bring-up on the VM (idempotent: re-run after any release or parameter change)
$id = aws cloudformation describe-stacks --stack-name arai-demo --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text
aws ssm send-command --instance-ids $id --document-name AWS-RunShellScript --comment "arai bringup" --parameters file://deploy\aws\bringup-command.json --query Command.CommandId --output text
# follow it: aws ssm get-command-invocation --command-id <id> --instance-id $id ; or open a shell (Session Manager plugin):
aws ssm start-session --target $id
sudo tail -f /var/log/arai-bringup.log
```

The first bring-up waits until `APP_HOST` resolves to the instance (the DuckDNS timer runs first), obtains the
certificate and starts the stack.

### 8.4 Seed the experiment data

The VM needs `data/EXP-20261005-04/artifacts` (worlds, bundles, published experiment), never `private/`:

```powershell
aws s3 sync data\EXP-20261005-04\artifacts s3://arai-819717422656-ap-south-1/seed/artifacts --exclude "datasets/*"
# then on the VM (SSM shell):
sudo aws s3 sync s3://arai-819717422656-ap-south-1/seed/artifacts /data/artifacts
sudo chown -R 1000:1000 /data/artifacts
cd /opt/arai/app; sudo docker compose -f docker-compose.yml -f deploy/aws/compose.vm.yml restart api worker
```

Without the folder the instance runs in baseline fallback (section 2.2). Alternatively reproduce it on the VM with the
offline pipeline of `README.md` (about 40 minutes on a laptop, longer on a t3.medium).

### 8.5 People

The VM runs the development login (AM-74): after the shared login, the sign-in page lists personas and anyone picks
one; there are no per-person passwords. The defaults are the six of section 2.5 (Asha, Ravi and Meera review and
approve, Arjun reviews, Priya views, Admin administers). Other names or roles: set `AUTH_DEV_USERS` and re-run
bring-up. Whoever holds the shared login can act as any persona, including Admin, so hand it out accordingly.

```powershell
aws ssm put-parameter --name /arai/config/AUTH_DEV_USERS --type String --overwrite --value "Asha=reviewer,approver;Kabir=reviewer;Priya=viewer;Admin=admin"
```

### 8.6 Start, stop, backups, restore

The VM stays on continuously for the first three months (to about 18 January 2027; about 25 USD a month against the
Free plan credits, design document section 6). For a heavy scoring session, resize: stop, `aws ec2 modify-instance-attribute
--instance-id $id --instance-type c7i-flex.large`, start; and back to `t3.small` afterwards. After the three months,
between sessions:

```powershell
aws ec2 stop-instances --instance-ids $id      # between sessions; the volumes and the parameters are all that costs
aws ec2 start-instances --instance-ids $id     # DuckDNS gets the new address within 30 s; the containers restart themselves
```

Backups: `/etc/cron.d/arai-backup` runs `deploy/aws/backup.sh` at 02:30 UTC: a dump of `arai` to
`s3://.../backup/db/` and a sync of `/data/artifacts` to `s3://.../backup/artifacts/`. Restore a database on a fresh
VM after bring-up: `zcat arai-<stamp>.sql.gz | docker compose ... exec -T db psql -U arai arai`.

### 8.7 Public access

The UI is reachable by anyone at `APP_HOST`; there is no Vercel address and no IP allowlist (both dropped on 18 Oct
2026, AM-73). Visitors need the shared login (`/arai/secret/BASIC_AUTH_USER` and `BASIC_AUTH_PASSWORD`) and then pick
a persona (section 8.5). Give the shared login only to people who should see the demonstration; rotate it by
changing the two parameters and re-running bring-up. Keycloak single sign-on remains available for a later real
deployment (section 2.6 and `.env.example`); it is not on this VM.

### 8.8 OPS-AC-05

From any machine, `.\scripts\ops_ac_05.ps1` with the hostname and the shared login writes
`reports\ops-ac-05\<date>\result.json`. It checks the HTTPS redirect, the shared login, the development login's
personas, the closed database port and the sign-in rate limit. Two checks are manual and listed in the result: a
sign-in as the viewer persona followed by a role refusal, and the idle session expiry. The same sign-in path is
checked end to end on a laptop by `tests\e2e\vm_devlogin_check.py` (section 5, step 5). Record the outcome and
the evidence path in `final-spec/acceptance-register.csv`.

### 8.9 Rebuild or tear down

Deleting the stack keeps the bucket (Retain) and snapshots the data volume (Snapshot); a new `aws cloudformation deploy`
with the same parameters and a bring-up restores the dump and syncs the artifacts back. Tear down for good:
`aws cloudformation delete-stack --stack-name arai-demo`, then empty and delete the bucket by hand and delete the
`/arai` parameters.
