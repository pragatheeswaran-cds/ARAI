"""Functional QA of ARAI on W5401: the selling claims against the simulation truth, and the reviewer's evidence
against the raw operational tables. Read-only: it never writes to the API or the files."""
import json
import random
import sys
from collections import Counter, defaultdict
from itertools import combinations

import httpx
import numpy as np
import pandas as pd

BASE = sys.argv[1].rstrip("/") + "/api/v1"
ROOT = "/home/user/ARAI/data/EXP-20261005-04"
W = f"{ROOT}/artifacts/worlds/W5401/operational"
P = f"{ROOT}/private/W5401"
c = httpx.Client(timeout=120)
FINDINGS = []


def finding(sev, area, text):
    FINDINGS.append((sev, area, text))
    print(f"  >> [{sev}] {area}: {text}")


def get(path, **q):
    r = c.get(BASE + path, params=q)
    r.raise_for_status()
    return r.json()


def pct(a, b):
    return f"{a}/{b} = {100 * a / b:.1f}%" if b else f"{a}/0"


# ------------------------------------------------------------------ load
runs = [r for r in get("/runs")["items"] if r["status"] == "succeeded" and r["world_id"] == "W5401"]
run = runs[-1]                                           # the first scored run of the demo
RUN = run["run_id"]
print("run", RUN, "budget", run["review_budget"], "threshold", round(run["threshold_score"], 2), "heavy cutoff", run["heavy_returner_cutoff"])
customers, cur = [], None
while True:
    page = get(f"/runs/{RUN}/customers", review_only="false", limit=100, **({"cursor": cur} if cur else {}))
    customers += page["items"]
    cur = page["next_cursor"]
    if not cur:
        break
api = pd.DataFrame(customers).set_index("customer_id")
print("customers from the API", len(api))

so = pd.read_csv(f"{W}/sales_order.csv", dtype=str)
sol = pd.read_csv(f"{W}/sales_order_line.csv", dtype={"order_line_no": int, "quantity": int, "return_window_days": int})
ro = pd.read_csv(f"{W}/return_order.csv", dtype=str)
rol = pd.read_csv(f"{W}/return_order_line.csv", dtype={"order_line_no": int, "quantity_returned": int, "return_line_no": int})
sku = pd.read_csv(f"{W}/sku_master.csv", dtype={"is_occasion_wear": int})
manifest = json.load(open(f"{W}/manifest.json"))
cutoff_day = pd.Timestamp(manifest["cutoff"][:10])
truth = pd.read_parquet(f"{P}/customer_truth.parquet").set_index("customer_id")
profile = pd.read_parquet(f"{P}/customer_profile.parquet").set_index("customer_id")
line_truth = pd.read_parquet(f"{P}/line_truth.parquet")
rel = pd.read_parquet(f"{P}/relationship_truth.parquet")
product = pd.read_parquet(f"{P}/product_truth.parquet").set_index("style_id")
actions = pd.read_parquet(f"{P}/action_truth.parquet")
CLAIM = {"wrong_item_sent", "missing_parts", "item_not_received", "empty_package"}
QUALITY = {"defective", "poor_quality", "not_as_described"}

lines = sol.merge(so[["order_id", "customer_id"]], on="order_id").merge(sku[["sku", "style_id", "category", "is_occasion_wear"]], on="sku")
lines["delivered_date"] = pd.to_datetime(lines["delivered_date"])
lines["delivered"] = lines["line_status"].eq("delivered") | lines["delivered_date"].notna()
lines["mature"] = lines["delivered_date"].notna() & (lines["delivered_date"] + pd.to_timedelta(lines["return_window_days"], unit="D") <= cutoff_day)
req = rol.merge(lines[["order_id", "order_line_no", "customer_id", "delivered_date", "return_window_days", "mature", "style_id", "is_occasion_wear"]],
                on=["order_id", "order_line_no"], how="left")
req["requested_at"] = pd.to_datetime(req["requested_at"], utc=True).dt.tz_convert("Asia/Kolkata")
req["req_day"] = req["requested_at"].dt.tz_localize(None).dt.normalize()
req["days"] = (req["req_day"] - req["delivered_date"]).dt.days
req["is_claim"] = req["reason_code"].isin(CLAIM)

