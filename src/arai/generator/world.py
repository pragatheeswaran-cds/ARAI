"""Generate one synthetic world stage by stage and write it to disk.

Stage order (final-spec component 02): profiles -> propensities and relationships -> base purchases and
delivery -> honest returns -> abuse-layer campaign orders and abusive actions -> snapshot -> private truth.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from arai import paths
from arai.catalog import load_catalog
from arai.generator import abuse, assemble, profiles as profile_stage, relationships, returns, sales
from arai.generator.context import Context
from arai.settings import load_settings

GENERATOR_NAME = "arai.generator"


@dataclass
class World:
    world_id: str
    seed: int
    n_customers: int
    purpose: str
    abuse_enabled: bool
    tables: dict            # the seven operational tables
    truth: dict             # private truth tables
    context: Context = field(repr=False)
    summary: dict = field(default_factory=dict)


def _concat(frames: list) -> pd.DataFrame:
    frames = [f for f in frames if f is not None and len(f)]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


class WorldBuilder:
    """Runs the generation stages in order. Each stage can be inspected before the next one runs."""

    def __init__(self, seed: int, n_customers: int | None = None, abuse_enabled: bool = True,
                 overrides: dict | None = None, spec_root: Path | None = None):
        s = load_settings(seed, spec_root, overrides)
        n = n_customers or s.default_customers(seed)
        world_id = f"W{seed}"
        if n != s.default_customers(seed):
            world_id += f"N{n}"
        if overrides:
            world_id += "X" + hashlib.sha256(repr(sorted(overrides.items())).encode()).hexdigest()[:6].upper()
        self.ctx = Context(s=s, seed=seed, n=n, world_id=world_id, catalog=load_catalog(s.spec_root), abuse_enabled=abuse_enabled)
        self.reservations = []

    # ------------------------------------------------------------------ stages
    def build_profiles(self) -> pd.DataFrame:
        self.profiles = profile_stage.allocate_abuse(self.ctx, profile_stage.build_profiles(self.ctx))
        return self.profiles

    def build_relationships(self) -> relationships.Relationships:
        self.rel = relationships.build_relationships(self.ctx, self.profiles)
        return self.rel

    def build_orders(self):
        orders, lines = sales.build_base_orders(self.ctx, self.profiles, self.rel)
        self.orders = orders
        self.lines = sales.apply_fulfilment(self.ctx, lines)
        self.units = sales.expand_units(self.lines)
        return self.orders, self.lines

    def build_honest_returns(self) -> pd.DataFrame:
        ctx = self.ctx
        self.defect_prone, self.fit_issue = returns.product_truth_draws(ctx)
        self.g_address = returns.address_multipliers(ctx, sorted(set(self.orders["address_id"])))
        self.unit_facts, self.honest_events = returns.build_honest_events(
            ctx, self.profiles, self.units, self.defect_prone, self.fit_issue, self.g_address)
        position = {key: i for i, key in enumerate(zip(self.units["order_id"], self.units["order_line_no"], self.units["unit_index"]))}
        self.reserved = np.zeros(len(self.units), dtype=bool)
        for event_id, order_id, line_no, indices in zip(self.honest_events["event_id"], self.honest_events["order_id"],
                                                        self.honest_events["order_line_no"], self.honest_events["unit_indices"]):
            for index in indices:
                self.reserved[position[(order_id, line_no, index)]] = True
                self.reservations.append((ctx.world_id, order_id, int(line_no), int(index), "honest_request", event_id))
        return self.honest_events

    def build_abuse(self):
        ctx = self.ctx
        self.hot_list = abuse.choose_hot_list(ctx)
        self.campaign_truth = pd.DataFrame(columns=["world_id", "campaign_id", "coordination_group_id", "target_style_id", "campaign_date"])
        self.actions, abusive, self.campaign_units = [], [], pd.DataFrame()
        if ctx.abuse_enabled:
            self.campaign_truth, campaign_actions, c_orders, c_lines, campaign_events = abuse.run_campaigns(
                ctx, self.profiles, self.rel, self.units, self.reserved, self.hot_list)
            solo_actions, solo_events = abuse.run_solo_actions(ctx, self.profiles, self.orders, self.units, self.reserved)
            self.actions = campaign_actions + solo_actions
            abusive = [campaign_events, solo_events]
            if len(c_orders):
                self.orders = _concat([self.orders, c_orders])
                self.lines = _concat([self.lines, c_lines])
                delivered = c_lines[c_lines["line_status"] == "delivered"]
                self.campaign_units = pd.DataFrame({
                    "order_id": delivered["order_id"].to_numpy(), "order_line_no": 1, "unit_index": 1,
                    "cust": delivered["cust"].to_numpy(), "style_idx": delivered["style_idx"].to_numpy(),
                    "delivered_date": delivered["delivered_date"].to_numpy(), "layer": "campaign",
                    "received_defective_unit": False, "genuine_fulfilment_cause": None, "carrier_damage": False,
                    "honest_cause": ""})
            for action in self.actions:
                for index in action["allocated_unit_indices"]:
                    self.reservations.append((ctx.world_id, action["order_id"], action["order_line_no"], index,
                                              "abusive_action", action["action_id"]))
        self.abusive_events = _concat(abusive)
        return pd.DataFrame(self.actions)

    def finalize(self) -> World:
        ctx = self.ctx
        events = _concat([self.honest_events, self.abusive_events])
        visible = events[events["visible"].astype(bool)] if len(events) else events
        headers, return_lines, placed = assemble.build_return_tables(ctx, visible)
        tables = assemble.build_operational(ctx, self.profiles, self.orders, self.lines, headers, return_lines)
        truth = assemble.build_truth(ctx, self.profiles, self.rel, self.orders, self.lines, self.unit_facts,
                                     self.campaign_units, placed, self.actions, self.campaign_truth, self.defect_prone,
                                     self.fit_issue, self.g_address, self.hot_list, self.reservations)
        world = World(world_id=ctx.world_id, seed=ctx.seed, n_customers=ctx.n, purpose=ctx.s.purpose_of(ctx.seed),
                      abuse_enabled=ctx.abuse_enabled, tables=tables, truth=truth, context=ctx)
        world.summary = {name: len(table) for name, table in tables.items()}
        return world

    def run(self) -> World:
        self.build_profiles()
        self.build_relationships()
        self.build_orders()
        self.build_honest_returns()
        self.build_abuse()
        return self.finalize()


def generate_world(seed: int, n_customers: int | None = None, abuse_enabled: bool = True,
                   overrides: dict | None = None, spec_root: Path | None = None) -> World:
    return WorldBuilder(seed, n_customers, abuse_enabled, overrides, spec_root).run()


# ---------------------------------------------------------------------- writing
def _schema(spec_root: Path) -> dict:
    return yaml.safe_load((Path(spec_root) / "contracts" / "data-schema.yaml").read_text(encoding="utf-8"))["tables"]


def format_for_csv(table: pd.DataFrame, columns: dict) -> pd.DataFrame:
    """Canonical text form: ISO dates, timestamps with the +05:30 offset, two-decimal money, empty cell for null."""
    if list(table.columns) != list(columns):
        raise ValueError(f"table columns {list(table.columns)} do not match the contract {list(columns)}")
    out = {}
    for name, spec in columns.items():
        values = table[name]
        if spec["type"] == "date":
            out[name] = pd.to_datetime(values).dt.strftime("%Y-%m-%d").fillna("")
        elif spec["type"] == "timestamp":
            out[name] = (pd.to_datetime(values).dt.strftime("%Y-%m-%dT%H:%M:%S") + "+05:30").fillna("")
        elif spec["type"] == "number":
            out[name] = values.map(lambda v: "" if pd.isna(v) else f"{v:.2f}")
        elif spec["type"] == "integer":
            out[name] = values.map(lambda v: "" if pd.isna(v) else str(int(v)))
        else:
            out[name] = values.map(lambda v: "" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v))
    return pd.DataFrame(out).astype(object)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _code_sha256() -> str:
    h = hashlib.sha256()
    for path in sorted((paths.REPO_ROOT / "src" / "arai").rglob("*.py")):
        h.update(path.relative_to(paths.REPO_ROOT).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()


def write_world(world: World, artifact_root: Path | None = None, private_root: Path | None = None) -> dict:
    """Write operational CSVs with their manifest, Parquet copies, and private truth under a separate root."""
    ctx = world.context
    name = world.world_id + ("" if world.abuse_enabled else ".abuse-off")
    base = Path(artifact_root or paths.ARTIFACT_ROOT) / "worlds" / name
    operational, parquet = base / "operational", base / "parquet"
    private = Path(private_root or paths.PRIVATE_TRUTH_ROOT) / name
    for directory in (operational, parquet, private):
        directory.mkdir(parents=True, exist_ok=True)

    schema = _schema(ctx.s.spec_root)
    files = {}
    for table_name in assemble.OPERATIONAL_TABLES:
        table = world.tables[table_name]
        path = operational / f"{table_name}.csv"
        format_for_csv(table, schema[table_name]["columns"]).to_csv(path, index=False, lineterminator="\n", encoding="utf-8")
        table.to_parquet(parquet / f"{table_name}.parquet", index=False)
        files[table_name] = {"filename": path.name, "sha256": _sha256(path), "row_count": int(len(table))}

    lock = paths.REPO_ROOT / "uv.lock"
    manifest = {
        "schema_version": "1.0", "world_id": world.world_id, "cutoff": ctx.s.cutoff.isoformat(),
        "history_start": ctx.s.history_start.isoformat(), "timezone": "Asia/Kolkata", "currency": "INR",
        "purpose": world.purpose, "files": files,
        "generator": {"name": GENERATOR_NAME, "version": version("arai"), "seed": int(world.seed),
                      "config_sha256": ctx.s.config_sha256(), "catalog_sha256": ctx.catalog.source_sha256,
                      "dependency_lock_sha256": _sha256(lock) if lock.exists() else "0" * 64,
                      "code_sha256": _code_sha256()},
    }
    (operational / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    truth_files = {}
    for truth_name, table in world.truth.items():
        path = private / f"{truth_name}.parquet"
        table.to_parquet(path, index=False)
        truth_files[truth_name] = {"filename": path.name, "sha256": _sha256(path), "row_count": int(len(table))}
    private_manifest = {"world_id": world.world_id, "seed": int(world.seed), "abuse_enabled": world.abuse_enabled,
                        "n_customers": world.n_customers, "overrides": ctx.s.overrides,
                        "implementation_defaults": {k: list(v) if isinstance(v, tuple) else v for k, v in ctx.s.impl.items()},
                        "catalog_transforms": ctx.catalog.transforms, "operational_manifest_sha256": _sha256(operational / "manifest.json"),
                        "files": truth_files}
    (private / "private-manifest.json").write_text(json.dumps(private_manifest, indent=2) + "\n", encoding="utf-8")
    return {"operational": operational, "parquet": parquet, "private": private, "manifest": manifest}
