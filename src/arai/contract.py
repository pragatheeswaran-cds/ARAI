"""Numbers and code lists that the specification fixes, read once from the bundled contracts.

Code that needs the eligibility minimum, the review budgets, the bootstrap settings or a reason-code group takes
it from here, so the contract and the code cannot drift apart. Nothing here touches data or private truth.
"""
from __future__ import annotations

import functools

import yaml

from arai.paths import SPEC_ROOT


@functools.lru_cache(maxsize=None)
def _load(name: str) -> dict:
    return yaml.safe_load((SPEC_ROOT / "contracts" / name).read_text(encoding="utf-8"))


def reason_group(name: str) -> tuple:
    """The reason codes of one feature group of contracts/reason-groups.yaml, in the contract's order."""
    return tuple(_load("reason-groups.yaml")["feature_groups"][name]["codes"])


def eligibility_min_lines() -> int:
    return int(_load("experiment.yaml")["eligibility"]["min_mature_sale_lines"])


def primary_fraction() -> float:
    return float(_load("experiment.yaml")["budgets"]["primary_fraction"])


def sensitivity_fractions() -> tuple:
    return tuple(float(f) for f in _load("experiment.yaml")["budgets"]["sensitivity_fractions"])


def bootstrap() -> tuple:
    """(repetitions, seed, percentiles) of the paired whole-world bootstrap."""
    uncertainty = _load("experiment.yaml")["uncertainty"]
    return int(uncertainty["world_bootstrap_repetitions"]), int(uncertainty["seed"]), tuple(uncertainty["interval_percentiles"])
