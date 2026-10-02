"""Exploratory data analysis for development worlds (final-spec component 05).

Every function takes a generated or stored world and returns small summary tables. Private truth is joined
freely here, so this module is for fixture, training and stress worlds only and none of its output may be
used as an operational feature. Counts always say what they count: units, lines, orders or customers.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from arai import diagnostics
from arai.diagnostics import CLAIM_CODES, FANOUT_CAP, QUALITY_CODES

FIT_CODES = ("wrong_size", "didnt_fit")
DISCRETIONARY_CODES = ("didnt_suit", "changed_my_mind", "not_as_expected", "found_better_price", "ordered_by_mistake", "late_delivery")
ORDER_BUCKETS = [0, 1, 3, 6, 11, 21, np.inf]
ORDER_BUCKET_LABELS = ["0", "1-2", "3-5", "6-10", "11-20", "21+"]
LINE_KEY = ["order_id", "order_line_no"]


def ratio(numerator, denominator):
    """A ratio that is null, never zero, when its denominator is zero."""
    return float(numerator) / float(denominator) if denominator else None


def auc(score, label) -> float | None:
    """Area under the ROC curve from ranks (ties share a rank). Null when one class is absent."""
    label = np.asarray(label).astype(bool)
    positives, negatives = int(label.sum()), int((~label).sum())
    if not positives or not negatives:
        return None
    ranks = stats.rankdata(np.asarray(score, dtype=float))
    return float((ranks[label].sum() - positives * (positives + 1) / 2) / (positives * negatives))


def enrichment(population: int, positives: int, subset: int, subset_positives: int) -> dict:
    """Enrichment and recall of a subset: (positive_subset/subset_size) / (positive_total/population)."""
    base, inside = ratio(positives, population), ratio(subset_positives, subset)
    return {"enrichment": None if not base or inside is None else inside / base,
            "recall": ratio(subset_positives, positives)}


# ------------------------------------------------------------------ structure
def structure(world) -> pd.DataFrame:
    """Rows, duplicate keys and empty cells per table."""
    from arai.generator.assemble import PRIMARY_KEYS
    rows = []
    for name, table in world.tables.items():
        nulls = table.isna().sum()
        rows.append({"table": name, "rows": len(table), "columns": table.shape[1],
                     "duplicate_keys": int(table.duplicated(PRIMARY_KEYS[name]).sum()),
                     "columns_with_nulls": ", ".join(f"{c} ({n})" for c, n in nulls[nulls > 0].items()) or "none"})
    return pd.DataFrame(rows)


def coverage(world) -> dict:
    """Time coverage and feasibility: nothing before signup or launch, nothing after the cutoff."""
    t = world.tables
    orders = t["sales_order"].merge(t["customer_master"][["customer_id", "signup_date"]], on="customer_id")
    lines = t["sales_order_line"].merge(t["sales_order"][["order_id", "order_date"]], on="order_id") \
                                 .merge(t["sku_master"][["sku", "launch_date"]], on="sku")
    returns = t["return_order_line"]
    cutoff = pd.Timestamp(world.snapshot_date) + pd.Timedelta(hours=23, minutes=59, seconds=59)
    return {
        "first_order": str(orders["order_date"].min().date()), "last_order": str(orders["order_date"].max().date()),
        "first_signup": str(t["customer_master"]["signup_date"].min().date()),
        "customers_signed_up_before_history": int((t["customer_master"]["signup_date"] < orders["order_date"].min()).sum()),
        "orders_before_signup": int((orders["order_date"] < orders["signup_date"]).sum()),
        "lines_before_sku_launch": int((lines["order_date"] < lines["launch_date"]).sum()),
        "requests_after_cutoff": int((returns["requested_at"] > cutoff).sum()),
        "currencies": sorted(t["sales_order"]["currency"].unique().tolist()),
        "customers_without_orders": int((~t["customer_master"]["customer_id"].isin(orders["customer_id"])).sum()),
    }


def distributions(world) -> dict:
    """Basket, quantity, order count, order value, maturity and state distributions."""
    t = world.tables
    lines = diagnostics.sale_lines(world)
    per_customer = t["sales_order"].groupby("customer_id").size().reindex(t["customer_master"]["customer_id"], fill_value=0)
    quantiles = [0.1, 0.25, 0.5, 0.75, 0.9, 0.99]
    delivered = lines[lines["line_status"] == "delivered"]
    return {
        "lines_per_order": lines.groupby("order_id").size().value_counts(normalize=True).sort_index().round(4),
        "quantity_per_line": lines["quantity"].value_counts(normalize=True).sort_index().round(4),
        "orders_per_customer": per_customer.quantile(quantiles).rename("orders per customer"),
        "order_total_inr": t["sales_order"]["order_total"].quantile(quantiles).round(0).rename("order total (INR)"),
        "line_status": lines["line_status"].value_counts(normalize=True).round(4),
        "return_line_status": t["return_order_line"]["line_status"].value_counts(normalize=True).round(4),
        "return_window_days": lines["return_window_days"].value_counts(normalize=True).sort_index().round(4),
        "channel": t["sales_order"]["channel"].value_counts(normalize=True).round(4),
        "discounted_line_share": round(float((lines["line_discount"] > 0).mean()), 4),
        "mature_share_of_delivered_lines": round(float(delivered["mature"].mean()), 4),
        "bracketed_order_share": round(float(
            delivered.groupby(["order_id", "style_id"])["sku"].nunique().gt(1).groupby("order_id").any().mean()), 4),
    }


def _opportunities(world) -> pd.DataFrame:
    """Abusive actions counted once per opportunity: the further lines of a whole-parcel claim are left out."""
    actions = world.truth["action_truth"]
    return actions[~actions["parcel_companion"]] if "parcel_companion" in actions else actions


def _requests(world) -> pd.DataFrame:
    """Return lines with sale-line context, reason group, timing and private intent."""
    t = world.tables
    lines = diagnostics.sale_lines(world)
    out = t["return_order_line"].merge(lines[LINE_KEY + ["customer_id", "style_id", "category", "delivered_date",
                                                         "return_window_days", "mature", "is_occasion_wear"]], on=LINE_KEY)
    out["days"] = (out["requested_at"].dt.normalize() - out["delivered_date"]).dt.days
    out["window_ratio"] = out["days"] / out["return_window_days"]
    out["group"] = np.select([out["reason_code"].isin(CLAIM_CODES), out["reason_code"].isin(QUALITY_CODES),
                              out["reason_code"] == "damaged", out["reason_code"].isin(FIT_CODES)],
                             ["transaction claim", "quality complaint", "carrier damage", "fit"], default="discretionary")
    actions = world.truth["action_truth"]
    actions = actions[actions["completed_action"]][["return_order_id", "return_line_no", "action_type", "campaign_id"]]
    out = out.merge(actions, on=["return_order_id", "return_line_no"], how="left")
    out["intent"] = out["action_type"].fillna("honest")
    return out


def reasons_and_timing(world) -> dict:
    """Reason mix, and where in the return window each kind of request arrives."""
    requests = _requests(world)
    active = requests[requests["line_status"] != "withdrawn"]
    timing = active.groupby("group")["window_ratio"].describe(percentiles=[0.5, 0.9])[["count", "mean", "50%", "90%"]].round(3)
    by_intent = active.groupby("intent")["window_ratio"].describe(percentiles=[0.5, 0.9])[["count", "mean", "50%", "90%"]].round(3)
    return {"reason_group_share": active["group"].value_counts(normalize=True).round(4),
            "reason_code_share": active["reason_code"].value_counts(normalize=True).round(4),
            "window_ratio_by_reason_group": timing, "window_ratio_by_intent": by_intent,
            "late_request_share": round(float((active["window_ratio"] > 1).mean()), 4),
            "requests_at_or_after_three_quarters_of_window": round(float((active["window_ratio"] >= 0.75).mean()), 4)}


def code_overlap(world) -> pd.DataFrame:
    """Per reason code, how many requests are honest and how many deceptive (lines, not units)."""
    requests = _requests(world)
    requests = requests[requests["line_status"] != "withdrawn"]
    table = pd.crosstab(requests["reason_code"], requests["intent"])
    table["deceptive_or_temporary"] = table.drop(columns="honest", errors="ignore").sum(axis=1)
    if "honest" not in table:
        table["honest"] = 0
    table["deceptive_share"] = (table["deceptive_or_temporary"] / (table["deceptive_or_temporary"] + table["honest"])).round(3)
    table["code_has_honest_use"] = table["honest"] > 0
    return table.sort_values("deceptive_or_temporary", ascending=False)


# ------------------------------------------------------------------ targets and labels
def targets_vs_realised(world, settings) -> pd.DataFrame:
    """Configured generation targets beside what the world realised."""
    truth, t = world.truth, world.tables
    accepted = settings.accepted
    profile, units = truth["customer_profile"], truth["unit_truth"]
    propensity = profile[profile["claim_propensity"] | profile["temporary_use_propensity"]]
    rates = np.r_[propensity.loc[propensity["claim_propensity"], "claim_action_rate"],
                  propensity.loc[propensity["temporary_use_propensity"], "temporary_use_action_rate"]]
    lines = t["sales_order_line"]
    orders = t["sales_order"].merge(truth["order_truth"][["order_id", "layer"]], on="order_id")
    base_orders = orders[orders["layer"] == "base"]
    realised_orders = base_orders.groupby("customer_id").size().reindex(profile["customer_id"], fill_value=0).to_numpy()
    requests = _requests(world)
    honest = requests[(requests["intent"] == "honest") & (requests["line_status"] != "withdrawn")]
    delivered_units = lines.loc[lines["line_status"] == "delivered", "quantity"].sum()
    rows = [
        ("claim propensity, share of accounts", 0.04, profile["claim_propensity"].mean()),
        ("temporary-use propensity, share of accounts", 0.03, profile["temporary_use_propensity"].mean()),
        ("both propensities, share of accounts", 0.005, (profile["claim_propensity"] & profile["temporary_use_propensity"]).mean()),
        ("mean action rate of propensity accounts", accepted["action_rate_mean_per_relevant_order"], rates.mean() if len(rates) else np.nan),
        ("genuine fulfilment failure per delivered unit", sum(accepted["genuine_claim_rates"].values()),
         units["genuine_fulfilment_cause"].notna().mean()),
        ("carrier damage per delivered unit", accepted["carrier_damage_rate"], units["carrier_damage"].mean()),
        ("cancelled share of lines", accepted["cancel_probability"], (lines["line_status"] == "cancelled").mean()),
        ("household members, share of accounts", accepted["household_member_share"], truth["customer_truth"]["household_id"].notna().mean()),
        ("heavy-return overlay, share of accounts", accepted["heavy_return_share"], profile["heavy_return_overlay"].mean()),
        ("orders per account (target total / realised base orders)", profile["target_order_count"].mean(), realised_orders.mean()),
        ("honest requested units per delivered unit (mean target propensity)", np.average(
            profile["target_return_propensity"], weights=np.maximum(profile["target_order_count"], 0)) if profile["target_order_count"].sum() else np.nan,
         honest["quantity_returned"].sum() / delivered_units if delivered_units else np.nan),
        ("withdrawn share of honest requests", accepted["honest_withdraw_probability"],
         (requests.loc[requests["intent"] == "honest", "line_status"] == "withdrawn").mean()),
        ("late share of honest item-return requests", accepted["max_late_request_share"],
         (honest.loc[honest["group"] != "transaction claim", "window_ratio"] > 1).mean()),
    ]
    out = pd.DataFrame(rows, columns=["measure", "target", "realised"])
    out["relative_deviation"] = (out["realised"] / out["target"] - 1).round(3)
    return out


def eligibility(world) -> dict:
    """Eligibility and the abuse it excludes, with every denominator."""
    summary = diagnostics.customer_summary(world)
    eligible = summary[summary["eligible"]]
    excluded = summary[~summary["eligible"]]
    actions = _opportunities(world)
    completed = actions[actions["completed_action"]]
    by_type = completed.merge(summary[["customer_id", "eligible"]], on="customer_id").groupby("action_type")["eligible"] \
        .agg(completed_actions="size", on_eligible_customers="sum")
    return {
        "customers": len(summary), "eligible_customers": len(eligible), "excluded_customers": len(excluded),
        "excluded_without_any_order": int((excluded["orders"] == 0).sum()),
        "abusers_all": int(summary["y_abuse"].sum()), "abusers_eligible": int(eligible["y_abuse"].sum()),
        "abusers_excluded": int(excluded["y_abuse"].sum()),
        "prevalence_all": ratio(summary["y_abuse"].sum(), len(summary)),
        "prevalence_eligible": ratio(eligible["y_abuse"].sum(), len(eligible)),
        "prevalence_excluded": ratio(excluded["y_abuse"].sum(), len(excluded)),
        "excluded_abuse_share_of_all_abusers": ratio(excluded["y_abuse"].sum(), summary["y_abuse"].sum()),
        "review_budget_k_at_5pct": int(np.ceil(0.05 * len(eligible))) if len(eligible) else 0,
        "completed_actions_by_type": by_type,
    }


def opportunities(world) -> pd.DataFrame:
    """Abusive opportunities drawn, completed and blocked, by scope and action type (actions, not customers)."""
    actions = _opportunities(world).copy()
    actions["scope"] = np.where(actions["campaign_id"].notna(), "ring campaign", "solo")
    actions["outcome"] = np.where(actions["completed_action"], "completed", actions["uncompleted_reason"])
    return pd.crosstab([actions["scope"], actions["action_type"]], actions["outcome"], margins=True, margins_name="all")


def prevalence_by(world) -> dict:
    """Prevalence by persona and by order count. More orders mean more chances to act, by construction."""
    summary = diagnostics.customer_summary(world)
    summary["order_bucket"] = pd.cut(summary["orders"], ORDER_BUCKETS, right=False, labels=ORDER_BUCKET_LABELS)
    summary["has_propensity"] = summary["claim_propensity"] | summary["temporary_use_propensity"]

    def table(key):
        grouped = summary.groupby(key, observed=True)
        out = grouped.agg(customers=("customer_id", "size"), eligible=("eligible", "sum"), abusers=("y_abuse", "sum"),
                          propensity_accounts=("has_propensity", "sum"))
        out["abusers_eligible"] = summary[summary["eligible"]].groupby(key, observed=True)["y_abuse"].sum().reindex(out.index, fill_value=0)
        out["prevalence"] = (out["abusers"] / out["customers"]).round(4)
        out["prevalence_eligible"] = (out["abusers_eligible"] / out["eligible"].replace(0, np.nan)).round(4)
        out["propensity_share"] = (out["propensity_accounts"] / out["customers"]).round(4)
        out["acted_given_propensity"] = (out["abusers"] / out["propensity_accounts"].replace(0, np.nan)).round(3)
        return out
    return {"by_persona": table("persona"), "by_order_count": table("order_bucket")}


def benign_segments(world) -> pd.DataFrame:
    """Evaluation segments of final-spec component 08, per eligible honest customer.

    heavy returner: raw return rate at or above the 90th percentile of all eligible customers;
    defective buyer: requested at least one genuinely defective unit on a mature line;
    household: actually used an identifier that another member of the same household also used.
    """
    summary = diagnostics.customer_summary(world)
    eligible = summary[summary["eligible"]]
    threshold = eligible["raw_return_rate"].quantile(0.9, interpolation="linear") if len(eligible) else np.nan
    heavy = set(eligible.loc[eligible["raw_return_rate"] >= threshold, "customer_id"])

    lines = diagnostics.sale_lines(world)
    allocation = world.truth["unit_allocation"]
    defective = world.truth["unit_truth"]
    defective = defective[defective["received_defective_unit"]][LINE_KEY + ["unit_index"]]
    requested = allocation[allocation["reservation_kind"] == "honest_request"].merge(defective, on=LINE_KEY + ["unit_index"])
    active = world.tables["return_order_line"]
    active = active[active["line_status"] != "withdrawn"][LINE_KEY].drop_duplicates()
    requested = requested.merge(active, on=LINE_KEY).merge(lines[LINE_KEY + ["customer_id", "mature"]], on=LINE_KEY)
    defective_buyers = set(requested.loc[requested["mature"], "customer_id"])

    truth = world.truth["customer_truth"]
    members = truth[truth["household_id"].notna()][["customer_id", "household_id"]]
    orders = world.tables["sales_order"].merge(members, on="customer_id")
    sharing = set()
    for kind in ("address_id", "device_id", "payment_id"):
        users = orders.groupby(["household_id", kind])["customer_id"].nunique()
        shared = users[users > 1].reset_index()[["household_id", kind]]
        sharing |= set(orders.merge(shared, on=["household_id", kind])["customer_id"])

    out = summary[["customer_id", "eligible", "y_abuse"]].copy()
    benign = out["eligible"] & (out["y_abuse"] == 0)
    out["legit_heavy_returner"] = benign & out["customer_id"].isin(heavy)
    out["defective_product_buyer"] = benign & out["customer_id"].isin(defective_buyers)
    out["benign_household"] = benign & out["customer_id"].isin(sharing)
    return out


def group_overlap(world) -> dict:
    """Overlap among action types and among benign segments. Overlapping groups are never summed as disjoint."""
    truth = world.truth["customer_truth"]
    kinds = ["deceptive_nonreceipt_claim", "deceptive_contents_claim", "temporary_use_return"]
    acted = truth[truth["y_abuse"] == 1]
    actions = pd.DataFrame({a: {b: int((acted[a] & acted[b]).sum()) for b in kinds} for a in kinds})
    segments = benign_segments(world)
    names = ["legit_heavy_returner", "defective_product_buyer", "benign_household"]
    benign = pd.DataFrame({a: {b: int((segments[a] & segments[b]).sum()) for b in names} for a in names})
    return {"action_type_overlap_customers": actions, "benign_segment_overlap_customers": benign,
            "benign_segment_sizes": {n: int(segments[n].sum()) for n in names},
            "eligible_honest_customers": int((segments["eligible"] & (segments["y_abuse"] == 0)).sum()),
            "abusers_with_more_than_one_action_type": int((acted[kinds].sum(axis=1) > 1).sum()),
            "coordinated_abusers": int(acted["coordinated_action_flag"].sum())}


def ingredient_support(world) -> pd.DataFrame:
    """Share of eligible customers for whom each feature ingredient is undefined, by label.

    A feature that is null for most honest customers and present for most abusers (or the reverse) lets a
    model learn from missingness alone; this table makes that visible before features exist.
    """
    summary = diagnostics.customer_summary(world)
    eligible = summary[summary["eligible"]].set_index("customer_id")
    requests = _requests(world)
    requests = requests[requests["line_status"] != "withdrawn"]
    neighbours = diagnostics.observed_graph(world)
    has = pd.DataFrame(index=eligible.index)
    has["any return request"] = has.index.isin(requests["customer_id"])
    has["any transaction claim"] = has.index.isin(requests.loc[requests["group"] == "transaction claim", "customer_id"])
    has["any request on a mature line"] = has.index.isin(requests.loc[requests["mature"], "customer_id"])
    has["any supported neighbour"] = has.index.isin(list(neighbours))
    undefined = (~has).groupby(eligible["y_abuse"].map({0: "honest", 1: "abuser"})).mean().T.round(3)
    undefined.columns = [f"undefined for {c}" for c in undefined.columns]
    return undefined


# ------------------------------------------------------------------ abuse mechanics
def action_rates(world) -> dict:
    """Per-account action rates and how often a propensity account ends up acting at all."""
    profile = world.truth["customer_profile"]
    done = _opportunities(world).query("completed_action").groupby("customer_id").size()
    rates = pd.concat([profile.loc[profile["claim_propensity"], "claim_action_rate"],
                       profile.loc[profile["temporary_use_propensity"], "temporary_use_action_rate"]])
    propensity = profile[profile["claim_propensity"] | profile["temporary_use_propensity"]]
    return {"rate_quantiles": rates.quantile([0.05, 0.25, 0.5, 0.75, 0.95]).round(3),
            "rate_below_5pct_share": round(float((rates < 0.05).mean()), 3) if len(rates) else None,
            "propensity_accounts": len(propensity), "propensity_accounts_that_acted": int(propensity["customer_id"].isin(done.index).sum()),
            "completed_actions_per_abuser": done.quantile([0.25, 0.5, 0.75, 0.95]) if len(done) else done,
            "one_off_abuser_share": round(float((done == 1).mean()), 3) if len(done) else None}


def address_claims(world) -> dict:
    """Genuine claims are clustered by address: how concentrated, and how many honest repeat claimants result."""
    address, units = world.truth["address_truth"], world.truth["unit_truth"]
    lines = world.tables["sales_order_line"].merge(world.tables["sales_order"][["order_id", "address_id", "customer_id"]], on="order_id")
    units = units.merge(lines[LINE_KEY + ["address_id", "customer_id"]], on=LINE_KEY).merge(address, on=["world_id", "address_id"], how="left")
    units["bucket"] = pd.cut(units["genuine_failure_multiplier"], [0, 0.25, 1, 2, 4, np.inf], right=False,
                             labels=["<0.25x", "0.25-1x", "1-2x", "2-4x", ">=4x"])
    by_bucket = units.groupby("bucket", observed=True).agg(delivered_units=("unit_index", "size"),
                                                           genuine_claim_units=("genuine_fulfilment_cause", "count"))
    by_bucket["claim_rate"] = (by_bucket["genuine_claim_units"] / by_bucket["delivered_units"]).round(4)
    by_bucket["share_of_genuine_claims"] = (by_bucket["genuine_claim_units"] / by_bucket["genuine_claim_units"].sum()).round(3)
    genuine = units[units["genuine_fulfilment_cause"].notna()].groupby("customer_id").size()
    truth = world.truth["customer_truth"].set_index("customer_id")["y_abuse"]
    honest = genuine[truth.reindex(genuine.index) == 0]
    return {"by_address_multiplier": by_bucket, "multiplier_mean": round(float(address["genuine_failure_multiplier"].mean()), 3),
            "addresses_at_4x_or_more_share": round(float((address["genuine_failure_multiplier"] >= 4).mean()), 3),
            "honest_customers_with_2plus_genuine_claims": int((honest >= 2).sum()),
            "honest_customers_with_3plus_genuine_claims": int((honest >= 3).sum())}


def hot_list_coverage(world) -> pd.DataFrame:
    """Per hot-list style: rings that planned, rings that completed, completing accounts and claim sources."""
    product = world.truth["product_truth"]
    hot = product[product["hot_listed"]].copy()
    actions = _opportunities(world)
    coordinated = actions[actions["campaign_id"].notna()].merge(
        world.truth["campaign"][["campaign_id", "target_style_id"]], on="campaign_id")
    stats_ = coordinated.groupby("target_style_id").agg(
        attempts=("action_id", "size"), completed=("completed_action", "sum"),
        completing_accounts=("customer_id", lambda s: s[coordinated.loc[s.index, "completed_action"]].nunique()),
        campaign_orders=("claim_source", lambda s: int((s == "campaign_order").sum())),
        reused_purchases=("claim_source", lambda s: int((s == "reused_purchase").sum())))
    hot["rings_planned"] = hot["planned_targeted_by"].map(len)
    hot["rings_completed"] = hot["completed_targeted_by"].map(len)
    return hot[["style_id", "rings_planned", "rings_completed", "targeting_level"]].merge(
        stats_, left_on="style_id", right_index=True, how="left").fillna(0)


def relationships(world) -> dict:
    """Assigned sharing against what the identifiers actually show, plus graph fan-out and connectivity."""
    orders, truth = world.tables["sales_order"], world.truth["customer_truth"]
    relationship = world.truth["relationship_truth"]
    column = {"address": "address_id", "device": "device_id", "payment": "payment_id"}
    # realised usage: share of a member's orders that carry the group's shared value
    used = []
    for kind, name in column.items():
        part = relationship[relationship["identifier_type"] == kind].merge(orders[["customer_id", name]], on="customer_id")
        part["used"] = part[name] == part["shared_value"]
        used.append(part.groupby(["group_type", "group_id", "customer_id", "identifier_type", "sampled_usage_probability"])["used"]
                    .agg(orders="size", realised="mean").reset_index())
    used = pd.concat(used, ignore_index=True) if used else pd.DataFrame()
    usage = used.groupby(["group_type", "identifier_type"]).agg(
        members_with_orders=("customer_id", "size"), mean_sampled_probability=("sampled_usage_probability", "mean"),
        mean_realised_usage=("realised", "mean"), never_used=("realised", lambda s: int((s == 0).sum()))).round(3)

    fanout = pd.concat({kind: orders.groupby(name)["customer_id"].nunique() for kind, name in column.items()})
    fanout_table = fanout.groupby(level=0).agg(values="size", shared_by_2plus=lambda s: int((s >= 2).sum()),
                                               dropped_above_cap=lambda s: int((s > FANOUT_CAP).sum()), largest="max")

    neighbours = diagnostics.observed_graph(world)
    linked = set(neighbours)
    rows = []
    for label, mask in (("household members", truth["household_id"].notna()),
                        ("coordination-group members", truth["coordination_group_id"].notna()),
                        ("shared-location members", truth["shared_location_id"].notna()),
                        ("ungrouped accounts", truth[["household_id", "coordination_group_id", "shared_location_id"]].isna().all(axis=1))):
        ids = truth.loc[mask, "customer_id"]
        rows.append({"group": label, "accounts": len(ids), "with_supported_neighbour": int(ids.isin(linked).sum()),
                     "share": ratio(ids.isin(linked).sum(), len(ids))})
    # connected components of the supported graph
    seen, sizes = set(), []
    for start in neighbours:
        if start in seen:
            continue
        stack, size = [start], 0
        seen.add(start)
        while stack:
            node = stack.pop()
            size += 1
            for other in neighbours[node]:
                if other not in seen:
                    seen.add(other)
                    stack.append(other)
        sizes.append(size)
    sizes = pd.Series(sizes, dtype=int)
    return {"usage": usage, "fanout": fanout_table, "linked_by_group": pd.DataFrame(rows),
            "components": {"count": len(sizes), "largest": int(sizes.max()) if len(sizes) else 0,
                           "size_distribution": sizes.value_counts().sort_index().to_dict()},
            "linked_accounts_that_are_ring_members_share": ratio(
                truth.loc[truth["coordination_group_id"].notna(), "customer_id"].isin(linked).sum(), len(linked))}


# ------------------------------------------------------------------ across worlds
def persona_table(world) -> pd.DataFrame:
    summary = diagnostics.customer_summary(world)
    return summary[["customer_id", "persona", "orders", "eligible", "y_abuse", "raw_return_rate", "claim_lines"]].assign(world_id=world.world_id)


def held_out_auc(train: pd.DataFrame, held_out: pd.DataFrame) -> pd.DataFrame:
    """AUC of two label-free shortcuts on held-out worlds: persona alone and order volume alone.

    Persona prevalence is learned on the training half and scored on the held-out half. Equal propensity
    does not imply AUC 0.5 for completed actions: accounts with more orders have more chances to act.
    """
    rows = []
    for label, frame_train, frame_test in (("all customers", train, held_out),
                                           ("eligible customers", train[train["eligible"]], held_out[held_out["eligible"]])):
        prevalence = frame_train.groupby("persona")["y_abuse"].mean()
        rows.append({"population": label, "customers": len(frame_test), "abusers": int(frame_test["y_abuse"].sum()),
                     "persona_only_auc": auc(frame_test["persona"].map(prevalence).fillna(0), frame_test["y_abuse"]),
                     "order_count_only_auc": auc(frame_test["orders"], frame_test["y_abuse"]),
                     "raw_return_rate_auc": auc(frame_test["raw_return_rate"].fillna(-1), frame_test["y_abuse"]),
                     "claim_count_auc": auc(frame_test["claim_lines"], frame_test["y_abuse"])})
    return pd.DataFrame(rows).round(3)


def allocation_independence(world) -> dict:
    """Stress 2507: with every actionable multiplier at 1, propensity must not depend on persona."""
    profile = world.truth["customer_profile"]
    actionable = profile[profile["target_order_count"] > 0]
    has = actionable["claim_propensity"] | actionable["temporary_use_propensity"]
    table = pd.crosstab(actionable["persona"], has)
    chi2, p_value, dof, _ = stats.chi2_contingency(table)
    rate = has.groupby(actionable["persona"]).agg(accounts="size", propensity_share="mean").round(4)
    return {"propensity_share_by_persona": rate, "chi2": round(float(chi2), 2), "dof": int(dof), "p_value": round(float(p_value), 4)}


def stress_metrics(world) -> dict:
    """The handful of measures the stress worlds are meant to move, one mechanism at a time."""
    truth, lines = world.truth, world.tables["sales_order_line"]
    profile = truth["customer_profile"]
    propensity = profile[profile["claim_propensity"] | profile["temporary_use_propensity"]]
    rates = np.r_[propensity.loc[propensity["claim_propensity"], "claim_action_rate"],
                  propensity.loc[propensity["temporary_use_propensity"], "temporary_use_action_rate"]]
    requests = _requests(world)
    honest = requests[(requests["intent"] == "honest") & (requests["line_status"] != "withdrawn")]
    delivered_units = lines.loc[lines["line_status"] == "delivered", "quantity"].sum()
    segments = benign_segments(world)
    summary = diagnostics.customer_summary(world)
    eligible = summary[summary["eligible"]]
    completed = _opportunities(world)["completed_action"].sum()
    return {
        "propensity_share": round(float(len(propensity) / len(profile)), 4),
        "mean_action_rate": round(float(rates.mean()), 4) if len(rates) else None,
        "completed_actions": int(completed),
        "honest_requested_units_per_delivered_unit": round(float(honest["quantity_returned"].sum() / delivered_units), 4),
        "defect_prone_styles": int((truth["product_truth"]["defect_state"] == "defect_prone").sum()),
        "defective_product_buyers": int(segments["defective_product_buyer"].sum()),
        "household_member_share": round(float(truth["customer_truth"]["household_id"].notna().mean()), 4),
        "benign_household_segment": int(segments["benign_household"].sum()),
        "prevalence_eligible": ratio(eligible["y_abuse"].sum(), len(eligible)),
        "return_rate_rule_precision_at_5pct": diagnostics.precision_at(world, summary, "raw_return_rate")["precision"],
    }


def collect(world, settings) -> dict:
    """Everything the exploration notebook needs from one world, as small tables."""
    summary = diagnostics.customer_summary(world)
    summary["claim_count"] = summary["claim_lines"]
    segments = benign_segments(world)
    requests = _requests(world)
    active = requests[requests["line_status"] != "withdrawn"]
    return {
        "world_id": world.world_id, "purpose": world.purpose,
        "structure": structure(world), "coverage": coverage(world),
        "targets": targets_vs_realised(world, settings).assign(world_id=world.world_id),
        "eligibility": eligibility(world),
        "opportunities": opportunities(world),
        "persona": persona_table(world),
        "segments": {name: int(segments[name].sum()) for name in ("legit_heavy_returner", "defective_product_buyer", "benign_household")},
        "overlap": group_overlap(world),
        "codes": code_overlap(world),
        "support": ingredient_support(world),
        "styles": diagnostics.style_evidence(world).assign(world_id=world.world_id),
        "rules": {"rank by raw return rate": diagnostics.precision_at(world, summary, "raw_return_rate"),
                  "rank by number of claims": diagnostics.precision_at(world, summary, "claim_count")},
        "rates": action_rates(world), "addresses": address_claims(world),
        "relationships": relationships(world), "hot_list": hot_list_coverage(world),
        "timing": active[["intent", "group", "window_ratio"]].assign(world_id=world.world_id),
        "stress": stress_metrics(world),
        "audit": artefact_audit(world), "orders": order_artefacts(world), "linked": linked_claimants(world),
        "claims_monthly": claims_by_month(world),
        "gate_preview": rule_gate_preview(world).assign(world_id=world.world_id),
        "opportunity": opportunity_prevalence(world),
    }


def detector_table(styles: pd.DataFrame, thresholds=(0.05, 0.075, 0.10)) -> pd.DataFrame:
    """Pooled style-signal performance against private truth, at several linked-claim thresholds.

    A detection on a sub_threshold style is reported separately and never counted as correct.
    """
    supported = styles[styles["mature_sale_lines"] >= 20]
    targeted = supported["targeting_level"] == "targeted"
    rows = []
    for threshold in thresholds:
        fired = (supported["linked_claimers"] >= 3) & (supported["linked_claim_share"] >= threshold)
        rows.append({"signal": f"targeting, linked share >= {threshold}", "truth_positive_styles": int(targeted.sum()),
                     "fired": int(fired.sum()), "true_positives": int((fired & targeted).sum()),
                     "fired_on_sub_threshold": int((fired & (supported["targeting_level"] == "sub_threshold")).sum()),
                     "precision": ratio((fired & targeted).sum(), fired.sum()), "recall": ratio((fired & targeted).sum(), targeted.sum())})
    rows.append({"signal": "targeting, three linked claimants only", "truth_positive_styles": int(targeted.sum()),
                 "fired": int((supported["linked_claimers"] >= 3).sum()),
                 "true_positives": int(((supported["linked_claimers"] >= 3) & targeted).sum()), "fired_on_sub_threshold": 0,
                 "precision": ratio(((supported["linked_claimers"] >= 3) & targeted).sum(), (supported["linked_claimers"] >= 3).sum()),
                 "recall": ratio(((supported["linked_claimers"] >= 3) & targeted).sum(), targeted.sum())})
    defect = supported["defect_state"] == "defect_prone"
    for threshold in (0.30, 0.50):
        fired = supported["damage_share"] >= threshold
        rows.append({"signal": f"quality, damage share >= {threshold}", "truth_positive_styles": int(defect.sum()),
                     "fired": int(fired.sum()), "true_positives": int((fired & defect).sum()), "fired_on_sub_threshold": 0,
                     "precision": ratio((fired & defect).sum(), fired.sum()), "recall": ratio((fired & defect).sum(), defect.sum())})
    table = pd.DataFrame(rows)
    # 95% Wilson intervals: these counts are small, so the point values alone overstate what is known
    table["recall_95"] = [wilson(tp, n) for tp, n in zip(table["true_positives"], table["truth_positive_styles"])]
    table["precision_95"] = [wilson(tp, n) for tp, n in zip(table["true_positives"], table["fired"])]
    return table


# ------------------------------------------------------------------ artefact audit (added after independent review)
def wilson(successes: int, trials: int, z: float = 1.96):
    """Wilson score interval for a proportion; (None, None) without trials."""
    if not trials:
        return None, None
    p = successes / trials
    centre = (p + z * z / (2 * trials)) / (1 + z * z / trials)
    half = z * np.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / (1 + z * z / trials)
    return float(centre - half), float(centre + half)


def request_kinds(world) -> pd.DataFrame:
    """Return lines labelled honest, solo abuse or ring abuse, with the shape of the order they sit on."""
    requests = _requests(world)
    requests["kind"] = np.where(requests["action_type"].isna(), "honest",
                                np.where(requests["campaign_id"].notna(), "ring abuse", "solo abuse"))
    lines = world.tables["sales_order_line"]
    shape = lines.groupby("order_id").agg(order_lines=("sku", "size"), order_units=("quantity", "sum"))
    delivered = lines[lines["line_status"] == "delivered"].groupby("order_id").size().rename("delivered_lines")
    requests = requests.merge(shape, on="order_id").merge(delivered, on="order_id") \
        .merge(lines[LINE_KEY + ["quantity"]].rename(columns={"quantity": "line_quantity"}), on=LINE_KEY)
    cutoff = pd.Timestamp(world.snapshot_date)
    requests["days_before_cutoff"] = (cutoff - requests["delivered_date"]).dt.days
    return requests


def nonreceipt_orders(requests: pd.DataFrame) -> pd.DataFrame:
    """Orders with a non-receipt claim and two or more delivered lines: does the claim cover every delivered line?

    One row per order and kind of request. An order claimed in part by an abuser and in part honestly is rare
    and appears once under each kind.
    """
    claims = requests[(requests["reason_code"] == "item_not_received") & (requests["delivered_lines"] >= 2)]
    per_order = claims.groupby(["order_id", "kind"]).agg(claimed_lines=("order_line_no", "nunique"),
                                                         delivered_lines=("delivered_lines", "first")).reset_index()
    per_order["whole_order"] = per_order["claimed_lines"] == per_order["delivered_lines"]
    return per_order


def artefact_audit(world) -> pd.DataFrame:
    """Could anything mechanical tell an abusive request from an honest one? One column per kind of request.

    A leak shows as a row where honest and abusive requests cannot overlap, for example a claim-timing range
    or an order shape that only one kind occupies. Rows marked "by design" are specified differences.
    """
    requests = request_kinds(world)
    claims = requests[requests["group"] == "transaction claim"]
    ordered = requests.sort_values(["return_order_id", "return_line_no"])
    out_of_order = ordered["requested_at"] < ordered.groupby("return_order_id")["requested_at"].shift()
    multi_line = claims[claims["order_lines"] >= 2]
    multi_unit = claims[claims["line_quantity"] >= 2]
    parcels = nonreceipt_orders(requests)
    rows = {
        "claim lines": claims.groupby("kind").size(),
        "claims: share with reason item_not_received": claims.groupby("kind")["reason_code"].apply(lambda s: (s == "item_not_received").mean()),
        "claims: share with a reason that needs no item back": claims.groupby("kind")["reason_code"].apply(
            lambda s: s.isin(["item_not_received", "empty_package"]).mean()),
        "claims on multi-line orders: share on the first line": multi_line.groupby("kind")["order_line_no"].apply(lambda s: (s == 1).mean()),
        "claims on multi-unit lines: share claiming every unit": multi_unit.groupby("kind").apply(
            lambda g: (g["quantity_returned"] == g["line_quantity"]).mean(), include_groups=False),
        "non-receipt on multi-line orders: share covering the whole order": parcels.groupby("kind")["whole_order"].mean(),
        "claims: median days after delivery": claims.groupby("kind")["days"].median(),
        "claims: 95th percentile days": claims.groupby("kind")["days"].quantile(0.95),
        "claims: maximum days": claims.groupby("kind")["days"].max(),
        "claims: share more than 10 days after delivery": claims.groupby("kind")["days"].apply(lambda s: (s > 10).mean()),
        "claims: share on single-line orders": claims.groupby("kind")["order_lines"].apply(lambda s: (s == 1).mean()),
        "claims: share on single-unit orders": claims.groupby("kind")["order_units"].apply(lambda s: (s == 1).mean()),
        "claims: share on lines delivered in the last 90 days": claims.groupby("kind")["days_before_cutoff"].apply(lambda s: (s <= 90).mean()),
        "claims: share on lines not yet mature": claims.groupby("kind")["mature"].apply(lambda s: (~s).mean()),
        "requests: lines out of time order in their header": out_of_order.groupby(ordered["kind"]).sum(),
        "requests: share refunded": requests.groupby("kind")["line_status"].apply(lambda s: (s == "refunded").mean()),
        "requests: share rejected": requests.groupby("kind")["line_status"].apply(lambda s: (s == "rejected").mean()),
        "requests: share withdrawn (by design honest only)": requests.groupby("kind")["line_status"].apply(lambda s: (s == "withdrawn").mean()),
        "requests: share after the window (by design honest only)": requests.groupby("kind")["window_ratio"].apply(lambda s: (s > 1).mean()),
        "requests: share with more than one unit": requests.groupby("kind")["quantity_returned"].apply(lambda s: (s > 1).mean()),
    }
    table = pd.DataFrame(rows).T.reindex(columns=["honest", "solo abuse", "ring abuse"])
    return table


def order_artefacts(world) -> dict:
    """Order-level checks: same-day orders, basket shape by private layer, and activity through the year."""
    orders = world.tables["sales_order"].merge(world.truth["order_truth"], on="order_id")
    lines = world.tables["sales_order_line"]
    shape = lines.groupby("order_id").agg(order_lines=("sku", "size"), order_units=("quantity", "sum"))
    orders = orders.merge(shape, on="order_id")
    orders["kind"] = np.where(orders["layer"] == "campaign", "campaign order",
                              np.where(orders["household_co_order"], "household co-order", "base order"))
    by_kind = orders.groupby("kind").agg(orders=("order_id", "size"), single_line_share=("order_lines", lambda s: (s == 1).mean()),
                                         mean_lines=("order_lines", "mean"), mean_units=("order_units", "mean"),
                                         mean_order_total=("order_total", "mean"))
    month = orders["order_date"].dt.to_period("M")
    monthly = pd.crosstab(month, orders["kind"])
    per_customer_day = orders.groupby(["customer_id", "order_date"]).size()
    quarter = orders[orders["kind"] != "campaign order"].groupby(orders["order_date"].dt.to_period("Q")).size()
    signup = world.tables["customer_master"]["signup_date"]
    signups = signup[signup >= orders["order_date"].min()].dt.to_period("M").value_counts().sort_index()
    return {"by_kind": by_kind.round(3), "monthly": monthly, "signups_monthly": signups,
            "same_day_repeat_order_share": float((per_customer_day > 1).sum() / len(orders)),
            "last_to_first_full_quarter_ratio": float(quarter.iloc[-2] / quarter.iloc[1]) if len(quarter) >= 4 else None}


def claims_by_month(world) -> pd.DataFrame:
    """Transaction-claim lines per request month, by kind of request: does one kind pile up late in the year?"""
    requests = request_kinds(world)
    claims = requests[requests["group"] == "transaction claim"]
    return pd.crosstab(claims["requested_at"].dt.to_period("M"), claims["kind"])


def linked_claimants(world) -> dict:
    """Customers with a linked claim line, split by private label: how much honest noise does the link signal carry?"""
    claims = diagnostics.linked_claims(world)
    summary = diagnostics.customer_summary(world)[["customer_id", "y_abuse", "eligible", "household_id", "coordination_group_id"]]
    linked = summary[summary["customer_id"].isin(claims.loc[claims["linked"], "customer_id"])]
    return {"linked_claimants": len(linked), "honest": int((linked["y_abuse"] == 0).sum()),
            "honest_household_members": int(((linked["y_abuse"] == 0) & linked["household_id"].notna()).sum()),
            "honest_ring_members": int(((linked["y_abuse"] == 0) & linked["coordination_group_id"].notna()).sum()),
            "abusers": int((linked["y_abuse"] == 1).sum())}


def rule_gate_preview(world) -> pd.DataFrame:
    """The two reference rules against the gate's benign segments: who each rule would wrongly select."""
    summary = diagnostics.customer_summary(world)
    summary["claim_count"] = summary["claim_lines"]
    segments = benign_segments(world).set_index("customer_id")
    rows = []
    for rule, score in (("rank by raw return rate", "raw_return_rate"), ("rank by number of claims", "claim_count")):
        selected = set(diagnostics.top_fraction(world, summary, score)["customer_id"])
        row = {"rule": rule, "selected": len(selected),
               "true_positives": int(summary.loc[summary["customer_id"].isin(selected), "y_abuse"].sum())}
        for name in ("legit_heavy_returner", "defective_product_buyer", "benign_household"):
            members = segments.index[segments[name]]
            row[name + "_selected"] = int(members.isin(selected).sum())
            row[name + "_size"] = len(members)
        rows.append(row)
    return pd.DataFrame(rows)


