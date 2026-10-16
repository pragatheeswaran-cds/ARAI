# Complete walkthrough, 16 Oct 2026 (branch auth-design)

Screenshots of one complete run of the browser walkthrough (`tests/e2e/walkthrough.py`, **66 of 66 checks passed**) and of
the baseline-fallback check (`tests/e2e/fallback_check.py`, **11 of 11 passed**), taken in headless Chromium 141 at
1440 px width against `arai local` on http://127.0.0.1:8000. Every check, with its detail, is in
`walkthrough-result.json` and `fallback-result.json`.

State of the instance: API contract 1.16.0 with the development login (the walkthrough signs in as Admin, then Ravi,
then Arjun and Admin again), the selected model `m-4faf6b8a2475c708f15608b1`, and world W5401 with three
snapshots of the same customers (9 July, 9 August and 9 September 2026), each scored, plus the three August review
outcomes of `scripts/history_demo.py`. The workspace opens on the latest snapshot's run, `run-020e5490d88f48c28e8c`
(5,676 eligible, 284 selected). RUNBOOK section 4.1 rebuilds exactly this state on another machine. The data is
simulated.

| Screenshot | Screen | What it shows |
|---|---|---|
| `00-sign-in.png` | Sign in | The development login's people with their roles; every note and decision is recorded under the person who signs in |
| `01-overview.png` | Overview | The September run: model and return-rate rule compared, refunds paid to each queue, the next customers, and the panel comparing the queue with the 9 August snapshot |
| `02-datasets-and-runs.png` | Datasets & runs | W5401's three snapshots, latest first (10,000, 9,791 and 9,502 customers), scoring readiness, the runs with their stage steppers, and the upload refusing an incomplete file set |
| `03-queue-rule-only.png` | Customer queue | Customers the return-rate rule selects and the model does not |
| `04-queue-search.png` | Customer queue | Search by customer id |
| `05-case-evidence.png` | Customer case, W5401-C03245 | Evidence tab: expected against actual returns, why this score, the analyst rules that would have fired |
| `06-case-returns.png` | Customer case | Returns tab: every return line with its reason code |
| `06-case-linked-accounts.png` | Customer case | Linked accounts tab |
| `06-case-notes.png`, `07-case-notes.png` | Customer case | Notes tab, each note marked with the snapshot it was written on, and the Decision panel |
| `07b-case-refusal.png` | Customer case | Ravi opens a case and the server refuses his own approval (second reviewer required, compared by user id) |
| `08-styles-targeting.png` | Style investigation | The style queue filtered to targeting |
| `09-style-detail.png` | Style detail | The four drawers and the SKU drill-down |
| `10-evaluation.png` | Evaluation | Validation and final test, every candidate, the hero curves for the September run, the limits |
| `11-evaluation-truth.png` | Evaluation | Simulated truth revealed, labelled as simulation |
| `12-overview-narrow.png` | Overview, phone width | No horizontal scroll at 420 px |
| `13-fallback-overview.png` | Overview, baseline fallback | A separate instance with only the return-rate baseline: the banner and the relabelled score |
| `14-fallback-case.png` | Customer case, baseline fallback | The case under the baseline |
| `15-overview-history.png` | Overview | **Since the previous snapshot of W5401 (09 Aug 2026)**: 249 in both queues, 35 new, 22 left, 2 decided on an earlier snapshot |
| `16-queue-history.png` | Customer queue, History filter "Decided on an earlier snapshot" | W5401-C08645 "rejected on the 09 Aug 2026 snapshot by Ravi" and W5401-C07084 "approved ... by Asha", each back in the September queue as a new case |
| `17-case-history.png` | Customer case W5401-C08645, History tab | Rank 11, 4 and 4 across July, August and September; the August review rejected; the callout that this snapshot's review starts on its own |
| `18-case-admin-reads.png` | Customer case, signed in as Admin | An admin reads the case but is offered no notes or decisions (admin operates, does not review) |
