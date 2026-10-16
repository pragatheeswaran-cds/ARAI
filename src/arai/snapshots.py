"""An earlier snapshot of a generated world: the same customers as the business would have exported them on an earlier date.

A world is one population of customers; each upload of it is a snapshot at a cutoff, and a customer keeps the same
identifier in every snapshot (decision AM-68). The generator writes one snapshot per world, at the experiment's cutoff.
This module replays the generator's own stages for the world's seed, which yields every planned timeline (dispatch and
transit days, cancellations and losses, each request's latency, withdrawal, decision, receipt and refund draws), and
settles those same timelines at an earlier date with the generator's own rules (`sales.apply_fulfilment`,
`returns.settle`, `assemble.build_return_tables`). Nothing is drawn afresh, so the earlier snapshot is a prefix of the
later one: every order, line, request and identifier it holds is in the later snapshot, and only states that move with
time (a line shipped or delivered, a request refunded, received, rejected or withdrawn) can differ.

The generator package itself is not changed, so worlds generated from seeds stay byte-identical to their records.

    uv run arai snapshot W5401 --as-of 2026-08-09
"""
from __future__ import annotations

import dataclasses
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from arai.generator import assemble, returns, sales
from arai.generator.context import Context
from arai.generator.world import World, WorldBuilder, _concat, write_world

AFTER_CUTOFF = "after_snapshot_cutoff"


def snapshot_name(world_id: str, as_of: date) -> str:
    """Folder name of an earlier snapshot beside the world's own: `W5401.as-of-2026-08-09`."""
    return f"{world_id}.as-of-{as_of.isoformat()}"


def _seed_of(world_id: str) -> int:
    if not (world_id.startswith("W") and world_id[1:].isdigit()):
        raise ValueError(f"{world_id}: an earlier snapshot is replayed from a default generated world (W<seed>)")
    return int(world_id[1:])


def _settled_at(builder: WorldBuilder, as_of: date) -> Context:
    """The builder's context with an earlier snapshot date; customer identifiers and every draw stay as they were."""
    s = builder.ctx.s
    if as_of >= s.snapshot_date:
        raise ValueError(f"as of {as_of} is not before the world's cutoff date {s.snapshot_date}")
    if as_of <= s.history_start:
        raise ValueError(f"as of {as_of} leaves no history after {s.history_start}")
    earlier = dataclasses.replace(s, experiment={**s.experiment, "snapshot_date": as_of.isoformat()})
    ctx = builder.ctx
    return Context(s=earlier, seed=ctx.seed, n=ctx.n, world_id=ctx.world_id, catalog=ctx.catalog, abuse_enabled=ctx.abuse_enabled)


def settle(builder: WorldBuilder, ctx: Context) -> World:
    """The world of a fully built `builder` (stages up to abuse) as observed at `ctx`'s snapshot."""
    snapshot = ctx.snapshot
    orders = builder.orders[builder.orders["order_date"].to_numpy().astype("datetime64[D]") <= snapshot].reset_index(drop=True)
    lines = builder.lines[builder.lines["order_id"].isin(set(orders["order_id"]))].reset_index(drop=True)
    lines = sales.apply_fulfilment(ctx, lines)
    events = _concat([builder.honest_events, builder.abusive_events])
    events = returns.settle(ctx, events)
    visible = events[events["visible"].astype(bool)].reset_index(drop=True)
    headers, return_lines, placed = assemble.build_return_tables(ctx, visible)
    tables = assemble.build_operational(ctx, builder.profiles, orders, lines, headers, return_lines)

    # an account that signed up after the cutoff is not yet in the export
    signed_up = tables["customer_master"]["signup_date"].to_numpy().astype("datetime64[D]") <= snapshot
    tables["customer_master"] = tables["customer_master"][signed_up].reset_index(drop=True)
    present = set(tables["customer_master"]["customer_id"])

    # an action is completed in this snapshot only when its request is visible at this cutoff
    seen = set(placed["event_id"]) if len(placed) else set()
    actions = []
    for action in builder.actions:
        action = dict(action)
        if action["order_id"] is not None:
            action["completed_action"] = action["action_id"] in seen
            if not action["completed_action"] and action["uncompleted_reason"] is None:
                action["uncompleted_reason"] = AFTER_CUTOFF
        actions.append(action)
    campaign_truth = builder.campaign_truth
    if len(campaign_truth):
        campaign_truth = campaign_truth[pd.to_datetime(campaign_truth["campaign_date"]).to_numpy().astype("datetime64[D]") <= snapshot]
    truth = assemble.build_truth(ctx, builder.profiles, builder.rel, orders, lines, builder.unit_facts, builder.campaign_units,
                                 placed, actions, campaign_truth, builder.defect_prone, builder.fit_issue, builder.g_address,
                                 builder.hot_list, builder.reservations)
    truth = _within(truth, present, set(orders["order_id"]), snapshot)
    world = World(world_id=ctx.world_id, seed=ctx.seed, n_customers=ctx.n, purpose=ctx.s.purpose_of(ctx.seed),
                  abuse_enabled=ctx.abuse_enabled, tables=tables, truth=truth, context=ctx)
    world.summary = {name: len(table) for name, table in tables.items()}
    return world


