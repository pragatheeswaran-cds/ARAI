# Demo script: the ARAI workbench on world W5401

A story and a click-by-click flow for a 20 to 25 minute demonstration of the return-abuse workbench. The slide deck
built from it is in `docs/demo-deck/`. Every number
below is what the screens show for the demonstration world W5401 scored on experiment 4, on its latest run
(`run-020e5490d88f48c28e8c`, re-scored 16 Oct 2026 under API contract 1.14.0 with the revised ring rule). The first
run of 15 Oct (`run-ed95a0e2fd3e49a69d4d`) has the same scores, ranks and selection. Since API contract 1.15.0 the
same world also holds its snapshots of 9 July and 9 August, the same customers a month and two months earlier, so a
customer's history shows on the queue, the case and the Overview (RUNBOOK.md section 4.1). Screenshots are in
`reports/ui/2026-10-16/`.

The data is simulated. Say so at the start and at the end: the application reads a synthetic world of 10,000
customers of an online apparel retailer (brands A to D, prices in INR, one year of history). The numbers show
that the method works on worlds the generator can produce; they are not results on real returns.

---

## 1. The story in one paragraph

A returns team can look at about five percent of its active customers each period. Today it picks them by return
rate, which fills the list with honest heavy returners and misses most of the people who game the returns
process: those who claim parcels never arrived, who return occasion wear after the event, and small groups of
linked accounts that claim on the same products within days of each other. ARAI ranks the same customers with a
model trained on the pattern of what they return and when, keeps the return-rate rule beside it for comparison,
and hands every case to a reviewer with the evidence, denominators and caveats on the page. Nothing on the screen
is a finding of misconduct: it is a queue of places worth a look, with the record laid out so a second person can
check the first.

Three characters carry the demo:

| Character | Who they stand for | Where they appear |
|---|---|---|
| Priya, returns operations lead | Owns the review budget and wants to know what the queue costs in honest customers | Overview, Evaluation |
| Arjun, first-line reviewer | Works the queue, writes notes, opens cases | Customer queue, Customer case |
| Meera, second reviewer | Approves or rejects cases she did not open | Decision panel, second-reviewer rule |

Each character is a person of the development login with the matching role (since API contract 1.16.0): Priya is a
viewer, Arjun a reviewer, Meera a reviewer and approver; Asha and Ravi (reviewers and approvers) wrote the August
history, and Admin registers and scores. Sign in as the character whose part you are playing; every note and decision
is recorded under the person signed in. `AUTH_DEV_USERS` changes the list (RUNBOOK section 2.5).

---

## 1b. Telling it as two weeks: the rule's week and the product's week

The story below says why the product is better without naming a capability. It is one reviewer's week, told twice:
same retailer, same 10,000 customers, same 284 review slots. Only the way the list was built differs. Use it as the
spine of the demo, with the scenes in section 4 as the evidence for each line; the baseline is shown inside the
product at every step (section 1c), so no separate baseline demonstration is needed.

**The week with the return-rate list**

- *Monday morning, 284 names.* Every one of them returns a lot. That is all the list knows. Arjun opens the first
  case, sees a 45 percent return rate, and has nothing else to look at.
- *Four of five visits find nothing.* On the validation worlds the rule is right 22.7 percent of the time. Arjun
  spends most of his week clearing people who buy three sizes and keep one.
- *The rule punishes loyalty.* 44 percent of honest heavy returners get a review. These are the best customers of a
  fit-sensitive category, and they are the ones being contacted.
- *The real cases never arrive.* Half of the customers who falsely claim a parcel never arrived stay below the
  heavy-returner line, and the rule finds fewer than one in three of them. A ring spreads its claims across several
  accounts, and the rule finds one ring member in four. The number the list uses cannot see what they do.
- *Friday, a decision nobody can defend.* Arjun escalates three people. If one of them calls to complain, the only
  answer is "your return rate is high". No second person checked, because there was nothing to check.

