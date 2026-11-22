# Implementation hands-on: how ARAI is built, step by step

For team members who will present or extend the project. `HANDS-ON.md` shows how to *use* the product, screen by
screen. This guide shows how it is *built*: you follow the data from a generated world to a case on the screen, run
a small lab at each step, and read the code that does it. At the end you can answer "how do you know?" for every
number you will show.

Allow about three hours. Every command and every number below was run on `main` on 22 Nov 2026.

| Step | What you learn | Lab | Time |
|---|---|---|---|
| 0 | Set up, and the rules that keep the experiment honest | | 15 min |
| 1 | The map: where each part lives | | 10 min |
| 2 | A synthetic world, and the line between data and truth | `lab1_world.py` | 15 min |
| 3 | The data contract and validation | `lab2_validation.py` | 15 min |
| 4 | Features and eligibility | `lab3_features.py` | 20 min |
| 5 | Why the return rate is the wrong ranking | `lab3_features.py` | 10 min |
| 6 | The experiment: candidates, gate, one final test | read and verify | 25 min |
| 7 | Scoring a snapshot with the published model | `lab4_scoring.py` | 15 min |
| 8 | The service: API, database, worker | `lab5_api.py` | 20 min |
| 9 | The screens | browser, one edit | 20 min |
| 10 | The review workflow and roles | `lab5_api.py --act` | 10 min |
| 11 | Links through a phone or a mailbox: evidence, not a model input | `lab4_scoring.py` | 10 min |
| 12 | The tests, and how to trust a change | pytest, vitest | 15 min |
| 13 | Presenting: the questions you will get | | 10 min |

The labs are in `scripts/handson/`. They generate their worlds in memory from seeds no experiment uses, so they
write nothing under `data/`, with one exception that says so (`lab5_api.py --act`).

---

## Step 0. Set up, and three rules

Commands are for PowerShell, from the repository root.

```powershell
git clone https://github.com/pragatheeswaran-cds/ARAI.git
cd ARAI
git checkout main
uv sync                                   # the Python environment, from uv.lock
cd web; npm install; npm run build; cd .. # the screens
```

If `uv` is "not recognized", open a new terminal; `RUNBOOK.md` gives its full path.

**The data is not in git.** Labs 1 to 3 need nothing more. From lab 4 on you need the experiment's data folder,
`data\EXP-20261005-04\` (the worlds, the published model, the local database). Get it from the project owner as an
archive and unpack it so that `data\EXP-20261005-04\artifacts\bundles` exists, or reproduce it from the seeds with
the eleven commands in `RUNBOOK.md` section 1.3 (about 40 minutes).

Three rules. They are what makes the result worth presenting, so learn them before touching anything:

1. **The final test ran once and is never run again.** Do not run `arai test`, `arai select`, `arai train` or
   `arai publish`, and do not generate a world from a seed the contract names (5101 to 5511). The commands refuse
   most of this themselves; do not work around a refusal.
2. **Truth never reaches the product.** The simulator knows who abused returns. That knowledge lives in a separate
   folder (`private\`), the service cannot read it, and a test checks that. You will read it in the labs only to
   keep score, after every score exists.
3. **Some files are locked to the published model.** `src\arai\features.py`, `dataset.py`, `modeling.py`,
   `bundles.py` and `ranking.py` are hashed into the bundle. Read them freely; a change to them means a new
   experiment, not a pull request.

For your own experiments use seeds from 9001 up. `arai generate --seed 9001` writes a 1,000-customer world you can
delete afterwards.

---

## Step 1. The map

One sentence: **a snapshot of seven tables goes in, a ranked queue of customers with evidence comes out, and a
person decides.**

```
 generator            validation          features           model              service               screens
 (simulated      ->   (data contract) ->  (one row per  ->   (trained once, ->  (scores a snapshot, ->  (queue, case,
  retailer)            accept or reject    customer)          then frozen)       stores results)         decision)
 src/arai/generator   validation.py       features.py        modeling.py        src/arai/service       web/src
                      operational.py      dataset.py         evaluation.py      api, store, views,
                                                             selection.py       scoring, worker
                                                             bundles.py
