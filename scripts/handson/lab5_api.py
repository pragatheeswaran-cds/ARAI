"""Lab 5: the service from the outside. Sign in, read a run, its queue and one case over the API, as the screens do.

    uv run arai local                                              # terminal 1: the product on http://127.0.0.1:8000
    uv run --no-sync python scripts/handson/lab5_api.py            # terminal 2: reads only
    uv run --no-sync python scripts/handson/lab5_api.py --act      # also takes one case through the workflow

Without --act nothing is written. With --act one case that is still Open is opened and escalated by Arjun (a reviewer)
and closed by Ravi (a lead); the reviews stay in the demo database, as any analyst's would.
See docs/implementation-hands-on.md, steps 8 and 10.
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
import uuid
from http.cookiejar import CookieJar

API = "/api/v1"


class Session:
    """One signed-in person: a cookie jar and the CSRF token the server gave at sign-in (sent on every POST)."""

    def __init__(self, base: str, user: str):
        self.base, self.user = base.rstrip("/"), user
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        me = self.post("/auth/dev-login", {"user": user})
        self.csrf, self.roles, self.permissions = me["csrf_token"], me["roles"], me["permissions"]

    def _send(self, request: urllib.request.Request):
        try:
            with self.opener.open(request) as response:
                body = response.read().decode("utf-8")
                return response.status, json.loads(body) if body else None
        except urllib.error.HTTPError as refused:
            return refused.code, json.loads(refused.read().decode("utf-8") or "null")

    def get(self, path: str):
        status, body = self._send(urllib.request.Request(self.base + API + path))
        if status != 200:
            raise SystemExit(f"GET {path} answered {status}: {body}")
        return body

    def post(self, path: str, payload: dict, expect: tuple = (200, 201)):
        headers = {"content-type": "application/json"}
        if getattr(self, "csrf", None):
            headers["x-csrf-token"] = self.csrf
        request = urllib.request.Request(self.base + API + path, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        status, body = self._send(request)
        if status not in expect:
            raise SystemExit(f"POST {path} answered {status}: {body}")
        return body if status in (200, 201) else {"status": status, **(body or {})}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--act", action="store_true", help="take one Open case through open, escalate and close")
    args = parser.parse_args()

    try:
        with urllib.request.urlopen(args.base_url.rstrip("/") + API + "/health") as response:
            health = json.loads(response.read())
    except OSError:
        raise SystemExit(f"Nothing answers at {args.base_url}. Start the product first: uv run arai local") from None
    print(f"HEALTH (open to everyone): scoring_ready {health['scoring_ready']}, model {health['model_kind']}")

    arjun = Session(args.base_url, "Arjun")
    print(f"\nSIGNED IN as Arjun: roles {arjun.roles}, may {arjun.permissions}")
    runs = [r for r in arjun.get("/runs?limit=100")["items"] if r["status"] == "succeeded"]
    if not runs:
        raise SystemExit("No scored run yet. Register and score a snapshot first (HANDS-ON.md, exercise 5).")
    run = max(runs, key=lambda r: (r["cutoff"], r["created_at"]))
    base = f"/runs/{run['run_id']}"
    print(f"\nRUN {run['run_id']}: world {run['world_id']}, cutoff {run['cutoff'][:10]}, {run['eligible_count']} ranked, "
          f"{run['selected_count']} selected, model kind {run['model_kind']}")

    counts = arjun.get(base + "/insights")["counts"]
    print(f"  risk levels: {counts['tiers']}")
    print(f"  case statuses among the selected: {counts['states']}")

    queue = arjun.get(base + "/customers?limit=5")["items"]
    print("\nQUEUE, first five (GET /runs/{id}/customers):")
    for c in queue:
        print(f"  rank {c['rank']:>3}  {c['customer_id']}  score {c['risk_score']:.1f}  {c['tier']:<8}  status {c['workflow']['state']:<10}  "
              f"{', '.join(s['label'] for s in c['primary_signals']) or 'no listed pattern'}")

    case = arjun.get(f"{base}/customers/{queue[0]['customer_id']}")
    print(f"\nONE CASE (GET /runs/{{id}}/customers/{{customer}}): sections {sorted(case)}")
    print(f"  {len(case['timeline'])} timeline events, {len(case['neighbors'])} linked accounts, {len(case['reviews'])} notes, "
          f"memo status {case['memo']['status']}")
    expected = case["customer"]["basket_expectation"]
    if expected:
        print(f"  returned {expected['actual_units']} of {expected['purchased_units']} units; buyers of the same products return about {expected['expected_units']:.1f}")

    viewer = Session(args.base_url, "Priya")
    refused = viewer.post(f"{base}/customers/{queue[0]['customer_id']}/reviews",
                          {"kind": "note", "disposition": "unresolved", "note": "lab 5", "idempotency_key": str(uuid.uuid4())}, expect=(403,))
    print(f"\nROLES: Priya (viewer, may {viewer.permissions}) tries to write a note: {refused['status']} {refused.get('error_code')}")

    if not args.act:
        print("\nRead only so far. Run again with --act to take one case through open, escalate and close.")
        return 0

    target = arjun.get(base + "/customers?state=new&limit=100")["items"]
    if not target:
        raise SystemExit("No case is Open any more in this run.")
    customer = target[-1]["customer_id"]
    path = f"{base}/customers/{customer}/reviews"
    review = lambda who, kind, reading, note, expect=(201,): who.post(
        path, {"kind": kind, "disposition": reading, "note": note, "idempotency_key": str(uuid.uuid4())}, expect=expect)
    state = lambda: arjun.get(f"{base}/customers/{customer}")["customer"]["workflow"]
    print(f"\nWORKFLOW on {customer} (was {state()['state']}):")
    review(arjun, "open", "unresolved", "Lab 5: opened to read the evidence.")
    print(f"  Arjun opens it          -> {state()['state']}")
    review(arjun, "escalate", "needs_investigation", "Lab 5: timing and claims need a closer look.")
    print(f"  Arjun escalates it      -> {state()['state']}")
    refused = review(arjun, "close", "needs_investigation", "Lab 5: trying to close.", expect=(403,))
    print(f"  Arjun tries to close it -> {refused['status']}: {refused.get('message')}")
    ravi = Session(args.base_url, "Ravi")
    review(ravi, "close", "needs_investigation", "Lab 5: outcome recorded by the lead.")
    after = state()
    print(f"  Ravi (lead) closes it   -> {after['state']}, outcome {after['outcome']}, decided by {after['decided_by']}")
    log = arjun.get(base + "/decisions?limit=3")["items"]
    print("  audit log, newest first: " + "; ".join(f"{r['kind']} by {r['reviewer_name']}" for r in log))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