**The same Monday, the other list**

- *284 names again, three quarters of them different.* 209 customers the rule would have reviewed are gone. 209 the
  rule never showed are here. 75 are on both.
- *Three of four visits find something.* Precision 74.3 percent on the validation worlds, 76.6 percent on the final
  test, and on this demo world 232 of the 284 against the rule's 75. Same budget, same hours, three times the yield.
- *The loyal customer is left alone.* Under 5 percent of honest heavy returners are reviewed instead of 44. The
  cleared list is on screen so the team can argue with it.
- *The first case explains itself.* Rank 1 bought 29 units and sent back 12 where a buyer of the same products would
  send back about 6. Four returns in thirteen went back late in the window. The rule ranked this customer 553rd.
- *Rings appear as rings.* Rank 4 is one of five linked accounts, four of them on the list, with a claim on the same
  product within days of each other. The reviewer sees the group once, not five strangers.
- *Friday, a decision with a record.* Arjun opens the case, writes what he saw, and the system refuses to let him
  approve his own work. Meera approves, with both names and times kept. If the customer calls, there is an answer.

**The three lines to repeat**

1. *Same budget, three times the hits.* The money is not in more reviews. It is in better ones.
2. *Return rate measures loyalty as often as abuse.* Ranking on it sends your best customers to the fraud desk.
3. *A queue you can argue with.* Every case shows its expectation, its denominators and the record behind each link,
   and a second person decides.

Say the week-one lines while the Overview and the queue are on screen, before any filter is touched; say the
week-two lines as each scene produces its evidence; say the three lines at the close.

## 1c. Where the baseline shows inside the flow

The rule is visible at every step of the product, which is itself part of the message: the product does not hide
what it replaced.

| Screen | What shows the rule | Line it supports |
|---|---|---|
| Overview, "Model and return-rate rule compared" | 209 model only, 75 both, 209 rule only | Three quarters of the two lists differ |
| Customer queue, column "Return-rate rule" | The rule's rank for every customer: rank 1 is the rule's 553rd, rank 5 its 2,254th | The real cases never arrive |
| Customer queue, Comparison "Selected by the rule, not by the model" | The 209 the rule would have reviewed | The rule punishes loyalty |
| Customer queue, Show "Cleared heavy returners" | The customers above the 40.6 percent cutoff the model left out, each with the reason it was left out and what was not observed (no claims, no late returns, no links) | The loyal customer is left alone |
| Customer case, "Analyst rules that would have fired" | The five legacy rules against this case | A decision nobody can defend, then one with a record |
| Evaluation, "Abusers caught against alerts used" | First 58 alerts: 58 abusers against 19; 0 honest heavy returners against 39 | Same budget, three times the hits |
| Evaluation, "How often each ranking is right" | Rule 22.7 percent, analyst rulebook 32.4, model 74.3 | Four of five visits find nothing |

## 1d. Optional cold open: the week with the rule, live

The product can serve the return-rate rule on its own: that is what it does when no model has passed the gate. A
second instance in that state, on the same W5401 data, lets the audience see week one instead of hearing it.

```powershell
uv run arai baseline-rehearsal          # http://127.0.0.1:8011, keeps its own database; first start scores W5401 (about 15 s)
```

Run it beside `uv run arai local` (port 8000); the two never share a folder. Open http://127.0.0.1:8011 in a
second tab. What the room sees: the banner saying no candidate passed the gate and the return-rate ranking is
active; 284 names ranked by a return-rate percentile with nothing else in the score column; no comparison views
and no rule column, because there is nothing to compare against; and the first case, a high return rate with no
pattern that explains the rank. Say the week-one lines over it, ninety seconds at most, then switch to the port
8000 tab: "same Monday, the other list". If the second instance is not running, skip this and tell week one from
the premise slide; nothing else in the demo depends on it.

