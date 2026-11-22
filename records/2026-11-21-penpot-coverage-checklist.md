# Penpot mockup coverage checklist

Date: 2026-11-21
Branch: `penpot-implementation` (cut from `main` at `2edaa4e`)

## What this is

A check of whether the current application has the information needed to build the six screens drafted in the
Penpot file "ARAI (Edit)", Page 1:

https://design.penpot.app/?screen=workspace&team-id=40e06342-8830-80d6-8008-989828484581&file-id=c828d3cf-7d4e-8145-8008-9c8e3df5bfda&page-id=40e06342-8830-80d6-8008-98985cbd947a&board-id=99c32043-0e20-8090-8008-99eebfd8f725

Boards read: Overview Dashboard, Risk Queue, Case Investigation, Customer Intelligence, SKU Intelligence, Profile
Section. (The seventh board, "All Screen View", is a contact sheet of the others.)

Compared against: the API routes in `src/arai/service/api.py`, the response builders in `src/arai/service/views.py`,
the result tables in `src/arai/service/results.py`, and the input schema in `final-spec/contracts/data-schema.yaml`.
The application was not run for this check.

Legend: ✅ covered, 🟡 partly covered, ❌ not covered.

## Verdict

The current app cannot implement all six screens as drafted. About half the elements are covered; the rest need
new aggregations, new workflow concepts, or data the input tables do not contain.

- Mostly covered: Risk Queue, Case Investigation, Customer Intelligence.
- Partly covered: Overview Dashboard, SKU Intelligence.
- Mostly not covered: Profile.

## Gaps that cut across every screen

| Gap | Why it matters |
|---|---|
| No date range ("Last 30 Days", "vs previous 30 days") | The app scores one snapshot per run. It can compare with the previous snapshot, but has no daily or monthly series. |
| No customer contact data (email, phone, region) | The input `customer_master` has only ID, signup date, status, loyalty tier and marketing channel. |
| No "case" entity (Case ID, Return ID) | A case in the app is one customer in one run, not one return. |
| Three risk levels, not four | The app has High / Medium / Low; the design adds Critical. |
| Currency | Data is INR; the design shows dollars. |
| Five nav items have no board and no page | Investigations list, Network Graph, Analytics, Configuration, Audit Log. The notification bell also has nothing behind it. |

## 1. Overview Dashboard

| Element | Status | Note |
|---|---|---|
| Suspected customers count | ✅ | Selected-for-review count per run |
| Risk level distribution | ✅ | Tier counts and score distribution (no Critical) |
| Change vs previous period | 🟡 | Previous-snapshot comparison only |
| Abuse pattern distribution | 🟡 | Evidence tags, ring kind and wardrobing exist; no aggregate endpoint, and labels differ |
| Total returns | 🟡 | In the input data; not exposed as a run total |
| Return fraud rate | ❌ | Not computed |
| False positive rate | ❌ | Only exists for experiments with truth labels |
| Fraud loss trend (daily) | ❌ | No time series |
| Fraudulent returns by channel | ❌ | `return_channel` is in the input but never aggregated |

## 2. Risk Queue

| Element | Status | Note |
|---|---|---|
| Customer ID, risk score, risk level | ✅ | |
| Patterns column | ✅ | Evidence tags and primary signals |
| Accounts (linked) | ✅ | Supported neighbours / community size |
| Search, risk-level, pattern and status filters | ✅ | Search is by customer only, not SKU |
| Tier count tiles, pagination | ✅ | Cursor paging, so no "page 124" jump |
| Status | 🟡 | App states are in review / awaiting approval / approved / rejected, not Open / Escalated / Closed |
| Refund / spend, return % | 🟡 | Refunded amount and returned vs purchased units exist; spend is not exposed |
| Case ID, created date | ❌ | No case entity |
| Date range filter | ❌ | |
| Row checkboxes (bulk action) | ❌ | No bulk endpoint |

## 3. Case Investigation

| Element | Status | Note |
|---|---|---|
| Customer ID, risk score, status badge | ✅ | |
| Risk indicators with values vs expected | ✅ | Signals, basket expectation, rules fired |
| Case timeline | ✅ | Order and return events; review events come from the reviews list |
| Assigned analyst, current status, resolution date | ✅ | Opened-by, workflow state, decided-at |
| Recommended action, decision notes | ✅ | AI memo and review notes |
| Clear / Escalate buttons | ✅ | Map to reject / request approval / approve |
| Refund amount | ✅ | Total refunded and claim refunded per customer |
| Channel | 🟡 | In the input orders; not in the case response |
| Refund status, amount at risk | ❌ | |
| Case ID, Return ID, region, priority badge | ❌ | |

