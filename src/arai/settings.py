"""Generation settings read from the specification package.

Numbers come from final-spec contracts and assets, so the specification stays the single source of truth.
Rules the specification states only in prose (for example the basket-size formula) live in the generator
code next to a comment naming the contract key. `IMPLEMENTATION_DEFAULTS` holds the choices the specification
leaves open; they are listed in records/2026-10-02-generator-implementation.md.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from arai.paths import SPEC_ROOT

IST = timezone(timedelta(hours=5, minutes=30))

# Choices the specification leaves open. Change only with a dated record, on development worlds.
IMPLEMENTATION_DEFAULTS = {
    "max_order_intensity_per_day": 1.0,     # caps target orders at one per eligible day
    "loyalist_lognormal": (-1.6, 0.7),      # position within the Loyalist order range: exp(N(mu, sigma)), clipped to 1
    "power_user_persona": "Loyalist",       # the team's config calls power users the "Loyalist heavy tail"
    "bleed_features": ("orders", "festive_order_ratio", "return_rate"),
    "bracketer_share": 0.10,                # accounts that sometimes order two sizes of one style
    "bracket_line_probability": 0.35,
    "fit_issue_sku_share": 0.10,
    "fit_issue_fit_reason_probability": 0.80,
    "second_device_probability": 0.30,
    "second_payment_probability": 0.40,
    "primary_identifier_probability": 0.80,
    "shared_location_usage": (0.6, 0.9),    # same range as households
    "shared_location_min_world": 500,       # smaller worlds get no shared-location group
    "request_hours": (8, 23),               # requests are submitted between 08:00 and 22:59 local time
    "decision_days": (1, 3),                # rejection is decided this many days after the request
    "withdraw_days": (0, 2),
    "return_receipt_days": 2,               # generator-config: return_receipt
    "loss_confirmation_days": 12,           # generator-config: loss_confirmation
    "header_span_days": 1,                  # a return header covers its first request date and the next day
}

# experiment.yaml stress seeds, one mechanism varied per world.
STRESS_OVERRIDES = {
    2501: {"ordinary_propensity_scale": 1.2},
    2502: {"ordinary_propensity_scale": 0.8},
    2503: {"defect_incidence_scale": 2.0},
    2504: {"household_share_scale": 2.0},
    2505: {"action_rate_scale": 0.5},
    2506: {"action_rate_scale": 2.0},
    2507: {"actionable_multipliers_all_one": True},
}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class Settings:
    spec_root: Path
    experiment: dict
    accepted: dict          # generator-config.yaml accepted_settings
    defaults: dict          # generator-config.yaml consolidation_defaults
    amendment: dict         # generator-config.yaml amendment_1_1
    policy: dict            # generator-policy.yaml
    profiles: dict          # assets/profile-config.yaml
    festive_windows: list   # assets/festive-windows.yaml
    impl: dict = field(default_factory=lambda: dict(IMPLEMENTATION_DEFAULTS))
    overrides: dict = field(default_factory=dict)

    @property
    def snapshot_date(self) -> date:
        return date.fromisoformat(self.experiment["snapshot_date"])

    @property
    def history_start(self) -> date:
        return date.fromisoformat(self.experiment["history_start"])

    @property
    def cutoff(self) -> datetime:
        return datetime.combine(self.snapshot_date, datetime.min.time(), IST).replace(hour=23, minute=59, second=59)

    def purpose_of(self, seed: int) -> str:
        e = self.experiment
        for purpose, key in (("train", "train_seeds"), ("validation", "validation_seeds"), ("test", "test_seeds"),
                             ("demo", "demo_seeds"), ("fixture", "fixture_seeds")):
            if seed in e[key]:
                return purpose
        return "stress" if seed in e["stress_seeds"] else "fixture"

    def default_customers(self, seed: int) -> int:
        return self.experiment["fixture_customers"] if self.purpose_of(seed) == "fixture" else self.experiment["customers_per_world"]

    def config_sha256(self) -> str:
        """One hash over every specification file that drives generation, plus overrides and open choices."""
        h = hashlib.sha256()
        for rel in ("contracts/experiment.yaml", "contracts/generator-config.yaml", "contracts/generator-policy.yaml",
                    "assets/profile-config.yaml", "assets/festive-windows.yaml", "assets/reason_codes.csv"):
            h.update(rel.encode() + b"\0" + _sha256(self.spec_root / rel).encode() + b"\0")
        h.update(repr(sorted(self.overrides.items())).encode())
        h.update(repr(sorted(self.impl.items())).encode())
        return h.hexdigest()


def load_settings(seed: int | None = None, spec_root: Path | None = None, overrides: dict | None = None) -> Settings:
    root = Path(spec_root or SPEC_ROOT)
    config = _load(root / "contracts" / "generator-config.yaml")
    applied = dict(STRESS_OVERRIDES.get(seed, {}))
    applied.update(overrides or {})
    return Settings(
        spec_root=root,
        experiment=_load(root / "contracts" / "experiment.yaml"),
        accepted=config["accepted_settings"],
        defaults=config["consolidation_defaults"],
        amendment=config["amendment_1_1"],
        policy=_load(root / "contracts" / "generator-policy.yaml"),
        profiles=_load(root / "assets" / "profile-config.yaml"),
        festive_windows=_load(root / "assets" / "festive-windows.yaml")["windows"],
        overrides=applied,
    )
