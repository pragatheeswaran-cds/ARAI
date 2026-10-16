"""Record a few review outcomes on an earlier snapshot of the demonstration world, so the history screens have something to show.

The demo's September snapshot of W5401 is preceded by snapshots of 9 July and 9 August (`arai snapshot`, decision AM-68). This
script writes, through the API of a running instance and exactly as a reviewer would, three August outcomes on customers who are
in the September queue too:

- W5401-C08645, a ring member at rank 4: opened, then rejected by a second reviewer (coordinated claims confirmed);
- W5401-C07084, a family at an address where parcels go missing: opened, then approved by a second reviewer as legitimate;
- W5401-C05428, a ring member at rank 23 in August: opened and sent for approval, not yet decided.

Each request carries a fixed idempotency key, so running the script again changes nothing. Nothing here touches a score.

With --load it first registers the world's snapshots from the artifact folder (the world itself and every
`worlds/<world>.as-of-<date>` folder `arai snapshot` wrote), through the same upload the browser makes, and scores each
snapshot that has no succeeded run yet with the active bundle. A snapshot already registered answers with its dataset
and is not uploaded twice; one already scored is not scored again. So on a laptop the whole history demo is:

    uv run arai snapshot W5401 --as-of 2026-07-09 2026-08-09          # once; writes the two earlier snapshots
    uv run arai local                                                   # in another terminal
    uv run --no-sync python scripts/history_demo.py --load              # register, score, record the August outcomes

    uv run --no-sync python scripts/history_demo.py                     # only the outcomes (instance on port 8000)
    uv run --no-sync python scripts/history_demo.py --base-url http://127.0.0.1:8010 --as-of 2026-08-09
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

TABLES = ("customer_master", "sku_master", "reason_code", "sales_order", "sales_order_line", "return_order", "return_order_line")

STORY = [
    ("W5401-C08645", [
        ("Asha", "open", "needs_investigation",
         ("Ring of five accounts sharing a device and a payment instrument; four are in this queue and two claimed 'not received' on "
         "the same style within days.")),
        ("Ravi", "reject", "needs_investigation",
         ("Second review: the matched claims and the shared payment instrument hold up. Refer to the returns policy team; ask for proof "
         "of delivery before refunding the next non-receipt claim.")),
    ]),
    ("W5401-C07084", [
        ("Meera", "open", "unresolved",
         "Household at one address; one matching claim. Checking the carrier record for that address before deciding."),
        ("Asha", "approve", "likely_legitimate",
         ("Second review: parcels to this address go missing for other customers too, and the family's claims follow those weeks. "
         "Treat as genuine carrier failures; no action on the account.")),
    ]),
    ("W5401-C05428", [
        ("Asha", "open", "needs_investigation",
         "Ring member with late occasion-wear returns. Opened for a closer look at the linked accounts."),
        ("Asha", "request_approval", "needs_investigation",
         "Evidence collected; asking a second reviewer to decide."),
    ]),
]


def call(base: str, path: str, body: dict | None = None, raw: bytes | None = None, content_type: str = "application/json") -> dict:
    data = raw if raw is not None else None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(base + "/api/v1" + path, method="POST" if data is not None else "GET", data=data,
                                     headers={"content-type": content_type})
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise SystemExit(f"{path}: HTTP {error.code} {error.read().decode()[:300]}") from None


def register(base: str, operational: Path) -> dict:
    """Upload one snapshot folder as the browser does (a manifest field and seven CSV files)."""
    boundary = uuid.uuid4().hex
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="manifest"\r\n\r\n'.encode()
             + (operational / "manifest.json").read_bytes() + b"\r\n"]
    for table in TABLES:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{table}"; filename="{table}.csv"\r\n'
                     f"Content-Type: text/csv\r\n\r\n".encode() + (operational / f"{table}.csv").read_bytes() + b"\r\n")
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    return call(base, "/datasets", raw=body, content_type=f"multipart/form-data; boundary={boundary}")


def all_runs(base: str) -> list:
    runs, cursor = [], None
    while True:
        page = call(base, "/runs?limit=100" + (f"&cursor={cursor}" if cursor else ""))
        runs += page["items"]
        cursor = page["next_cursor"]
        if not cursor:
            return runs


def load(base: str, world: str, artifact_root: Path) -> None:
    """Register every snapshot of `world` found under the artifact root and score the ones with no succeeded run."""
    folders = sorted(artifact_root.glob(f"worlds/{world}.as-of-*/operational")) + [artifact_root / "worlds" / world / "operational"]
    for operational in folders:
        if not (operational / "manifest.json").is_file():
            raise SystemExit(f"{operational} is missing: generate the world (README) and its snapshots (arai snapshot) first.")
        dataset = register(base, operational)
        label = f"{dataset['world_id']} snapshot {dataset['cutoff'][:10]} ({dataset['customer_count']:,} customers)"
        if any(r["dataset_id"] == dataset["dataset_id"] and r["status"] == "succeeded" for r in all_runs(base)):
            print(f"{label}: registered and already scored")
            continue
        run = call(base, "/runs", {"dataset_id": dataset["dataset_id"], "idempotency_key": f"history-demo-{dataset['dataset_id']}"})
        for _ in range(240):                                          # scoring 10,000 customers takes seconds; allow minutes
            run = call(base, f"/runs/{run['run_id']}")
            if run["status"] in ("succeeded", "failed", "interrupted"):
                break
            time.sleep(2)
        if run["status"] != "succeeded":
            raise SystemExit(f"{label}: run {run['run_id']} ended {run['status']}: {run.get('error')}")
        print(f"{label}: scored, run {run['run_id']}, {run['selected_count']} selected of {run['eligible_count']} eligible")


def snapshot_run(base: str, world: str, as_of: str) -> dict:
    """The newest succeeded run on the snapshot of `world` whose cutoff date is `as_of`."""
    cursor = None
    while True:
        page = call(base, "/runs?limit=100" + (f"&cursor={cursor}" if cursor else ""))
        for run in page["items"]:                                    # newest first
            if run["world_id"] == world and run["status"] == "succeeded" and run["cutoff"].startswith(as_of):
                return run
        cursor = page["next_cursor"]
        if not cursor:
            raise SystemExit(f"No succeeded run on the {as_of} snapshot of {world}: register and score it first (RUNBOOK section 4).")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--world", default="W5401")
    parser.add_argument("--as-of", default="2026-08-09", help="the earlier snapshot's cutoff date")
    parser.add_argument("--load", action="store_true", help="first register and score the world's snapshots from the artifact folder")
    parser.add_argument("--artifact-root", type=Path, default=None, help="default: the experiment's artifacts folder")
    args = parser.parse_args()
    if args.load:
        # only --load reads the artifact folder
        from arai import paths
        load(args.base_url, args.world, args.artifact_root or paths.ARTIFACT_ROOT)
    run = snapshot_run(args.base_url, args.world, args.as_of)
    print(f"{args.world} snapshot {args.as_of}: run {run['run_id']}")
    for customer, events in STORY:
        for step, (reviewer, kind, reading, note) in enumerate(events):
            review = call(args.base_url, f"/runs/{run['run_id']}/customers/{customer}/reviews",
                          {"reviewer_name": reviewer, "kind": kind, "disposition": reading, "note": note,
                           "idempotency_key": f"history-demo-{args.as_of}-{customer}-{step}"})
            print(f"  {customer}: {kind} by {reviewer} ({review['review_id']})")
    latest = max((r for r in all_runs(args.base_url) if r["world_id"] == args.world and r["status"] == "succeeded"),
                 key=lambda r: r["cutoff"])
    previous = latest["previous_snapshot"]
    if previous:
        print(f"Since the previous snapshot ({previous['cutoff'][:10]}): {previous['repeat']} in both queues, {previous['new']} new, "
              f"{previous['left']} left, {previous['approved_before'] + previous['rejected_before']} decided before")
    return 0


if __name__ == "__main__":
    sys.exit(main())
