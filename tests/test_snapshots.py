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


def test_a_return_order_takes_its_channel_when_a_later_request_needs_the_item_back(world, earlier):
    """A header whose requests so far need no item back reads not_applicable; it takes a channel when a later request that
    does joins it. That one change is how time moves a channel; any other change of channel breaks the prefix."""
    before = {name: table.copy() for name, table in earlier["world"].tables.items()}
    orders = before["return_order"]
    shipped = orders.index[orders["return_channel"] != "not_applicable"][0]
    channel = orders.at[shipped, "return_channel"]
    orders.at[shipped, "return_channel"] = "not_applicable"
    assert snapshots.prefix_differences(before, world.tables)["return_order"] == []
    other = next(c for c in orders["return_channel"].unique() if c not in ("not_applicable", channel))
    orders.at[shipped, "return_channel"] = other
    assert snapshots.prefix_differences(before, world.tables)["return_order"] == ["return_channel: 1 rows differ"]


def test_a_snapshot_that_is_not_a_prefix_is_not_left_on_disk(world, written, monkeypatch, capsys):
    """`arai snapshot` stops at a snapshot that fails its check and removes it, so a later --load cannot register it."""
    from arai import cli
    artifacts, private = written["operational"].parents[2], written["private"].parent
    as_of = world.snapshot_date - timedelta(days=20)
    monkeypatch.setattr(snapshots, "prefix_differences", lambda earlier, later: {"return_order": ["return_channel: 1 rows differ"]})
    code = cli.main(["snapshot", world.world_id, "--as-of", as_of.isoformat(), "--artifact-root", str(artifacts), "--private-root", str(private)])
    name = snapshots.snapshot_name(world.world_id, as_of)
    assert code == 1 and "NOT a prefix" in capsys.readouterr().out
    assert not (artifacts / "worlds" / name).exists() and not (private / name).exists()
    assert (artifacts / "worlds" / world.world_id / "operational" / "manifest.json").is_file()      # the world itself stays


def test_writing_the_same_snapshot_again_keeps_its_manifest(world, tmp_path):
    """A rerun of `arai snapshot` after the code or lock changed writes the same data; the manifest (whose hash is the
    registered snapshot's identity) stays as it was, so an instance that registered it accepts it again."""
    import json
    as_of = world.snapshot_date - timedelta(days=25)
    built = snapshots.build_earlier(world.world_id, as_of)
    first = snapshots.write_earlier(built, as_of, tmp_path / "artifacts", tmp_path / "private")
    path = first["operational"] / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["generator"]["code_sha256"] = "0" * 64        # as if an earlier commit had written it
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    kept = path.read_bytes()
    again = snapshots.write_earlier(built, as_of, tmp_path / "artifacts", tmp_path / "private")
    assert again["unchanged"] and path.read_bytes() == kept and again["manifest"]["generator"]["code_sha256"] == "0" * 64
    assert validate_world(again["operational"]).accepted