```

| Folder | What is in it |
|---|---|
| `final-spec/` | The specification the code is built to: sixteen component texts, the contracts (`contracts/*.yaml`), the decision log (`DECISIONS.md`). When code and spec disagree, that is a bug |
| `src/arai/generator/` | The simulator: customers, relationships, orders, honest returns, abuse, and the tables written from them |
| `src/arai/` (top level) | The offline pipeline: validation, features, training, evaluation, selection, publishing |
| `src/arai/service/` | The running product: API, database access, scoring worker, sign-in |
| `web/src/` | The React screens |
| `tests/` | 253 Python tests; `tests/e2e/` holds the browser walkthrough |
| `records/` | Dated records of every experiment, review and decision |
| `scripts/handson/` | The labs of this guide |

**Read (5 minutes):** the first twenty lines of `final-spec/components/01-goals-and-scope.md`, and `CONTEXT.md` for
the vocabulary. Note two words you will keep using: *suspected* (never fraud) and *evidence* (never proof).

---

## Step 2. A synthetic world, and the line between data and truth

There is no real customer data in this project. A generator simulates an online apparel retailer for a year and
writes what such a retailer could export.

**Run**

```powershell
uv run --no-sync python scripts\handson\lab1_world.py
```

**You should see** seven operational tables (1,000 customers, about 8,000 orders, about 2,600 return lines),
thirteen private truth tables, "30 of 1000 customers abused returns at least once (3.0%)", and one abuser's returns
by reason code.

**What it shows.** The seven tables are everything the product ever reads. `y_abuse`, the label, exists only in
`customer_truth`, which the product cannot reach. The abuser's story is visible in ordinary columns: claims such as
"item not received" and "empty package" among honest-looking returns.

**Read**

- `src/arai/generator/world.py`, class `WorldBuilder`: the stages run in order (profiles, relationships, orders,
  honest returns, abuse), and each can be inspected before the next.
- `src/arai/rng.py`: every random draw comes from a stream named by (seed, entity, purpose). That is why one stage
  can never disturb another, and why the same seed gives the same world byte for byte.
- `final-spec/contracts/data-schema.yaml`: the seven tables, column by column.

**Try it**

1. Run the lab twice with the same seed: identical. Run it with `--seed 9002`: a different world.
2. In `data-schema.yaml`, find `forbidden_columns` under `sku_master`. Why must `is_defective` never be exported?
   (Because a real retailer does not know it either; the model must find product problems from returns.)

**When presenting:** "The data is simulated, and we say so at the start and at the end. What the simulation gives us
is something no real dataset has: we know who actually abused returns, so we can measure how often the model is
right."

---

## Step 3. The data contract and validation

A snapshot is accepted whole or rejected whole. Nothing is cleaned silently, and a rejection names the rule.

**Run**

```powershell
uv run --no-sync python scripts\handson\lab2_validation.py
```

**You should see** five cases: the generated world accepted; an orphan sale line rejected with rule `F001`; an
unknown column rejected with `S001`; a file changed after its manifest was written rejected with `M002`; and a
snapshot without the optional contact columns accepted.

**What it shows.** The manifest carries a hash of every file, so what was validated is what gets scored. Unknown
columns are refused, which is how a truth column can never slip into an upload. The three contact columns (region,
email, phone) are optional, so snapshots written before they existed stay valid.

**Read**

- `src/arai/validation.py`: `validate_world` and the rule families (M manifest, S schema, T types, F foreign keys,
  and so on). Each rule has a test in `tests/test_validation.py`.
- `samples/README.md`: five small snapshots you can upload in the browser, one of them made to be rejected.

**Try it:** `uv run --no-sync pytest tests\test_validation.py -q` (27 tests, about 20 seconds). Open the test for
`F001` and read how little it takes to state a rule.

---

## Step 4. Features and eligibility

Scoring starts by turning seven tables into one row per customer.

**Run**

```powershell
uv run --no-sync python scripts\handson\lab3_features.py
```

**You should see** 59 columns of which 43 are model inputs and 2 are evidence only; 554 of 1,000 customers
eligible; and one customer who returned 52.7% of their units where buyers of the same products return 19.9%.

**What it shows**

- **Eligibility.** A customer needs three mature sale lines (delivered, return window closed) to be ranked. The rest
  are "insufficient history": shown, never ranked, never called low risk.
- **Expected against actual.** `raw_return_rate` is what the customer returned. `expected_return_rate` is what
  buyers of the same products return. `residual_z` is the gap between them in standard units. A customer who buys
  styles everyone returns is not unusual; the same rate on styles nobody returns is.
- **Evidence only.** The two link measures are computed and shown to the analyst but are not model inputs: sharing
  an address is not guilt.

**Read**

- `final-spec/contracts/features.yaml`: the 43 features in order, each with its definition and what happens when it
  cannot be computed.
- `src/arai/features.py`, function `compute_features`: follow one feature from the tables to the column, for example
  `late_return_lines`.

**Try it:** `uv run --no-sync pytest tests\test_features.py -q` (27 tests, about 15 seconds). Each test builds a tiny
world by hand with `make_tables` in `tests/helpers.py`, so you can read exactly which orders produce which value.

---

## Step 5. Why the return rate is the wrong ranking

The lab you just ran ends with the question the whole project answers.

**You should see** (bottom of `lab3_features.py`): a review budget of 28 customers, of whom 3 are abusers (11%),
where 5.1% of all ranked customers are abusers.

Run it at full size for steadier numbers:

```powershell
uv run --no-sync python scripts\handson\lab3_features.py --customers 10000
```

**What it shows.** A team can review about 5% of its customers. Picking them by return rate fills the list with
honest heavy returners, because a high return rate measures how much someone shops and how they choose sizes as
often as it measures abuse. The return-rate rule is kept in the product as the baseline every result is compared
with.

**Read:** `src/arai/ranking.py` (38 lines): the budget is 5% rounded up, and ties are broken by a public hash, never
by row order, so a ranking cannot be nudged by sorting the input.

---

## Step 6. The experiment: candidates, a gate, and one final test

This is the step to understand best, because it is what stands behind the number on your slide.

**The protocol**, in the order the commands enforce:

1. Generate **training** worlds (seeds 5101 to 5110). Train nine candidate models and two references.
2. A **dry run** of the gate on out-of-fold training scores, before any validation world exists.
3. Generate **validation** worlds (5201 to 5205). **Select**: a candidate passes the gate when its precision at the 5%
   budget is above the return-rate rule's and it reviews none of five honest groups more often than the rule does.
   Among those that pass, the highest precision wins.
4. Generate **test** worlds (5301 to 5305). Run the **final test once**. It cannot be run again.
5. **Publish** the selected model as a bundle.

**The result of experiment 4** (`records/2026-10-05-experiment-4.md`): the selected candidate, `hgb_leaf15_w6_s3`,
has precision **0.766 against 0.218** for the return-rate rule on the five test worlds, with all five honest-group
legs met.

**The five honest groups** the gate protects: legitimate heavy returners, buyers of defective products, honest
household members, honest repeat genuine claimants, and honest customers with exactly one genuine delivery failure.
A model that catches more abusers by reviewing more of any of these fails.

**Verify it yourself** (reads only; fits nothing, selects nothing):

```powershell
uv run --no-sync python scripts\verify_experiment.py
```

It takes about three minutes and should end with `ALL CHECKS PASSED` (23 checks). Each line is one claim of the
record with PASS or FAIL: the contract is the one the experiment was trained under, worlds were generated in the
required order, every world matches its recorded hash, the recorded test figures come out again when the frozen
model scores the stored test features, and the published bundle is that model. One line is worth reading aloud: the
generator has been extended since the experiment (it now writes contact details), and the check regenerates the
demonstration world with today's code and finds every stored file byte for byte the same.

**Read**

- `final-spec/contracts/experiment.yaml`: the seeds, the `expectation` written before any world existed, the nine
  candidates, the gate's segments.
- `src/arai/selection.py` (93 lines): the gate. It is short enough to read whole.
- `src/arai/evaluation.py`, `benign_segments`: how each honest group is defined from the private truth.
- `docs/experiment-4-verification-guide.md`: the owner's check of the experiment, claim by claim.

**Try it:** `uv run --no-sync pytest tests\test_evaluation.py -q` (15 tests, about 5 seconds). Find the test named
`test_gate_needs_strictly_higher_precision_and_no_worse_segment_rate` and read what makes a candidate fail.

**When presenting, say the limits too.** They are in the record and you will be asked:

- The result is on worlds this generator can produce. It says nothing yet about real returns.
- On stress worlds where honest customers return late, the frozen model's precision falls to 0.35 to 0.46. The model
  leans on return timing, and it does not transfer to a retailer whose honest customers behave differently.
- The repeat-claimant leg is met with little margin.
- Quote the gap to the rule (three and a half times), not the 76.6% alone.

---

## Step 7. Scoring a snapshot with the published model

Now use the published model on data it has never seen.

**Run** (needs the data folder; about a minute)

```powershell
uv run --no-sync python scripts\handson\lab4_scoring.py
```

**You should see** a new 10,000-customer world scored: 5,744 ranked, 288 selected for review; the top five of the
queue with the rule's rank beside the model's (rank 1 is the rule's 2,293rd); and

```
  the model's queue holds 213 abusers (74%)
  the return-rate rule's queue holds 74 abusers (26%)
```

The first line of output, about a "different dependency lock", is a notice that your library versions are checked
against the bundle's; it is not an error.

**What it shows.** Seed 9001 is in no experiment, so this is a fresh world, and the model's share of abusers in the
queue is close to the published 76.6%. That is what "the result holds on new worlds of this simulator" means, and
you have now seen it yourself.

**Read**

- `src/arai/bundles.py`: a bundle is the fitted model, the training reference scores and a manifest of hashes.
  `resolve_active` loads the published one; `code_differs` warns when the scoring code is not the code it was
  built with.
- `src/arai/service/scoring.py`, `score_snapshot`: the stages (features, eligibility, scores, ranks, evidence).
  Notice the comment where the evidence starts: everything after it changes what is shown, never a score.
- The score shown on screen is `reference_percentile`: where this customer's raw score falls among the training
  scores. It is not a probability, and the screens say so wherever it appears.

**Try it:** run the lab with `--customers 1000`. The percentages jump around: 28 reviews are too few to measure
anything. This is why the experiment pools five worlds of 10,000.

---

## Step 8. The service: API, database, worker

**Run**

```powershell
uv run arai local                                              # terminal 1: http://127.0.0.1:8000, leave it running
uv run --no-sync python scripts\handson\lab5_api.py            # terminal 2
```

Use `uv run --no-sync` while the server runs; plain `uv run` may try to refresh the environment and fail with "file
is being used by another process".

**You should see** the health check, Arjun signed in as a reviewer, the latest run (W5401: 5,676 ranked, 284
selected), the counts by risk level (86 Critical, 198 High, 307 Medium, 5,085 Low), the first five of the queue,
one case with its sections, and Priya, a viewer, refused with 403 when she tries to write a note.

**What it shows.** The screens have no logic of their own about who is risky: they show what these calls return.
Everything the API serves comes from PostgreSQL; the worker writes a run's results there in the same transaction
that marks the run succeeded.

**Read**

| File | Its one job |
|---|---|
| `service/api.py` | The routes. Each one is thin: check, call the store or a view, return |
| `service/store.py` | Every SQL statement. Nothing else talks to the database |
| `service/views.py` | Turns stored rows into what the contract promises (tier, status, signals) |
| `service/worker.py`, `scoring.py` | Scores a queued run and publishes its results |
| `service/auth.py` | Sign-in, sessions, and one table that says which permission each route needs |
| `service/migrations/` | The database schema, one numbered file per change |
| `final-spec/contracts/openapi.yaml` | The API contract. A test fails if a route exists that the contract does not name, or the reverse |

**Try it**

1. Open http://127.0.0.1:8000/api/v1/openapi.json in the browser and find `/runs/{run_id}/customers`.
2. In `service/auth.py`, find `ROUTE_PERMISSIONS`. Which permission does exporting the queue need, and which roles
   have it? (`export`: reviewer, approver and admin.)

---

## Step 9. The screens

With the server from step 8 still running, open http://127.0.0.1:8000 and choose **Arjun**.

**Walk** Dashboard, Risk Queue, a case, Customers, Network Graph, Products / SKU, Analytics. `HANDS-ON.md` has the
guided tour with what to look for on each; twenty minutes of it is enough here.

**Read**

| File | What it holds |
|---|---|
| `web/src/api-types.ts` | Generated from `openapi.yaml` by `npm run api-types`. Never edited by hand, so the screens cannot drift from the API |
| `web/src/api.ts` | The typed client: one function per route |
| `web/src/derive.ts` | Every label and every small calculation the screens share, with tests in `derive.test.ts` |
| `web/src/pages/` | One file per screen |
| `web/src/components/` | The queue table, the charts, the shared building blocks |

**Try it: one safe edit, end to end**

```powershell
cd web
npm run dev          # terminal 3: http://127.0.0.1:5173 with live reload, using the API on port 8000
```

1. In `web/src/derive.ts`, find `STATE_LABEL` and change `in_review: "In Review"` to `"Under Review"`. The queue's
   Status column changes as you save.
2. Run `npx vitest run`. One test fails, the one that expects "In Review". That is the test doing its job.
3. Undo your edit (`git checkout web/src/derive.ts`) and run the tests again: 30 pass.

**When presenting:** point out what is *not* on the screens. No screen says fraud, confidence or probability. The
dashboard says "suspected". The browser walkthrough checks for those words and fails if one appears.

---

## Step 10. The review workflow and roles

A case goes **Open → In Review → Escalated → Closed**. A reviewer opens a case and either clears it or escalates it.
A lead closes an escalated case as confirmed or not confirmed. Every step needs a note and is recorded under the
person who signed in.

**Run** (this writes three reviews into the demo database, as an analyst would)

```powershell
uv run --no-sync python scripts\handson\lab5_api.py --act
```

**You should see**

```
  Arjun opens it          -> in_review
  Arjun escalates it      -> escalated
  Arjun tries to close it -> 403: Closing an escalated case with its outcome needs the approver (lead) role.
  Ravi (lead) closes it   -> closed, outcome confirmed, decided by Ravi
  audit log, newest first: close by Ravi; escalate by Arjun; open by Arjun
```

Then look at the same case in the browser, and at **Audit Log** in the sidebar.

**What it shows.** The status of a case is not stored. It is derived from the append-only list of reviews: the
latest workflow event decides. Nothing is ever edited or deleted, so the record of who did what cannot be rewritten.

**Read**

- `service/store.py`, `append_review`: the rules, checked under one lock per customer so two people cannot decide
  the same case at once. The docstring lists every refusal.
- `service/views.py`, `workflow`: status and outcome derived from the latest event.
- `final-spec/DECISIONS.md`, row AM-76: why the workflow is what it is.

---

## Step 11. Links through a phone or a mailbox: evidence, not a model input

Where a snapshot carries contact details, the analyst sees accounts linked by any two of five identifier types:
address, device, payment method, phone number, mailbox. The model still reads only the first three.

**Look again at the end of the `lab4_scoring.py` output from step 7:**

```
CONTACT DETAILS: scored again without phone, email and region. Every score identical: True.
  Links shown to the analyst with them: 1205; without them: 1050.
  Groups of linked accounts: 279 (rings: 49) against 249 (rings: 37).
```

**What it shows.** The same snapshot was scored twice, with and without its contact columns. Every score is
identical; what changes is what the analyst is shown: 155 more links and twelve more rings.

**Why it was built this way.** The owner first approved an experiment that would have put these links into the
model. Before any data was generated, an independent review measured that the wider graph changes one model input
for about ten customers in ten thousand, so the experiment could not have shown what the links add. It was
withdrawn, and the links became evidence. The story is in `records/2026-11-22-contact-links-design-review.md`. It is
a good example to tell: the review saved a sealed test from being spent on a question it could not answer.

**Read**

- `src/arai/service/links.py` (short): the evidence graph. Compare `build_graph` here with the one in
  `features.py`: the same rules, two more identifier types.
- `tests/test_links.py` and, in `tests/test_service.py`,
  `test_contact_links_change_what_is_shown_and_never_a_score_a_rank_or_a_selection`.

**Try it:** `uv run --no-sync pytest tests\test_links.py -q` (4 tests, about 5 seconds).

---

## Step 12. The tests, and how to trust a change

| Command | What it covers | Time |
|---|---|---|
| `uv run --no-sync pytest tests\test_features.py -q` | Features, on hand-built worlds | 15 s |
| `uv run --no-sync pytest tests\test_validation.py -q` | Every rule of the data contract | 20 s |
| `uv run --no-sync pytest tests\test_generator.py -q` | The simulator's laws and its reproducibility | 50 s |
| `uv run --no-sync pytest tests\test_evaluation.py -q` | Budget, gate, bootstrap | 5 s |
| `uv run --no-sync pytest tests --ignore=tests\e2e -q` | Everything: 253 tests, with a private PostgreSQL started for the run | 22 min |
| `cd web; npx vitest run` | The screens' logic: 30 tests | 7 s |
| `uv run --no-sync python tests\e2e\walkthrough.py` | A real browser through every screen: 71 checks (needs the server and the twelve snapshots, `RUNBOOK.md` 4.1) | 3 min |
| `uv run python scripts\spec_package.py` | The specification package: hashes, links, acceptance register | 10 s |

Three tests worth reading, because each protects something you will claim:

- `test_serving_does_not_import_offline_modules_or_need_private_truth` (`tests/test_service.py`): the service runs
  with the truth folder pointing nowhere.
- `test_the_served_contract_is_the_bundled_one_and_every_route_is_in_it`: no route outside the contract.
- `test_same_seed_reproduces_every_table` (`tests/test_generator.py`): reproducibility.

**How a change is made here:** the decision goes in `final-spec/DECISIONS.md` as a numbered row, the contract changes
with it, the code follows, the tests cover it, and `scripts\spec_package.py` rebuilds the package's hashes. Read the
last four rows (AM-76 to AM-79) to see the shape.

---

## Step 13. Presenting: the questions you will get

| Question | Short answer | Where you saw it |
|---|---|---|
| Is the score a probability of abuse? | No. It is a percentile against the training worlds. The queue is the top 5% by rank | Step 7; `bundles.reference_percentile` |
| How do you know the model is better than the return rate? | Same budget, same worlds: 76.6% of its queue are abusers against 21.8%, on five sealed test worlds, tested once. On a world generated just now, 74% against 26% | Steps 6 and 7 |
| Could the model have seen the answers? | The label lives in a folder the service cannot read; uploads with unknown columns are refused; a test runs the service with the truth folder missing | Steps 2, 3, 12 |
| Does it punish loyal customers who return a lot? | That is what the gate is for: the model may not review honest heavy returners, or four other honest groups, more often than the rule does | Step 6; `selection.py` |
| Is this real data? | No, simulated, and the screens say so on every page. The numbers show the method works on worlds this generator can produce | Step 2 |
| Where is it weak? | It leans on return timing: on stress worlds where honest customers return late, precision falls to 0.35 to 0.46 | Step 6 |
| Does the product decide anything? | No. It ranks and shows evidence. A person clears or escalates, and nothing reaches an order or a refund | Step 10 |
| Who can do what? | Viewer reads; reviewer notes, opens, clears, escalates; lead closes escalated cases; admin registers data and manages people | Steps 8 and 10; `auth.py` |
| Does the model use phone numbers or emails? | No. They link accounts for the analyst only; scores are identical with and without them | Step 11 |
| What happens when no model qualifies? | The return-rate ranking is served with a banner saying why | `HANDS-ON.md`, exercise 13 |
| Can it run on our data? | The data contract is the interface: a manifest and seven tables. The pipeline, the evaluation and the test discipline stay the same | Step 3 |

**Words to use:** selected for review, suspected, evidence, pattern in the record, expectation, simulated world.
**Words to avoid:** fraudster, fraud score, confidence, proof, guilty.

---

## Clean up

- Stop the server with Ctrl+C in terminal 1 (and the dev server in terminal 3).
- If you ran `arai generate --seed 9001` yourself, delete `data\EXP-20261005-04\artifacts\worlds\W9001*` and
  `data\EXP-20261005-04\private\W9001*`. The labs themselves wrote nothing there.
- `git status` should show nothing changed. If it does, `git checkout .` puts every file back.
- The three reviews `lab5_api.py --act` wrote stay in the demo database. To remove all notes:
  `uv run arai db-clean --notes --dry-run`, then with `--yes`.

## Where to go next

| To | Read |
|---|---|
| Use the product screen by screen, as each role | `HANDS-ON.md` |
| Start, stop, load data, troubleshoot | `RUNBOOK.md` |
| Give the demonstration | `docs/demo-script.md` |
| Check the experiment claim by claim | `docs/experiment-4-verification-guide.md` |
| Understand a decision | `final-spec/DECISIONS.md`, and the dated files in `records/` |
| Know what is still open | `pendings.md` |