## 4. Customer Intelligence

| Element | Status | Note |
|---|---|---|
| Customer ID, risk score and level | ✅ | |
| Total returns, refund amount | ✅ | |
| Return reason mix | ✅ | Reason codes on timeline events |
| Product concentration by category | ✅ | Customer's styles carry category |
| Risk summary sentence | ✅ | AI memo summary |
| Notes tab, return history tab | ✅ | Reviews; timeline and snapshot history |
| Network tab / "View Network Graph" | 🟡 | Community members and edges are in the API; no graph is drawn |
| Return trends by month, last return, avg latency | 🟡 | Derivable from the timeline in the browser; not provided ready-made |
| Peer comparison | 🟡 | Basket expectation gives expected vs actual units; not the three metrics drawn |
| Linked instruments (devices, addresses, payments) | 🟡 | Shared identifier types with neighbours exist; the customer's own counts do not |
| Total orders | 🟡 | In the input; not confirmed as exposed by the API |
| Email, phone, region, search by email/phone | ❌ | Not in the data |

## 5. SKU Intelligence

| Element | Status | Note |
|---|---|---|
| SKU table: category, orders, returns, return rate | ✅ | Kept at style level, with SKUs beneath |
| Reasons for returns | ✅ | Reason codes per style |
| Supporting / contradictory signals | ✅ | Quality signal, targeting signal, claim and damage shares, linked claimers |
| Linked customers tab | ✅ | Flagged returners, ring returners |
| Risk level per SKU | 🟡 | A state plus two flags, not High / Medium / Low |
| Expected rate and deviation | 🟡 | Raw and shrunk return rates exist; category average is not exposed |
| KPI tiles, top categories, risk distribution | 🟡 | Computable from the style list; no aggregate endpoint |
| Customer concentration (top 1% / 5% / 10%) | ❌ | |
| AI assessment per SKU | ❌ | The memo is per customer only |
| Monthly return-rate trend, forecast tab | ❌ | |
| Export | ❌ | Export exists for the customer queue only |

## 6. Profile

| Element | Status | Note |
|---|---|---|
| Name, email, role | ✅ | From `/me` |
| Last login, account created, active status | 🟡 | Stored for the admin user list; not returned by `/me` |
| Edit personal information, security tab | ❌ | Identity is managed in Keycloak, not the app |
| Employee ID, department, region, phone, photo | ❌ | Not stored |
| Preferences tab | ❌ | |

## In the app but not in the design

Datasets (upload and runs), Evaluation, and People and access have no board. They need a place in the new
navigation or are dropped.

## Decisions (2026-11-21, by the project owner)

| # | Topic | Decision |
|---|---|---|
| 1 | Case model | Customer-wise, as planned: a case is one customer in one run. Screens show a generated case ID and the customer's returns inside the case. Return ID, refund status and amount at risk are dropped. |
| 2 | Contact data | Add region, email and phone to the data. Email and phone also become ring signals: two more shared identifiers in the link graph, beside address, device and payment. Needs generator changes, new features and a new experiment run. |
| 3 | Time range | Trends inside the snapshot: a backend aggregation of orders, returns and refunds by day from the snapshot's own history. The date picker filters charts and totals; risk scores stay as of the snapshot cutoff. |
| 4 | Risk levels | Four levels everywhere: Critical, High, Medium, Low. Places in the design that show three are design bugs. |
| 5 | Critical rule | Critical = selected for review (High) and a member of a detected ring. |
| 6 | Case status | Simplify to the design: Open, In Review, Escalated, Closed. The two-person approval step is removed; the analyst's Clear or Escalate is the decision. |
| 7 | After escalate | Clear Case closes the case. Escalate Case sets Escalated; a lead or admin later records the fraud team's outcome and the case becomes Closed. |
| 8 | Navigation | Map onto existing pages: Investigations = the cases I have open; Network Graph = a new ring graph page; Analytics = the existing Evaluation page; Configuration = existing Datasets and People; Audit Log = sign-in events plus case decisions. |
| 9 | Product screen | Style level, with SKUs listed inside each style. Add category average and deviation, a four-level product risk rating, customer concentration, monthly return trend and export. The assessment text is rule-based from the quality and targeting signals. |
| 10 | Fraud metrics | Both: "suspected" numbers from flagged customers and analyst decisions for live data, and true fraud rate and false positives where the snapshot has a published truth file. |
| 11 | Profile | Read-only from sign-on: name, email, role, status, account created, last login. Edit, Change Photo and Security link out to Keycloak. Employee ID, Department, Phone and the Preferences tab are removed. |
| 12 | Small items | Build the notification bell, bulk actions in the queue, and keep the queue export button. |
| 13 | Currency | Indian rupees everywhere. Dollar amounts in the Penpot boards are a design bug. |
| 14 | Penpot file | Code only. Differences between the app and the boards are logged in the repo for the designer; the Penpot file is not edited. |
| 15 | Frontend | Restyle and extend the existing React app in place; keep routes, API client and tests. |