# ------------------------------------------------------------------ A. the selling claims against truth
print("\n== A1-A2 queue precision and honest heavy returners (W5401 itself)")
elig = api[api["eligibility_status"] == "eligible"].copy()
elig["y"] = truth.loc[elig.index, "y_abuse"].astype(int)
sc = pd.DataFrame(list(elig["support_counts"]), index=elig.index)
elig["rate"] = sc["mature_requested_units"] / sc["mature_purchased_units"]
sel, rule = elig[elig["selected_for_review"]], elig[elig["baseline_selected"]]
print("  model queue precision", pct(int(sel["y"].sum()), len(sel)), "| rule precision", pct(int(rule["y"].sum()), len(rule)))
print("  eligible abusers", int(elig["y"].sum()), "of all abusers", int(truth["y_abuse"].sum()), "| recall model", pct(int(sel["y"].sum()), int(elig["y"].sum())),
      "rule", pct(int(rule["y"].sum()), int(elig["y"].sum())))
heavy_honest = elig[(elig["y"] == 0) & (elig["rate"] >= run["heavy_returner_cutoff"])]
print("  honest heavy returners", len(heavy_honest), "| reviewed by model", pct(int(heavy_honest["selected_for_review"].sum()), len(heavy_honest)),
      "| by rule", pct(int(heavy_honest["baseline_selected"].sum()), len(heavy_honest)))

print("\n== A3 the two 209s")
model_only = elig[elig["selected_for_review"] & ~elig["baseline_selected"]]
rule_only = elig[~elig["selected_for_review"] & elig["baseline_selected"]]
both = elig[elig["selected_for_review"] & elig["baseline_selected"]]
print("  model-only", len(model_only), "abusers", pct(int(model_only["y"].sum()), len(model_only)))
print("  rule-only", len(rule_only), "abusers", pct(int(rule_only["y"].sum()), len(rule_only)), "| honest profiles among rule-only:",
      dict(heavy_overlay=int(profile.loc[rule_only.index, "heavy_return_overlay"].sum()), bracketer=int(profile.loc[rule_only.index, "bracketer"].sum())))
print("  both", len(both), "abusers", pct(int(both["y"].sum()), len(both)))

print("\n== A4 curve point k=58 recomputed")
cv = get(f"/experiments/{run['model_id'] and 'EXP-20261005-04'}/curves", run_id=RUN, max_points=20000)
point = next(p for p in cv["points"] if p["k"] == 58)
def at_k(col, k):
    top = elig[elig[col] <= k]
    return int(top["y"].sum()), int(((top["y"] == 0) & (top["rate"] >= run["heavy_returner_cutoff"])).sum())
print("  endpoint", point, "| recomputed model", at_k("rank", 58), "rule", at_k("baseline_rank", 58))
if (point["model_abusers_caught"], point["model_legitimate_heavy_reviewed"]) != at_k("rank", 58) or \
   (point["baseline_abusers_caught"], point["baseline_legitimate_heavy_reviewed"]) != at_k("baseline_rank", 58):
    finding("High", "Evaluation curve", f"k=58 differs: endpoint {point} vs recomputed model {at_k('rank', 58)} rule {at_k('baseline_rank', 58)}")
print("  curve abusers", cv["abusers"], "legit heavy", cv["legitimate_heavy_returners"], "| recomputed", int(elig["y"].sum()), len(heavy_honest))
k284 = next(p for p in cv["points"] if p["k"] == 284)
print("  k=284", k284, "| recomputed model", at_k("rank", 284), "rule", at_k("baseline_rank", 284))

print("\n== A5 the demo's hero cases")
acts = actions[actions["completed_action"]].groupby("customer_id")["action_type"].apply(lambda s: dict(Counter(s)))
for cid, label in (("W5401-C03245", "rank 1 (script: 'explains itself')"), ("W5401-C07624", "rank 2"), ("W5401-C05428", "rank 3 (ring)"),
                   ("W5401-C08645", "rank 4 (script: the ring)"), ("W5401-C04755", "rank 5")):
    t, p = truth.loc[cid], profile.loc[cid]
    print(f"  {cid} {label}: y_abuse={int(t.y_abuse)} actions={acts.get(cid, {})} coord={bool(t.coordinated_action_flag)} "
          f"household={t.household_id} persona={p.persona} heavy_overlay={bool(p.heavy_return_overlay)} bracketer={bool(p.bracketer)}")
    if cid in ("W5401-C03245", "W5401-C08645") and int(t.y_abuse) == 0:
        finding("High", "Demo script", f"{cid} ({label}) is honest in the simulation truth")

