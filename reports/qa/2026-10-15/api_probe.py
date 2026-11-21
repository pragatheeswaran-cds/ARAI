"""QA probe of the ARAI API: edge cases, validation, workflow rules, pagination, consistency. Prints FINDING lines for anomalies."""
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

B = sys.argv[1].rstrip("/") + "/api/v1"
WORLD = Path(sys.argv[2])
c = httpx.Client(timeout=120)
findings = []


def note(kind, text):
    findings.append((kind, text))
    print(f"{kind}: {text}")


def get(p, **q):
    return c.get(B + p, params=q)


def body(r):
    try:
        return r.json()
    except Exception:
        return {"_raw": r.text[:300]}


def expect(label, r, status, code=None):
    b = body(r)
    ok = r.status_code == status and (code is None or b.get("error_code") == code)
    print(("ok   " if ok else "FAIL ") + f"{label}: {r.status_code} {b.get('error_code') or ''} {str(b.get('message') or '')[:100]}")
    if not ok:
        note("BUG?", f"{label}: expected {status} {code or ''}, got {r.status_code} {json.dumps(b)[:300]}")
    return b


print("== health / contract")
h = get("/health").json(); print(h)
spec = get("/openapi.json").json(); print("contract version", spec["info"]["version"])
r = c.get(B + "/nope"); expect("unknown api path is a JSON 404", r, 404)
print("  content-type:", r.headers.get("content-type"))
r = c.get(sys.argv[1] + "/api/v1/runs/../../etc/passwd"); print("traversal via api:", r.status_code)
r = c.get(sys.argv[1] + "/some/unknown/route"); print("unknown ui route:", r.status_code, r.headers.get("content-type"))
r = c.get(sys.argv[1] + "/assets/does-not-exist.js"); print("missing asset:", r.status_code, r.headers.get("content-type"))
r = c.get(sys.argv[1] + "/%2e%2e/%2e%2e/etc/passwd"); print("encoded traversal:", r.status_code)
r = c.request("OPTIONS", B + "/runs"); print("OPTIONS /runs:", r.status_code)
r = c.get(B + "/runs", headers={"Origin": "http://evil.example"}); print("CORS header:", r.headers.get("access-control-allow-origin"))
print("security headers:", {k: r.headers.get(k) for k in ("x-content-type-options", "content-security-policy", "x-frame-options", "cache-control")})

print("== datasets")
ds = get("/datasets").json()["items"]; print("datasets", [(d["dataset_id"], d["world_id"]) for d in ds])
expect("unknown dataset 404", get("/datasets/ds-doesnotexist"), 404)
expect("limit=0 rejected", get("/datasets", limit=0), 422)
expect("limit=101 rejected", get("/datasets", limit=101), 422)
expect("bad cursor rejected", get("/datasets", cursor="!!!"), 422)
TABLES = ["customer_master", "sku_master", "reason_code", "sales_order", "sales_order_line", "return_order", "return_order_line"]
manifest = (WORLD / "manifest.json").read_text()
files = {t: (f"{t}.csv", (WORLD / f"{t}.csv").read_bytes(), "text/csv") for t in TABLES}
r = c.post(B + "/datasets", data={"manifest": manifest}, files=files); dsb = expect("re-register W5401 is idempotent 200", r, 200)
DS = dsb.get("dataset_id")
r = c.post(B + "/datasets", data={"manifest": manifest}, files={k: v for k, v in files.items() if k != "reason_code"}); expect("missing part 422", r, 422, "invalid_upload")
r = c.post(B + "/datasets", data={"manifest": manifest, "extra": "x"}, files=files); expect("unknown part 422", r, 422, "invalid_upload")
r = c.post(B + "/datasets", data={"manifest": manifest}, files={**files, "sku_master": ("../evil.csv", files["sku_master"][1], "text/csv")}); expect("path in filename 422", r, 422, "invalid_upload")
r = c.post(B + "/datasets", data={"manifest": "not json"}, files=files); expect("manifest not json 422", r, 422)
# drop a required column from reason_code
rc = (WORLD / "reason_code.csv").read_text().splitlines()
header = rc[0].split(","); broken = "\n".join([",".join(header[1:])] + [",".join(l.split(",")[1:]) for l in rc[1:]])
r = c.post(B + "/datasets", data={"manifest": manifest}, files={**files, "reason_code": ("reason_code.csv", broken.encode(), "text/csv")}); b = expect("missing column 422", r, 422)
print("   details:", json.dumps(b.get("details"))[:300])
# manifest with another world id but the same files
m2 = json.loads(manifest); m2["world_id"] = "W9999"
r = c.post(B + "/datasets", data={"manifest": json.dumps(m2)}, files=files); b = expect("manifest world mismatch rejected", r, 422)
print("   ", json.dumps(b)[:300])
m3 = json.loads(manifest); m3["cutoff"] = "2031-01-01T00:00:00Z"
r = c.post(B + "/datasets", data={"manifest": json.dumps(m3)}, files=files); b = expect("future cutoff rejected", r, 422)
print("   ", json.dumps(b)[:300])
import socket
sk = socket.create_connection(("127.0.0.1", 8000)); sk.sendall(b"POST /api/v1/datasets HTTP/1.1\r\nHost: x\r\nContent-Type: multipart/form-data; boundary=q\r\nContent-Length: 99999999999\r\n\r\n--q\r\n"); sk.settimeout(5)
try: print("huge declared content-length:", sk.recv(300).decode(errors="replace").splitlines()[0])
except Exception as e_: print("huge declared content-length: no answer", e_)
sk.close()
r = c.post(B + "/datasets", content=b"garbage", headers={"content-type": "multipart/form-data; boundary=x"}); expect("garbage multipart 422", r, 422)
# empty csv file for a table
r = c.post(B + "/datasets", data={"manifest": manifest}, files={**files, "return_order_line": ("return_order_line.csv", b"", "text/csv")}); b = expect("empty table file rejected", r, 422)
print("   ", json.dumps(b)[:200])

