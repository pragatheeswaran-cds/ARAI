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

    @property
    def snapshot_date(self):
        return self.context.s.snapshot_date


@dataclass
class StoredWorld:
    """A world read back from disk: the same tables and truth, without the generation context."""
    world_id: str
    purpose: str
    tables: dict
    truth: dict
    manifest: dict = field(repr=False)

    @property
    def snapshot_date(self):
        return pd.Timestamp(self.manifest["cutoff"][:10]).date()


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
        if orders is None:                      # nobody ordered (all-dormant boundary fixture)
            self.orders = self.lines = self.units = pd.DataFrame()
            return self.orders, self.lines
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
        for key in self._reserve_honest(self.honest_events):
            self.reserved[position[key]] = True
        return self.honest_events

    def _reserve_honest(self, events: pd.DataFrame) -> list:
        """Record the unit reservations of honest requests (withdrawn and not-yet-visible ones included)."""
        keys = []
        for event_id, order_id, line_no, indices in zip(events["event_id"], events["order_id"], events["order_line_no"],
                                                        events["unit_indices"]):
            for index in indices:
                keys.append((order_id, line_no, index))
                self.reservations.append((self.ctx.world_id, order_id, int(line_no), int(index), "honest_request", event_id))
        return keys

    def build_abuse(self):
        ctx = self.ctx
        self.hot_list = abuse.choose_hot_list(ctx)
        self.campaign_truth = pd.DataFrame(columns=["world_id", "campaign_id", "coordination_group_id", "target_style_id", "campaign_date"])
        self.actions, abusive, self.campaign_units = [], [], pd.DataFrame()
        if ctx.abuse_enabled:
            occupied = {}
            for cust, day in zip(self.orders["cust"].to_numpy(), self.orders["order_date"].to_numpy().astype("datetime64[D]")):
                occupied.setdefault(int(cust), set()).add(day)
            self.campaign_truth, campaign_actions, c_orders, c_lines, campaign_events = abuse.run_campaigns(
                ctx, self.profiles, self.rel, self.units, self.reserved, self.hot_list, occupied)
            solo_actions, solo_events = abuse.run_solo_actions(ctx, self.profiles, self.orders, self.units, self.reserved)
            self.actions = campaign_actions + solo_actions
            abusive = [campaign_events, solo_events]
            if len(c_orders):
                self.orders = _concat([self.orders, c_orders])
                self.lines = _concat([self.lines, c_lines])
                # the claimed unit is the abusive action; every other delivered unit behaves like any honest unit
                c_units = sales.expand_units(c_lines)
                claimed_keys = {(a["order_id"], a["order_line_no"], i) for a in campaign_actions
                                if a["claim_source"] == "campaign_order" for i in a["allocated_unit_indices"]}
                claimed = np.array([key in claimed_keys for key in zip(c_units["order_id"], c_units["order_line_no"],
                                                                       c_units["unit_index"])], dtype=bool)
                self.g_address.update(returns.address_multipliers(
                    ctx, sorted(set(c_units["address_id"]) - set(self.g_address))))
                claimed_units = c_units[claimed]
                facts = [pd.DataFrame({
                    "order_id": claimed_units["order_id"].to_numpy(), "order_line_no": claimed_units["order_line_no"].to_numpy(),
                    "unit_index": claimed_units["unit_index"].to_numpy(), "cust": claimed_units["cust"].to_numpy(),
                    "style_idx": claimed_units["style_idx"].to_numpy(), "delivered_date": claimed_units["delivered_date"].to_numpy(),
                    "layer": "campaign", "received_defective_unit": False, "genuine_fulfilment_cause": None,
                    "carrier_damage": False, "delivery_incident": False, "honest_cause": ""})]
                others = c_units[~claimed].reset_index(drop=True)
                if len(others):
                    other_facts, other_events = returns.build_honest_events(
                        ctx, self.profiles, others, self.defect_prone, self.fit_issue, self.g_address, purpose="honest_campaign")
                    facts.append(other_facts)
                    self._reserve_honest(other_events)
                    self.honest_events = _concat([self.honest_events, other_events])
                self.campaign_units = _concat(facts)
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

    def _finalize_without_orders(self) -> World:
        """A world in which no account has ordered: the reference tables plus empty transaction tables."""
        ctx, schema = self.ctx, _schema(self.ctx.s.spec_root)
        tables = {name: assemble.empty_table(schema[name]["columns"]) for name in assemble.OPERATIONAL_TABLES}
        reference = assemble.build_reference_tables(ctx, self.profiles)
        tables.update({name: reference[name] for name in ("customer_master", "sku_master", "reason_code")})
        defect_prone, fit_issue = returns.product_truth_draws(ctx)
        style_ids = ctx.catalog.styles["style_id"].to_numpy()
        defaults = ctx.s.defaults["defect_unit_probability"]
        truth = {
            "customer_profile": self.profiles.drop(columns=["signup_date", "eligible_start", "eligible_days", "abuse_category",
                                                            "allocation_weight"]).assign(world_id=ctx.world_id),
            "customer_truth": pd.DataFrame({
                "world_id": ctx.world_id, "customer_id": ctx.customer_ids, "y_abuse": 0, "deceptive_nonreceipt_claim": False,
                "deceptive_contents_claim": False, "temporary_use_return": False, "coordinated_action_flag": False,
                "household_id": self.rel.household_id, "coordination_group_id": self.rel.coordination_group_id,
                "shared_location_id": self.rel.shared_location_id}),
            "relationship_truth": self.rel.truth,
            "product_truth": pd.DataFrame({
                "world_id": ctx.world_id, "style_id": style_ids, "defect_state": np.where(defect_prone, "defect_prone", "ordinary"),
                "latent_defect_probability": np.where(defect_prone, defaults["defect_prone_style"], defaults["ordinary_style"]),
                "hot_listed": False, "targeting_level": "none", "targeted": False}),
        }
        world = World(world_id=ctx.world_id, seed=ctx.seed, n_customers=ctx.n, purpose=ctx.s.purpose_of(ctx.seed),
                      abuse_enabled=ctx.abuse_enabled, tables=tables, truth=truth, context=ctx)
        world.summary = {name: len(table) for name, table in tables.items()}
        return world

    def run(self) -> World:
        self.build_profiles()
        self.build_relationships()
        self.build_orders()
        if not len(self.orders):
            return self._finalize_without_orders()
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
    """Hash of the code that determines a world's content: the generator, catalog adapter, settings and streams."""
    h = hashlib.sha256()
    package = paths.REPO_ROOT / "src" / "arai"
    for path in sorted([*(package / "generator").rglob("*.py"), package / "catalog.py", package / "settings.py", package / "rng.py"]):
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


def load_world(world_id: str, artifact_root: Path | None = None, private_root: Path | None = None) -> StoredWorld:
    """Read a written world: operational tables from Parquet and private truth from its separate root."""
    base = Path(artifact_root or paths.ARTIFACT_ROOT) / "worlds" / world_id
    private = Path(private_root or paths.PRIVATE_TRUTH_ROOT) / world_id
    manifest = json.loads((base / "operational" / "manifest.json").read_text(encoding="utf-8"))
    tables = {name: pd.read_parquet(base / "parquet" / f"{name}.parquet") for name in assemble.OPERATIONAL_TABLES}
    truth = {path.stem: pd.read_parquet(path) for path in sorted(private.glob("*.parquet"))}
    return StoredWorld(world_id=manifest["world_id"], purpose=manifest["purpose"], tables=tables, truth=truth, manifest=manifest)