print("\n== A6 rings and households against truth")
comm = elig.dropna(subset=["community"])
everyone_comm = api.dropna(subset=["community"]).copy()
everyone_comm["cid"] = everyone_comm["community"].map(lambda d: d["id"])
everyone_comm["kind"] = everyone_comm["community"].map(lambda d: d["kind"])
coord_members = set(rel.loc[rel["group_type"] == "coordination", "customer_id"]) | set(truth.index[truth["coordinated_action_flag"]])
house_members = set(rel.loc[rel["group_type"] == "household", "customer_id"])
summary = defaultdict(Counter)
false_rings = []
for cid_, group in everyone_comm.groupby("cid"):
    kind = group["kind"].iloc[0]
    members = list(group.index)
    abusers = int(truth.loc[members, "y_abuse"].sum())
    coord = sum(m in coord_members for m in members)
    summary[kind]["communities"] += 1
    summary[kind]["with_coordination_member"] += coord > 0
    summary[kind]["with_any_abuser"] += abusers > 0
    summary[kind]["members"] += len(members)
    summary[kind]["abusers"] += abusers
    if kind == "ring" and abusers == 0:
        false_rings.append((cid_, members, int(group["selected_for_review"].sum())))
for kind, s in summary.items():
    print(f"  {kind}: {dict(s)}")
print("  rings with no abuser at all:", len(false_rings), false_rings[:4])
if false_rings:
    finding("Medium", "Linked accounts", f"{len(false_rings)} of {summary['ring']['communities']} communities labelled ring hold no abuser in truth "
            f"(households called rings), e.g. {false_rings[0][0]} with {len(false_rings[0][1])} members, {false_rings[0][2]} in the queue")
missed = [cid_ for cid_, g in everyone_comm.groupby("cid") if g["kind"].iloc[0] == "household" and sum(m in coord_members for m in g.index) >= 2]
print("  households with two or more coordination members (missed rings):", len(missed))
coord_in_comm = sum(m in set(everyone_comm.index) for m in coord_members)
print("  coordination members linked into any community:", pct(coord_in_comm, len(coord_members)))

print("\n== A7 wardrobing indicator against temporary-use truth")
ww = api[api["eligibility_status"] == "eligible"]
temp = truth.loc[ww.index, "temporary_use_return"]
for status in ("elevated", "possible"):
    m = ww["wardrobing_status"] == status
    print(f"  {status}: {pct(int(temp[m].sum()), int(m.sum()))} are temporary-use abusers")
print("  temporary-use abusers flagged elevated or possible:", pct(int(temp[ww["wardrobing_status"].isin(["elevated", "possible"])].sum()), int(temp.sum())))

print("\n== A8 style verdicts against product truth")
styles = get(f"/runs/{RUN}/styles")["items"]
for s in styles:
    pt = product.loc[s["style_id"]]
    tag = []
    if pt["defect_state"] == "defect_prone":
        tag.append("defect_prone")
    if pt["targeted"]:
        tag.append("targeted")
    if s["state"] != "no_elevated_signal" or tag:
        print(f"  {s['style_id']}: verdict {s['state']:<20} truth {tag or ['ordinary']}")
        if (s["state"] == "quality") != (pt["defect_state"] == "defect_prone") or (s["state"] == "targeting") != bool(pt["targeted"]):
            finding("Medium", "Style verdicts", f"{s['style_id']} verdict {s['state']} vs truth {tag or ['ordinary']}")

