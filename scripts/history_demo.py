"""Record a few review outcomes on an earlier snapshot of the demonstration world, so the history screens have something to show.

The demo's September snapshot of W5401 is preceded by snapshots of 9 July and 9 August (`arai snapshot`, decision AM-68). This
script writes, through the API of a running instance and exactly as a reviewer would, three August outcomes on customers who are
in the September queue too:

- W5401-C08645, a ring member at rank 4: opened, then rejected by a second reviewer (coordinated claims confirmed);
- W5401-C07084, a family at an address where parcels go missing: opened, then approved by a second reviewer as legitimate;
- W5401-C05428, a ring member at rank 23 in August: opened and sent for approval, not yet decided.

Each request carries a fixed idempotency key, so running the script again changes nothing. Nothing here touches a score.

    uv run --no-sync python scripts/history_demo.py                     # instance on http://127.0.0.1:8000
    uv run --no-sync python scripts/history_demo.py --base-url http://127.0.0.1:8010 --as-of 2026-08-09
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

STORY = [
    ("W5401-C08645", [
        ("Asha", "open", "needs_investigation",
         "Ring of five accounts sharing a device and a payment instrument; four are in this queue and two claimed 'not received' on "
         "the same style within days."),
        ("Ravi", "reject", "needs_investigation",
         "Second review: the matched claims and the shared payment instrument hold up. Refer to the returns policy team; ask for proof "
         "of delivery before refunding the next non-receipt claim."),
    ]),
    ("W5401-C07084", [
        ("Meera", "open", "unresolved",
         "Household at one address; one matching claim. Checking the carrier record for that address before deciding."),
        ("Asha", "approve", "likely_legitimate",
         "Second review: parcels to this address go missing for other customers too, and the family's claims follow those weeks. "
         "Treat as genuine carrier failures; no action on the account."),
    ]),
    ("W5401-C05428", [
        ("Asha", "open", "needs_investigation",
         "Ring member with late occasion-wear returns. Opened for a closer look at the linked accounts."),
        ("Asha", "request_approval", "needs_investigation",
         "Evidence collected; asking a second reviewer to decide."),
    ]),
]


def call(base: str, path: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(base + "/api/v1" + path, method="POST" if body is not None else "GET",
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise SystemExit(f"{path}: HTTP {error.code} {error.read().decode()[:300]}") from None


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
    args = parser.parse_args()
    run = snapshot_run(args.base_url, args.world, args.as_of)
    print(f"{args.world} snapshot {args.as_of}: run {run['run_id']}")
    for customer, events in STORY:
        for step, (reviewer, kind, reading, note) in enumerate(events):
            review = call(args.base_url, f"/runs/{run['run_id']}/customers/{customer}/reviews",
                          {"reviewer_name": reviewer, "kind": kind, "disposition": reading, "note": note,
                           "idempotency_key": f"history-demo-{args.as_of}-{customer}-{step}"})
            print(f"  {customer}: {kind} by {reviewer} ({review['review_id']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