The instance's fixture is in git under `rehearsal/baseline` (see its README); its database sits beside it and is
not tracked, so its notes and runs persist between starts on one machine like the main instance's. `--fresh`
rebuilds the fixture from the current bundles and empties that database; `--port` and `--demo-world` change the
defaults.

---

## 2. Before the audience arrives

0. For the cold open (section 1d), start `uv run arai baseline-rehearsal` first and check http://127.0.0.1:8011
   shows the baseline banner and a scored run.
1. Start the application and wait for the health line (RUNBOOK.md section 2; every environment command is in its section 0):
   ```powershell
   uv run arai local
   curl.exe -s http://127.0.0.1:8000/api/v1/health
   ```
   `scoring_ready` and `promoted_model_ready` must both be `true` and `model_kind` must be `supervised`.
2. Open http://127.0.0.1:8000. The Overview must show 5,676 eligible customers and 284 selected for W5401. If it
   says no scored run is available, register and score W5401 (RUNBOOK.md section 4), about 15 seconds.
2b. Load the July and August snapshots of W5401 and the three August review outcomes (RUNBOOK.md section 4.1:
   `uv run arai snapshot W5401 --as-of 2026-07-09 2026-08-09` once, then with the instance up
   `uv run --no-sync python scripts\history_demo.py --load`). The Overview must then show
   **Since the previous snapshot of W5401 (09 Aug 2026)**: 249, 35, 22 and 2.
3. Sign in as **Arjun** on the sign-in page. Signing out and in as another character takes two clicks (**Sign out**
   at the top right).
4. Know the state the walkthrough leaves behind: the top-ranked case W5401-C03245 is already **in review**, opened
   by "Walkthrough reviewer" before sign-in existed, with a few walkthrough notes on it (newer ones by Ravi), and each
   walkthrough run since opens one more case as Ravi. That is useful (section 4.4 uses it); do not
   wipe it unless you want to open the case live.
5. Investigation memos read **Memo unavailable: no API key** unless `ANTHROPIC_API_KEY` is set in the environment
   the server runs in. Decide beforehand which version you are showing (section 4.3).
6. Close other tabs on port 8000 so the "Load more" paging and filters behave as rehearsed. Window width of
   1440 px matches the screenshots.

---

## 3. Running order

| Minute | Scene | Screen | Point made |
|---|---|---|---|
| before 0 | Cold open, optional | Baseline rehearsal instance, port 8011 | The week with the rule, seen live: a queue with nothing but a return-rate percentile |
| 0 to 2 | Why return rate is the wrong queue | Overview | 209 customers the model selects that the rule does not, and the reverse |
| 2 to 6 | The queue a reviewer sees | Customer queue | Tiers anchored to the budget, Escalate against Hold, rings grouped, the rule's rank beside the model's |
| 6 to 13 | One case end to end | Customer case, W5401-C03245 | Expected against actual, why the score, reason codes, notes, the second-reviewer rule |
| 13 to 17 | A ring, and the same ring last month | Customer case, W5401-C08645, then its History tab | Five linked accounts, one coordinated claim match; rejected on the August snapshot, back at rank 4 as September's own case |
| 17 to 19 | Products, not people | Style investigation | Two styles with similar return rates and different stories; whose problem each is |
| 19 to 23 | What the numbers rest on | Evaluation | Curves, precision against the rule, honest customers reviewed, final test, limits |
| 23 to 25 | How a new month gets in | Datasets & runs, then the Overview | Eight files, validation, the stepper; the same customers next month: 249 again, 35 new, 22 left |

If time is short, drop the ring scene and the upload scene; the story holds without them.

---

## 4. Scene by scene

### 4.1 Overview (0 to 2 minutes)

Screenshot `01-overview.png`.

Open on the Overview. The header strip names the run, the world and the model, and the page shows three
panels.

