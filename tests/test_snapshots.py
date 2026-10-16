"""Earlier snapshots of a generated world (decision AM-68): the same customers as exported on an earlier date, replayed
from the generator's own timelines, never drawn afresh."""
from datetime import timedelta

import pytest

from arai import snapshots
from arai.generator.assemble import OPERATIONAL_TABLES
from arai.generator.world import _schema, format_for_csv
from arai.paths import SPEC_ROOT
from arai.validation import validate_world


def _csv(table, columns) -> str:
    return format_for_csv(table, columns).to_csv(index=False, lineterminator="\n")


def test_settled_at_its_own_cutoff_the_replay_is_the_world_itself(world, written):
    """The replay settles the generator's timelines with the generator's rules: at the world's cutoff it writes the same files."""
    builder = snapshots.replay(world.world_id)
    same = snapshots.settle(builder, builder.ctx)
    schema = _schema(SPEC_ROOT)
    for name in OPERATIONAL_TABLES:
        assert _csv(same.tables[name], schema[name]["columns"]) == (written["operational"] / f"{name}.csv").read_text(encoding="utf-8"), name
    assert same.truth["customer_truth"]["y_abuse"].tolist() == world.truth["customer_truth"]["y_abuse"].tolist()


def test_an_earlier_snapshot_is_a_valid_upload_and_a_prefix_of_the_later_one(world, earlier):
    assert validate_world(earlier["operational"]).accepted
    assert snapshots.prefix_differences(earlier["world"].tables, world.tables) == {name: [] for name in OPERATIONAL_TABLES}
    manifest = earlier["manifest"]
    assert manifest["world_id"] == world.world_id and manifest["cutoff"].startswith(earlier["as_of"].isoformat())
    assert earlier["operational"].parent.name == snapshots.snapshot_name(world.world_id, earlier["as_of"])
    before, after = earlier["world"].tables, world.tables
    assert set(before["customer_master"]["customer_id"]) <= set(after["customer_master"]["customer_id"])   # the same identifiers
    assert len(before["sales_order"]) < len(after["sales_order"]) and len(before["return_order_line"]) < len(after["return_order_line"])
    # time moves states one way only: nothing delivered or refunded earlier is undelivered or unrefunded later
    lines = before["sales_order_line"].merge(after["sales_order_line"], on=["order_id", "order_line_no"], suffixes=("", "_later"))
    assert not ((lines["line_status"] == "delivered") & (lines["line_status_later"] != "delivered")).any()
    requests = before["return_order_line"].merge(after["return_order_line"], on=["return_order_id", "return_line_no"], suffixes=("", "_later"))
    assert not ((requests["line_status"] == "refunded") & (requests["line_status_later"] != "refunded")).any()
    # an abusive action completed by the earlier cutoff is completed later too; truth never reaches an operational file
    truth = earlier["world"].truth["customer_truth"].merge(world.truth["customer_truth"], on="customer_id", suffixes=("", "_later"))
    assert (truth["y_abuse"] <= truth["y_abuse_later"]).all()
    assert not any(path.name.startswith(("customer_truth", "action_truth")) for path in earlier["operational"].iterdir())


def test_an_earlier_snapshot_must_be_earlier_and_of_a_default_generated_world(world):
    with pytest.raises(ValueError, match="not before"):
        snapshots.build_earlier(world.world_id, world.snapshot_date)
    with pytest.raises(ValueError, match="default generated world"):
        snapshots.build_earlier("ACME", world.snapshot_date - timedelta(days=30))