def opportunity_prevalence(world) -> pd.DataFrame:
    """Accounts with a propensity, by how many relevant orders they had: how often does a propensity turn into an action?"""
    profile = world.truth["customer_profile"]
    propensity = profile[profile["claim_propensity"] | profile["temporary_use_propensity"]][["customer_id"]]
    orders = world.tables["sales_order"].merge(world.truth["order_truth"][["order_id", "layer"]], on="order_id")
    delivered = world.tables["sales_order_line"].query("line_status == 'delivered'")["order_id"].unique()
    relevant = orders[(orders["layer"] == "base") & orders["order_id"].isin(delivered)].groupby("customer_id").size()
    propensity = propensity.assign(relevant_orders=propensity["customer_id"].map(relevant).fillna(0).astype(int))
    actions = _opportunities(world)
    drawn = actions.groupby("customer_id").size()
    done = actions[actions["completed_action"]].groupby("customer_id").size()
    propensity["opportunities"] = propensity["customer_id"].map(drawn).fillna(0).astype(int)
    propensity["acted"] = propensity["customer_id"].isin(done.index)
    propensity["bucket"] = pd.cut(propensity["relevant_orders"], ORDER_BUCKETS, right=False, labels=ORDER_BUCKET_LABELS)
    return propensity.groupby("bucket", observed=True).agg(propensity_accounts=("customer_id", "size"),
                                                           opportunities_drawn=("opportunities", "sum"), acted=("acted", "sum"))