Say: "Ten thousand customers, of whom 5,676 have enough mature purchase history to be ranked at all. The team's
budget is five percent of those: 284 customers. The question is which 284."

Point at **Model and return-rate rule compared**:

- Selected by the model, not by the return-rate rule: **209**.
- Selected by the return-rate rule, not by the model: **209**.
- Both agree on **75**.

Say: "Three quarters of the two lists differ. The rest of the demo is about why the model's 209 are the better
use of a reviewer's hour, and how a reviewer can check that for themselves on every case."

Then point at **Refunds paid to the customers in each queue**:

| Queue | Refunds paid | Of which on transaction claims |
|---|---|---|
| Selected by the model (284) | INR 52.1 lakh | INR 20.5 lakh |
| Would be selected by the return-rate rule (284) | INR 57.7 lakh | INR 9.5 lakh |

Say: "The rule reviews more money. The model reviews more than twice the money paid out on claims where nothing
came back to inspect." Read the callout under the table: these are observed refunds, not losses, and a claim refund
is not proof of abuse.

Do not read the **Next customers to investigate** list aloud yet; click **View results** on it to move on.

### 4.2 Customer queue (2 to 6 minutes)

Screenshots `02-queue.png`, `03-queue-rule-only.png`, `04-queue-grouped.png`, `03-queue-cleared.png`.

The queue opens on the review set: 50 rows and a **Load more** button, 284 in total.

Walk the columns left to right:

- **Rank and score.** The score is a percentile against the training worlds, not a probability. The threshold for
  this run is 95.5; the queue is everyone at or above it.
- **Tier.** Every selected customer is **High**; the tiers are anchored to the budget, not to fixed bands, so High
  always means "in this period's queue". Hover the (?) for the one-sentence rule.
- **Gate outcome.** A presentation rule over the results, not a model output: **Escalate** (98 customers) is
  selected and in a ring or with the wardrobing indicator elevated; **Hold** (186) is selected otherwise.
- **Primary signals.** Chips such as "Two or more late returns, 4 of 13 item-return lines" or "Shares
  identifiers with 4 accounts". Each chip carries its denominator.
- **Return-rate rule.** The rule's own rank and whether the rule would have selected the customer.
- **Status.** New, in review, awaiting approval, approved, rejected.

Now three filter moves, each of which changes the address bar so a view can be sent as a link:

1. **Show: All customers**, then **Model and return-rate rule: Selected by the rule, not by the model.** The rows
   are the rule's 209: high return rates, no claim or timing pattern, and the model leaves them out of the queue.
   Say: "These are mostly the honest heavy returners the rule has always sent for review."
2. Back to **Show: Review set**, then **Group: by ring**. Members of the same ring sit under their first member,
   so a reviewer sees the group once. 86 of the 284 are ring members, across 30 rings; 19 more are household
   members, which the kind rule labels differently and the queue does not escalate for.
3. **Show: Cleared heavy returners.** Customers above the heavy-returner cutoff (a return rate of 40.6 percent in
   this run) whom the model did not select. Each row gives the reason it was left out, mostly "below the review
   threshold", followed by what the model did not see for that customer, for example "no claims matched by a linked
   account, no late returns, no linked accounts". Read one row aloud: the argument is in what is absent. Say: "This is the list the rule would have reviewed and the model
   argues you need not. It is on the page so that the argument can be lost as well as won." If asked how often the
   model is wrong here: in the functional review of this run, 21 of the 443 cleared heavy returners were abusers.

With any of these views on screen, point at **Export this view as CSV**: every row of the current filters, with
refunds, status and who opened or decided each case, for the returns-policy or service team. No note text leaves
the system that way.

Reset the filters, type the last five characters of the top customer's id (`03245`) into **Search customer ID**,
press Enter, and open the case with the keyboard (Tab to the link, Enter) to show the queue works without a
mouse.

### 4.3 One case end to end: W5401-C03245 (6 to 13 minutes)

