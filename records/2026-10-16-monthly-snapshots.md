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

## A year of monthly snapshots (2026-10-17)

The owner asked for the demonstration world month by month for a whole year instead of three months. W5401's history
starts on 10 Sep 2025, so the year is the world itself (9 Sep 2026) and eleven earlier snapshots on the 9th of each month:

    uv run arai snapshot W5401 --as-of 2025-10-09 2025-11-09 2025-12-09 2026-01-09 2026-02-09 2026-03-09 2026-04-09 2026-05-09 2026-06-09 2026-07-09 2026-08-09

All eleven pass validation and the prefix check (2 min 38 s here). Each was registered and scored with the same bundle
through `scripts/history_demo.py --load`, as a reviewer would upload them:

| Snapshot | Customers | Eligible | Review set | Against the previous snapshot |
|---|---|---|---|---|
| 09 Oct 2025 | 6,210 | 0 | 0 | first snapshot |
| 09 Nov 2025 | 6,585 | 621 | 32 | 0 in both, 32 new, 0 left |
| 09 Dec 2025 | 6,953 | 2,467 | 124 | 14 in both, 110 new, 18 left |
| 09 Jan 2026 | 7,319 | 3,210 | 161 | 94 in both, 67 new, 30 left |
| 09 Feb 2026 | 7,709 | 3,670 | 184 | 129 in both, 55 new, 32 left |
| 09 Mar 2026 | 8,067 | 3,955 | 198 | 159 in both, 39 new, 25 left |
| 09 Apr 2026 | 8,447 | 4,272 | 214 | 177 in both, 37 new, 21 left |
| 09 May 2026 | 8,802 | 4,555 | 228 | 197 in both, 31 new, 17 left |
| 09 Jun 2026 | 9,152 | 4,840 | 242 | 207 in both, 35 new, 21 left |
| 09 Jul 2026 | 9,502 | 5,119 | 256 | 226 in both, 30 new, 16 left |
| 09 Aug 2026 | 9,791 | 5,408 | 271 | 248 in both, 23 new, 8 left |
| 09 Sep 2026 | 10,000 | 5,676 | 284 | 249 in both, 35 new, 22 left |

The queue settles as history accumulates: after one month nobody has the three mature sale lines that ranking needs;
from March on, four in five or more of a month's queue were already in the previous one. The July, August and September
figures are those of the three-month record above; the September runs' scores, ranks and selection did not change.

**Two defects found and fixed on the way** (branch `year-of-snapshots`):

- The prefix check refused the 9 November snapshot: one return order's `return_channel` read `not_applicable` there and
  a real channel in the world. A return order collects the requests a customer makes within a few days; while all of
  them need no item back (a "not received" claim) its channel is `not_applicable`, and it takes a channel when a later
  request that does need the item joins it. That is a state moving with time, so the check now allows exactly that
  change, from `not_applicable` to a channel, and still refuses any other (`tests/test_snapshots.py`). The generator and
  the snapshot files are unchanged: July and August were written again and are byte-identical to the hashes above.
- A snapshot that failed its check stayed on disk, where `history_demo.py --load` would have registered it; it is now
  removed. And writing a snapshot whose data is unchanged keeps its existing manifest: the manifest names the code and
  lock that wrote it, its hash is the registered snapshot's identity, and rewriting it after a code change made an
  instance refuse the same data as "different content".

The empty October queue now says why it is empty (nobody ranked yet) instead of suggesting a filter.

Every file of the new snapshots, so another machine can confirm it wrote the same data:

