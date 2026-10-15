"""Score attribution by family re-scoring, the analyst rules that would have fired, and the order of the evidence chips.

Frontend data plan WP2, decisions D1 and D6. Everything here is predict-side: the frozen pipeline is called again
with one feature family held at typical values and the score read off. Boosted trees do not decompose additively,
so the honest statement is "the score with this family at typical values", never contributions that sum to the
score. Nothing is fitted and no selection changes; the published queue is untouched.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from arai import bundles

# the two families the offline ablation defines (ablation.TIMING_FEATURES and CLAIM_FEATURES), repeated here because the
# serving side imports no offline module; the service test checks the two stay equal
TIMING_FEATURES = ("late_return_lines", "late_window_share", "median_window_ratio", "item_ratio_max", "item_ratio_second",
                   "item_ratio_mean", "mid_late_lines", "late_occasion_return_lines", "mid_or_late_occasion_lines", "item_in_window_lines")
CLAIM_FEATURES = ("claim_share", "coordinated_claim_share", "claim_lines", "claim_order_count", "claim_order_rate", "claim_unit_rate",
                  "claim_excess_z", "claimed_share_of_claim_orders", "whole_order_claim_share", "claim_day_span", "claim_distinct_days",
                  "claims_in_densest_fortnight", "nonreceipt_share_of_claims", "multi_code_claim_orders", "multi_code_claim_share",
                  "max_claim_lines_per_order", "claimed_order_size_ratio", "claim_style_others_rate_mean", "claim_style_others_rate_max",
                  "claim_value_ratio")
# family -> (label, model features); the five families partition the 43 model features of the contract
FAMILIES = (
    ("claims", "Transaction claims", CLAIM_FEATURES),
    ("timing", "Return timing", TIMING_FEATURES),
    ("expected_vs_actual", "Returns against the basket's expectation",
     ("raw_return_rate", "expected_return_rate", "residual_z", "requested_refund_ratio", "trend_90d")),
    ("composition", "What is returned", ("damage_reason_share", "bracketing_share", "occasion_return_share", "discretionary_share",
                                        "open_window_share")),
    ("volume", "Volume", ("mature_sale_lines", "log_order_count", "units_per_order")),
)
FAMILY_LABELS = {family: label for family, label, _ in FAMILIES}
# evidence tag -> the family whose features read it; supported_links is evidence only and belongs to no family
TAG_FAMILY = {"repeat_claims": "claims", "linked_claims": "claims", "late_returns": "timing", "returns_above_expected": "expected_vs_actual",
              "supported_links": None}
PRIMARY_SIGNALS = 3
# the analyst rulebook (selection.RULEBOOK_RULES), as rules that would have fired; report-only, never part of the score
RULES = (("rate_p90", "Return rate at or above the training 90th percentile"),
         ("claims_2", "Two or more visible transaction-claim return lines"),
         ("refund_ratio_p90", "Requested refund ratio at or above the training 90th percentile"),
         ("linked_claimant", "A supported link and at least one own claim line"),
         ("late_half", "Half or more of timed returns late in the window, with two or more timed lines"))
TYPICAL_TRAINING, TYPICAL_SNAPSHOT = "training", "snapshot"


def typical_values(bundle: bundles.Bundle, scored: pd.DataFrame) -> tuple:
    """(feature -> typical value, source). The training median travels with the bundle; a bundle without one falls back
    to the median of this snapshot's eligible customers, and the source says so."""
    quantiles = bundle.manifest.get("feature_quantiles") or {}
    if all(quantiles.get(name) for name in bundle.feature_order):
        return {name: float(quantiles[name][1]) for name in bundle.feature_order}, TYPICAL_TRAINING
    return {name: float(np.nanmedian(scored[name].to_numpy(dtype=float))) for name in bundle.feature_order}, TYPICAL_SNAPSHOT