Screenshots `05-case-evidence.png`, `06-case-returns.png`, `06-case-linked-accounts.png`, `07-case-notes.png`.

Rank 1, score 99.99, tier High, gate outcome Hold. The return-rate rule ranks this customer **553rd**: the rule
would never have shown this case.

**Evidence tab, top to bottom:**

- **Expected vs actual returns.** 12 units requested back of 29 purchased on mature sale lines, and INR 24,365
  refunded, none of it on transaction claims (the **Refunds paid** row). A customer buying
  the same products would be expected to request about 5.7, with a normal band of 1.5 to 10.0. The expectation is
  built from what was bought, so a customer who buys fit-sensitive jeans is not punished for a jeans return rate.
  Open **Why the expectation is where it is** to show the products behind the number.
- **Why this score.** Five families, each shown as the score the customer would have without that family. Without
  the **return timing** family the score drops from 99.99 to 51.7 and the customer leaves the queue; removing any
  other family changes almost nothing. Say the sentence on the panel: these are not parts that add up. Underneath,
  **Analyst rules that would have fired**: two of the five legacy rules fire here (return rate above the training
  90th percentile, refund ratio above it). The claim and link rules do not.
- **Claims, timing and composition.** The raw counts: 4 of 13 item-return lines late in their window, what was
  returned, which styles.
- **Wardrobing indicator: possible.** Two occasion-wear items returned in the last quarter of their window and
  two quality complaints on styles other buyers do not complain about. Read the limitation aloud: the indicator
  cannot establish that an item was worn, and it is independent of the model score.
- **Investigation memo.** Without an API key the panel says **Memo unavailable: no API key** and nothing else;
  that is the designed behaviour, not an error. With a key set, each selected customer gets a drafted memo after
  the run finishes, with a summary, key evidence, alternative explanations and a recommended action, every
  sentence of which has to pass a gate that checks it against the case's own numbers before it is stored; drafts
  that fail twice are stored as unavailable with the reason. Either way the memo is labelled a draft and sits
  below the evidence, never above it.

**Returns tab.** Every return request line with its reason **code** and group (fit, discretionary, transaction
claim, item complaint), day in the return window, and whether the item was received. No free text from the
customer is shown anywhere.

**Linked accounts tab.** This customer has none. Say: "Links are shown only when the record supports them: a
shared device, payment instrument or address, and only with the evidence. We will see a ring in a minute."

**Notes tab and the Decision panel.** The case is already **in review**, opened by "Walkthrough reviewer" before sign-in
existed, so that note carries an **unverified name** marker; notes written since say **(signed in)**. Notes are append
only and each one says which snapshot and run it was written on.

Now the second-reviewer rule, two ways:

- *Roles.* Signed in as Arjun (a reviewer), the Decision panel offers Open, Request approval and notes but no
  Approve or Reject: "Approving or rejecting needs the approver role." Open the next case marked **New** (queue,
  Status: New), write a note, press **Open case**, then **Request approval**.
- *Refusal.* Sign out and sign in as **Meera** (reviewer and approver). On a case Meera opens herself, **Approve** is
  refused in the server's own words: "You opened this case. A different reviewer must approve or reject it."
  (screenshot `07b-case-refusal.png`). Say: "The rule compares who signed in, not a typed name, and it lives in the
  server, not in the button."
- *Approval.* On the case Arjun opened, Meera writes "Reviewed the timing evidence; agree it needs the policy team"
  and presses **Approve**. The status tile turns to Approved with both names and times, each recorded under the
  person who signed in.

Press **Download case summary** at the top of the case: a plain-text hand-off with the evidence, every return
line with its status and refund, and the notes, for whoever acts on the decision.

Finish with **If the threshold moved**: drag the slider to show how many customers the queue would hold at any
score, and that the page tells you the budget this would cost. It changes nothing on the server.

### 4.4 A ring: W5401-C08645 (13 to 16 minutes)

