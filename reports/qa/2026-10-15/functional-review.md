# Functional and product review, 15 Oct 2026

A review of ARAI from the point of view of a returns-operations owner preparing to sell it: every claim the demo
script and deck make was recomputed independently, and every number a reviewer sees on the case screens was
reconciled with the raw operational tables. The review ran against `arai local` on API contract 1.13.0, world
W5401 scored on experiment 4 (run `run-ed95a0e2fd3e49a69d4d`), with the simulation's private truth for W5401 as the
reference. Nothing in the product was changed by this review.

**Verdict.** The core selling claims hold on the demo world, often more strongly than the deck states, and the
evidence the reviewer sees is exact. One product behaviour would hurt in front of a returns buyer (families
labelled as fraud rings), four lines of demo wording are inaccurate or ambiguous, and four product gaps will come
up in any buyer conversation.

Severity used below: **High** = would mislead a buyer or a reviewer about a customer; **Medium** = a screen or a
demo claim does not say what is true; **Low** = wording or polish.

## 1. Method

| Part | What was done | Script |
|---|---|---|
| Selling claims | Precision, recall, honest heavy returners, the two 209-customer comparison lists, the curve points, the demo's hero cases, rings, wardrobing indicator and style verdicts, each recomputed from W5401's private truth | `functional_check.py` (part A) |
| Reviewer evidence | Support counts for all 10,000 customers, eligibility, the rule's rank, the evidence chips for the 284 queued customers, 20 timelines, 448 linked-account edges, 37 style rows, the basket expectation, each recomputed from the seven operational CSV files | `functional_check.py` (part B), plus follow-up recounts |
| Returns-process integrity | 17 copies of W5401 each breaking one rule of the returns process, fed to the snapshot validator, plus one legal edge case | `domain_rules.py` |
| Product questions | Refund value in each queue, sensitivity of the rule baseline to its tie-break, what the screens say about withdrawn requests and about the decision buttons | ad hoc queries, recorded in the findings |

Both scripts are read-only. `functional_check.py` needs a running instance with a scored W5401 run and the
private truth under `data/EXP-20261005-04/private/W5401`; `domain_rules.py` needs only the W5401 operational
files.

```powershell
uv run arai local                                                        # terminal 1
uv run --no-sync python reports\qa\2026-10-15\functional_check.py http://127.0.0.1:8000
uv run --no-sync python reports\qa\2026-10-15\domain_rules.py
```

`functional_check.py` counts withdrawn requests in its first recount (part B1 to B4) and so reports differences
that are explained in section 3; the follow-up recount that excludes them is described there.

## 2. Selling claims, recomputed on W5401

| Claim | Deck or script says | W5401, from truth |
|---|---|---|
| Model queue precision | 74.3% on validation worlds, 76.6% on the final test | **81.7%**, 232 of 284 |
| Return-rate rule precision | 22.7% on validation worlds | 26.4%, 75 of 284 |
| Recall of eligible abusers | 66.6% (validation) | model 68.0%, rule 22.0% (of 341) |
| Honest heavy returners sent for review | 4.6% against 44.2% | **4.1% against 47.5%** (18 and 209 of 440) |
| First 58 alerts | 58 abusers, 0 honest heavy returners, against 19 and 39 | identical |
| Full budget, 284 alerts | | 232 and 18 against 75 and 209 |
| The model's 209 not chosen by the rule | mostly abusers | 167 abusers (79.9%) |
| The rule's 209 not chosen by the model | mostly honest heavy returners | 199 honest (95.2%) |
| Chosen by both | | 65 of 75 abusers |
| Ranks 1 to 5 shown in the demo | strong cases | all five abusers; rank 1 made six temporary-use (wardrobing) returns; rank 4 is a coordinated-group member with contents claims, non-receipt claims and wardrobing |
| Escalate and Hold | a stated presentation rule | Escalate right 95.0% (96 of 101), Hold 74.3% (136 of 183) |
| Wardrobing indicator | report only, high precision, low recall | elevated 93.8% and possible 92.6% precise; flags 33% of temporary-use abusers |
| Style verdicts | 3 quality, 3 abuse target | all 6 correct against the product truth; 1 of 4 targeted styles not flagged (finding 6) |
| Rings | patterns in the record | 31 of 35 contain abusers (finding 1) |
| Basket expectation | calibrated expectation | 24,802 expected units against 24,850 actual over the eligible; 84% of customers inside their normal band |