def _within(truth: dict, customers: set, orders: set, snapshot) -> dict:
    """Private truth restricted to what exists at the cutoff: its customers, its orders, its delivered units."""
    out = {}
    for name, table in truth.items():
        keep = np.ones(len(table), dtype=bool)
        if "customer_id" in table:
            keep &= table["customer_id"].isin(customers).to_numpy()
        if "order_id" in table and name != "action_truth":           # an uncompleted action may name a later order
            keep &= table["order_id"].isin(orders).to_numpy()
        out[name] = table[keep].reset_index(drop=True)
    return out


def build_earlier(world_id: str, as_of: date) -> World:
    """Replay the world's generation and settle it at `as_of`."""
    builder = WorldBuilder(_seed_of(world_id))
    if builder.ctx.world_id != world_id:
        raise ValueError(f"seed {_seed_of(world_id)} generates {builder.ctx.world_id}, not {world_id}")
    builder.build_profiles()
    builder.build_relationships()
    builder.build_orders()
    builder.build_honest_returns()
    builder.build_abuse()
    return settle(builder, _settled_at(builder, as_of))


def prefix_differences(earlier: dict, later: dict) -> dict:
    """What would break the prefix property, table by table: rows of the earlier snapshot missing from the later one,
    and fields that differ although they do not move with time. Empty lists everywhere mean the earlier snapshot is a
    true prefix of the later one."""
    moving = {"sales_order_line": {"line_status", "shipped_date", "delivered_date"},
              "return_order_line": {"line_status", "refund_amount", "return_received_flag"},
              "return_order": {"refund_total", "return_created_at", "available_at"}}
    found = {}
    for name, keys in assemble.PRIMARY_KEYS.items():
        a, b = earlier[name], later[name]
        merged = a.merge(b, on=keys, how="left", suffixes=("", "_later"), indicator=True)
        problems = [f"{int((merged['_merge'] == 'left_only').sum())} rows missing later"] if (merged["_merge"] == "left_only").any() else []
        for column in a.columns:
            if column in keys or column in moving.get(name, set()):
                continue
            left, right = merged[column], merged[column + "_later"]
            differs = ~((left == right) | (left.isna() & right.isna())) & (merged["_merge"] == "both")
            if differs.any():
                problems.append(f"{column}: {int(differs.sum())} rows differ")
        found[name] = problems
    return found


def write_earlier(world: World, as_of: date, artifact_root: Path | None = None, private_root: Path | None = None) -> dict:
    """Write the earlier snapshot beside its world: `worlds/<world>.as-of-<date>/operational` with its manifest, and its
    private truth under the same name in the private root."""
    name = snapshot_name(world.world_id, as_of)
    renamed = dataclasses.replace(world, world_id=name)          # write_world names folders after the world id
    written = write_world(renamed, artifact_root, private_root)
    manifest_path = written["operational"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["world_id"] = world.world_id                        # the snapshot belongs to the world, not to the folder
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    private_manifest_path = written["private"] / "private-manifest.json"
    private_manifest = json.loads(private_manifest_path.read_text(encoding="utf-8"))
    private_manifest.update(world_id=world.world_id, snapshot_of=world.world_id, as_of=as_of.isoformat(),
                            operational_manifest_sha256=_sha(manifest_path))
    for table in written["private"].glob("*.parquet"):           # truth rows name the world, not the folder
        frame = pd.read_parquet(table)
        if "world_id" in frame and (frame["world_id"] == name).any():
            frame.assign(world_id=world.world_id).to_parquet(table, index=False)
            private_manifest["files"][table.stem]["sha256"] = _sha(table)
    private_manifest_path.write_text(json.dumps(private_manifest, indent=2) + "\n", encoding="utf-8")
    return {**written, "manifest": manifest, "name": name}


def _sha(path: Path) -> str:
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

