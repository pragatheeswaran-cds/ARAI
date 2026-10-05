"""Reference rankings, the promotion gate and model selection (final-spec components 08 and 09).

The gate is a point-estimate rule at the 5% budget: a candidate must have strictly higher precision than the
raw-return-rate baseline and no higher false-positive rate in each benign segment the contract lists. Report-only
references are scored the same way and can never be selected.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from arai.evaluation import MIN_SEGMENT_SIZE, PRIMARY_FRACTION, SEGMENTS, confusion, select

BASELINE = "raw_return_rate"
RULEBOOK_RULES = ("raw_return_rate >= training p90", "visible transaction-claim return lines >= 2",
                  "requested_refund_ratio >= training p90", "supported_neighbor_count >= 1 and own claim lines >= 1",
                  "late_window_share >= 0.50 with >= 2 timed return lines")


def rulebook_thresholds(training: pd.DataFrame) -> dict:
    """Percentiles of eligible training customers (linear interpolation), frozen for scoring."""
    eligible = training[training["eligible"]]
    return {"raw_return_rate_p90": float(eligible["raw_return_rate"].quantile(0.9, interpolation="linear")),
            "requested_refund_ratio_p90": float(eligible["requested_refund_ratio"].quantile(0.9, interpolation="linear"))}


def rulebook_score(frame: pd.DataFrame, thresholds: dict) -> pd.Series:
    """Number of fired analyst rules (0-5); ties are ordered by raw return rate. A null input does not fire."""
    fired = ((frame["raw_return_rate"] >= thresholds["raw_return_rate_p90"]).astype(int)
             + (frame["claim_lines"] >= 2).astype(int)
             + (frame["requested_refund_ratio"] >= thresholds["requested_refund_ratio_p90"]).astype(int)
             + ((frame["supported_neighbor_count"] >= 1) & (frame["claim_lines"] >= 1)).astype(int)
             + ((frame["late_window_share"] >= 0.5) & (frame["timed_return_lines"] >= 2)).astype(int))
    return fired + 0.1 * frame["raw_return_rate"].fillna(0.0)          # the rate is at most 1, so it only orders ties


def rulebook_out_of_fold(frame: pd.DataFrame, folds: dict) -> pd.Series:
    """Rulebook scores for training rows, with thresholds taken from the other folds' worlds."""
    scores = pd.Series(np.nan, index=frame.index)
    fold_of = frame["world_id"].map(folds)
    for fold in sorted(set(folds.values())):
        held_out = fold_of == fold
        scores[held_out] = rulebook_score(frame[held_out], rulebook_thresholds(frame[~held_out]))
    return scores


def gate(candidate: dict, baseline: dict, require_coverage: bool = True) -> tuple:
    """(passed, reasons). `candidate` and `baseline` are pooled confusion dictionaries at the primary budget."""
    reasons = []
    if candidate["precision"] is None or baseline["precision"] is None:
        return False, ["precision undefined"]
    if not candidate["precision"] > baseline["precision"]:
        reasons.append("precision not above the baseline")
    for segment in SEGMENTS:
        if require_coverage and candidate[segment + "_size"] < MIN_SEGMENT_SIZE:
            reasons.append(f"{segment} has fewer than {MIN_SEGMENT_SIZE} members")
            continue
        if candidate[segment + "_fpr"] is None:
            reasons.append(f"{segment} false-positive rate undefined")
        elif candidate[segment + "_fpr"] > baseline[segment + "_fpr"]:
            reasons.append(f"{segment} false-positive rate above the baseline")
    return not reasons, reasons


def scorecard(frame: pd.DataFrame, rankings: dict, selectable: dict, require_coverage: bool = True) -> pd.DataFrame:
    """One row per ranking at the primary budget, with the gate verdict for the selectable ones.

    rankings: name -> score column in `frame`; selectable: name -> registered ordinal (references are absent).
    """
    baseline = confusion(frame, select(frame, rankings[BASELINE], PRIMARY_FRACTION))
    rows = []
    for name, column in rankings.items():
        result = confusion(frame, select(frame, column, PRIMARY_FRACTION))
        row = {"ranking": name, **{k: result[k] for k in ("k", "true_positives", "positives", "precision", "recall")},
               **{s + "_fpr": result[s + "_fpr"] for s in SEGMENTS},
               "worst_segment_fpr": max(result[s + "_fpr"] or 0.0 for s in SEGMENTS)}
        if name == BASELINE:
            row.update(role="baseline", status="comparison", reasons="")
        elif name in selectable:
            passed, reasons = gate(result, baseline, require_coverage)
            row.update(role="candidate", ordinal=selectable[name], status="passed" if passed else "rejected", reasons="; ".join(reasons))
        else:
            row.update(role="reference", status="report only", reasons="")
        rows.append(row)
    return pd.DataFrame(rows).set_index("ranking")


def choose(card: pd.DataFrame) -> str | None:
    """Highest precision among passing candidates, then smallest worst-segment rate, then registered ordinal."""
    passing = card[(card["role"] == "candidate") & (card["status"] == "passed")]
    if passing.empty:
        return None
    return passing.sort_values(["precision", "worst_segment_fpr", "ordinal"], ascending=[False, True, True]).index[0]
