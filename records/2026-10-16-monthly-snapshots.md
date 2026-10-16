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

## Reproducing it on another machine

`arai snapshot` replays the generator for the world's seed, so the snapshots are regenerated, not copied: run twice it
wrote byte-identical files. On a fresh database `scripts/history_demo.py --load` registered and scored the three
snapshots and recorded the August outcomes in about two minutes, with the numbers above, and the browser walkthrough
passed 61 of 61 against it (RUNBOOK section 4.1). The files of this branch's snapshots, for comparison:

| Snapshot | Table | Rows | SHA-256 |
|---|---|---|---|
| 2026-07-09 | customer_master | 9,502 | `bd1d31d933d73b344d8f69bb6173d9b6b51f140335e22cd252d327bbfa87a048` |
| 2026-07-09 | sku_master | 300 | `27048143e1f617dc145623d86ce5bda712a9212fffc06cfbb4bd113ab89dc484` |
| 2026-07-09 | reason_code | 16 | `c3e219f89cd51f5a927653163409a153022c0dac38ef410070a5ef481bc3a6ec` |
| 2026-07-09 | sales_order | 71,301 | `629e21fd6199c335203cc7bdca3756e7f7953c39322759b7f6a2991c0f485779` |
| 2026-07-09 | sales_order_line | 113,969 | `927be3f694684186c69cb05054704cd6fcbe6a4435c5346652cb7fbd555146bb` |
| 2026-07-09 | return_order | 21,038 | `4358a13b3b85c31c0fb59d872129038c0327077c88434912c89feba76215d9ec` |
| 2026-07-09 | return_order_line | 23,006 | `edcea7200a872f10fa3ee2f3d613016b909fc1ec04190bd2f28bb3be0939f0fd` |
| 2026-08-09 | customer_master | 9,791 | `372d98cd2caf3e63d45e6f5165331cadfabf71fdea0d7f96ca5ab93588770f40` |
| 2026-08-09 | sku_master | 300 | `27048143e1f617dc145623d86ce5bda712a9212fffc06cfbb4bd113ab89dc484` |
| 2026-08-09 | reason_code | 16 | `c3e219f89cd51f5a927653163409a153022c0dac38ef410070a5ef481bc3a6ec` |
| 2026-08-09 | sales_order | 77,762 | `1b4880ef380865fdb7f3be880f77fb8fe3d17f1bb92392c85b2b1b3f50e62353` |
| 2026-08-09 | sales_order_line | 124,286 | `2180f3b359f4c95c91b25bfd2da122ad09cd16e9b72e346380147d92e8663f42` |
| 2026-08-09 | return_order | 23,004 | `4c3666e4c5601e0e23ee41e85116f4ccaca8c15a7477c0201dc731db2afb674b` |
| 2026-08-09 | return_order_line | 25,106 | `6f4ef846027f1fd2ff222f49b8341788f84606386a77aeefae36c01bf5920f5b` |

This was rehearsed in a Linux container. The CSV files are written with `\n` line endings on every system, so on
Windows the same hashes are expected; comparing them (RUNBOOK section 4.1) is how to confirm it. Run ids differ between
machines (they are random), and dataset ids may (they hash the manifest file, whose line endings follow the operating
system); customer ids, scores, ranks, selections and the counts above follow from the files.