By abuse type (eligible customers), the model catches, and the rule catches:

| Abuse type | Eligible | Model | Rule |
|---|---|---|---|
| Deceptive non-receipt claims | 149 | 71.8% | 31.5% |
| Deceptive contents claims | 215 | 67.0% | 25.6% |
| Temporary use (wardrobing) | 120 | 76.7% | 15.8% |
| Coordinated action | 110 | 85.5% | 25.5% |

27 abusers have too little history to rank (fewer than three mature sale lines); the Evaluation page already
states this limit.

**The baseline is a fair opponent.** 121 customers share the return rate at the rule's cut (50%). Breaking that tie
by most requested units, by fewest, or limiting the rule to customers with eight or more purchased units moves the
rule's precision between 26.4% and 27.1%. The comparison does not depend on how the rule's ties are broken.

**Honest customers a reviewer will meet in the queue (52 of 284):** 14 received a defective unit, 18 had genuine
non-receipts (8 of them two or more), 10 are household members, 5 are size bracketers, 4 are honest heavy
returners (groups overlap). 47 of the 52 are marked Hold; the 5 marked Escalate are the subject of finding 1.

## 3. Reviewer evidence against the raw tables

Every check below matched exactly once two definitions were applied, both of which are the product's documented
behaviour.

| Evidence | Checked | Result |
|---|---|---|
| Support counts (mature sale lines, purchased units, requested units) | all 10,000 customers | exact, with withdrawn requests excluded |
| Eligibility (three or more mature sale lines) | all 10,000 customers | no disagreement |
| The return-rate rule's rank | 5,676 eligible customers | ordered by raw return rate with no inversion; `baseline_selected` equals rank within the budget |
| Late-return and claim chips | the 284 queued customers | exact, with withdrawn requests excluded |
| Timelines: event counts, day in window, return window, refund amount | 20 queued customers | exact; transaction claims carry their own event type `transaction_claim` |
| Linked-account edges | 448 edges in 81 communities | every edge backed by at least two shared identifier types, each value shared by no more than 25 accounts |
| Coordinated-claim flags on edges | the same 448 edges | match a recount of claims on the same style within seven days |
| Style rows: returners, flagged returners, reason-code lines and units | all 37 styles | exact, with withdrawn requests excluded |

The two definitions:

- **Withdrawn requests are not requests.** All 625 differences in the first recount of requested units are exactly
  the customers with a withdrawn request line; excluding them gives zero differences. Rejected requests do count,
  which is sound for abuse detection (an attempt is evidence). The screens do not say this; see finding 4.
- **Transaction claims are a separate timeline event type.** The first recount looked only for `return_request`
  events; claims appear as `transaction_claim` events with the same fields.

## 4. Returns-process integrity on upload

The validator rejected every snapshot that broke a rule of the returns process, each with the rule a returns
analyst would expect.

| Broken rule | Validator |
|---|---|
| Returned quantity above the purchased quantity | rejected, Q001 |
| The same unit refunded twice | rejected, A002 and Q001 |
| Item return requested before delivery | rejected, C003 |
| Refund three times the price paid | rejected, A002 |
| Return header total not the sum of its lines | rejected, A002 |
| Return filed by a customer who did not place the order | rejected, F002 |
| "Not received" claim with the item marked received back | rejected, R002 |
| Return against a sale line that does not exist | rejected, F001 |
| Duplicate return line key | rejected, K001 |
| Negative returned quantity | rejected, T004 |
| Reason code outside the codebook | rejected, F001 |
| Return requested after the snapshot cutoff | rejected, C003 and R001 |
| Sale line delivered before it shipped | rejected, C002 |
| Item return on a line that was never delivered | rejected, A002, F002 and F003 |
| Money refunded on a rejected return line | rejected, A002 |
| Returned SKU differs from the SKU sold | rejected, F003 |
| Request after the window closed, rejected with no refund (legal) | accepted, as it should be |
| Free-text reason supplied | accepted: `reason_text` is a contract field marked evidence-only and never read or shown by the service |

The real W5401 data is clean on the same rules: no over-returns, no double refunds, no refund above the price
paid, no refund on rejected or withdrawn lines, every header total equal to its lines, and no non-receipt or
empty-parcel claim marked as received back. All 1,011 "not received" claims sit on lines the carrier marked
delivered (see gap 4).