print("== runs")
runs = get("/runs").json()["items"]; print("runs:", [(r_["run_id"], r_["status"]) for r_ in runs])
RUN = next(r_["run_id"] for r_ in runs if r_["status"] == "succeeded")
expect("unknown run 404", get("/runs/run-doesnotexist"), 404)
expect("run unknown dataset 404", c.post(B + "/runs", json={"dataset_id": "ds-x", "idempotency_key": "k"}), 404)
expect("run empty key 422", c.post(B + "/runs", json={"dataset_id": DS, "idempotency_key": ""}), 422)
expect("run extra field 422", c.post(B + "/runs", json={"dataset_id": DS, "idempotency_key": "k1", "foo": 1}), 422)
expect("run unknown model 409", c.post(B + "/runs", json={"dataset_id": DS, "idempotency_key": "k2", "model_id": "m-nope"}), 409, "model_not_available")
expect("cancel succeeded run 409", c.post(B + f"/runs/{RUN}/cancel"), 409, "run_finished")
expect("cancel unknown 404", c.post(B + "/runs/run-x/cancel"), 404)
key = "qa-" + uuid.uuid4().hex[:8]
r1 = c.post(B + "/runs", json={"dataset_id": DS, "idempotency_key": key}); b1 = expect("submit run 202", r1, 202)
r2 = c.post(B + "/runs", json={"dataset_id": DS, "idempotency_key": key}); b2 = expect("same key replays", r2, 202)
if b1.get("run_id") != b2.get("run_id"):
    note("BUG", f"idempotent replay returned a different run: {b1.get('run_id')} vs {b2.get('run_id')}")
r3 = c.post(B + "/runs", json={"dataset_id": DS, "idempotency_key": key, "model_id": b1.get("model_id")}); print("same key, explicit same model:", r3.status_code, body(r3).get("error_code"))
# cancel it right away, then watch
rc_ = c.post(B + f"/runs/{b1['run_id']}/cancel"); print("cancel fresh run:", rc_.status_code, body(rc_).get("status"), body(rc_).get("error"))
time.sleep(3)
cr = get(f"/runs/{b1['run_id']}").json(); print("cancelled run now:", cr["status"], cr["stage"], cr["progress"], cr["error"], "memos", cr["memos"])
expect("customers of a cancelled run 409", get(f"/runs/{b1['run_id']}/customers"), 409)
if cr["status"] not in ("interrupted",):
    note("BUG?", f"cancelled run has status {cr['status']} (expected interrupted)")
# a second real run for determinism
key2 = "qa-" + uuid.uuid4().hex[:8]
rb = c.post(B + "/runs", json={"dataset_id": DS, "idempotency_key": key2}).json(); RUN2 = rb["run_id"]
for _ in range(120):
    rb = get(f"/runs/{RUN2}").json()
    if rb["status"] in ("succeeded", "failed", "interrupted"):
        break
    time.sleep(1)