print("\n== A9 honest customers the reviewer will meet in the queue")
lt = line_truth.merge(so[["order_id", "customer_id"]], on="order_id")
defect_buyers = set(lt.loc[lt["received_defective_unit"], "customer_id"])
genuine_fail = lt[lt["genuine_nonreceipt"]].groupby("customer_id").size()
honest_sel = sel[sel["y"] == 0]
print("  honest in the queue", len(honest_sel), "of", len(sel))
print("   received a defective unit:", int(sum(i in defect_buyers for i in honest_sel.index)),
      "| two or more genuine non-receipts:", int(sum(genuine_fail.get(i, 0) >= 2 for i in honest_sel.index)),
      "| one genuine non-receipt:", int(sum(genuine_fail.get(i, 0) == 1 for i in honest_sel.index)),
      "| household member:", int(sum(i in house_members for i in honest_sel.index)),
      "| heavy-return overlay:", int(profile.loc[honest_sel.index, "heavy_return_overlay"].sum()),
      "| bracketer:", int(profile.loc[honest_sel.index, "bracketer"].sum()))
print("   their gate outcome:", dict(Counter(honest_sel["gate_outcome"])), "| abusers' gate outcome:", dict(Counter(sel[sel['y'] == 1]["gate_outcome"])))
esc = sel[sel["gate_outcome"] == "ESCALATE"]
print("  Escalate precision", pct(int(esc["y"].sum()), len(esc)), "| Hold precision", pct(int(sel[sel['gate_outcome'] == 'HOLD']['y'].sum()), int((sel['gate_outcome'] == 'HOLD').sum())))

print("\n== A10 abusers by action type: caught, missed, out of reach")
for col in ("deceptive_nonreceipt_claim", "deceptive_contents_claim", "temporary_use_return", "coordinated_action_flag"):
    group = truth.index[truth[col]]
    in_elig = [i for i in group if i in elig.index]
    caught = int(elig.loc[in_elig, "selected_for_review"].sum())
    print(f"  {col}: {len(group)} total, {len(in_elig)} eligible, caught {pct(caught, len(in_elig))}, rule caught {pct(int(elig.loc[in_elig, 'baseline_selected'].sum()), len(in_elig))}")
ineligible_abusers = [i for i in truth.index[truth["y_abuse"] == 1] if api.loc[i, "eligibility_status"] != "eligible"]
print("  abusers with too little history to rank:", len(ineligible_abusers))

print("\n== A11 cleared heavy returners")
cleared = elig[~elig["selected_for_review"] & (elig["rate"] >= run["heavy_returner_cutoff"])]
print("  cleared heavy returners", len(cleared), "| abusers among them", pct(int(cleared["y"].sum()), len(cleared)))
for reason, g in cleared.groupby(cleared["cleared_reason"].fillna("none")):
    print(f"   {reason}: {len(g)}, abusers {int(g['y'].sum())}")

print("\n== A12 narrative: claimants and ring members have ordinary return rates")
for col, label in (("deceptive_nonreceipt_claim", "non-receipt claimants"), ("coordinated_action_flag", "coordinated members")):
    g = [i for i in truth.index[truth[col]] if i in elig.index]
    below = int((elig.loc[g, "rate"] < run["heavy_returner_cutoff"]).sum())
    print(f"  {label}: below the heavy cutoff {pct(below, len(g))}, median rate {elig.loc[g, 'rate'].median():.2f} vs all eligible {elig['rate'].median():.2f}")

# ------------------------------------------------------------------ B. the reviewer's evidence against the raw tables
print("\n== B1 support counts for all 10,000 customers")
g = lines.groupby("customer_id")
mature = lines[lines["mature"]]
mreq = req[req["mature"] == True]                                         # noqa: E712
raw = pd.DataFrame({"mature_sale_lines": mature.groupby("customer_id").size(), "mature_purchased_units": mature.groupby("customer_id")["quantity"].sum(),
                    "mature_requested_units": mreq.groupby("customer_id")["quantity_returned"].sum(),
                    "all_requested_units": req.groupby("customer_id")["quantity_returned"].sum()}).reindex(api.index).fillna(0).astype(int)
apisc = pd.DataFrame(list(api["support_counts"]), index=api.index)[raw.columns].fillna(0).astype(int)
diff = (raw != apisc).any(axis=1)
print("  customers whose support counts differ from the raw tables:", int(diff.sum()))
if diff.any():
    ex = diff[diff].index[0]
    finding("High", "Evidence", f"support counts differ for {int(diff.sum())} customers, e.g. {ex}: raw {raw.loc[ex].to_dict()} api {apisc.loc[ex].to_dict()}")
