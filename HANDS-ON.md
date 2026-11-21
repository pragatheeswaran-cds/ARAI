# ARAI hands-on: from a fresh clone to every screen, end to end

A guided lab to do once, at your own pace, on your laptop. Each exercise says what to do, what you should see, and why
it matters. It uses only commands from `RUNBOOK.md`, which stays the reference (section numbers are given as RUNBOOK
x.y). Commands are for PowerShell from the repository root; on macOS or Linux use forward slashes.

| | |
|---|---|
| **Time** | About 2 hours. Most of it is waiting: generating the data takes about 40 minutes, scoring a year of snapshots about 10 |
| **You need** | git, [uv](https://docs.astral.sh/uv/), Node.js (to build the UI once), a browser. Docker only for the optional Keycloak exercise |
| **Data** | Everything is simulated. No real customer appears anywhere |

The path: build the data (exercises 1-3), start the product (4), use it as an admin, a reviewer, an approver and a
viewer (5-12), see the fallback (13), clean up and check (14-15). Exercise 16 adds Keycloak.

---

## 1. Set up the code

```powershell
git fetch origin
git checkout year-of-snapshots      # the branch with all the work; main does not have it yet
uv sync                             # Python 3.12 and every dependency, from uv.lock
cd web; npm install; npm run build; cd ..
uv run arai --help                  # lists generate, snapshot, train, ... local, db-clean
```

**You should see** the list of `arai` commands. **Why:** `uv.lock` pins every library, so your results match the
records byte for byte.

## 2. Generate the synthetic data and reproduce the experiment

Skip to exercise 3 if you copied `data\EXP-20261005-04` from a machine that has it.

```powershell
uv run arai generate --seed 5101 5102 5103 5104 5105 5106 5107 5108 5109 5110 5501 5502 5503 5504 5505 5506 5507 5508 5509 5510 5511
uv run arai train
uv run arai dry-run
uv run arai ablation
uv run arai stress
uv run arai generate --seed 5201 5202 5203 5204 5205
uv run arai select
uv run arai generate --seed 5301 5302 5303 5304 5305
uv run arai test
uv run arai generate --seed 5401
uv run arai publish --demo-world W5401
uv run arai baseline-rehearsal --fresh      # Ctrl+C once it says the run succeeded (needed for exercise 13)
```

**You should see** each world reported with its customers, orders and return lines; `test` reports that the final test
**passed**; `publish` writes the bundles and the report. **Why:** the order is enforced. Training refuses to run once
validation worlds exist, and the test runs once. That is what makes the result trustworthy (RUNBOOK 1.3).

**Look at the data.** Open `data\EXP-20261005-04\artifacts\worlds\W5401\operational\` in Explorer: seven CSV files
(customers, SKUs, reason codes, orders, order lines, returns, return lines) and `manifest.json`. That is exactly what a
retailer would upload. The answers (who is an abuser) live separately in `data\EXP-20261005-04\private\`, which the
product never reads.

**Make a world of your own** and check it the way an upload is checked:

```powershell
uv run arai generate --seed 9001
uv run arai validate data\EXP-20261005-04\artifacts\worlds\W9001\operational
```

**You should see** `"violations": []`. Try breaking it: delete a line from `return_order_line.csv` in a copy of the
folder and validate the copy. It is refused, naming the file and the key.

## 3. A year of monthly snapshots

The demonstration world W5401 is 10,000 customers with a year of history up to 9 Sep 2026. Write the same customers
as they stood on the 9th of each earlier month:

```powershell
uv run arai snapshot W5401 --as-of 2025-10-09 2025-11-09 2025-12-09 2026-01-09 2026-02-09 2026-03-09 2026-04-09 2026-05-09 2026-06-09 2026-07-09 2026-08-09
```

**You should see** eleven lines, each followed by `a prefix of the world's own snapshot`. **Why:** a customer keeps
the same identifier in every month, so the product can show their history. The check proves no month invents anything
that the next month contradicts (RUNBOOK 4.1).

## 4. Start the product

```powershell
uv run arai local                   # terminal 1; leave it running. Database, API, worker and UI in one process
```

In a second terminal:

```powershell
curl.exe -s http://127.0.0.1:8000/api/v1/health
```

**You should see** `"scoring_ready":true`, `"promoted_model_ready":true` and `"model_kind":"supervised"`.

## 5. As Admin: register and score a snapshot by hand

Open http://127.0.0.1:8000. The sign-in page lists six people (the development login, RUNBOOK 2.5). Choose **Admin**.

1. Go to **Datasets & runs**. Under **Register a snapshot**, choose the eight files of
   `data\EXP-20261005-04\artifacts\worlds\W5401.as-of-2026-06-09\operational` (the manifest and the seven CSVs) and
   click **Validate and register**.
2. In **Registered datasets**, click **Score with the active bundle** on the new row. Watch the run's stages (Ingest,
   Features, Detection, Investigation) turn done in a few seconds.