print("second run:", rb["status"], "selected", rb["selected_count"], "model_only", rb["model_only_count"], "stage_log", [s["stage"] for s in rb["stage_log"]])
expect("run list filter by dataset", get("/runs", dataset_id=DS), 200)
print("runs for unknown dataset:", get("/runs", dataset_id="ds-x").status_code, len(get("/runs", dataset_id="ds-x").json()["items"]))
run = get(f"/runs/{RUN}").json()
# null summary fields on a succeeded run?
nulls = [k for k, v in run.items() if v is None and k not in ("error", "completed_at")]
print("null fields on succeeded run:", nulls)
if nulls:
    note("BUG?", f"succeeded run body has null fields: {nulls}")


print("== customers")
def walk(**q):
    out, cur = [], None
    while True:
        r = get(f"/runs/{RUN}/customers", limit=100, **({"cursor": cur} if cur else {}), **q)
        if r.status_code != 200:
            return r
        j = r.json(); out += j["items"]; cur = j["next_cursor"]
        if not cur:
            return out

expect("limit=0", get(f"/runs/{RUN}/customers", limit=0), 422)
expect("limit=101", get(f"/runs/{RUN}/customers", limit=101), 422)
expect("bad enum", get(f"/runs/{RUN}/customers", tier="high"), 422)
expect("bad evidence", get(f"/runs/{RUN}/customers", evidence="nope"), 422)
expect("cursor of another filter set", get(f"/runs/{RUN}/customers", cursor=get(f"/runs/{RUN}/customers", limit=1).json()["next_cursor"], tier="HIGH"), 422)
expect("cursor reused on other run", get(f"/runs/{RUN2}/customers", cursor=get(f"/runs/{RUN}/customers", limit=1).json()["next_cursor"]), 422)
tampered = get(f"/runs/{RUN}/customers", limit=1).json()["next_cursor"]
import base64
p = json.loads(base64.urlsafe_b64decode(tampered)); p["p"] = -5
expect("tampered cursor position", get(f"/runs/{RUN}/customers", cursor=base64.urlsafe_b64encode(json.dumps(p).encode()).decode()), 422)
p["p"] = 10 ** 12
r = get(f"/runs/{RUN}/customers", cursor=base64.urlsafe_b64encode(json.dumps(p).encode()).decode()); print("cursor past the end:", r.status_code, len(body(r).get("items", [])))
sel = walk(); print("review set", len(sel))
ids = [x["customer_id"] for x in sel]
if len(ids) != len(set(ids)):
    note("BUG", "duplicate customers across pages of the review set")
ranks = [x["rank"] for x in sel]
if ranks != sorted(ranks) or ranks != list(range(1, len(ranks) + 1)):
    note("BUG", f"review set ranks are not 1..n in order: first {ranks[:5]} last {ranks[-5:]}")
scores = [x["risk_score"] for x in sel]
if any(a < b for a, b in zip(scores, scores[1:])):
    note("BUG", "risk_score not non-increasing along rank")
everyone = walk(review_only="false"); print("all customers", len(everyone))
elig = sum(1 for x in everyone if x["eligibility_status"] == "eligible"); print("eligible in list", elig, "run says", run["eligible_count"], "excluded", run["excluded_count"])
if elig != run["eligible_count"]:
    note("BUG?", f"eligible rows {elig} differ from run.eligible_count {run['eligible_count']}")
if len(everyone) != run["eligible_count"] + run["excluded_count"]:
    note("BUG?", f"all-customer list {len(everyone)} != eligible+excluded {run['eligible_count'] + run['excluded_count']}")
ins = [x for x in everyone if x["eligibility_status"] != "eligible"]
print("insufficient history rows", len(ins), "example", json.dumps(ins[0], default=str)[:400] if ins else None)
# consistency rules
for x in everyone:
    s = x["selected_for_review"]
    if s != (x["rank"] is not None and x["rank"] <= run["review_budget"]):
        note("BUG", f"{x['customer_id']}: selected_for_review {s} but rank {x['rank']} vs budget {run['review_budget']}"); break