elig_raw = (raw["mature_sale_lines"] >= 3)
mis_elig = int((elig_raw != (api["eligibility_status"] == "eligible")).sum())
print("  eligibility (3 or more mature sale lines) disagreements:", mis_elig)
if mis_elig:
    finding("High", "Eligibility", f"{mis_elig} customers' eligibility disagrees with the 3-mature-line rule")

print("\n== B2 the return-rate rule's ranking")
order = elig.sort_values("baseline_rank")
inversions = int((order["rate"].diff() > 1e-12).sum())
print("  rank order against raw return rate: inversions", inversions, "| baseline_selected == rank <= budget:",
      bool((elig["baseline_selected"] == (elig["baseline_rank"] <= run["review_budget"])).all()))
if inversions:
    finding("Medium", "Rule column", f"the rule's rank is not ordered by raw return rate ({inversions} inversions)")
ties = order.groupby("rate").size()
print("  ties at the rule's cut (rate of rank 284 shared by):", int(ties.get(order.iloc[run['review_budget'] - 1]["rate"], 0)), "customers")

print("\n== B3 primary signals for the 284")
late_mismatch, claim_mismatch = [], []
for cid, row in sel.iterrows():
    mine = req[req["customer_id"] == cid]
    item = mine[~mine["is_claim"]]
    late = item[(item["days"] >= 0.75 * item["return_window_days"]) & (item["days"] <= item["return_window_days"]) & (item["days"] >= 0)]
    for s in row["primary_signals"]:
        if s["tag"] == "late_returns" and (s["value"] != len(late) or s["denominator"] != len(item)):
            late_mismatch.append((cid, s["value"], s["denominator"], len(late), len(item)))
        if s["tag"] == "repeat_claims" and (s["value"] != int(mine["is_claim"].sum()) or s["denominator"] != len(mine)):
            claim_mismatch.append((cid, s["value"], s["denominator"], int(mine["is_claim"].sum()), len(mine)))
print("  late-return chips that differ from the raw lines:", len(late_mismatch), late_mismatch[:3])
print("  claim chips that differ:", len(claim_mismatch), claim_mismatch[:3])
if late_mismatch:
    finding("Medium", "Evidence", f"{len(late_mismatch)} late-return chips differ from a recount on all item-return lines, e.g. {late_mismatch[0]} (api value, denom, raw late, raw item lines)")
if claim_mismatch:
    finding("Medium", "Evidence", f"{len(claim_mismatch)} claim chips differ from a recount, e.g. {claim_mismatch[0]}")

print("\n== B4 timelines of 30 customers")
random.seed(7)
sample = list(sel.index[:15]) + random.sample(list(elig.index[elig["selected_for_review"] == False]), 15)   # noqa: E712
tl_issues = []
for cid in sample:
    case = get(f"/runs/{RUN}/customers/{cid}")
    tl = pd.DataFrame(case["timeline"])
    purchases, returns = tl[tl["event_type"] == "purchase"], tl[tl["event_type"] == "return_request"]
    mine_lines, mine_req = lines[lines["customer_id"] == cid], req[req["customer_id"] == cid]
    if len(purchases) != len(mine_lines) or len(returns) != len(mine_req):
        tl_issues.append((cid, "count", len(purchases), len(mine_lines), len(returns), len(mine_req)))
        continue
    merged = returns.merge(mine_req, left_on=["order_id", "order_line_no"], right_on=["order_id", "order_line_no"], suffixes=("", "_raw"))
    bad_day = merged[(merged["day_in_window"].notna()) & (merged["day_in_window"] != merged["days"])]
    if len(bad_day):
        tl_issues.append((cid, "day_in_window", bad_day[["day_in_window", "days"]].head(2).to_dict("records")))
    bad_amt = merged[(merged["amount_inr"] - merged["refund_amount"].astype(float)).abs() > 0.005]
    if len(bad_amt):
        tl_issues.append((cid, "refund amount", bad_amt[["amount_inr", "refund_amount"]].head(2).to_dict("records")))
print("  timeline issues:", len(tl_issues), tl_issues[:4])
for issue in tl_issues[:2]:
    finding("Medium", "Timeline", f"{issue}")