## 5. Findings

### Finding 1 (High): families with a poor delivery address are labelled fraud rings

4 of the 35 communities labelled *ring* contain no abuser. Each is a single household (one household id in truth)
whose accounts share an address and a device, and whose members had genuine carrier failures. Two members claimed
"not received" on the same style within seven days, which is one coordinated-claim match, and one match is enough
for the kind rule (decision D3) to say *ring*. Four of the five honest customers marked **Escalate** come from these
four communities.

| Community | Members | In the queue | Shared identifiers | Matches | Genuine non-receipts per member |
|---|---|---|---|---|---|
| W5401-L1B37F7382819 | 2 | 1 (rank 216) | address, device | 1 | 1 and 4 |
| W5401-L8837EFCAF00B | 2 | 1 (rank 166) | address, device | 1 | 1 and 2 |
| W5401-LB468D504E82F | 3 | 1 (rank 181) | address, device | 1 | 2, 1 and 0 |
| W5401-LC36C354B2FBA | 2 | 0 | address, device | 1 | 1 and 2 |

The observable data separates them cleanly:

| | True rings (31) | False rings (4) |
|---|---|---|
| At least one edge shares a payment instrument | 29 | 0 |
| Two or more members in the queue | 29 | 0 |
| Two or more coordinated-claim matches | 14 | 0 |
| Every edge is address and device only | 2 | 4 |

*Why it matters.* A household at an address where parcels go missing is the textbook honest pattern in returns
operations. Escalating it as a ring is the false positive most likely to reach a customer complaint, and the demo
script currently says "a household looks different: shared address, ordinary returns, and the kind rule says
household", which these four cases contradict.

*Recommendation, needs a decision.* When every edge of a community is address and device only, require two or more
coordinated-claim matches or two or more members in the queue before calling it a ring. On W5401 this removes all
four false rings and keeps 29 to 31 of the true ones. It changes decision D3, so it needs a decision row, an offline
check like `records/2026-10-15-community-kind-check.md`, and a re-score.

### Finding 2 (Medium): the cleared view's reason rarely explains anything, and the demo says it does

Of 443 cleared heavy returners (eligible, outside the queue, at or above the 40.6% cutoff), 434 carry the reason
"below the review threshold", 8 "size bracketing" and 1 "returns at the rate the basket predicts". The demo script
(section 4.2) and slide 8 say every row shows "a return pattern inside the basket's expectation".

The cleared list itself is sound: only 21 of the 443 (4.7%) are abusers. The weakness is the explanation. "Below the
threshold" restates the decision; a returns analyst will ask what the customer did *not* do.

*Recommendation.* Correct the demo wording now. In the product, name what is absent for these customers (for
example "no transaction claims, no late returns, no linked accounts"), which the stored evidence tags already
support.

### Finding 3 (Medium): two narrative lines overstate

| Line in the demo script (section 1b) | W5401 |
|---|---|
| "A customer who claims 'parcel not received' on one order in five has an ordinary return rate" | 49.7% of non-receipt abusers are below the heavy-returner cutoff; their median return rate is 41% against 17% for all eligible customers |
| "A ring of five accounts sharing a card looks like five light returners" | 58.2% of coordinated members are below the cutoff; median return rate 37% |

A buyer's analyst can refute "ordinary" and "light". The accurate statement is still strong: half of the
non-receipt abusers never cross the heavy-returner line and the rule catches 31.5% of them; more than half of the
ring members never cross it and the rule catches 25.5% of them.

### Finding 4 (Low): the screens do not say that withdrawn requests are excluded

The evidence tiles and chips exclude withdrawn requests (section 3), while the Returns tab lists every request line
with its status. On the rank-3 case (W5401-C05428) the tile reads 21 requested units and the Returns tab shows 22
rows; the 22nd is a withdrawn `late_delivery` request. A reviewer reconciling the two will think a number is wrong.

*Recommendation.* Label the counts "excluding withdrawn requests" and mark withdrawn rows on the Returns tab as not
counted.

### Finding 5 (Low): "Approve" and "Reject" do not say what is approved

The Decision panel offers Open, Request approval, Approve and Reject, and says the decision is "yours and a second
person's", but never states what an approval means. In returns operations "approve" usually means approving the
return or the refund.