for x in everyone:
    if x["tier"] == "HIGH" and not x["selected_for_review"]:
        note("BUG", f"{x['customer_id']}: tier HIGH but not selected"); break
    if x["selected_for_review"] and x["tier"] != "HIGH":
        note("BUG", f"{x['customer_id']}: selected but tier {x['tier']}"); break
    if x["tier"] == "MEDIUM" and not (x["risk_score"] is not None and x["risk_score"] >= 90):
        note("BUG", f"{x['customer_id']}: MEDIUM with score {x['risk_score']}"); break
for x in everyone:
    ring = bool(x["community"] and x["community"]["kind"] == "ring")
    exp = "ESCALATE" if x["selected_for_review"] and (ring or x["wardrobing_status"] == "elevated") else ("HOLD" if x["selected_for_review"] else None)
    if exp and x["gate_outcome"] != exp:
        note("BUG", f"{x['customer_id']}: gate {x['gate_outcome']} expected {exp} (ring={ring}, wardrobing={x['wardrobing_status']})"); break
    if not x["selected_for_review"] and x["gate_outcome"] not in ("WARNING", "LOW"):
        note("BUG", f"{x['customer_id']}: not selected but gate {x['gate_outcome']}"); break
for x in everyone:
    be = x["basket_expectation"]
    if be and not (be["band_low"] <= be["expected_units"] <= be["band_high"]):
        note("BUG", f"{x['customer_id']}: expectation outside its band {be}"); break
    if be and be["band_low"] < 0:
        note("BUG?", f"{x['customer_id']}: band_low negative {be['band_low']}"); break
    if be and be["actual_units"] > be["purchased_units"]:
        note("BUG?", f"{x['customer_id']}: actual {be['actual_units']} > purchased {be['purchased_units']}"); break
print("primary signal counts", sorted({len(x["primary_signals"]) for x in everyone}))
print("eligibility insufficient with rank?", sum(1 for x in ins if x["rank"] is not None))
cleared = [x for x in everyone if x["cleared_reason"]]; print("cleared_reason rows", len(cleared), set(x["cleared_reason"] for x in cleared))
heavy = [x for x in everyone if x["eligibility_status"] == "eligible" and not x["selected_for_review"] and x["raw_return_rate"] is not None and x["raw_return_rate"] >= run["heavy_returner_cutoff"]] if everyone and "raw_return_rate" in everyone[0] else None
print("heavy not selected (by raw_return_rate):", None if heavy is None else len(heavy), "keys", list(everyone[0].keys()))
# filters
for q in ({"tier": "HIGH"}, {"tier": "MEDIUM"}, {"tier": "LOW"}, {"gate": "ESCALATE"}, {"gate": "HOLD"}, {"gate": "WARNING"}, {"gate": "LOW"},
          {"community": "ring"}, {"community": "household"}, {"community": "none"}, {"comparison": "model_only"}, {"comparison": "baseline_only"}, {"comparison": "both"},
          {"state": "in_review"}, {"state": "new"}, {"wardrobing": "elevated"}, {"eligibility": "insufficient_history"}, {"disposition": "unreviewed"}):
    a = walk(**q); bb = walk(review_only="false", **q)
    print(f"filter {q}: review set {len(a) if isinstance(a, list) else a.status_code}, all {len(bb) if isinstance(bb, list) else bb.status_code}")
tier_sum = sum(len(walk(review_only="false", tier=t)) for t in ("HIGH", "MEDIUM", "LOW")); print("tier partition sum", tier_sum, "eligible", run["eligible_count"])
if tier_sum != run["eligible_count"]:
    note("BUG?", f"tiers do not partition the eligible customers: {tier_sum} vs {run['eligible_count']}")
gate_sum = sum(len(walk(review_only="false", gate=g)) for g in ("ESCALATE", "HOLD", "WARNING", "LOW")); print("gate partition sum", gate_sum)
comp = {k: len(walk(review_only="false", comparison=k)) for k in ("model_only", "baseline_only", "both")}; print("comparison", comp, "run says", run["model_only_count"], run["baseline_only_count"])
if comp["model_only"] != run["model_only_count"] or comp["baseline_only"] != run["baseline_only_count"]:
    note("BUG", f"comparison filter counts {comp} disagree with the run counts")
if comp["both"] + comp["model_only"] != run["selected_count"]:
    note("BUG", f"both+model_only {comp['both'] + comp['model_only']} != selected {run['selected_count']}")