print("\n== B5-B6 linked-account edges against shared identifiers")
ids = {k: so.groupby("customer_id")[k].apply(set) for k in ("address_id", "device_id", "payment_id")}
fan = {k: so.groupby(k)["customer_id"].nunique() for k in ("address_id", "device_id", "payment_id")}
claims = req[req["is_claim"]][["customer_id", "style_id", "req_day"]]
edge_issues, match_issues, checked = [], [], 0
seen_comm = set()
for cid in everyone_comm.index:
    comm_id = everyone_comm.loc[cid, "cid"]
    if comm_id in seen_comm or (everyone_comm.loc[cid, "kind"] != "ring" and len(seen_comm) > 80):
        continue
    seen_comm.add(comm_id)
    detail = get(f"/runs/{RUN}/customers/{cid}")["community"]
    for e in detail["edges"]:
        checked += 1
        shared = {k.replace("_id", "") for k in ids if (ids[k].get(e["a"], set()) & ids[k].get(e["b"], set()))
                  and any(fan[k][v] <= 25 for v in ids[k][e["a"]] & ids[k][e["b"]])}
        if not set(e["types"]) <= shared or len(set(e["types"])) < 2:
            edge_issues.append((e["a"], e["b"], e["types"], sorted(shared)))
        ca, cb = claims[claims["customer_id"] == e["a"]], claims[claims["customer_id"] == e["b"]]
        pairs = ca.merge(cb, on="style_id")
        near = int(((pairs["req_day_x"] - pairs["req_day_y"]).abs().dt.days <= 7).sum()) if len(pairs) else 0
        if (near > 0) != (e["coordinated_claim_matches"] > 0):
            match_issues.append((e["a"], e["b"], e["coordinated_claim_matches"], near))
print(f"  edges checked {checked} in {len(seen_comm)} communities | edges not backed by two shared identifier types: {len(edge_issues)} {edge_issues[:3]}")
print("  coordinated-claim flags that disagree with a recount (same style, within 7 days):", len(match_issues), match_issues[:3])
if edge_issues:
    finding("High", "Linked accounts", f"{len(edge_issues)} edges are not backed by two shared identifier types, e.g. {edge_issues[0]}")
if match_issues:
    finding("Medium", "Linked accounts", f"{len(match_issues)} coordinated-claim flags disagree with a same-style-within-7-days recount, e.g. {match_issues[0]}")

print("\n== B7 style counts")
style_issues = []
selected_ids = set(sel.index)
for s in styles:
    st = s["style_id"]
    ml = mature[mature["style_id"] == st]
    mr = mreq[mreq["style_id"] == st]
    returners = set(mr["customer_id"])
    fr = s["flagged_returner_share"] or {}
    if fr and fr["denominator"] != len(returners):
        style_issues.append((st, "returners", fr["denominator"], len(returners)))
    if fr and fr["numerator"] != len(returners & selected_ids):
        style_issues.append((st, "flagged", fr["numerator"], len(returners & selected_ids)))
    api_codes = {r["code"]: r["lines"] for r in s["reason_codes"]}
    raw_all = req[req["style_id"] == st].groupby("reason_code").size().to_dict()
    raw_mat = mr.groupby("reason_code").size().to_dict()
    if api_codes != raw_all and api_codes != raw_mat:
        style_issues.append((st, "reason lines", dict(list(api_codes.items())[:3]), dict(list(raw_all.items())[:3])))
print("  style count issues:", len(style_issues), style_issues[:5])
for issue in style_issues[:2]:
    finding("Medium", "Style counts", f"{issue}")

print("\n== B8 basket expectation calibration over the eligible")
be = pd.DataFrame([b for b in elig["basket_expectation"] if b])
print(f"  sum expected {be['expected_units'].sum():.0f} vs sum actual {be['actual_units'].sum():.0f} "
      f"| share of customers inside their band {((be['actual_units'] >= be['band_low']) & (be['actual_units'] <= be['band_high'])).mean():.3f}"
      f" | band_low negative for {(be['band_low'] < 0).sum()} customers")
gap = abs(be['expected_units'].sum() - be['actual_units'].sum()) / be['actual_units'].sum()
if gap > 0.05:
    finding("Medium", "Basket expectation", f"expected and actual units differ by {gap:.1%} over the eligible population")

print("\n== FINDINGS")
for sev, area, text in FINDINGS:
    print(f"- [{sev}] {area}: {text}")