*Recommendation.* Name the decision in returns terms, for example "Confirm for policy action" and "Close as
legitimate", or state the meaning beside the buttons. The API values can stay.

### Finding 6 (Low): one of four targeted styles is not flagged

BA-TSH-02 is targeted in truth and reads "Normal". All six verdicts shown are correct, so this is a coverage limit,
not an error. The demo should not imply that every targeted product is found; the deck's report-only figures
already speak of recall.

## 6. Product gaps a buyer will raise

1. **No money on any screen.** Refund amounts appear only on individual timeline rows. On W5401 the model's 284
   received Rs 52.1 lakh of refunds, Rs 23.7 lakh of it on abusive return lines, which is 81% of all abusive refund
   value in the world (Rs 29.2 lakh). The rule's 284 received more refunds in total (Rs 57.7 lakh) but only Rs 8.0
   lakh on abusive lines (27%). "The rule reviews more money, mostly honest money" is the strongest sales line
   available and the product cannot show it. Suggested: refunded value and abusive-pattern value per case, per
   queue and on the Overview, labelled as observed refunds.
2. **No export or hand-off.** A queue or a case cannot be exported for the returns-policy or customer-service team.
3. **No history across months.** Customer identifiers are scoped to a snapshot (W5401-C00001), so next month's
   upload starts with no notes and no prior decisions. By design for simulated worlds; a real deployment needs a
   stable customer key across snapshots. *Addressed on 16 Oct 2026 by change 5 (AM-68): a world now holds monthly
   snapshots of the same customers.*
4. **No delivery-proof data.** Every "not received" claim sits on a line the carrier marked delivered. Proof of
   delivery (photo, signature, location) is the signal returns teams rely on most for non-receipt claims, and the
   data contract has no field for it. Finding 1 is partly a consequence: without it, a failing address and a lying
   customer look alike.

Also worth stating in a sales conversation: the investigation memo appears only when an API key is configured;
there are no policy actions (restricting returns, requiring photos), by design; and reviewer names are free text,
not an authenticated identity.

## 7. Checked and correct by design

- Free-text reasons are accepted on upload but never shown (contract: evidence only).
- Rejected requests count as requests; withdrawn requests do not.
- `late_delivery` is grouped as discretionary, not as a transaction claim (reason-groups.yaml, D-018).
- Transaction claims have their own timeline event type.
- A return line requested on 9 Sep 2026 at 15:55 IST is before the 23:59 IST cutoff; an earlier probe that compared
  date strings flagged it wrongly.
- Customers with too little history have no tier and no gate outcome; the contract makes both nullable.

## 8. Changes made from this review

| # | Change | Kind | Covers | Status |
|---|---|---|---|---|
| 1 | Correct the cleared-reason wording, the two narrative lines and the household line in the demo script and deck; add W5401's own figures (232 against 75; Rs 23.7 lakh against Rs 8.0 lakh) | docs only | findings 2, 3, 1 (wording) | done 16 Oct 2026 |
| 2 | Label counts as excluding withdrawn requests; explain Approve and Reject in returns terms | UI copy | findings 4, 5 | done 16 Oct 2026 |
| 3 | Refine the ring kind rule for address-and-device-only communities | decision D3 change, re-score | finding 1 | done 16 Oct 2026 (AM-66) |
| 4 | Refund value at stake on case, queue and Overview; export; cleared reasons that name what is absent | backlog | gaps 1 and 2, finding 2 | done 16 Oct 2026 (AM-67) |
| 5 | Customer history across monthly snapshots of the same world | contract 1.15.0, schema version 11 | gap 3 | done 16 Oct 2026 (AM-68) |

**What changes 1 and 2 did.**

- *Demo script* (`docs/demo-script.md`): the week-one line now says half of the false non-receipt claimants stay
  below the heavy-returner line and the rule finds fewer than one in three of them, and that the rule finds one ring
  member in four; the cleared-view step says most rows read "below the review threshold" and gives 21 of 443 as the
  error rate if asked; the ring scene points at the payment edge and names the household limit; the Evaluation scene
  reads the full-budget figures off the page (232 and 18 against 75 and 209) and gives the refund figures as coming
  from this review, not from a screen; a new question to expect covers "why is this family a ring".
- *Deck* (`docs/demo-deck`, and the hosted copy): slides 2 (notes), 6, 8, 13 and 15 carry the same corrections; slide 15
  shows the full-budget and refund figures, the latter labelled as not on screen.