## Build order

1. New shell and navigation (dark top bar, left sidebar).
2. Risk Queue, Case Investigation and Customer Intelligence, with the workflow change.
3. Overview Dashboard and Product screen, with the new aggregations.
4. Profile, notification bell, bulk actions.
5. Email, phone and region in the data and the model, with a new experiment. The contact fields appear on the
   screens at this step.

## Differences from the Penpot boards (log for the designer)

Kept up to date as each step is built (decision 14).

### Step 1: shell and navigation

- The sidebar lists only pages that exist: Dashboard, Risk Queue, Products / SKU, Analytics, Configuration, and
  People & access for administrators. Investigations, Customers, Network Graph, Audit Log and Profile are added in
  the step that builds them.
- Analytics opens the existing Evaluation page; Configuration opens the existing Datasets & runs page.
- The top bar shows "Signed in as <name> (<roles>)" with a Sign out button instead of the "Analyst" dropdown. The
  dropdown arrives with the Profile page (step 4), and the notification bell with it.
- Kept from the existing app, not drawn in Penpot: the "synthetic data only" strip above the top bar, the run
  context header and run strip above each page, the fallback banner, and the footer disclaimer.
- Page contents (cards, tables, badges) still use the earlier green styling until their screen is restyled.

### Step 2: workflow, Risk Queue, Case Investigation

- Workflow (AM-76, contract 3.0.0): Open, In Review, Escalated, Closed. A closed case shows how it ended: cleared,
  confirmed after escalation, or not confirmed after escalation. Only a lead (the approver role) closes an escalated
  case; an admin cannot, because admins do not review cases in this app (decision 7 said "lead or admin").
- No screen uses the word "fraud", following the app's rule that signals are not proof of misconduct: the board's
  "Escalate to Fraud Team" reads "escalated to the investigation team", and outcomes read "confirmed after
  escalation" and "not confirmed after escalation".
- Case ID is the customer's own number ("CASE-03245" for W5401-C03245), since a case is one customer in one run.
  There is no Return ID, Region, Channel, Refund Status or Amount at Risk.
- Risk Queue: no Date Range filter and no count tiles yet (both come with the step 3 aggregations); no row
  checkboxes yet (step 4). "Observed Spend" and "Refund / Spend" are shown as "Refunded" in rupees; "Created" is
  dropped. The app's own columns (Recommendation, Return-rate rule, Latest note) and filters ("More filters") are kept.
- Risk Queue paging is "Load more", not numbered pages.
- Case Investigation: Case Summary and Financial Impact cards lead the page; the app's evidence tabs, memo, decision
  panel and threshold slider follow in the earlier layout. The Actions menu is not built; Clear Case and Escalate
  Case are in the Decision panel, with a required note.
- Customer Intelligence is not built yet: the customer link in the queue opens the case page.

### Steps 3 and 4: Dashboard, Products, Customer Intelligence, workspace pages (AM-77, contract 3.1.0)

- Overview Dashboard: the period picker (30, 90, 180, 365 days, whole history) filters the totals and the trend; risk
  levels and the queue are always as of the snapshot. "Return Fraud Rate" is shown as "Suspected Return Rate" (return
  lines of customers selected for review) and "Fraud Loss Trend" as "Suspected Loss Trend" (refunds paid to them),
  because a selected customer is not a confirmed case. "False Positive Rate" is cleared or not-confirmed cases over
  closed cases, and reads n/a until a case is closed. A separate panel shows the true abuse rate and true false
  positive rate when the snapshot's world has published synthetic truth (decision 10).
- Abuse Pattern Distribution uses the app's own observed patterns (claims, linked claims, late returns, returns above
  expectation, shared identifiers, ring, wardrobing indicator), not the board's five labels.
- Channels are the return channels in the data (courier pickup, drop-off point, post), not Online / In-store / Mobile.
- All money is in rupees, with lakh and crore short forms.
- The earlier Overview panels (next customers, workspace context, previous snapshot, refunds, model against the rule)
  stay below the dashboard.
