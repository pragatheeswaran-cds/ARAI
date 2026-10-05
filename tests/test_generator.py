"""Generator invariants from final-spec component 02 (GEN acceptance criteria) on fixture world 2001."""
import json

import numpy as np
import pandas as pd
import pytest
import yaml

from arai.generator import WorldBuilder, generate_world
from arai.generator.world import format_for_csv
from arai.paths import SPEC_ROOT

SCHEMA = yaml.safe_load((SPEC_ROOT / "contracts" / "data-schema.yaml").read_text(encoding="utf-8"))["tables"]
LINE_KEY = ["order_id", "order_line_no"]


def test_same_seed_reproduces_every_table(world):
    again = generate_world(world.seed)
    for name, table in world.tables.items():
        pd.testing.assert_frame_equal(table, again.tables[name])
    for name, table in world.truth.items():
        pd.testing.assert_frame_equal(table, again.truth[name])


def test_different_seeds_differ(world):
    other = generate_world(2002)
    assert other.world_id != world.world_id
    assert len(other.tables["sales_order"]) != len(world.tables["sales_order"])


def test_operational_tables_carry_only_contract_columns(world):
    for name, table in world.tables.items():
        assert list(table.columns) == list(SCHEMA[name]["columns"])
    assert not set(world.tables["sku_master"].columns) & set(SCHEMA["sku_master"]["forbidden_columns"])


def test_catalog_adapter_preserves_the_source(world):
    sku = world.tables["sku_master"]
    source = pd.read_csv(SPEC_ROOT / "assets" / "sku_master_source.csv")
    assert len(sku) == 300 and sku["style_id"].nunique() == 37
    merged = sku.merge(source, left_on="sku", right_on="sku_id")
    assert (merged["unit_price_x"] == merged["unit_price_y"]).all()
    assert (merged["return_window_days_x"] == merged["return_window_days_y"]).all()
    assert (merged["launch_date_x"].dt.strftime("%Y-%m-%d") == merged["launch_date_y"]).all()


def test_all_five_sale_states_occur(world):
    assert set(world.tables["sales_order_line"]["line_status"]) == {"awaiting_dispatch", "cancelled", "shipped", "delivered", "lost_in_transit"}


def test_expected_overlay_rates_are_four_three_and_half_percent(world):
    builder = WorldBuilder(world.seed)
    profiles = builder.build_profiles()
    assert profiles["allocation_weight"].mean() == pytest.approx(1.0)       # so mean probabilities are .035/.025/.005
    assert (profiles.loc[profiles["annual_order_target"] == 0, "allocation_weight"] == 0).all()


def test_invalid_overlay_probability_fails_instead_of_clipping():
    builder = WorldBuilder(2001)
    builder.ctx.s.policy["overlay"]["categorical_coefficients"]["claim_only"] = 0.6
    with pytest.raises(ValueError):
        builder.build_profiles()


def test_abuse_off_preserves_base_and_honest_events(world, world_without_abuse):
    on, off = world, world_without_abuse
    layer = on.truth["order_truth"].set_index("order_id")["layer"]
    base_orders = on.tables["sales_order"][on.tables["sales_order"]["order_id"].map(layer) == "base"].reset_index(drop=True)
    base_lines = on.tables["sales_order_line"][on.tables["sales_order_line"]["order_id"].map(layer) == "base"].reset_index(drop=True)
    pd.testing.assert_frame_equal(base_orders, off.tables["sales_order"])
    pd.testing.assert_frame_equal(base_lines, off.tables["sales_order_line"])
    pd.testing.assert_frame_equal(on.tables["customer_master"], off.tables["customer_master"])

    # honest requests keep their content; header identifiers and line numbers may differ once abusive requests share headers
    actions = on.truth["action_truth"]
    abusive = set(zip(actions["return_order_id"].dropna(), actions["return_line_no"].dropna().astype(int)))
    returns = on.tables["return_order_line"]
    honest = returns[[key not in abusive for key in zip(returns["return_order_id"], returns["return_line_no"])]]
    honest = honest[honest["order_id"].map(layer) == "base"]            # campaign orders' honest requests exist only with abuse
    content = [c for c in returns.columns if c not in ("return_order_id", "return_line_no")]
    key = ["order_id", "order_line_no", "requested_at", "reason_code"]
    pd.testing.assert_frame_equal(honest[content].sort_values(key).reset_index(drop=True),
                                  off.tables["return_order_line"][content].sort_values(key).reset_index(drop=True))
    assert (off.truth["order_truth"]["layer"] == "base").all()
    assert off.truth["customer_truth"]["y_abuse"].sum() == 0 and len(off.truth["action_truth"]) == 0