Screenshots `06-case-linked-accounts.png` for a ring member, `04-queue-grouped.png`.

Go back to the queue, set **Group: by ring**, and open rank 4, W5401-C08645. Gate outcome **Escalate**.

- 33 units requested back of 56 purchased; expected about 10.9, band 4.9 to 16.8.
- Evidence chips: repeat claims (transaction claims on 4 of 34 return lines), linked claims, late returns, shares
  identifiers with 4 accounts.
- **Linked accounts: ring pattern.** Five accounts joined by shared device and payment identifiers; 4 of the 5
  are in this queue, one is ranked 1,228th and not selected. The panel shows every member with its own units,
  rank and tags, the edges between members with their types, and **one coordinated claim match**: two members
  claiming on the same product within days. Say: "The ring is a pattern in the record, and the page shows the
  record." Point at the edge types: this ring shares payment instruments, as 29 of the 31 rings in this run do.
  A group that shares only an address and a device, the shape of a household, needs two matching claims or two
  members in the queue before it is called a ring. Open W5401-C07084 to show the other side: a family at an
  address where parcels go missing, one matching claim, now labelled household and marked Hold (section 6).
- **Wardrobing indicator: elevated.** Three late occasion-wear returns and occasion-wear units far above what this
  customer's other returns predict.

Compare with rank 3, W5401-C05428, whose ring has 3 of 5 members in the queue and one member with insufficient
history: the linked-accounts panel still lists that member inside the ring, unranked, so the reviewer knows the
fifth account exists.

**The same ring last month (one minute).** Back on W5401-C08645, point at the callout above the tabs: *Rejected on
the 09 Aug 2026 snapshot by Ravi.* Open the **History** tab (screenshot `17-case-history.png`): rank 11 on 9 July,
rank 4 on 9 August, rank 4 now; Escalate each time; 26, 30 and 33 units requested back; the August review opened by
Asha and rejected by Ravi, with both notes on the **Notes** tab marked as written on the August snapshot. Say: "Next
month's export brings the same customers with the same identifiers, so the product remembers. But last month's
decision does not decide this month's evidence: the case is new again, with the decision on it." Then open
W5401-C05428 from the queue: its History shows it climbing from rank 38 to 23 to 3 while its August review waited
for a second reviewer.

### 4.5 Style investigation (16 to 19 minutes)

Screenshots `10-styles.png`, `08-styles-targeting.png`, `09-style-detail.png`.

Click **Style investigation**. 37 styles; 6 carry a verdict, 31 read **Normal**.

The panel at the top, **Two styles with similar return rates and different stories**, picks the pair
automatically: a **Quality issue** style (many returns name a quality reason; suggested owner Merchandising)
beside an **Abuse target** style (an ordinary product returned by an unusual set of buyers, linked accounts
claiming on it within days of each other; suggested owner Returns policy). Say: "Same return rate, opposite
action. One goes to the buying team, one goes to the returns-policy team, and the return-rate report cannot tell
them apart."

In this run the verdicts are: abuse target for Brand_B Jacket BB-JKT-02, Brand_C Jeans BC-JNS-01 and Brand_D
Dress BD-DRS-03; quality issue for Brand_B T-shirt BB-TSH-01, Brand_D Dress BD-DRS-02 and Brand_D Jeans BD-JNS-02.

Set **Verdict: Abuse target** and open BB-JKT-02:

- **Who is returning it.** 72 of 529 returners are flagged (13.6 percent, against 6 to 8 percent on normal
  styles), 33 of them ring members.
- **Reasons given.** Reason codes with line and unit counts; here the transaction-claim group (item not received,
  missing parts, wrong item sent, empty package) is unusually large for a jacket.
- **When in the window** and **How risky the returners are**, with denominators and the SKU drill-down.

### 4.6 Evaluation (19 to 23 minutes)