- Risk Queue: count tiles are Total Cases, Critical / High, Medium, Low. Bulk actions are Open, Clear and Escalate with
  one required note; closing an escalated case stays a single-case action for a lead.
- Product / SKU Intelligence: rows are styles. The board's tabs (SKU List, Product Analysis, Abuse vs Defect Analysis,
  Linked Customers, Trends) are sections of the list page and the style page instead. "Expected Rate" is the category's
  return rate, with the deviation in percentage points. The assessment is rule-based text, labelled as such. No
  forecast. Export is a CSV of the style list.
- Customer Intelligence: a new page under Customers. Tabs are not built: Overview content is on the page, and Return
  History, Behaviour, Network and Notes link to the investigation page and the Network Graph. Peer Comparison shows
  return rate, units against the basket expectation and the run's heavy-returner line. Linked Instruments shows the
  accounts sharing identifiers by type, not the customer's own device, address and payment counts. Email, phone and
  region wait for step 5.
- Investigations lists the cases the signed-in person has open. Network Graph draws one group of linked accounts at a
  time, with the list of groups beside it. Audit Log lists case workflow events; sign-in events stay under People &
  access for administrators. Analytics is the Evaluation page; Configuration is Datasets & runs.
- Profile is read-only: name, role, email, status, account created, last login, session end. No photo, employee ID,
  department, phone, Security or Preferences tab.
- Notifications cover three events of the last thirty days: a case you opened was closed by someone else, a case was
  escalated (for a lead), a run was scored.

## Decisions for experiment 5 (2026-11-22, by the project owner)

Asked one at a time after steps 1 to 5a were built. They complete decision 2 (email and phone as ring signals).

| # | Topic | Decision |
|---|---|---|
| E1 | Run it | Yes: run experiment 5, with new sealed worlds and one run of the final test. |
| E2 | Link rule | Phone and mailbox are identifier types beside address, device and payment method. Two accounts are linked when they share any two of the five, as before; every link that exists today stays valid, and new links and rings can form through phone or email. |
| E3 | ID, seeds, folder | EXP-20261122-05; seeds 6101-6110 train, 6201-6205 validation, 6301-6305 test, 6401 demo, 6501-6511 stress; everything under `data/EXP-20261122-05`. Experiment 4's worlds, model and database stay untouched. |
| E4 | Gate | The five legs of experiment 4 plus a sixth: honest household members who share a phone or a mailbox are not reviewed more often by the model than by the return-rate rule. |
| E5 | Simulator | Keep the contact-sharing settings of AM-78 for training, validation and test (ring: phone 0.60, mailbox 0.50; household: phone 0.30, mailbox 0.05; recycled numbers 0.5 percent). Add stress worlds where rings share less (0.30, 0.25) and households share more (0.50, 0.15). |
| E6 | On a pass | Publish experiment 5 in its own folder and serve it, with its own demo world (W6401) and database. On a fail, experiment 4 stays active. |
| E7 | Who closes an escalated case | Leads only (the approver role), as built. This replaces "lead or admin" in decision 7. |
| E8 | Merge to `main` | After experiment 5 has its result: the whole of `penpot-implementation` is merged and pushed. |

### Decision E9 (2026-11-22): no experiment 5; the links are evidence

The contract and code of experiment 5 were written and reviewed independently before any world existed
(`records/2026-11-22-contact-links-design-review.md`). The review measured that the wider graph changes one model
feature for about ten customers in ten thousand, so the experiment could not have shown what the links add. Asked
how to proceed, the owner chose **"Show the links, keep the model"**.

| Decision | Status after E9 |
|---|---|
| E1 run experiment 5 | Withdrawn. No world, contract or bundle of it exists |
| E2 link rule | Kept, in the evidence layer: phone and mailbox are a fourth and fifth identifier type, any two shared make a link, every earlier link stays valid. The model's own graph stays the three order identifiers |
| E3 seeds, E4 sixth gate leg, E5 stress worlds, E6 publish on a pass | Withdrawn with the experiment |
| E7 leads only close an escalated case | Stands |
| E8 merge to `main` | Stands: after this work, the branch is merged and pushed |

What an analyst now sees where a snapshot carries contact details (AM-79, API contract 3.3.0): linked accounts,
groups, rings, the Critical level and the Network Graph include links through a shared phone or mailbox. Scores,
ranks and the selection are unchanged, and a test requires that.
