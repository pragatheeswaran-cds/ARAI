"""Customer profiles and abuse propensities. Both are private generation targets, never model inputs."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from arai.generator.context import DAY, Context
from arai.rng import stream


def _draw_orders(rng, segment: dict, n: int, impl: dict) -> np.ndarray:
    spec = segment["orders"]
    if "always" in spec:
        return np.full(n, int(spec["always"]))
    lo, hi = spec["range"]
    if spec.get("skew") == "lognormal":
        mu, sigma = impl["loyalist_lognormal"]
        base = np.rint(lo + (hi - lo) * np.minimum(1.0, np.exp(rng.normal(mu, sigma, n)))).astype(int)
    else:
        base = rng.integers(lo, hi + 1, n)
    masses = spec.get("masses") or {}
    if masses:
        values = np.array(list(masses) + [-1])
        probabilities = list(masses.values())
        pick = values[rng.choice(len(values), size=n, p=probabilities + [1 - sum(probabilities)])]
        base = np.where(pick >= 0, pick, base)
    return base


def _draw(rng, segments: dict, persona: str, feature: str, n: int, impl: dict) -> np.ndarray:
    segment = segments[persona]
    if feature == "orders":
        return _draw_orders(rng, segment, n, impl)
    lo, hi = segment[feature]
    return rng.integers(lo, hi + 1, n) if feature == "tenure_days" else rng.uniform(lo, hi, n)


def build_profiles(ctx: Context) -> pd.DataFrame:
    """One private profile per account: persona, tenure, order target, festive share and honest return propensity."""
    s, n = ctx.s, ctx.n
    cfg, impl, accepted = s.profiles, s.impl, s.accepted
    segments, realism = cfg["segments"], cfg["realism"]
    rng = stream(ctx.seed, "world", "profiles")

    personas = list(cfg["segment_mix"])
    mix = np.array([cfg["segment_mix"][p] for p in personas], dtype=float)
    persona = np.array(personas, dtype=object)[rng.choice(len(personas), size=n, p=mix / mix.sum())]
    tenure = np.zeros(n, dtype=int)
    orders = np.zeros(n, dtype=int)
    festive = np.zeros(n)
    returns = np.zeros(n)
    for name in personas:
        mask = persona == name
        k = int(mask.sum())
        if k:
            tenure[mask] = _draw(rng, segments, name, "tenure_days", k, impl)
            orders[mask] = _draw(rng, segments, name, "orders", k, impl)
            festive[mask] = _draw(rng, segments, name, "festive_order_ratio", k, impl)
            returns[mask] = _draw(rng, segments, name, "return_rate", k, impl)
    active = persona != "Dormant"

    # soft persona boundaries: one feature copied from another persona
    donors = [p for p in personas if p != "Dormant"]
    targets = {"orders": orders, "festive_order_ratio": festive, "return_rate": returns}
    for i in np.flatnonzero(active & (rng.random(n) < realism["bleed_prob"])):
        donor = donors[rng.integers(len(donors))]
        feature = impl["bleed_features"][rng.integers(len(impl["bleed_features"]))]
        targets[feature][i] = _draw(rng, segments, donor, feature, 1, impl)[0]

    festive_bleed = active & (persona != "Seasonal") & (rng.random(n) < realism["festive_bleed_prob"])
    festive = np.where(festive_bleed, rng.uniform(*realism["festive_bleed_range"], n), festive)

    power_user = (persona == impl["power_user_persona"]) & (rng.random(n) < accepted["power_user_share"])
    lo, hi = realism["power_user_orders"]
    orders = np.where(power_user, rng.integers(lo, hi + 1, n), orders)

    heavy = active & (rng.random(n) < accepted["heavy_return_share"])
    returns = np.where(heavy, rng.uniform(*accepted["heavy_return_range"], n), returns)
    returns = np.clip(returns * s.overrides.get("ordinary_propensity_scale", 1.0), 0.0, 1.0)
    bracketer = active & (rng.random(n) < impl["bracketer_share"])

    signup = ctx.snapshot - tenure * DAY
    eligible_start = np.maximum(signup, ctx.history_start)
    eligible_days = ((ctx.snapshot - eligible_start) / DAY).astype(int) + 1
    target = np.minimum(orders, np.floor(impl["max_order_intensity_per_day"] * eligible_days).astype(int))
    return pd.DataFrame({
        "customer_id": ctx.customer_ids,
        "persona": persona,
        "tenure_days": tenure,
        "signup_date": signup,
        "eligible_start": eligible_start,
        "eligible_days": eligible_days,
        "target_order_count": target,
        "target_return_propensity": returns,
        "target_festive_share": festive,
        "target_days_per_order": np.where(target > 0, eligible_days / np.maximum(target, 1), np.nan),
        "heavy_return_overlay": heavy,
        "power_user": power_user,
        "bracketer": bracketer,
    })


def allocate_abuse(ctx: Context, profiles: pd.DataFrame) -> pd.DataFrame:
    """Joint categorical allocation of claim and temporary-use propensity (generator-policy.yaml overlay).

    Expected whole-world rates are 4% claim, 3% temporary use and 0.5% both. They are probabilities, not
    quotas. An invalid probability fails the configuration; nothing is clipped.
    """
    s, n = ctx.s, ctx.n
    overlay = s.policy["overlay"]
    multipliers = {k: float(v) for k, v in overlay["persona_multipliers"].items()}
    if s.overrides.get("actionable_multipliers_all_one"):
        multipliers = {k: (1.0 if v > 0 else 0.0) for k, v in multipliers.items()}
    m = profiles["persona"].map(multipliers).to_numpy(dtype=float) * (profiles["target_order_count"].to_numpy() > 0)
    if s.overrides.get("disable_overlays"):
        m = np.zeros(n)
    mean = m.mean()
    w = m / mean if mean > 0 else np.zeros(n)

    c = overlay["categorical_coefficients"]
    p = np.column_stack([c["claim_only"] * w, c["temporary_use_only"] * w, c["both"] * w])
    if (p < 0).any() or (p.sum(axis=1) > 1).any():
        raise ValueError("abuse overlay produced an invalid probability; fix the configuration instead of clipping")
    u = stream(ctx.seed, "world", "abuse_allocation").random(n)
    edges = np.cumsum(p, axis=1)
    category = np.select([u < edges[:, 0], u < edges[:, 1], u < edges[:, 2]],
                         ["claim_only", "temporary_use_only", "both"], default="neither")
    claim = np.isin(category, ["claim_only", "both"])
    temporary = np.isin(category, ["temporary_use_only", "both"])

    a, b = map(float, re.search(r"Beta\(([\d.]+),\s*([\d.]+)\)", s.amendment["action_rate"]["distribution"]).groups())
    scale = s.overrides.get("action_rate_scale", 1.0)
    rates = stream(ctx.seed, "world", "action_rates")
    claim_rate = np.where(claim, np.clip(rates.beta(a, b, n) * scale, 0.0, 1.0), 0.0)
    temporary_rate = np.where(temporary, np.clip(rates.beta(a, b, n) * scale, 0.0, 1.0), 0.0)
    return profiles.assign(abuse_category=category, claim_propensity=claim, temporary_use_propensity=temporary,
                           claim_action_rate=claim_rate, temporary_use_action_rate=temporary_rate,
                           allocation_weight=w)