Screenshots `12-evaluation.png`, `10-evaluation.png`, `11-evaluation-truth.png`.

Click **Evaluation**. This is Priya's page: what the queue costs and what it rests on.

- **Abusers caught against alerts used.** Two curves on this very run, drawn from the simulation's truth, which
  the server exposes only here and marks as such: for every number of alerts, how many of W5401's 341 abusers
  each ranking catches and how many of its 440 legitimate heavy returners it drags in. The model's first 58
  alerts catch 58 abusers and no honest heavy returner; the rule's first 58 catch 19 and review 39 honest heavy
  returners. With the pointer off the chart the page reads the full budget: at 284 alerts the model's queue holds
  232 abusers and 18 honest heavy returners, the rule's 75 and 209.
- **Money behind the truth.** The Overview showed observed refunds. The functional review of this run
  (`reports/qa/2026-10-15/functional-review.md`) adds what only the simulation's truth can say: refunds paid on
  abusive return lines come to INR 23.7 lakh in the model's 284 against INR 8.0 lakh in the rule's 284. Say it as
  "the rule reviews more money, mostly honest money", and say that this figure comes from the truth, not a screen.
- **How often each ranking is right** (validation worlds, five percent budget):

  | Ranking | Precision | Recall | Honest heavy returners sent for review |
  |---|---|---|---|
  | Selected model | 74.3% (1,059 of 1,425) | 66.6% | 4.6% |
  | Analyst rulebook (reference) | 32.4% | 29.1% | 38.5% |
  | Return-rate rule | 22.7% (324 of 1,425) | 20.4% | 44.2% |

- **Final test**, run once on five held-out worlds: model 1,081 of 1,411 alerts correct (76.6 percent); rule 307
  of 1,411 (21.8 percent). Status: passed.
- **Where the model is wrong.** 366 false positives on the validation worlds; 31 percent of them are honest heavy
  returners, 29 percent honest buyers of defective products. Say: "These are the people a reviewer will meet and
  clear. The page counts them rather than hiding them."
- **Style signals and wardrobing indicator (report only).** Targeting signal precision 19 of 19, quality signal
  precision 15 of 15 on validation worlds; wardrobing elevated precision 96 percent at 13 percent recall. Say
  "report only" each time: none of these fed the model selection.
- **Limits.** Read two: the model leans on two signals (claims and timing) and how sharply they separate is a
  setting of this simulation; 168 of 1,758 abusers on the validation worlds have too little history to be ranked
  at all.
- **Run manifest** at the bottom: experiment id, seeds, bundle ids, contract version, code revision. Say: "Every
  number on this page can be regenerated from these seeds."

### 4.7 Datasets & runs (23 to 25 minutes)

Screenshots `02-datasets-and-runs.png`, `13-upload.png`.

Click **Datasets & runs**. Show, without necessarily doing it:

- **Register a snapshot.** The checklist of eight files (manifest and seven tables). Validation runs on upload
  against the data contract; a snapshot that fails is rejected whole and the page lists every broken rule.
- **Score with the active bundle.** The stepper shows the stages as the worker reports them: validate, features,
  eligibility, scoring, evidence, publish. Scoring 10,000 customers took 13 seconds on this run. A run can be
  cancelled from the page while it is in progress.
- **Scoring readiness** names the active bundle, the baseline it falls back to, and the worker's last heartbeat.

If you do register W5401 again, the server answers with the existing dataset (same manifest hash) and a new run
can be started with a fresh idempotency key; previous runs and notes stay.