| Snapshot | File | Rows | SHA-256 |
|---|---|---|---|
| 2025-10-09 | customer_master | 6,210 | `da929c04991db81cfd6256ae551537018dbd54ee07999658ba16be52f17a957f` |
| 2025-10-09 | sku_master | 300 | `27048143e1f617dc145623d86ce5bda712a9212fffc06cfbb4bd113ab89dc484` |
| 2025-10-09 | reason_code | 16 | `c3e219f89cd51f5a927653163409a153022c0dac38ef410070a5ef481bc3a6ec` |
| 2025-10-09 | sales_order | 5,431 | `32044bafd8c66076a5635e14c35db81eafd96b31e0a4b9f02d744b82a7f0ef23` |
| 2025-10-09 | sales_order_line | 8,668 | `7fdfb4ca35bf7ffd916766bd373b1a7c082be66127de9bd7fe80a30044214a07` |
| 2025-10-09 | return_order | 621 | `2e561125e3f1ed02f159f77eca86296649ebc5b65614edadf59994562a26e52c` |
| 2025-10-09 | return_order_line | 659 | `79bc777b570020fbe6e5f73bd4590c76b3069ffce4cc8623d19bfb2f0d116894` |
| 2025-11-09 | customer_master | 6,585 | `916421fe2032081a7f7f5f537123af721c7fa65466a0d396ad59a94cdff483c5` |
| 2025-11-09 | sku_master | 300 | `27048143e1f617dc145623d86ce5bda712a9212fffc06cfbb4bd113ab89dc484` |
| 2025-11-09 | reason_code | 16 | `c3e219f89cd51f5a927653163409a153022c0dac38ef410070a5ef481bc3a6ec` |
| 2025-11-09 | sales_order | 21,642 | `b36cbc85aa430cb9660ab90db48f10573fa44438e38bfc466fc3974f3fe925e7` |
| 2025-11-09 | sales_order_line | 34,508 | `d1b0d0ed954fbcf1690eb854aeacfc423477818e3f95fbdda201d19a4386c079` |
| 2025-11-09 | return_order | 3,587 | `a1bfc61091b6cbe79a81f8a89bf389964269d2209b7d60c84b12d157af28f78e` |
| 2025-11-09 | return_order_line | 3,967 | `c8e1ada661aba09362345883520af825679080de791bb2cdcc9b96a376622e75` |
| 2025-12-09 | customer_master | 6,953 | `68f4eec04f7aa17178fbf496002bfc541c77e7c160c56274ee29a82f510e4181` |
| 2025-12-09 | sku_master | 300 | `27048143e1f617dc145623d86ce5bda712a9212fffc06cfbb4bd113ab89dc484` |
| 2025-12-09 | reason_code | 16 | `c3e219f89cd51f5a927653163409a153022c0dac38ef410070a5ef481bc3a6ec` |
| 2025-12-09 | sales_order | 26,863 | `9564374fa2cef9897d60cda652cb5e11c7fb1cf7d5d0826feab74925bb8eee53` |
| 2025-12-09 | sales_order_line | 42,829 | `dc4408674540cabfaae8c7d3e9db7110fd6d9be4766500bd9899c673f528bf52` |
| 2025-12-09 | return_order | 7,431 | `1cef3515be628b79ca284b57b6ded06a62fa59de3b9910b7ed965edb8fed5df6` |
| 2025-12-09 | return_order_line | 8,404 | `b66bd5434501fe204ee0a61054cacffe424e4fd68026b0ab73d660051beb17c6` |
| 2026-01-09 | customer_master | 7,319 | `e92066fdbfe363efc2abaad43b0d1b19c90b1106e35e6ff2d2b6231ba838689b` |
| 2026-01-09 | sku_master | 300 | `27048143e1f617dc145623d86ce5bda712a9212fffc06cfbb4bd113ab89dc484` |
| 2026-01-09 | reason_code | 16 | `c3e219f89cd51f5a927653163409a153022c0dac38ef410070a5ef481bc3a6ec` |
| 2026-01-09 | sales_order | 37,109 | `87e414b146595604a265aca83b08f94dcf10e0f76ff7dccc50f446763a43642c` |
| 2026-01-09 | sales_order_line | 59,213 | `76add5d113cbf34e9e1f23e5f25228da65356dc886e46d0b8014f6d98289172a` |
| 2026-01-09 | return_order | 9,674 | `386ac918131b5194228deb2efa643faebc377e44a98627160141ffe25417903b` |
| 2026-01-09 | return_order_line | 10,836 | `880dc14bb1e4d18c441e5a8c68449562fa002f5755fb8d515156ca5761dfaef6` |
| 2026-02-09 | customer_master | 7,709 | `1b9c92b17dc981673950b4dd382225d41bb5e4a97833481cd7459f46a884792a` |
| 2026-02-09 | sku_master | 300 | `27048143e1f617dc145623d86ce5bda712a9212fffc06cfbb4bd113ab89dc484` |
| 2026-02-09 | reason_code | 16 | `c3e219f89cd51f5a927653163409a153022c0dac38ef410070a5ef481bc3a6ec` |
| 2026-02-09 | sales_order | 42,443 | `12e3a31f44b2544ae213701923d16072210d9ab66472bde7ea18e867760e16d2` |
| 2026-02-09 | sales_order_line | 67,674 | `75b3225290f345ba97e653821bb3c53e912f32cc9fb8e24c6ee0d7356d35e2cd` |
| 2026-02-09 | return_order | 12,274 | `0bc6b43eed9459b83a1fcec94afbfaa4da788478bab344381524f165f6aaef9e` |
| 2026-02-09 | return_order_line | 13,686 | `7a2a8b2d080558eaa8e33b4b047017c878adf92c646194b748298ea5aad2f472` |
| 2026-03-09 | customer_master | 8,067 | `c4ae8f4490ac19c419810a33902927c02939a6918c336b620d7322d43924c318` |
| 2026-03-09 | sku_master | 300 | `27048143e1f617dc145623d86ce5bda712a9212fffc06cfbb4bd113ab89dc484` |
| 2026-03-09 | reason_code | 16 | `c3e219f89cd51f5a927653163409a153022c0dac38ef410070a5ef481bc3a6ec` |
| 2026-03-09 | sales_order | 47,439 | `0bded5a70925a74130b42ef283d3debbbfedd482a3895569d8367e715594e0bd` |
| 2026-03-09 | sales_order_line | 75,678 | `10f62d729d958df9207b3062a3e0859cbf7a8f23f515441fc748adf96c2922ef` |
| 2026-03-09 | return_order | 13,836 | `6c1714e1aac7dfe68f8b12454c20aa723ab8cddb1ec3cc1ce86315e334f30154` |
| 2026-03-09 | return_order_line | 15,364 | `982948f812e6b0439459a5d76005c0dbaf2f40a9bffb33be5bffc377b54b6858` |
| 2026-04-09 | customer_master | 8,447 | `2bb034a6ca5f2c5a2dd7a59965267edd90f0427e513a88ff7e98527b21ab4d5c` |
| 2026-04-09 | sku_master | 300 | `27048143e1f617dc145623d86ce5bda712a9212fffc06cfbb4bd113ab89dc484` |
| 2026-04-09 | reason_code | 16 | `c3e219f89cd51f5a927653163409a153022c0dac38ef410070a5ef481bc3a6ec` |
| 2026-04-09 | sales_order | 53,115 | `cf6ad4826d47e130258037d19731542e994f5df2fed7ddeb2b78d4694e75f04c` |
| 2026-04-09 | sales_order_line | 84,741 | `3698eb261a68a058afec9b7558b20d671812e1f9e7de3c60ab92d9d6d73e2ce3` |
| 2026-04-09 | return_order | 15,533 | `4ac396545b13349adea548dbf222ec9b2df9e1eb8ba1e0956532b4799e7cff1c` |
| 2026-04-09 | return_order_line | 17,185 | `f6f896409d6c8de82ffaa09413044278f76435ee6f6d1b020a1b9dce38f98984` |
| 2026-05-09 | customer_master | 8,802 | `4db38748c09a2d4fd19dc102ae7ec90a6cdc7799c4dfab23b4b1fe1da11ab5c0` |
| 2026-05-09 | sku_master | 300 | `27048143e1f617dc145623d86ce5bda712a9212fffc06cfbb4bd113ab89dc484` |
| 2026-05-09 | reason_code | 16 | `c3e219f89cd51f5a927653163409a153022c0dac38ef410070a5ef481bc3a6ec` |
| 2026-05-09 | sales_order | 58,948 | `465632796e9d0a4b0b544890e7bbaeecffb4a76d0137cbbdc3fb20ede10603c1` |
| 2026-05-09 | sales_order_line | 94,034 | `74e5b1cabfe2773560fcbff8fac11ccbb8cb5d8b8b76bf1ce392099c8b3f8fce` |
| 2026-05-09 | return_order | 17,236 | `0c06e147b3a9748dac7fa409232c907918412c40b32d1eec550ea5a266052728` |
| 2026-05-09 | return_order_line | 18,978 | `6c269bd18e7574b66119be0c00c0a7fe59260dd59b3068b08846201eb38b9270` |
| 2026-06-09 | customer_master | 9,152 | `0f030fe0230b781deef9427b4caab1c64e094f051d118a8c8f5006423d5a032b` |
| 2026-06-09 | sku_master | 300 | `27048143e1f617dc145623d86ce5bda712a9212fffc06cfbb4bd113ab89dc484` |
| 2026-06-09 | reason_code | 16 | `c3e219f89cd51f5a927653163409a153022c0dac38ef410070a5ef481bc3a6ec` |
| 2026-06-09 | sales_order | 65,222 | `e7ea1846f04424053d35ce04d318bea9f536ebb5758a1e66b9e8198a22b11af2` |
| 2026-06-09 | sales_order_line | 104,134 | `c78498b0c2333b0c1c7937896f3b1ab5560cb765153d4ed4d5b1983e901fde69` |
| 2026-06-09 | return_order | 19,126 | `25b3447ba85dd8da482fedd8bd22fa8dd69a8185473daff5ee6c0c8ad32778d0` |
| 2026-06-09 | return_order_line | 20,975 | `87039ec7d4c3c85f6e5f429c329378d93c2103d058599d1d0799009dd90be812` |
