"""The review-set rule, shared by offline evaluation and by serving (final-spec components 08 and 11).

Top k = min(N, ceil(fraction * N)) eligible customers of one world by raw score, ties broken by a public hash.
Nothing here knows about labels.
"""
from __future__ import annotations

import hashlib
import math

import numpy as np
import pandas as pd

from arai import contract

TIE_NAMESPACE = "review-tie-v02"
PRIMARY_FRACTION = contract.primary_fraction()


def tie_key(world_id: str, customer_id: str) -> str:
    """Public tie-break: ascending SHA256 of the namespace, world and customer."""
    return hashlib.sha256(f"{TIE_NAMESPACE}|{world_id}|{customer_id}".encode("utf-8")).hexdigest()


def budget(eligible: int, fraction: float = PRIMARY_FRACTION) -> int:
    return min(eligible, math.ceil(fraction * eligible))


def rank_world(world_id: str, customer_ids, scores) -> np.ndarray:
    """1-based rank of each eligible customer of one world: score descending, then the tie hash ascending."""
    scores = np.asarray(scores, dtype=float)
    if not np.isfinite(scores).all():
        raise ValueError(f"world {world_id} has a missing or non-finite score")
    frame = pd.DataFrame({"score": scores, "tie": [tie_key(world_id, c) for c in customer_ids]})
    order = frame.sort_values(["score", "tie"], ascending=[False, True], kind="stable").index.to_numpy()
    ranks = np.empty(len(frame), dtype=int)
    ranks[order] = np.arange(1, len(frame) + 1)
    return ranks