ring_ids = {x["community"]["id"] for x in everyone if x["community"] and x["community"]["kind"] == "ring"}; print("ring ids in all", len(ring_ids), "run ring_count", run["ring_count"])
rid = sorted(ring_ids)[0]
members = walk(review_only="false", community_id=rid); print("community_id filter", rid, len(members), [m["customer_id"] for m in members])
print("community_id of other run on this run:", len(walk(review_only="false", community_id="W5401-L000000000000")))
# search
top = sel[0]["customer_id"]
for s in (top, top.lower(), top[-5:], " " + top + " ", "C0", "'; DROP TABLE runs; --", "%", "_", "ünïcode", "W5401-C03245 OR 1=1"):
    r = get(f"/runs/{RUN}/customers", search=s, review_only="false", limit=5)
    print(f"search {s!r}: {r.status_code} {len(body(r).get('items', []))} {[i['customer_id'] for i in body(r).get('items', [])][:3]}")
r = get(f"/runs/{RUN}/customers", search="x" * 5000); print("very long search:", r.status_code)
r = get(f"/runs/{RUN}/customers", exclude_reviewer="x" * 101); expect("exclude_reviewer too long", r, 422)
print("state partition", {s: len(walk(review_only="false", state=s)) for s in ("new", "in_review", "awaiting_approval", "approved", "rejected", "auto_logged")})

print("== score distribution")
sd = get(f"/runs/{RUN}/score-distribution").json()
tot = sum(b_["count"] for b_ in sd["bins"]); selc = sum(b_["selected_count"] for b_ in sd["bins"])
print("bins", len(sd["bins"]), "sum", tot, "selected", selc, "threshold", sd["threshold_score"])
if tot != sd["eligible_count"] or selc != sd["review_budget"]:
    note("BUG", f"score distribution sums {tot}/{selc} vs {sd['eligible_count']}/{sd['review_budget']}")
aoa = [b_["at_or_above"] for b_ in sd["bins"]]
if aoa != sorted(aoa, reverse=True) or aoa[0] != sd["eligible_count"]:
    note("BUG", f"at_or_above not monotonic or wrong start: {aoa[:3]}...{aoa[-3:]}")
print("last bins", sd["bins"][-2:])

print("== case")
expect("unknown customer 404", get(f"/runs/{RUN}/customers/W5401-C99999"), 404)
expect("customer of other world 404", get(f"/runs/{RUN}/customers/W2001-C00001"), 404)
expect("case on cancelled run 409", get(f"/runs/{b1['run_id']}/customers/{top}"), 409)
case = get(f"/runs/{RUN}/customers/{top}").json()
tl = case["timeline"]; dates = [e["observed_at"] for e in tl]
if dates != sorted(dates):
    note("BUG?", "timeline not in date order")
refs = {e["source_ref"] for e in tl}
missing_refs = [ref for s in case["signals"] for ref in s["source_refs"] if ref not in refs]
print("signal source_refs not in timeline:", len(missing_refs), missing_refs[:3])
if missing_refs:
    note("BUG?", f"{len(missing_refs)} signal source_refs do not resolve to a timeline entry, e.g. {missing_refs[:2]}")
print("timeline event types", {e["event_type"] for e in tl}, "entries", len(tl))
after_cut = [e for e in tl if e["observed_at"] > case["cutoff"][:10]]
if after_cut:
    note("BUG", f"timeline has {len(after_cut)} events after the cutoff {case['cutoff']}")
print("memo", case["memo"]["status"], case["memo"]["reason"])
# insufficient-history customer case
insc = ins[0]["customer_id"] if ins else None
if insc:
    r = get(f"/runs/{RUN}/customers/{insc}"); print("insufficient-history case:", r.status_code, json.dumps({k: body(r).get(k) for k in ("score_breakdown", "wardrobing", "memo")}, default=str)[:400])
    if r.status_code != 200:
        note("BUG", f"case of an insufficient-history customer returns {r.status_code}")
# a ring member's community members all resolve
rc_case = get(f"/runs/{RUN}/customers/{members[0]['customer_id']}").json()
cm = rc_case["community"]; print("community members", len(cm["members"]), "size", cm["size"], "selected_count", cm["selected_count"], "edges", len(cm["edges"]))
if len(cm["members"]) != cm["size"]:
    note("BUG", f"community size {cm['size']} but {len(cm['members'])} members listed")
if cm["selected_count"] != sum(1 for m in cm["members"] if m["selected_for_review"]):
    note("BUG", "community selected_count disagrees with its members")