3. Try a broken upload: choose only some of the files and click **Validate and register**. It is refused and names
   what is missing. Nothing is stored.

Now load every other month, plus three review outcomes recorded on the August snapshot (second terminal):

```powershell
uv run --no-sync python scripts\history_demo.py --load      # about 10 minutes; safe to rerun
```

**You should see** twelve snapshots of W5401 in **Registered datasets** and a scored run for each. The last line
printed reads `Since the previous snapshot (2026-08-09): 249 in both queues, 35 new, 22 left, 2 decided before`.
**Why:** an admin registers and scores; an admin does not review cases (open any case: no note or decision controls).

## 6. As Ravi: read the Overview

**Sign out** (top right) and choose **Ravi** (reviewer and approver).

**You should see** W5401 with 5,676 customers scored and 284 in the queue. There is a comparison of the model with the
return-rate rule, and a panel **Since the previous snapshot of W5401 (09 Aug 2026)**: 249 also in the previous queue,
35 new, 22 left, 2 decided on an earlier snapshot. **Why:** the queue is 5% of the customers who can be ranked, so a
team of reviewers can work through it. The rule would flag mostly honest heavy returners.

## 7. The customer queue

Open **Customer queue**.

1. **Model and return-rate rule** → *Selected by the rule, not by the model*: customers a plain return-rate rule would
   have sent, mostly honest heavy returners and buyers of defective products.
2. Back to *All*. **History** → *Decided on an earlier snapshot*: W5401-C08645 (rejected on the August snapshot by Ravi)
   and W5401-C07084 (approved by Asha), each back in the September queue as a new case.
3. **Show** → *Cleared heavy returners*: people with high return rates the model left out, each with the reason.
4. Clear the filters, search **W5401-C08645**, then click **Export this view as CSV**.

**You should see** the CSV open with one row per customer in the current view and no note text. **Why:** filters change
what is shown, never a score or the run's selection.

## 8. A case, start to finish: the two-person rule

1. Still as **Ravi**, filter **Status** → *New*, open any case, and read the tabs: **evidence** (expected against actual
   returns and why the score is high), **returns** (every return line with its reason code), **linked accounts**
   (shared addresses, cards or devices), **history** (every monthly snapshot this customer appears in) and **notes**.
2. Note the case id, sign out, and sign in as **Arjun** (reviewer only). Open the same case. Choose a reading
   (*Needs investigation*), write a note and click **Open case**. Then write another note and click **Request
   approval**. There is no Approve button: *Approving or rejecting needs the approver role.*
3. Sign out and sign in as **Ravi**. The queue shows a band **Awaiting your approval: 1 case(s) another reviewer
   opened** with Arjun's case. Open it, write a note and click **Approve**. The decision is recorded under Ravi's name.
4. Now, as Ravi, open a different *New* case yourself (**Open case**, with a note), and try **Approve** on it.

**You should see** the refusal *You opened this case. A different reviewer must approve or reject it.* **Why:** the
server compares signed-in people, not typed names, so nobody can approve their own case. No action here suspends an
account or refunds an order: the product records the human decision only.

Click **Download case summary** on any case for a printable hand-off.

## 9. A year of one customer's history

Search **W5401-C08645** and open the **history** tab.

**You should see** twelve rows from 9 Oct 2025 to 9 Sep 2026: not ranked in October (one month of history is not enough),
rank 255 in November, selected for review in nine months, rejected on the August snapshot by Ravi. **Why:** each month is
scored on its own; the review restarts each month, with earlier decisions shown, not carried over.

