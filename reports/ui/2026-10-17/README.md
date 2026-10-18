# A year of monthly snapshots, 17 Oct 2026 (branch year-of-snapshots)

The browser walkthrough (`tests/e2e/walkthrough.py`) run once more after W5401 gained eleven earlier monthly snapshots
(9 Oct 2025 to 9 Aug 2026, beside the world's own 9 Sep 2026): **71 of 71 checks passed** (`walkthrough-result.json`).
Only the screens that change with a year of history are kept here; the others are as in `../2026-10-16/`. The data is
simulated; `records/2026-10-16-monthly-snapshots.md` has every month's figures and file hashes.

| Screenshot | Screen | What it shows |
|---|---|---|
| `02-datasets-and-runs.png` | Datasets & runs | The twelve snapshots of W5401, latest first, each scored |
| `15-overview-history.png` | Overview | Since the previous snapshot (09 Aug 2026): 249 in both queues, 35 new, 22 left, 2 decided on an earlier snapshot |
| `16-queue-history.png` | Customer queue, History filter | Customers decided on an earlier snapshot, back in the September queue |
| `17-case-history.png` | Customer case W5401-C08645, History tab | All twelve months: not ranked in October, rank 255 in November, selected for review in nine months, rejected on the August snapshot by Ravi |
| `20-queue-empty-october.png` | Customer queue, 9 Oct 2025 snapshot | After one month nobody has three mature sale lines, so nobody is ranked; the queue says so |
