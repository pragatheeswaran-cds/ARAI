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