**A new month.** The dataset list shows W5401 three times: **09 Sept 2026**, **09 Aug 2026** and **09 Jul 2026**, the
same 10,000-customer world exported on three dates (9,502, 9,791 and 10,000 accounts as new customers sign up). Say:
"Next month's export is not a new world. It is the next snapshot of the same customers." Go to the **Overview**
(screenshot `15-overview-history.png`): **Since the previous snapshot of W5401 (09 Aug 2026)**: 249 customers are in
both queues, 35 are new to this one, 22 left it, 2 were decided last month (1 rejected, 1 approved). Click **New to
the queue**: the queue filters to those 35, each marked "new to the queue since 09 Aug 2026 (rank ... then)".
For the money question: in the simulation, 28 of those 35 are abusers and 8 of them first acted after 9 August
(offline, from the simulation's truth; `records/2026-10-16-monthly-snapshots.md`), not on screen.

---

## 5. Closing (one minute)

"Three things to take away. The queue is built from what customers return and when, not from how much, and on
these worlds that triples the share of reviews that find something while cutting honest heavy returners in the
queue from 44 percent to under 5. Every case shows its denominators, its expectation and the record behind each
link, so a second reviewer can disagree with the first on the page. And everything here is simulated: the next
step is the same pipeline on a real month of returns, with the same evaluation page to say what changed."

---

## 6. Questions to expect

| Question | Answer |
|---|---|
| Is the score a probability that this customer is abusing returns? | No. It is a percentile against the training worlds. The page says so wherever the score appears, and no screen uses the words fraud or confidence. |
| Why is every customer in the queue "High"? | Tiers are anchored to the review budget: High is the queue, Medium is a score of 90 or above outside it, Low is the rest. Switch **Show** to All customers to see Medium and Low. |
| What decides Escalate against Hold? | A stated rule over the results, printed on hover: selected and in a ring, or with the wardrobing indicator elevated, is Escalate. It is not a model output and changes no rank. |
| Who can approve a case? | A signed-in approver who did not open it; the server compares user ids, so one person cannot approve their own case under another name. On a laptop the people come from the development login; a shared deployment signs in through Keycloak single sign-on, with roles from Keycloak groups (step 2 of `docs/design/authentication-and-roles.md`). |
| Where do the memos come from? | A drafting model called after the run, only when an API key is configured, with each draft checked against the case's own numbers before it is stored. Without a key the panel says so and shows nothing else. |
| Why are the bundle ids different from the experiment record? | The manifest hashes the dependency lock and library versions as well as the code and seeds. Scores, ranks and selections reproduce exactly; the ids differ when the environment does. |
| Can this run on our data? | The data contract (manifest plus seven tables) is the interface; the pipeline, the evaluation page and the final-test discipline are the same. The results on this page are from a simulator and say nothing yet about real returns. |
| Why is this family not marked as a ring? (W5401-C07084) | Since contract 1.14.0 a group whose accounts share only an address and a device needs two matching claims or two members in the queue to be a ring. Family members at an address where parcels go missing can both claim "not received" on the same order within days for honest reasons; under the first rule 4 such families in this run were called rings. The revision was checked on the five validation worlds before it shipped (`records/2026-10-16-community-kind-rule-revision.md`); it gave up one real coordination group out of 183, whose member stays in the queue as Hold. |
| What happens next month? | The next export of the same customers registers as a new snapshot of the same world. Each snapshot is scored on its own; notes and earlier decisions stay with the customer; the queue marks who is new, who is back and who was decided before; the review starts afresh each month so last month's reading never decides this month's evidence. Different worlds or retailers are never linked. |
| Can we hand this list to our policy team? | Yes: **Export this view as CSV** on the queue (every row of the current filters, with refunds and who decided each case, no note text), and **Download case summary** on a case. |
| What happens when no model passes the gate? | The baseline return-rate ranking is served, the banner says why, the score column is relabelled a return-rate percentile, and the comparison views disappear. `tests/e2e/fallback_check.py` demonstrates it. |

---

## 7. Words to use and words to avoid

Use: selected for review, evidence, pattern in the record, expectation, denominator, draft memo, simulated world.

Avoid: fraudster, fraud score, confidence, proof, guilty, the model knows. The screens do not use them and the
demo should not either.