- *Case page*: "Actual units requested for return" notes that rejected requests count and withdrawn ones do not; the
  Returns tab heading counts withdrawn lines ("22 request line(s), 1 withdrawn and not counted" on W5401-C05428), each
  withdrawn row says "withdrawn by the customer, not counted", other rows show their status, and the callout states the
  rule. The queue's "Requested / mature units" header carries the same rule as a tooltip.
- *Decision panel*: a "What a decision means" paragraph: Open takes the case into review; Approve records a second
  reviewer's sign-off with the reading chosen; Reject records that the second reviewer does not sign it off; neither
  approves, refuses or reverses a return or a refund, and nothing reaches the order or refund system. The button labels
  and the API are unchanged.

Checked after the change: type check clean, 21 web tests, UI build, browser walkthrough 54 of 54 (screenshots in
`reports/ui/2026-10-16`).

**What changes 3 and 4 did (API contract 1.14.0).**

- *Ring rule (AM-66).* A community whose edges share only an address and a device is a ring only with two or more
  coordinated claim matches or two or more members in the queue; the first rule stands where a payment instrument is
  shared. Checked offline with the active bundle on the five validation worlds and W5401
  (`records/2026-10-16-community-kind-rule-revision.md`): rings holding a coordination group went from 183 of 204 to
  182 of 190, rings with no abuser from 15 to 5; one coordination group (W5203) became a household and its queued
  member moved from Escalate to Hold. W5401 was re-scored (`run-020e5490d88f48c28e8c`): 31 rings, the four families
  of finding 1 now households, Escalate 98 and Hold 186, every score, rank and selection unchanged.
- *Money (AM-67).* Every customer row carries refunds paid and the part paid on transaction claims, from the stored
  timeline; the run carries the same totals for the review set and the rule's set. The Overview shows them: the
  model's 284 received INR 52.1 lakh, INR 20.5 lakh of it on transaction claims; the rule's 284 received INR 57.7
  lakh, INR 9.5 lakh on claims. Labelled as observed refunds, not losses or proof. The truth-based figure of gap 1
  stays a demo talking point from this review.
- *Export (AM-67).* `GET /runs/{run_id}/customers/export` and an **Export this view as CSV** link on the queue give
  every row of the current filters, with refunds and workflow, no note text, formula-like cells quoted. The case page
  has **Download case summary**, a plain-text hand-off.
- *Cleared reasons (AM-67).* Customers outside the queue carry `absent_signals`; cleared rows and the case's cleared
  callout now add what was not observed, for example "below the review threshold · no claims matched by a linked
  account, no late returns, no linked accounts".

Checked after the change: 216 Python tests, 24 web tests, walkthrough 54 of 54, fallback 11 of 11,
specification package PASS.

**What change 5 did (API contract 1.15.0).**

- *Snapshots of one world (AM-68).* A world is one population of customers and a dataset is one snapshot of it at a
  cutoff; the same customer keeps its identifier in every snapshot, and different worlds are never linked. A later
  export of W5401 registers as a new snapshot instead of being refused. W5401 as of 9 July and 9 August was replayed from
  the generator's own timelines (`arai snapshot`) and checked to be a prefix of the September world
  (`records/2026-10-16-monthly-snapshots.md`).
- *History on screen.* The queue's Status / history column says how an earlier snapshot's review ended ("rejected on
  the 09 Aug 2026 snapshot by Ravi") and where the customer stood ("also in the 09 Aug 2026 queue (rank 4)", "new to the
  queue since ..."), with a History filter; the case has a History tab with the customer in every snapshot and notes
  that say which snapshot they were written on; the Overview compares the review set with the previous snapshot's
  (249 in both, 35 new, 22 left); the export carries the history columns.
- *Review cycle per snapshot.* Open, approval and decision run per snapshot: a case decided in August comes back in
  September as that month's own case, with the August decision shown on it, so last month's reading never silently
  decides this month's evidence.
- *What the movement means* (offline, each snapshot's own truth): 80%, 79% and 82% of the July, August and September
  review sets are abusers; 28 of the 35 customers new to September's queue are abusers, 8 of whom first acted after
  9 August.

Checked after the change: 221 Python tests, 28 web tests, walkthrough 61 of 61 (six history checks), fallback 11 of 11,
specification package PASS.