def test_labels_reconstruct_from_actions_and_return_lines(world):
    actions = world.truth["action_truth"]
    completed = actions[actions["completed_action"]]
    returns = world.tables["return_order_line"].set_index(["return_order_id", "return_line_no"])
    lines = world.tables["sales_order_line"].set_index(LINE_KEY)
    cutoff = pd.Timestamp(world.context.s.cutoff.replace(tzinfo=None))
    for _, action in completed.iterrows():
        row = returns.loc[(action["return_order_id"], action["return_line_no"])]
        assert (row["order_id"], row["order_line_no"]) == (action["order_id"], action["order_line_no"])
        assert row["requested_at"] <= cutoff and row["line_status"] != "withdrawn"
        assert lines.loc[(action["order_id"], action["order_line_no"]), "line_status"] == "delivered"
    truth = world.truth["customer_truth"].set_index("customer_id")["y_abuse"]
    assert set(truth[truth == 1].index) == set(completed["customer_id"])
    uncompleted = actions[~actions["completed_action"]]
    assert uncompleted["uncompleted_reason"].notna().all() and uncompleted["return_order_id"].isna().all()


def test_no_unit_is_reserved_twice(world):
    allocation = world.truth["unit_allocation"]
    assert not allocation.duplicated(["order_id", "order_line_no", "unit_index"]).any()
    quantity = world.tables["sales_order_line"].set_index(LINE_KEY)["quantity"]
    assert (allocation["unit_index"] <= allocation.set_index(LINE_KEY).index.map(quantity)).all()


def test_campaign_orders_are_private_and_only_hit_hot_list_styles(world):
    order_truth = world.truth["order_truth"]
    campaign_orders = set(order_truth.loc[order_truth["layer"] == "campaign", "order_id"])
    assert campaign_orders, "fixture world should contain campaign orders"
    product = world.truth["product_truth"]
    hot = set(product.loc[product["hot_listed"], "style_id"])
    style = world.tables["sku_master"].set_index("sku")["style_id"]
    lines = world.tables["sales_order_line"]
    on_campaign = lines[lines["order_id"].isin(campaign_orders)].assign(hot=lambda f: f["sku"].map(style).isin(hot))
    assert on_campaign.groupby("order_id")["hot"].any().all()  # one line is the target; other lines are ordinary

    actions = world.truth["action_truth"]
    coordinated = actions[actions["completed_action"] & actions["campaign_id"].notna()]
    target = coordinated[~coordinated["parcel_companion"]]     # a whole-parcel claim also covers the ordinary lines
    claimed = target.merge(lines, on=LINE_KEY)["sku"].map(style)
    assert set(claimed) <= hot
    assert set(coordinated["action_type"]) <= {"deceptive_nonreceipt_claim", "deceptive_contents_claim"}
    assert coordinated["claim_source"].isin(["reused_purchase", "campaign_order"]).all()


def test_style_is_targeted_only_with_three_accounts_from_one_group(world):
    for _, style in world.truth["product_truth"].iterrows():
        by_group = json.loads(style["coordinated_claim_accounts_by_group"])
        largest = max(by_group.values(), default=0)
        assert style["targeted"] == (largest >= 3)
        assert style["targeting_level"] == ("targeted" if largest >= 3 else "sub_threshold" if by_group else "none")
        assert style["hot_listed"] or not by_group


def test_csv_and_parquet_hold_the_same_values(world, written):
    for name in world.tables:
        text = pd.read_csv(written["operational"] / f"{name}.csv", dtype=str, keep_default_na=False)
        parquet = format_for_csv(pd.read_parquet(written["parquet"] / f"{name}.parquet"), SCHEMA[name]["columns"])
        assert (text.to_numpy() == parquet.to_numpy()).all(), name


