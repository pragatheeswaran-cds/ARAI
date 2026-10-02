"""Deterministic boundary fixtures (final-spec component 02) and the ring-formation rule."""
import numpy as np
import pandas as pd

from arai import diagnostics
from arai.generator import WorldBuilder, abuse, generate_world, load_world, write_world
from arai.validation import validate_world

LINE_KEY = ["order_id", "order_line_no"]


def test_all_dormant_world_has_accounts_and_no_transactions(tmp_path):
    world = generate_world(2001, 200, overrides={"all_dormant": True})
    assert world.summary["customer_master"] == 200
    assert all(world.summary[name] == 0 for name in ("sales_order", "sales_order_line", "return_order", "return_order_line"))
    assert world.truth["customer_truth"]["y_abuse"].sum() == 0
    assert not world.truth["customer_profile"][["claim_propensity", "temporary_use_propensity"]].to_numpy().any()
    out = write_world(world, tmp_path / "artifacts", tmp_path / "private")
    assert validate_world(out["operational"]).accepted


def test_quantity_three_line_with_one_honest_and_one_abusive_request_yields_two_units():
    builder = WorldBuilder(2001)
    builder.build_profiles()
    builder.build_relationships()
    builder.build_orders()
    honest = builder.build_honest_returns()
    units = builder.units.assign(reserved=builder.reserved)

    per_line = units.groupby(LINE_KEY).agg(quantity=("quantity", "first"), reserved=("reserved", "sum"),
                                           cust=("cust", "first"), delivered=("delivered_date", "first"))
    delivered_lines = units.groupby("order_id")["order_line_no"].nunique()
    settled = honest[honest["visible"].astype(bool) & (honest["line_status"] != "withdrawn")].set_index(LINE_KEY)
    early = per_line["delivered"] <= pd.Timestamp(builder.ctx.s.snapshot_date) - pd.Timedelta(days=90)
    candidates = per_line[(per_line["quantity"] == 3) & (per_line["reserved"] == 1) & early
                          & per_line.index.get_level_values("order_id").map(delivered_lines).isin([1])
                          & per_line.index.isin(settled.index)]
    assert len(candidates), "fixture world should contain a quantity-three line with exactly one honest request"
    (order_id, line_no), line = candidates.index[0], candidates.iloc[0]
    honest_request = settled.loc[[(order_id, line_no)]].iloc[0]
    honest_unit = honest_request["unit_indices"][0]

    # make this one customer a certain claimant and nobody else an abuser
    profiles = builder.profiles.assign(claim_propensity=False, temporary_use_propensity=False,
                                       claim_action_rate=0.0, temporary_use_action_rate=0.0)
    profiles.loc[line["cust"], ["claim_propensity", "claim_action_rate"]] = [True, 1.0]
    actions, events = abuse.run_solo_actions(builder.ctx, profiles, builder.orders, builder.units, builder.reserved)

    event = events[events["order_id"] == order_id].iloc[0]
    assert event["order_line_no"] == line_no and event["unit_indices"][0] != honest_unit
    assert bool(event["visible"])
    reserved_after = builder.units.assign(reserved=builder.reserved).groupby(LINE_KEY)["reserved"].sum().loc[(order_id, line_no)]
    assert reserved_after == 2                                    # one honest unit and one abusive unit, never the same unit
    assert honest_request["quantity"] + event["quantity"] == 2


def test_campaigns_start_only_after_the_ring_has_formed(world):
    campaigns = world.truth["campaign"]
    profiles = world.truth["customer_profile"].set_index("customer_id")
    truth = world.truth["customer_truth"]
    signup = world.tables["customer_master"].set_index("customer_id")["signup_date"]
    for group_id, dates in campaigns.groupby("coordination_group_id")["campaign_date"]:
        members = truth.loc[truth["coordination_group_id"] == group_id, "customer_id"]
        capable = members[profiles.loc[members, "claim_propensity"].to_numpy()]
        assert len(capable), "a ring without claim-capable members plans no campaign"
        joined = signup[capable].sort_values()
        assert dates.min() >= joined.iloc[min(1, len(joined) - 1)]      # the ring starts with its second capable member
    actions = world.truth["action_truth"]
    coordinated = actions[actions["campaign_id"].notna()].merge(campaigns[["campaign_id", "campaign_date"]], on="campaign_id")
    assert (coordinated["campaign_date"] >= coordinated["customer_id"].map(signup)).all()   # nobody acts before signing up
    assert "pre_signup" not in set(actions["uncompleted_reason"].dropna())


def test_stored_world_reads_back_identically(world, written):
    stored = load_world(world.world_id, written["operational"].parents[2], written["private"].parent)
    assert stored.world_id == world.world_id and stored.purpose == "fixture"
    assert {name: len(table) for name, table in stored.tables.items()} == world.summary
    assert diagnostics.generation_report(stored) == diagnostics.generation_report(world)
    np.testing.assert_array_equal(stored.truth["customer_truth"]["y_abuse"].to_numpy(),
                                  world.truth["customer_truth"]["y_abuse"].to_numpy())
