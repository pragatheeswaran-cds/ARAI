# Sample snapshots: try ARAI by hand

Five small folders, each the eight files one upload takes: `manifest.json` and the seven operational CSV files
(customer_master, sku_master, reason_code, sales_order, sales_order_line, return_order, return_order_line). They are
synthetic, generated from seeds by `scripts/make_samples.py`, and carry no private truth. The whole set is about 8 MB;
the demonstration world W5401 is 30 MB, so these are for trying the flow, not for judging the model.

| Folder | World | Customers | Shows |
|---|---|---|---|
| `01-ordinary-300` | W7001N300 | 300 | The everyday case: upload, score, review a short queue (9 selected out of 173 eligible) |
| `02-honest-only-300` | W7002N300 | 300 | The same shopping without any abuse mechanism: the queue still fills to its budget (9 of 167), so the reviewers' job is to clear people, not confirm them |
| `03-history-1000-june` | W7004 as of 9 June 2026 | 913 | The first snapshot of a world (23 selected of 457 eligible) |
| `04-history-1000-september` | W7004 as of 9 September 2026 | 1,000 | The next snapshot of the same customers (28 of 553): the case's History tab, the Overview's "since the previous snapshot" panel, decisions carried forward |
| `05-rejected-orphan-line` | W7001N300 | 300 | A broken export: one sales order removed while its line stays. Validation refuses it whole with rule F001 (`order_id not in sales_order`); nothing is stored |

The counts above come from scoring with the active bundle of EXP-20261005-04; they are deterministic.

## The walk

1. **Sign in.** On the demonstration VM (https://arai-demo.duckdns.org) or `uv run arai local`, pick a persona.
   Admin registers and scores; Asha, Ravi and Meera review and approve; Arjun reviews; Priya only looks.
2. **Register.** As Admin, open **Datasets & runs**, choose the eight files of `01-ordinary-300`, press
   **Validate and register**. The page names the world, its cutoff and its customer count.
3. **Score.** Press **Score with the active bundle**. Three hundred customers take a few seconds; the run page shows
   the stages and ends with the summary (eligible, selected, communities, rings).
4. **Review.** Sign out, sign in as Asha, open the queue, open a case, request approval. Sign in as Ravi to approve or
   reject it: the opener cannot decide their own case (the second-reviewer rule), so Asha approving is refused.
   Priya sees everything and can change nothing. Memos are unavailable on an instance without `ANTHROPIC_API_KEY`,
   by design.
5. **History.** Register and score `03-history-1000-june`, then `04-history-1000-september`. The queue and every case
   of September carry June's history; a case decided in June is a new case in September with the June decision shown.
6. **A rejection.** Upload `05-rejected-orphan-line`. The checklist is green (all eight files are there) and the
   server still refuses it: the reasons are grouped by rule, nothing is repaired or stored.

The same steps from a terminal, through the API with `curl.exe`, are in `RUNBOOK.md` section 4.

## Starting over

- `uv run arai local` instance: `uv run arai db-clean --all --yes` (or `--world W7001N300` for one world).
- Any other database, including the Compose stack and the VM: `scripts/db_clear.py` (`--dry-run` first). Models,
  the active pointer, people and sessions stay; notes, runs and datasets go. On the VM, from `/opt/arai/app`:

  ```bash
  sudo docker compose -f docker-compose.yml -f deploy/aws/compose.vm.yml exec -T api \
       uv run --no-sync python - --all --yes < scripts/db_clear.py
  ```

## Regenerating

`uv run --no-sync python scripts/make_samples.py` rewrites the five folders byte for byte (seeds 7001, 7002 and 7004
of the current generator; the fifth is derived from the first) and validates them: four accepted, one rejected.
`--check` only validates. If the generator or its configuration changes, the manifests' generator hashes change with
them, which is intended: a sample always matches the simulator in the repository.