Then open the October snapshot's queue (**Datasets & runs** → the 9 Oct 2025 run → **View results**). It is empty and
says why: nobody has the three settled purchase lines the model needs yet.

## 10. Style investigation

Open **Style investigation**, filter by a state such as *targeting*, and open a style.

**You should see** the style's linked claimants and its SKU drill-down. **Why:** coordinated groups target particular
styles; this view finds them from the product side rather than the customer side.

## 11. Evaluation

Open **Evaluation**.

**You should see** the result on five untouched simulated test worlds. Of the customers the model sends for review at
the 5% budget, 76.6% are abusers, against 21.8% for the return-rate rule. The page also shows the gate's protected
honest groups and what the result depends on. Click **Reveal simulated truth** to see the answers for the demonstration
world. They appear only on this page, never on a case.

## 12. As Priya and as Admin: roles and access

1. Sign in as **Priya** (viewer). Every screen reads, but there is no note, decision, export or scoring control.
2. Sign in as **Admin** and open **People & access**. Everyone who has signed in is listed, with each role and where it
   comes from, plus status, last sign-in and open sessions.
3. Click **Disable** on Arjun's row, give a reason, and confirm. Sign out and try to sign in as **Arjun**: refused,
   *This account is disabled. Ask an administrator.*
4. Sign in as **Admin** again, click **Enable** on Arjun, and look at the **Sign-in log** below the list: the disable and
   enable are there with your name and reason.

**Why:** roles come from the identity source (Keycloak groups on a shared deployment). ARAI never edits them, but an
admin can take access away at once (RUNBOOK 2.7).

## 13. The fallback: when no model qualifies

Stop nothing. In a new terminal:

```powershell
uv run arai baseline-rehearsal      # a second instance on port 8011, serving the return-rate rule only
```

Open http://127.0.0.1:8011 and sign in.

**You should see** a banner: *No candidate passed the validation gate. The return-rate ranking is active...* The queue
is the rule's ranking, labelled as such. **Why:** if a model ever fails its gate or its test, the product says so and
falls back honestly instead of pretending. Stop it with Ctrl+C.

## 14. Clean up

```powershell
uv run --no-sync arai db-clean --all --dry-run       # shows what would be removed; nothing happens without --yes
uv run --no-sync arai db-clean --notes --yes         # removes the notes and decisions you made in this lab
```

`--notes` also removes the three August outcomes the demo recorded; run `scripts\history_demo.py` again to put them
back. Stop the instance with Ctrl+C in terminal 1 (RUNBOOK 2.1 and 2.4).

## 15. Check everything

```powershell
uv run --no-sync pytest -q                                    # "237 passed", about 10 minutes
cd web; npm test; npx tsc --noEmit; cd ..                     # "30 passed"
uvx ruff@0.16.8 check src tests scripts                       # "All checks passed!"
uv run --no-sync python tests\e2e\walkthrough.py              # with the instance up: "71 of 71 checks passed"
```

## 16. Optional: single sign-on with Keycloak

Needs Docker. RUNBOOK 2.6 has the details; the people and passwords are in RUNBOOK "Start here".

```powershell
Copy-Item .env.example .env                          # set POSTGRES_PASSWORD in it (Compose requires it)
docker compose --profile sso up -d keycloak          # http://127.0.0.1:8081; about a minute the first time
$env:AUTH_MODE = "oidc"; $env:OIDC_ISSUER = "http://127.0.0.1:8081/realms/arai"; $env:OIDC_ALLOW_HTTP = "1"
$env:OIDC_CLIENT_ID = "arai"; $env:OIDC_CLIENT_SECRET = "arai-dev-secret"
$env:OIDC_REDIRECT_URI = "http://127.0.0.1:8000/api/v1/auth/callback"
uv run arai local
```

Open http://127.0.0.1:8000 (not `localhost`) and click **Sign in with Keycloak**. Sign in as `asha` with password
`arai-dev` and check that her roles are reviewer and approver. Then remove her from the `arai-approvers` group in the
Keycloak admin console (http://127.0.0.1:8081/admin, `kcadmin` / `kcadmin-dev`), sign out and in again. **Approve** is
gone: roles are read at every sign-in. Finish with `docker compose --profile sso down`.

This is the first time this setup meets a real Keycloak; if something differs, note the error message.
