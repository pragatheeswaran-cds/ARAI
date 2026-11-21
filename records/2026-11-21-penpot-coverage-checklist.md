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

## Open decisions

1. **Contact data.** Email, phone and region would have to be added to the generator and the input contract, or
   removed from the design. Recommendation: remove them, since the spec treats IDs as opaque and carries no
   personal data.
2. **Case model.** Keep "one customer per run" and relabel the design, or introduce a real case entity with its own
   ID and created date. Keeping the current model is far less work.
3. **Time range.** The daily trends and "last 30 days" need a new time-series aggregation over the input tables.
   Without it, the Overview and SKU trend charts cannot be built.
