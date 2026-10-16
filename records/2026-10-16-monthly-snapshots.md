# Monthly snapshots of one world (2026-10-16)

Gap 3 of the functional review (`reports/qa/2026-10-15/functional-review.md`) was that customer identifiers were scoped to
one upload, so a returns team's next monthly export would start with no notes, no decisions and no history. Decision AM-68
makes a world one population of customers and a dataset one **snapshot** of it at a cutoff: the same customer keeps the same
identifier in every snapshot of its world. Different worlds (W5201, W5401, ...) are separate populations and are never linked.

## The demonstration world in three months

W5401 (10,000 customers, history from 10 Sep 2025) was generated at its cutoff of 9 Sep 2026. Its snapshots of 9 July and
9 August were replayed from the generator's own timelines (`arai snapshot W5401 --as-of 2026-07-09 2026-08-09`,
`src/arai/snapshots.py`): every order, sale line, return request and identifier in an earlier snapshot is in the later one
unchanged, and only states that move with time (a line shipped or delivered, a request refunded, received, rejected or
withdrawn) differ. Replayed at 9 September the method reproduces W5401's files byte for byte (`tests/test_snapshots.py`).

| Snapshot | Customers | Eligible | Review set | Against the previous snapshot |
|---|---|---|---|---|
| 09 Jul 2026 | 9,502 | 5,119 | 256 | first snapshot |
| 09 Aug 2026 | 9,791 | 5,408 | 271 | 248 in both, 23 new, 8 left |
| 09 Sep 2026 | 10,000 | 5,676 | 284 | 249 in both, 35 new, 22 left |

Each snapshot was scored on its own with the active bundle (`m-4faf6b8a2475c708f15608b1`); no score, rank or selection of
the September runs changed.

## What the movement means (offline, from each snapshot's own private truth)

Truth for an earlier snapshot counts only the abusive actions completed by its cutoff. This check reads it offline; the
product never does.

| Snapshot | Abusers in the review set | Abusers in the world by then |
|---|---|---|
| 09 Jul 2026 | 204 of 256 (80%) | 333 |
| 09 Aug 2026 | 215 of 271 (79%) | 351 |
| 09 Sep 2026 | 232 of 284 (82%) | 368 |

- New to the September queue: 35 customers, 28 of them abusers. 8 of those 28 completed their first abusive action after
  9 August; the other 20 had acted earlier and crossed the line as their evidence accumulated.
- Left the queue by September: 22 customers, 11 of them abusers, overtaken by others under a review budget that is a fixed
  share of the eligible customers. A customer who leaves the queue is not cleared: the history says where it stood.
- In both queues: 249 customers, 204 of them abusers.

## In the demonstration database

`scripts/history_demo.py` records three August outcomes through the API, as reviewers would: W5401-C08645 (ring, rank 4)
opened by Asha and rejected by Ravi; W5401-C07084 (a household at an address where parcels go missing) opened by Meera and
approved by Asha as legitimate; W5401-C05428 (ring, rank 23) opened by Asha and sent for approval. In September all three
are in the queue again as new cases of that month, with the August outcome shown on them; C05428 has climbed from rank 38
in July and 23 in August to rank 3.