def test_manifest_matches_the_contract(written):
    import jsonschema
    schema = json.loads((SPEC_ROOT / "contracts" / "manifest.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(written["manifest"])
    assert written["manifest"]["purpose"] == "fixture" and written["manifest"]["generator"]["seed"] == 2001
    assert not any(written["operational"].glob("*truth*")) and not any(written["operational"].glob("*.parquet"))


def test_stress_seed_scales_action_rates():
    def mean_rate(seed):
        profiles = WorldBuilder(seed, 2000).build_profiles()
        return profiles.loc[profiles["claim_propensity"], "claim_action_rate"].mean()
    assert 0.1 < mean_rate(2001) < 0.3
    assert WorldBuilder(2505).ctx.s.overrides == {"action_rate_scale": 0.5}
    assert WorldBuilder(2506).ctx.s.overrides == {"action_rate_scale": 2.0}


def test_realised_rates_are_near_their_targets(world):
    units = world.truth["unit_truth"]
    assert 0.008 < units["genuine_fulfilment_cause"].notna().mean() < 0.025     # about 1.5% of delivered units
    assert 0.002 < units["carrier_damage"].mean() < 0.010                       # about 0.5%
    status = world.tables["return_order_line"]["line_status"].value_counts(normalize=True)
    assert status["withdrawn"] < 0.06 and status["rejected"] < 0.08
    multiplier = world.truth["address_truth"]["genuine_failure_multiplier"]
    assert 0.8 < multiplier.mean() < 1.2


def test_every_world_marks_eight_percent_of_styles_defect_prone(world):
    product = world.truth["product_truth"]
    assert (product["defect_state"] == "defect_prone").sum() == 3            # round(0.08 * 37)
    assert product.loc[product["defect_state"] == "defect_prone", "latent_defect_probability"].eq(0.25).all()


def test_two_request_dates_under_one_header_keep_their_own_times(world):
    returns = world.tables["return_order_line"]
    dates = returns.assign(day=returns["requested_at"].dt.normalize()).groupby("return_order_id")["day"].nunique()
    assert (dates > 1).any(), "fixture world should contain a header spanning two request dates"
    header_id = dates[dates > 1].index[0]
    lines = returns[returns["return_order_id"] == header_id]
    assert lines["requested_at"].nunique() > 1 and (lines["available_at"] == lines["requested_at"]).all()
    header = world.tables["return_order"].set_index("return_order_id").loc[header_id]
    assert header["return_created_at"] == lines["requested_at"].max() == header["available_at"]


def test_return_lines_are_aggregated_before_joining_sales():
    from arai import diagnostics
    world = generate_world(2002)
    returns = world.tables["return_order_line"]
    assert returns.duplicated(LINE_KEY).any(), "some sale lines should have more than one return line"
    lines = diagnostics.sale_lines(world)
    assert len(lines) == len(world.tables["sales_order_line"])              # no duplicated exposure
    active = returns[returns["line_status"] != "withdrawn"]
    assert lines["requested_units"].sum() == active["quantity_returned"].sum()
    assert (lines["requested_units"] <= lines["quantity"]).all()


def test_temporary_use_prefers_orders_with_occasion_wear():
    from arai.generator import abuse
    builder = WorldBuilder(2001)
    builder.build_profiles(); builder.build_relationships(); builder.build_orders(); builder.build_honest_returns()
    units = builder.units.assign(reserved=builder.reserved, occasion=builder.ctx.catalog.sku_occasion[builder.units["sku_idx"].to_numpy()])
    free = units[~units["reserved"]]
    with_occasion = set(free.loc[free["occasion"], "order_id"])
    per_customer = free[free["order_id"].isin(with_occasion)].groupby("cust")["order_id"].nunique()
    cust = per_customer.idxmax()
    # a rate of 0.4 gives probability 1.0 on orders with occasion wear (0.4 x 2.5) and 0.22 otherwise (0.4 x 0.55)
    profiles = builder.profiles.assign(claim_propensity=False, temporary_use_propensity=False,
                                       claim_action_rate=0.0, temporary_use_action_rate=0.0)
    profiles.loc[cust, ["temporary_use_propensity", "temporary_use_action_rate"]] = [True, 0.4]
    actions, events = abuse.run_solo_actions(builder.ctx, profiles, builder.orders, builder.units, builder.reserved.copy())
    acted = set(events["order_id"])
    occasion_orders = set(free.loc[(free["cust"] == cust) & free["occasion"], "order_id"])
    assert occasion_orders and occasion_orders <= acted                      # every such order produces an action
    chosen = events[events["order_id"].isin(occasion_orders)]
    assert builder.ctx.catalog.sku_occasion[chosen["sku_idx"].to_numpy(dtype=int)].all()   # on the occasion-wear unit
    other_orders = set(free.loc[free["cust"] == cust, "order_id"]) - occasion_orders
    assert len(acted & other_orders) < len(other_orders) or not other_orders


# ---- artefact checks (specification v1.3): nothing mechanical may separate honest from abusive requests
CLAIMS = ["item_not_received", "wrong_item_sent", "missing_parts", "empty_package"]


def _claims_with_kind(world):
    lines = world.tables["sales_order_line"]
    returns = world.tables["return_order_line"].merge(lines[LINE_KEY + ["delivered_date"]], on=LINE_KEY)
    returns["days"] = (returns["requested_at"].dt.normalize() - returns["delivered_date"]).dt.days
    actions = world.truth["action_truth"]
    done = actions[actions["completed_action"]][["return_order_id", "return_line_no", "campaign_id"]].assign(abusive=True)
    returns = returns.merge(done, on=["return_order_id", "return_line_no"], how="left")
    returns["kind"] = np.where(returns["abusive"].isna(), "honest", np.where(returns["campaign_id"].notna(), "ring", "solo"))
    return returns[returns["reason_code"].isin(CLAIMS)]


def test_every_transaction_claim_follows_one_timing_law(world):
    claims = _claims_with_kind(world)
    assert claims["days"].max() <= 30
    slow = claims[claims["days"] > 10]
    assert (slow["kind"] == "honest").any(), "honest claims must also occur more than ten days after delivery"
    assert claims.groupby("kind")["days"].median().between(3, 8).all()


def test_return_lines_are_numbered_in_time_order(world):
    returns = world.tables["return_order_line"].sort_values(["return_order_id", "return_line_no"])
    earlier = returns["requested_at"] < returns.groupby("return_order_id")["requested_at"].shift()
    assert not earlier.any()


def test_no_account_places_two_orders_on_one_day(world):
    assert not world.tables["sales_order"].duplicated(["customer_id", "order_date"]).any()


def test_campaign_orders_have_ordinary_baskets():
    world = generate_world(2101, 4000)                    # enough campaign orders to compare shapes
    layer = world.truth["order_truth"].set_index("order_id")["layer"]
    lines = world.tables["sales_order_line"]
    per_order = lines.groupby("order_id").agg(lines=("sku", "size"), units=("quantity", "sum"))
    per_order["layer"] = per_order.index.map(layer)
    multi = per_order.groupby("layer")["lines"].apply(lambda s: (s > 1).mean())
    assert (per_order["layer"] == "campaign").sum() > 30
    assert abs(multi["campaign"] - multi["base"]) < 0.15
    assert (per_order.loc[per_order["layer"] == "campaign", "units"] > 1).any()
    # the unclaimed units of campaign orders can be returned honestly
    actions = world.truth["action_truth"]
    abusive = set(zip(actions["return_order_id"].dropna(), actions["return_line_no"].dropna().astype(int)))
    returns = world.tables["return_order_line"]
    on_campaign = returns[returns["order_id"].map(layer) == "campaign"]
    assert any(key not in abusive for key in zip(on_campaign["return_order_id"], on_campaign["return_line_no"]))


def test_campaign_claims_are_not_tied_to_the_first_line():
    world = generate_world(2101, 4000)
    actions = world.truth["action_truth"]
    lines = world.tables["sales_order_line"]
    size = lines.groupby("order_id")["order_line_no"].size()
    claims = actions[actions["completed_action"] & (actions["claim_source"] == "campaign_order") & ~actions["parcel_companion"]]
    multi = claims[claims["order_id"].map(size) >= 2]
    assert len(multi) > 15
    assert 0.2 < (multi["order_line_no"] == 1).mean() < 0.8


def test_deceptive_claims_share_the_honest_code_mix_and_can_cover_a_parcel():
    world = generate_world(2101, 4000)
    actions = world.truth["action_truth"]
    done = actions[actions["completed_action"] & actions["action_type"].str.startswith("deceptive")]
    returns = world.tables["return_order_line"].set_index(["return_order_id", "return_line_no"])
    codes = pd.Series([returns.loc[(r, n), "reason_code"] for r, n in zip(done["return_order_id"], done["return_line_no"])],
                      index=done.index)
    assert ((codes == "item_not_received") == (done["action_type"] == "deceptive_nonreceipt_claim")).all()
    first = ~done["parcel_companion"]
    assert 0.15 < (codes[first] == "item_not_received").mean() < 0.40     # .27 by specification, not one half
    # whole-parcel claims: every action of the claim is non-receipt, and a companion never stands alone
    parcel = actions[actions["whole_parcel"]]
    assert len(parcel) and (parcel["action_type"] == "deceptive_nonreceipt_claim").all()
    companions = actions[actions["parcel_companion"]]
    assert len(companions) and companions["whole_parcel"].all()
    parents = set(actions.loc[actions["whole_parcel"] & ~actions["parcel_companion"], "action_id"])
    assert set(companions["action_id"].str.rsplit("-L", n=1).str[0]) <= parents
    # a whole-parcel claim takes every unit of the line it starts on
    quantity = world.tables["sales_order_line"].set_index(LINE_KEY)["quantity"]
    campaign_parcels = parcel[(parcel["claim_source"] == "campaign_order") & parcel["order_id"].notna()]
    taken = campaign_parcels["allocated_unit_indices"].map(len).to_numpy()
    assert (taken == quantity.loc[list(zip(campaign_parcels["order_id"], campaign_parcels["order_line_no"]))].to_numpy()).all()


def test_signups_are_flat_across_the_history_window(world):
    signup = world.tables["customer_master"]["signup_date"]
    start = pd.Timestamp(world.context.s.history_start)
    inside = signup[signup >= start]
    first_half = (inside < start + pd.Timedelta(days=182)).mean()
    assert 0.40 < first_half < 0.60


def test_household_co_orders_follow_a_member_order_with_the_same_style(world):
    order_truth = world.truth["order_truth"]
    co_orders = set(order_truth.loc[order_truth["household_co_order"], "order_id"])
    assert co_orders and (order_truth.loc[order_truth["household_co_order"], "layer"] == "base").all()
    household = world.truth["customer_truth"].set_index("customer_id")["household_id"]
    orders = world.tables["sales_order"]
    style = world.tables["sku_master"].set_index("sku")["style_id"]
    first = world.tables["sales_order_line"].query("order_line_no == 1").set_index("order_id")["sku"].map(style)
    orders = orders.assign(household=orders["customer_id"].map(household), first_style=orders["order_id"].map(first))
    for _, order in orders[orders["order_id"].isin(co_orders)].iterrows():
        partners = orders[(orders["household"] == order["household"]) & (orders["customer_id"] != order["customer_id"])
                          & (orders["first_style"] == order["first_style"])
                          & (order["order_date"] - orders["order_date"]).dt.days.between(0, 2)]
        assert len(partners), "a co-order follows another household member's order of the same style"


def test_delivery_incidents_lose_whole_parcels(world):
    units = world.truth["unit_truth"]
    lost = units[units["delivery_incident"]]
    assert len(lost) and (lost["genuine_fulfilment_cause"] == "item_not_received").all()
    in_lost_orders = units[units["order_id"].isin(lost["order_id"])]
    base_layer = world.truth["order_truth"].set_index("order_id")["layer"]
    base_only = in_lost_orders[in_lost_orders["order_id"].map(base_layer) == "base"]
    assert base_only["delivery_incident"].all()          # every delivered unit of a failed parcel is lost


def test_dormant_accounts_never_order(world):
    persona = world.truth["customer_profile"].set_index("customer_id")["persona"]
    buyers = set(world.tables["sales_order"]["customer_id"])
    assert not buyers & set(persona[persona == "Dormant"].index)


# ------------------------------------------------------------------ generator-config 3.0: a less generous simulator (AM-49)
def _item_returns_with_truth(world):
    """Visible item-return lines (never claims) with their point in the window and whether an abusive action placed them."""
    t = world.tables
    lines = t["return_order_line"].merge(t["sales_order_line"][["order_id", "order_line_no", "delivered_date", "return_window_days"]],
                                         on=["order_id", "order_line_no"])
    lines = lines.merge(t["return_order"][["return_order_id", "customer_id"]], on="return_order_id")
    actions = world.truth["action_truth"]
    placed = actions[actions["completed_action"]][["return_order_id", "return_line_no", "action_type"]]
    lines = lines.merge(placed, on=["return_order_id", "return_line_no"], how="left")
    lines["ratio"] = (lines["requested_at"].dt.normalize() - lines["delivered_date"]).dt.days / lines["return_window_days"]
    return lines[~lines["reason_code"].isin(["item_not_received", "wrong_item_sent", "missing_parts", "empty_package"])]


def test_honest_customers_return_late_often_enough_that_a_late_return_is_not_a_tell():
    world = generate_world(2001, overrides={"honest_return_timing": "amendment_3_0"})      # as stress world 5508 is generated
    settings = world.context.s.realism["honest_return_timing"]
    profile = world.truth["customer_profile"]
    active = profile["persona"] != "Dormant"
    assert not profile.loc[~active, "late_returner"].any()
    assert abs(profile.loc[active, "late_returner"].mean() - settings["late_returner_share"]) < 0.04
    assert abs(profile.loc[profile["late_returner"], "claim_propensity"].mean() - profile.loc[active, "claim_propensity"].mean()) < 0.04
    item = _item_returns_with_truth(world)
    honest = item[item["action_type"].isna() & (item["ratio"] <= 1)]
    habit = honest["customer_id"].map(profile.set_index("customer_id")["late_returner"])
    last_quarter = honest["ratio"] >= 0.75
    assert 0.03 < last_quarter.mean() < 0.09                          # about one honest return in twenty (one in two hundred before)
    assert last_quarter[habit].mean() > 4 * last_quarter[~habit].mean()      # the habit is what makes them repeat
    late = item[(item["ratio"] >= 0.75) & (item["ratio"] <= 1)]
    assert late["action_type"].isna().mean() > 0.85                   # most late returns are honest now


def test_some_temporary_use_returns_come_back_as_early_as_honest_ones():
    """Enough temporary-use actions to measure: three fixture seeds pooled."""
    ratios = []
    for seed in (2001, 2002, 2003):
        item = _item_returns_with_truth(generate_world(seed, overrides={"temporary_use_timing": "amendment_3_0"}))    # as stress world 5509
        ratios.append(item.loc[item["action_type"] == "temporary_use_return", "ratio"])
    ratios = pd.concat(ratios)
    assert len(ratios) > 30
    assert 0.2 < (ratios < 0.5).mean() < 0.55                         # Beta(5,2) alone would put 11% before half of the window
    assert (ratios >= 0.75).mean() > 0.2                              # and it still returns late more often than an honest customer


def test_action_rates_follow_the_configured_law_and_stress_seeds_keep_their_meaning():
    from arai.settings import STRESS_OVERRIDES, beta_law, load_settings
    settings = load_settings()
    a, b = beta_law(settings.realism["action_rate"]["distribution"])
    assert (a, b) == (1.2, 4.8) and a / (a + b) == pytest.approx(settings.realism["action_rate"]["mean"], abs=0.001)
    assert STRESS_OVERRIDES[5505] == STRESS_OVERRIDES[4505] == STRESS_OVERRIDES[2505] == {"action_rate_scale": 0.5}
    assert set(settings.experiment["stress_seeds"]) == set(range(5501, 5512)) and settings.purpose_of(5505) == "stress"
    profiles = pd.concat([generate_world(seed).truth["customer_profile"] for seed in (2001, 2002, 2003)])
    rates = pd.concat([profiles.loc[profiles["claim_propensity"], "claim_action_rate"],
                       profiles.loc[profiles["temporary_use_propensity"], "temporary_use_action_rate"]])
    assert abs(rates.mean() - 0.2) < 0.03


def test_generator_config_four_generates_as_version_one_three_did_and_three_stress_worlds_blur_timing(world):
    """AM-51: the less generous values of amendment_3_0 are set aside; three stress worlds apply one part of them each."""
    from arai.settings import load_settings
    plain = load_settings().realism
    assert plain["honest_return_timing"]["late_returner_share"] == 0 and plain["honest_return_timing"]["background_probability"] == 0
    assert plain["temporary_use_timing"]["early_probability"] == 0
    assert not world.truth["customer_profile"]["late_returner"].any()                       # nobody has the habit
    item = _item_returns_with_truth(world)
    honest = item[item["action_type"].isna() & (item["ratio"] <= 1)]
    assert (honest["ratio"] >= 0.75).mean() < 0.02                                          # Beta(2,5): about one in two hundred
    late, early, both, full = (load_settings(seed).realism for seed in (5508, 5509, 5510, 5511))
    assert late["honest_return_timing"]["late_returner_share"] == 0.12 and late["temporary_use_timing"]["early_probability"] == 0
    assert early["honest_return_timing"]["late_returner_share"] == 0 and early["temporary_use_timing"]["early_probability"] == 0.3
    assert both["honest_return_timing"]["late_returner_share"] == 0.12 and both["temporary_use_timing"]["early_probability"] == 0.3
    assert {r["action_rate"]["mean"] for r in (plain, late, early, both)} == {0.2}           # only 5511 takes the 3.0 action rate
    assert full["action_rate"]["mean"] == 0.143 and full["honest_return_timing"] == late["honest_return_timing"]
    assert full["temporary_use_timing"] == early["temporary_use_timing"]
    hashes = [load_settings(seed).config_sha256() for seed in (None, 5508, 5509, 5510, 5511)]
    assert len(set(hashes)) == 5                                                             # each world records what generated it


def test_generate_refuses_a_seed_of_an_earlier_experiment(tmp_path, capsys):
    """A retired seed would otherwise be generated as a small fixture world carrying the name of a recorded world."""
    from arai import cli, contract
    assert contract.retired_seed_owner(3101) == "EXP-20261005-02" and contract.retired_seed_owner(4401) == "EXP-20261005-03"
    assert contract.retired_seed_owner(2001) is None and contract.retired_seed_owner(5101) is None
    roots = ["--artifact-root", str(tmp_path / "artifacts"), "--private-root", str(tmp_path / "private")]
    assert cli.main(["generate", "--seed", "3101", *roots]) == 1
    assert "belongs to EXP-20261005-02" in capsys.readouterr().out and not (tmp_path / "artifacts").exists()


def test_generate_refuses_to_overwrite_a_world_of_another_simulator(tmp_path, capsys):
    """Worlds of earlier experiments are records: the command leaves them alone unless told otherwise."""
    import json

    from arai import cli
    roots = ["--artifact-root", str(tmp_path / "artifacts"), "--private-root", str(tmp_path / "private")]
    assert cli.main(["generate", "--seed", "2003", "--customers", "150", *roots]) == 0
    manifest = tmp_path / "artifacts" / "worlds" / "W2003N150" / "operational" / "manifest.json"
    assert cli.main(["generate", "--seed", "2003", "--customers", "150", *roots]) == 0        # the same simulator: reproducible, allowed
    earlier = json.loads(manifest.read_text())
    earlier["generator"]["config_sha256"] = "0" * 64                                         # as an earlier contract left it
    manifest.write_text(json.dumps(earlier))
    kept = manifest.read_bytes()
    assert cli.main(["generate", "--seed", "2003", "--customers", "150", *roots]) == 1
    assert "left untouched" in capsys.readouterr().out and manifest.read_bytes() == kept
    assert cli.main(["generate", "--seed", "2003", "--customers", "150", "--overwrite", *roots]) == 0
    assert json.loads(manifest.read_text())["generator"]["config_sha256"] != "0" * 64
