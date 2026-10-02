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
    assert (profiles.loc[profiles["target_order_count"] == 0, "allocation_weight"] == 0).all()


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

    actions = on.truth["action_truth"]
    abusive = set(zip(actions["return_order_id"].dropna(), actions["return_line_no"].dropna().astype(int)))
    returns = on.tables["return_order_line"]
    honest = returns[[key not in abusive for key in zip(returns["return_order_id"], returns["return_line_no"])]].reset_index(drop=True)
    pd.testing.assert_frame_equal(honest, off.tables["return_order_line"])
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
    assert set(lines.loc[lines["order_id"].isin(campaign_orders), "sku"].map(style)) <= hot

    actions = world.truth["action_truth"]
    coordinated = actions[actions["completed_action"] & actions["campaign_id"].notna()]
    claimed = coordinated.merge(lines, on=LINE_KEY)["sku"].map(style)
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