edge_ids = {e["a"] for e in cm["edges"]} | {e["b"] for e in cm["edges"]}; member_ids = {m["customer_id"] for m in cm["members"]}
if not edge_ids <= member_ids:
    note("BUG", f"edges name non-members {edge_ids - member_ids}")
for m in cm["members"]:
    r = get(f"/runs/{RUN}/customers/{m['customer_id']}")
    if r.status_code != 200:
        note("BUG", f"community member {m['customer_id']} case returns {r.status_code}")
sb = case["score_breakdown"]
for f in sb["families"]:
    if f["in_queue_without"] != (f["raw_score_without"] >= sb["threshold_raw_score"]):
        note("BUG", f"breakdown in_queue_without inconsistent for {f['family']}")
    if (f["tier_without"] == "HIGH") != f["in_queue_without"]:
        note("BUG", f"breakdown tier_without inconsistent for {f['family']}")

print("== reviews / workflow")
CUST = sel[10]["customer_id"]            # a fresh selected customer
NOTSEL = next(x["customer_id"] for x in everyone if not x["selected_for_review"] and x["eligibility_status"] == "eligible")
def review(cust, **kw):
    payload = {"reviewer_name": "QA One", "disposition": "unresolved", "note": "qa", "idempotency_key": "qa-" + uuid.uuid4().hex, **kw}
    return c.post(B + f"/runs/{RUN}/customers/{cust}/reviews", json=payload)
expect("whitespace note 422", review(CUST, note="   "), 422)
expect("whitespace name 422", review(CUST, reviewer_name="   "), 422)
expect("name 101 chars 422", review(CUST, reviewer_name="x" * 101), 422)
expect("note 4001 chars 422", review(CUST, note="x" * 4001), 422)
expect("bad kind 422", review(CUST, kind="delete"), 422)
expect("bad disposition 422", review(CUST, disposition="guilty"), 422)
expect("extra field 422", review(CUST, extra=1), 422)
expect("approve a new case 409", review(CUST, kind="approve"), 409, "case_not_open")
expect("request_approval on new case 409", review(CUST, kind="request_approval"), 409, "case_not_open")
expect("reject a new case 409", review(CUST, kind="reject"), 409, "case_not_open")
r = review(CUST, kind="feedback", disposition="likely_legitimate"); print("feedback on a selected customer:", r.status_code, body(r).get("error_code"))
r = review(NOTSEL, kind="open"); print("open a non-selected customer:", r.status_code, body(r).get("error_code"), body(r).get("message", "")[:80])
r = review(NOTSEL, kind="feedback", disposition="likely_legitimate"); print("feedback on non-selected:", r.status_code)
o = review(CUST, kind="open", disposition="needs_investigation"); expect("open 201", o, 201)
st = get(f"/runs/{RUN}/customers/{CUST}").json()["customer"]["workflow"]; print("after open:", st)
if st["state"] != "in_review" or st["opened_by"] != "QA One":
    note("BUG", f"workflow after open: {st}")
r = review(CUST, kind="open"); print("open twice:", r.status_code, body(r).get("error_code"))
st2 = get(f"/runs/{RUN}/customers/{CUST}").json()["customer"]["workflow"]
if r.status_code == 201 and st2["opened_at"] != st["opened_at"]:
    note("BUG?", f"a second 'open' while in review changed opened_at/opened_by: {st2}")
expect("same reviewer approve 409", review(CUST, kind="approve"), 409, "second_reviewer_required")
expect("same reviewer reject 409", review(CUST, kind="reject"), 409, "second_reviewer_required")
r = review(CUST, kind="approve", reviewer_name="qa one"); print("case-variant name approve:", r.status_code, body(r).get("error_code"))
if r.status_code == 201:
    note("BUG?", "the second-reviewer rule is case-sensitive: 'qa one' approved a case opened by 'QA One'")
    # reopen for the remaining checks
    review(CUST, kind="open", reviewer_name="QA One")
r = review(CUST, kind="approve", reviewer_name="QA One "); print("trailing-space name approve:", r.status_code, body(r).get("error_code"))
if r.status_code == 201:
    note("BUG", "the second-reviewer rule is defeated by a trailing space in the name")
    review(CUST, kind="open", reviewer_name="QA One")
