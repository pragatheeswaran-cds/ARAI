# The demonstration dataset: how to generate and load it

The demonstration runs on one synthetic world, **W5401**: 10,000 customers with a year of orders and returns up to
9 Sep 2026, loaded as twelve monthly snapshots (9 Oct 2025 to 9 Sep 2026). Everything in it is simulated. This page
gives the steps in one place, from a fresh clone to the Dashboard; `RUNBOOK.md` has the detail (sections 1.3, 4, 4.1
and 4.2).

| What the demonstration shows | Where it comes from |
|---|---|
| Dashboard, Risk Queue, Investigations, Customers, Network Graph, Products / SKU, Analytics, Audit Log | W5401, the 9 Sep 2026 snapshot, scored (steps 2 and 4) |
| A customer's history month by month, and the September queue compared with August | the eleven earlier snapshots of W5401 (steps 3 and 4) |
| Cases decided on an earlier snapshot and back in the queue | the three August outcomes written by `scripts\history_demo.py` (step 4) |
| A customer's email, phone and region, and accounts linked by a shared phone or mailbox | a second world, W5601N10000 (step 5); W5401 was written before these columns existed |

The data is not in git: it is written under `data\EXP-20261005-04\`. Run every command from the repository root, in
PowerShell.

## 1. Prepare the clone

```powershell
git checkout main; git pull
uv sync
cd web; npm install; npm run build; cd ..
```

## 2. Generate the worlds and publish the model (about 40 minutes)

W5401 cannot be scored without the published model, and the model comes from the experiment, so the whole sequence is
run once, in this order. The order is enforced: training and the dry run refuse to run once validation worlds exist,
selection needs the dry run, and the test runs once. A seed and the commit reproduce a world byte for byte.

```powershell
uv run arai generate --seed 5101 5102 5103 5104 5105 5106 5107 5108 5109 5110 5501 5502 5503 5504 5505 5506 5507 5508 5509 5510 5511   # training and stress worlds
uv run arai train                     # freeze features, fit nine candidates and two references
uv run arai dry-run                   # gate dry run and calibration check, before any validation world
uv run arai ablation                  # what the result depends on
uv run arai stress                    # the frozen models on the stress worlds; diagnostic
uv run arai generate --seed 5201 5202 5203 5204 5205   # validation worlds
uv run arai select                    # apply the gate, freeze the selection
uv run arai generate --seed 5301 5302 5303 5304 5305   # test worlds
uv run arai test                      # the final test: runs once
uv run arai generate --seed 5401      # the demonstration world W5401 (about 15 seconds)
uv run arai publish --demo-world W5401   # bundles, active pointer, published experiment report
```

**Do not run this where the data already exists.** On a machine that has `data\EXP-20261005-04\artifacts\bundles`
(this one, or a clone where the team archive `ARAI-data-EXP-20261005-04-<date>.zip` was unpacked), skip to step 3: the
final test ran once, and `train`, `select`, `test` and `publish` must not be run again there.

Check:

```powershell
Get-ChildItem data\EXP-20261005-04\artifacts                              # active, bundles, experiments, worlds
Get-ChildItem data\EXP-20261005-04\artifacts\worlds\W5401\operational     # manifest.json and seven .csv files
```

## 3. Write the eleven earlier monthly snapshots (about 3 minutes)

W5401 as it stood on the 9th of each month from October 2025 to August 2026. The command replays the generator for
seed 5401 and checks that each snapshot is a prefix of W5401; running it again changes nothing that is already right.

```powershell
uv run arai snapshot W5401 --as-of 2025-10-09 2025-11-09 2025-12-09 2026-01-09 2026-02-09 2026-03-09 2026-04-09 2026-05-09 2026-06-09 2026-07-09 2026-08-09
```

Each one is a folder `data\EXP-20261005-04\artifacts\worlds\W5401.as-of-<date>\operational`.

## 4. Load it into the product (about 10 minutes)

```powershell
# terminal 1: leave it running
uv run arai local                                  # http://127.0.0.1:8000

# terminal 2: register and score the twelve snapshots, then record the three August review outcomes. Safe to rerun:
# what is already registered or scored is skipped.
uv run --no-sync python scripts\history_demo.py --load
```

The last line it prints must read `Since the previous snapshot (2026-08-09): 249 in both queues, 35 new, 22 left,
2 decided before`.

Open http://127.0.0.1:8000 and choose a person. You should see:

- the Dashboard of W5401 with 5,676 customers scored and 284 in the queue (86 Critical, 198 High);
- twelve snapshots under Configuration, each with a scored run;
- W5401-C08645 (confirmed after escalation on the August snapshot) and W5401-C07084 (cleared in August) back in the
  September queue as new cases, each with the August decision on its history.

Customers in the snapshot / ranked / selected for review, month by month:

| 9 Oct 25 | 9 Nov | 9 Dec | 9 Jan 26 | 9 Feb | 9 Mar | 9 Apr | 9 May | 9 Jun | 9 Jul | 9 Aug | 9 Sep |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 6,210 / 0 / 0 | 6,585 / 621 / 32 | 6,953 / 2,467 / 124 | 7,319 / 3,210 / 161 | 7,709 / 3,670 / 184 | 8,067 / 3,955 / 198 | 8,447 / 4,272 / 214 | 8,802 / 4,555 / 228 | 9,152 / 4,840 / 242 | 9,502 / 5,119 / 256 | 9,791 / 5,408 / 271 | 10,000 / 5,676 / 284 |

In October nobody is ranked: after one month of history no customer has the three mature sale lines the model needs.

To load the same data into the demonstration VM instead, see `RUNBOOK.md` section 8.10 (the script takes
`--base-url https://arai-demo.duckdns.org` and each person's password from the environment, section 8.5).

## 5. Optional: a world with email, phone and region

```powershell
uv run arai generate --seed 5601 --customers 10000     # W5601N10000, a seed no experiment uses; about 20 seconds
uv run arai register data\EXP-20261005-04\artifacts\worlds\W5601N10000\operational
```

Score it from **Configuration** (**Score with the active bundle**). The Customers page then shows each customer's
email, phone and region, and the search finds a customer by any of them. Every email is at example.com and every phone
number starts with 5, which no Indian mobile number does.

## Start again

```powershell
uv run arai db-clean --all --world W5401 --dry-run  # what would be removed
uv run arai db-clean --all --world W5401 --yes      # the notes, runs and registered datasets of W5401
uv run --no-sync python scripts\history_demo.py --load
```

The worlds written in steps 2 and 3 stay on disk (`db-clean` removes the registered copies under `artifacts\datasets`,
not `artifacts\worlds`), so those steps are not repeated.