def attribute(bundle: bundles.Bundle, scored: pd.DataFrame, raw: np.ndarray, risk_score: np.ndarray, threshold_raw: float | None) -> tuple:
    """(rows, source): one row per eligible customer and family, with the score the frozen pipeline gives when that family
    sits at typical values and everything else stays as observed.

    `in_queue_without` says whether that score is at or above the raw score at rank k (the queue's edge), everyone
    else unchanged: a counterfactual for this customer alone. Empty when nothing is eligible.
    """
    columns = ["customer_id", "family", "raw_score_without", "score_without", "delta_points", "in_queue_without"]
    if not len(scored):
        return pd.DataFrame(columns=columns), None
    typical, source = typical_values(bundle, scored)
    frames = []
    for family, _, names in FAMILIES:
        altered = scored.copy()
        for name in names:
            if name in typical and name in altered:        # the baseline reads one feature; the others stay as observed
                altered[name] = typical[name]
        raw_without = bundles.raw_scores(bundle, altered)
        if not np.isfinite(raw_without).all():
            raise ValueError(f"re-scoring with the {family} family at typical values produced a non-finite score")
        score_without = np.clip(bundles.reference_percentile(bundle, raw_without), 0.0, 100.0)
        frames.append(pd.DataFrame({"customer_id": scored["customer_id"].to_numpy(), "family": family,
                                    "raw_score_without": raw_without, "score_without": score_without,
                                    "delta_points": score_without - risk_score,
                                    "in_queue_without": (raw_without >= threshold_raw) if threshold_raw is not None else False}))
    rows = pd.concat(frames, ignore_index=True).sort_values(["customer_id", "family"]).reset_index(drop=True)
    return rows[columns], source


def primary_signals(tags: pd.Series, rows: pd.DataFrame) -> pd.Series:
    """Per customer, the evidence tags in the order the attribution ranks their families: the family whose typical values
    lower the score most comes first; a tag with no family comes last; then the tags' own order. Up to three, joined by '|'."""
    delta = rows.pivot(index="customer_id", columns="family", values="delta_points") if len(rows) else pd.DataFrame()

    def order(customer_id, tagged: str) -> str:
        names = [t for t in str(tagged or "").split("|") if t]
        weights = delta.loc[customer_id] if customer_id in delta.index else {}
        ranked = sorted(enumerate(names), key=lambda item: (
            0 if TAG_FAMILY.get(item[1]) else 1, float(weights.get(TAG_FAMILY.get(item[1]), 0.0)) if TAG_FAMILY.get(item[1]) else 0.0, item[0]))
        return "|".join(name for _, name in ranked[:PRIMARY_SIGNALS])
    return pd.Series([order(c, t) for c, t in zip(tags.index, tags.to_numpy())], index=tags.index, dtype=object)


def rules_fired(features: pd.DataFrame, bundle: bundles.Bundle) -> pd.DataFrame:
    """The five analyst rules per customer: True, False, or None when the rule's training threshold is not in the bundle or an
    input is missing. Report-only: a rule firing is a statement about the customer's measures, not about the score."""
    quantiles = bundle.manifest.get("feature_quantiles") or {}
    rate_p90 = quantiles.get("raw_return_rate")
    ratio_p90 = quantiles.get("requested_refund_ratio")
    out = pd.DataFrame(index=features.index)
    out["rule_rate_p90"] = (features["raw_return_rate"] >= rate_p90[2]).where(features["raw_return_rate"].notna(), None) \
        if rate_p90 else pd.Series(None, index=features.index, dtype=object)
    out["rule_claims_2"] = (features["claim_lines"] >= 2).where(features["claim_lines"].notna(), None)
    out["rule_refund_ratio_p90"] = (features["requested_refund_ratio"] >= ratio_p90[2]).where(features["requested_refund_ratio"].notna(), None) \
        if ratio_p90 else pd.Series(None, index=features.index, dtype=object)
    out["rule_linked_claimant"] = ((features["supported_neighbor_count"] >= 1) & (features["claim_lines"] >= 1)) \
        .where(features["supported_neighbor_count"].notna() & features["claim_lines"].notna(), None)
    out["rule_late_half"] = ((features["late_window_share"] >= 0.5) & (features["timed_return_lines"] >= 2)) \
        .where(features["late_window_share"].notna() & features["timed_return_lines"].notna(), None)
    return out.astype(object)