expect("request approval by opener 201", review(CUST, kind="request_approval"), 201)
st = get(f"/runs/{RUN}/customers/{CUST}").json()["customer"]["workflow"]; print("after request:", st["state"])
r = review(CUST, kind="request_approval"); print("request twice:", r.status_code, body(r).get("error_code"))
a = review(CUST, kind="approve", reviewer_name="QA Two", disposition="unresolved"); expect("second reviewer approves 201", a, 201)
st = get(f"/runs/{RUN}/customers/{CUST}").json()["customer"]["workflow"]; print("after approve:", st)
if st["state"] != "approved" or st["decided_by"] != "QA Two":
    note("BUG", f"workflow after approve: {st}")
print("approve with disposition 'unresolved' accepted (disposition and kind unrelated?):", a.status_code)
expect("approve again 409", review(CUST, kind="approve", reviewer_name="QA Three"), 409, "case_not_open")
expect("reject after approve 409", review(CUST, kind="reject", reviewer_name="QA Three"), 409, "case_not_open")
r = review(CUST, kind="note", reviewer_name="QA Three"); print("note after approve:", r.status_code)
r = review(CUST, kind="open", reviewer_name="QA Three"); print("reopen approved case:", r.status_code)
st = get(f"/runs/{RUN}/customers/{CUST}").json()["customer"]["workflow"]; print("after reopen:", st)
if st["state"] == "in_review" and st["decided_by"] is not None:
    note("BUG?", f"reopened case still carries decided_by/decided_at: {st}")
r = review(CUST, kind="reject", reviewer_name="QA One"); print("reject reopened case by another:", r.status_code, body(r).get("error_code"))
# idempotency
k = "qa-" + uuid.uuid4().hex
r1 = review(CUST, idempotency_key=k, note="same"); r2 = review(CUST, idempotency_key=k, note="same")
print("idempotent review replay:", r1.status_code, r2.status_code, body(r1).get("review_id") == body(r2).get("review_id"))
if body(r1).get("review_id") != body(r2).get("review_id"):
    note("BUG", "review idempotency replay created a second review")
r3 = review(CUST, idempotency_key=k, note="different"); expect("same key different note 409", r3, 409, "idempotency_conflict")
r4 = c.post(B + f"/runs/{RUN}/customers/{sel[11]['customer_id']}/reviews", json={"reviewer_name": "QA One", "disposition": "unresolved", "note": "same", "idempotency_key": k, "kind": "note"})
print("same key on another customer:", r4.status_code, body(r4).get("error_code"))
if r4.status_code == 201 and body(r4).get("customer_id") != sel[11]["customer_id"]:
    note("BUG", "idempotency key reused on another customer replayed the first customer's review")
# content
xss = '<img src=x onerror=alert(1)>"\'&'
r = review(CUST, note=xss, reviewer_name="<b>QA</b>"); print("html in note stored verbatim:", r.status_code, body(r).get("note") == xss)
r = review(CUST, note="\u0000null byte"); print("null byte in note:", r.status_code, body(r).get("error_code"))
if r.status_code >= 500:
    note("BUG", f"null byte in a note gives {r.status_code}")
r = review(CUST, note="x" * 4000); print("note 4000 chars:", r.status_code)
r = review(CUST, note="é" * 4000); print("note 4000 multibyte chars:", r.status_code)
revs = walk_r = get(f"/runs/{RUN}/customers/{CUST}/reviews", limit=5).json(); print("reviews page", len(revs["items"]), "cursor", bool(revs["next_cursor"]))
allr, cur = [], None
while True:
    j = get(f"/runs/{RUN}/customers/{CUST}/reviews", limit=5, **({"cursor": cur} if cur else {})).json(); allr += j["items"]; cur = j["next_cursor"]
    if not cur: break
print("reviews total", len(allr), "unique", len({x["review_id"] for x in allr}), "ordered oldest first", [x["created_at"] for x in allr] == sorted(x["created_at"] for x in allr))
if len(allr) != len({x["review_id"] for x in allr}):
    note("BUG", "review pagination repeats rows")
case_revs = get(f"/runs/{RUN}/customers/{CUST}").json()["reviews"]; print("case embeds", len(case_revs), "reviews")
if len(case_revs) != len(allr):
    note("BUG?", f"case body embeds {len(case_revs)} reviews but the list has {len(allr)}")
# reviews visible from the other run (same world)?
r = get(f"/runs/{RUN2}/customers/{CUST}") if rb["status"] == "succeeded" else None
if r is not None:
    print("other run on same world sees the reviews:", len(r.json()["reviews"]), "workflow", r.json()["customer"]["workflow"]["state"])

print("== styles")
st_ = get(f"/runs/{RUN}/styles").json(); print("styles", len(st_["items"]), "cursor", st_["next_cursor"])
expect("unknown style 404", get(f"/runs/{RUN}/styles/XX-NOPE-99"), 404)
expect("bad state 422", get(f"/runs/{RUN}/styles", state="bogus"), 422)
pages, cur, n = [], None, 0
while True:
    j = get(f"/runs/{RUN}/styles", limit=10, **({"cursor": cur} if cur else {})).json(); pages += j["items"]; cur = j["next_cursor"]; n += 1
    if not cur: break
print("style pages", n, "total", len(pages), "unique", len({s["style_id"] for s in pages}))
if len(pages) != len(st_["items"]) or len(pages) != len({s["style_id"] for s in pages}):
    note("BUG", "style pagination loses or repeats styles")
sums = {}
for s in st_["items"]:
    sums[s["state"]] = sums.get(s["state"], 0) + 1
print("states", sums)
for s in st_["items"][:3]:
    d = get(f"/runs/{RUN}/styles/{s['style_id']}").json()
    print(s["style_id"], "skus", len(d["skus"]), "customer_ids", len(d["customer_ids"]), "returners", len(d["returners"]), "signals", len(d["signals"]))
    if d["style"] != s:
        diff = [k for k in s if s[k] != d["style"].get(k)]
        if diff: note("BUG?", f"style {s['style_id']} list row and detail disagree on {diff}")
    fr = s["flagged_returner_share"]
    if fr and fr["numerator"] > fr["denominator"]:
        note("BUG", f"{s['style_id']} flagged share numerator > denominator")
    for cid in d["customer_ids"][:3]:
        if get(f"/runs/{RUN}/customers/{cid}").status_code != 200:
            note("BUG", f"style {s['style_id']} names customer {cid} whose case is not served")

print("== experiments")
ex = get("/experiments").json()["items"]; EID = ex[0]["experiment_id"]
expect("unknown experiment 404", get("/experiments/EXP-nope"), 404)
expect("curves need run_id 422", get(f"/experiments/{EID}/curves"), 422)
expect("curves unknown run 404", get(f"/experiments/{EID}/curves", run_id="run-x"), 404)
expect("curves max_points=1 422", get(f"/experiments/{EID}/curves", run_id=RUN, max_points=1), 422)
cv = get(f"/experiments/{EID}/curves", run_id=RUN, max_points=2).json(); print("curves 2 points:", [p_["k"] for p_ in cv["points"]])
cv = get(f"/experiments/{EID}/curves", run_id=RUN).json(); ks = [p_["k"] for p_ in cv["points"]]
print("curve points", len(ks), "first/last k", ks[0], ks[-1], "budget", cv["review_budget"])
if ks != sorted(ks) or ks[-1] != cv["review_budget"]:
    note("BUG?", f"curve k values do not end at the budget or are unordered: last {ks[-1]} budget {cv['review_budget']}")
for a_, b_ in zip(cv["points"], cv["points"][1:]):
    if b_["model_abusers_caught"] < a_["model_abusers_caught"] or b_["baseline_abusers_caught"] < a_["baseline_abusers_caught"]:
        note("BUG", "curve counts decrease along k"); break
expect("curves on a cancelled run 409", get(f"/experiments/{EID}/curves", run_id=b1["run_id"]), 409)
tr = get(f"/experiments/{EID}/truth", limit=100).json(); print("truth page", len(tr["items"]), "world", tr["world_id"], "keys", list(tr["items"][0].keys()) if tr["items"] else None)
tot, cur = 0, None
while True:
    j = get(f"/experiments/{EID}/truth", limit=100, **({"cursor": cur} if cur else {})).json(); tot += len(j["items"]); cur = j["next_cursor"]
    if not cur: break
print("truth rows", tot)
e = get(f"/experiments/{EID}").json(); print("experiment keys", list(e.keys())[:6], "summary selection", e["summary"]["selection_status"])

print("\n== FINDINGS", len(findings))
for k, t in findings:
    print(f"- [{k}] {t}")
print("RUN", RUN, "RUN2", RUN2, "CANCELLED", b1["run_id"], "CUST", CUST)
