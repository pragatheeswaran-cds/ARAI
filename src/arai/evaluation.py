"""Model and evidence evaluation (final-spec component 08).

Offline only. Private truth is joined here after scores are frozen, and nothing in this module is reachable
from the inference path. Every ratio keeps its numerator and denominator; a zero denominator gives null.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from arai import dataset, paths
from arai.generator import load_world
from arai.ranking import PRIMARY_FRACTION, budget, rank_world, tie_key  # noqa: F401  (tie_key is part of this module's interface)

SEGMENTS = ("legit_heavy_returner", "defective_product_buyer", "benign_household")
ACTION_TYPES = ("deceptive_nonreceipt_claim", "deceptive_contents_claim", "temporary_use_return")
SENSITIVITY_FRACTIONS = (0.01, 0.10)
BOOTSTRAP_REPETITIONS, BOOTSTRAP_SEED = 1000, 20260926
MIN_SEGMENT_SIZE = 200
LINE_KEY = ["order_id", "order_line_no"]


def ratio(numerator, denominator):
    return float(numerator) / float(denominator) if denominator else None


def select(frame: pd.DataFrame, score: str, fraction: float = PRIMARY_FRACTION) -> pd.Series:
    """Review selection per world: the top k = min(N, ceil(fraction*N)) eligible customers by raw score.

    `frame` holds eligible customers only. Ties are broken by the public hash, never by rounding.
    """
    selected = pd.Series(False, index=frame.index)
    for world_id, group in frame.groupby("world_id", sort=True):
        if not len(group):
            raise ValueError(f"world {world_id} has no eligible customer")
        ranks = rank_world(world_id, group["customer_id"], group[score])       # the same rule serving uses
        selected.loc[group.index[ranks <= budget(len(group), fraction)]] = True
    return selected


def confusion(frame: pd.DataFrame, selected: pd.Series) -> dict:
    """Pooled counts over worlds (k is chosen per world first), with segment false-positive rates."""
    y = frame["y_abuse"] == 1
    out = {"eligible": int(len(frame)), "k": int(selected.sum()), "true_positives": int((selected & y).sum()),
           "positives": int(y.sum())}
    out["precision"] = ratio(out["true_positives"], out["k"])
    out["recall"] = ratio(out["true_positives"], out["positives"])
    for segment in SEGMENTS:
        members = frame[segment].astype(bool)
        out[segment + "_size"] = int(members.sum())
        out[segment + "_selected"] = int((selected & members).sum())
        out[segment + "_fpr"] = ratio(out[segment + "_selected"], out[segment + "_size"])
    for action in ACTION_TYPES + ("coordinated_action_flag",):
        acted = frame[action].astype(bool)
        out["recall_" + action] = ratio((selected & acted).sum(), acted.sum())
    return out


def per_world(frame: pd.DataFrame, selected: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({w: confusion(g, selected.loc[g.index]) for w, g in frame.groupby("world_id", sort=True)}).T


def evaluate(frame: pd.DataFrame, score: str, fractions=(PRIMARY_FRACTION, *SENSITIVITY_FRACTIONS)) -> dict:
    """Pooled metrics at each review budget."""
    return {fraction: confusion(frame, select(frame, score, fraction)) for fraction in fractions}


def bootstrap(frame: pd.DataFrame, scores: dict, baseline: str, fraction: float = PRIMARY_FRACTION) -> pd.DataFrame:
    """Paired whole-world bootstrap of precision and its difference from the baseline (percentile intervals).

    Worlds are resampled together for every ranking, so the difference is paired. With five worlds this is a
    coarse measure of spread; it supports no claim of a significant improvement.
    """
    worlds = sorted(frame["world_id"].unique())
    counts = {}
    for name, score in scores.items():
        chosen = select(frame, score, fraction)
        stats = per_world(frame, chosen)
        counts[name] = stats[["true_positives", "k"]].astype(float).loc[worlds].to_numpy()
    rng = np.random.Generator(np.random.PCG64(BOOTSTRAP_SEED))
    draws = rng.integers(0, len(worlds), size=(BOOTSTRAP_REPETITIONS, len(worlds)))
    rows = []
    base = counts[baseline][draws].sum(axis=1)
    base_precision = base[:, 0] / base[:, 1]
    for name, values in counts.items():
        sample = values[draws].sum(axis=1)
        precision = sample[:, 0] / sample[:, 1]
        low, high = np.percentile(precision, [2.5, 97.5])
        d_low, d_high = np.percentile(precision - base_precision, [2.5, 97.5])
        rows.append({"ranking": name, "precision": values[:, 0].sum() / values[:, 1].sum(), "lower_95": low, "upper_95": high,
                     "difference_from_baseline_lower_95": d_low, "difference_from_baseline_upper_95": d_high})
    return pd.DataFrame(rows).set_index("ranking")


# ------------------------------------------------------------------ private joins
def benign_segments(world, features: pd.DataFrame) -> pd.DataFrame:
    """The three benign segments of the gate, per customer. All require an honest, eligible customer.

    heavy returner: raw return rate at or above the 90th percentile of ALL eligible customers, abusers included
                    (linear interpolation, ties included);
    defective buyer: requested at least one genuinely defective unit on a mature line (carrier damage excluded);
    household: actually used an identifier that another member of the same household also used.
    """
    truth = world.truth["customer_truth"]
    frame = features[["customer_id", "eligible", "raw_return_rate"]].merge(truth[["customer_id", "y_abuse", "household_id"]], on="customer_id")
    eligible = frame[frame["eligible"]]
    threshold = eligible["raw_return_rate"].quantile(0.9, interpolation="linear") if len(eligible) else np.nan
    heavy = set(eligible.loc[eligible["raw_return_rate"] >= threshold, "customer_id"])

    cutoff = pd.Timestamp(world.snapshot_date)
    lines = world.tables["sales_order_line"].merge(world.tables["sales_order"][["order_id", "customer_id"]], on="order_id")
    lines["mature"] = (lines["line_status"] == "delivered") & (
        lines["delivered_date"] + pd.to_timedelta(lines["return_window_days"], unit="D") <= cutoff)
    defective = world.truth["unit_truth"]
    defective = defective[defective["received_defective_unit"]][LINE_KEY + ["unit_index"]]
    allocation = world.truth["unit_allocation"]
    requested = allocation[allocation["reservation_kind"] == "honest_request"].merge(defective, on=LINE_KEY + ["unit_index"])
    active = world.tables["return_order_line"]
    active = active[active["line_status"] != "withdrawn"][LINE_KEY].drop_duplicates()
    requested = requested.merge(active, on=LINE_KEY).merge(lines[LINE_KEY + ["customer_id", "mature"]], on=LINE_KEY)
    defective_buyers = set(requested.loc[requested["mature"], "customer_id"])

    members = truth[truth["household_id"].notna()][["customer_id", "household_id"]]
    orders = world.tables["sales_order"].merge(members, on="customer_id")
    sharing = set()
    for kind in ("address_id", "device_id", "payment_id"):
        users = orders.groupby(["household_id", kind])["customer_id"].nunique()
        shared = users[users > 1].reset_index()[["household_id", kind]]
        sharing |= set(orders.merge(shared, on=["household_id", kind])["customer_id"])

    benign = frame["eligible"] & (frame["y_abuse"] == 0)
    out = frame[["customer_id", "eligible", "y_abuse"]].copy()
    out["legit_heavy_returner"] = benign & out["customer_id"].isin(heavy)
    out["defective_product_buyer"] = benign & out["customer_id"].isin(defective_buyers)
    out["benign_household"] = benign & out["customer_id"].isin(sharing)
    return out


def evaluation_frame(world_ids: list, artifact_root: Path | None = None, private_root: Path | None = None) -> pd.DataFrame:
    """Eligible customers of the named worlds with frozen features, label, action types and benign segments.

    This is the private evaluation join. It happens after features and scores are frozen.
    """
    frames = []
    for world_id in world_ids:
        world = load_world(world_id, artifact_root, private_root)
        if world.purpose in ("demo", "fixture"):
            raise ValueError(f"{world_id} is a {world.purpose} world and can never enter a scorecard")
        features = dataset.load_features(world_id, artifact_root)
        segments = benign_segments(world, features)
        truth = world.truth["customer_truth"][["customer_id", *ACTION_TYPES, "coordinated_action_flag"]]
        frame = features.merge(segments[["customer_id", "y_abuse", *SEGMENTS]], on="customer_id").merge(truth, on="customer_id")
        frame["all_abusers_in_world"] = int(segments["y_abuse"].sum())
        frames.append(frame[frame["eligible"]])
    return pd.concat(frames, ignore_index=True)


def coverage(frame: pd.DataFrame, world_ids: list, private_root: Path | None = None) -> dict:
    """Whole-population abuse coverage: how much abuse the eligibility rule leaves outside the ranking."""
    total = 0
    for world_id in world_ids:
        truth = pd.read_parquet(Path(private_root or paths.PRIVATE_TRUTH_ROOT) / world_id / "customer_truth.parquet")
        total += int(truth["y_abuse"].sum())
    eligible = int(frame["y_abuse"].sum())
    return {"abusers_all": total, "abusers_eligible": eligible, "abusers_excluded": total - eligible,
            "excluded_share": ratio(total - eligible, total),
            "segment_sizes": {s: int(frame[s].sum()) for s in SEGMENTS},
            "segments_below_minimum": [s for s in SEGMENTS if frame[s].sum() < MIN_SEGMENT_SIZE]}


def opportunity_actions(actions: pd.DataFrame) -> pd.DataFrame:
    """Abusive actions counted once per opportunity.

    A whole-parcel claim is one opportunity written as several actions (one per sale line, the further ones
    marked parcel_companion with the parent's identifier plus "-L<line>"). The opportunity is completed if any
    of its lines is visible at the cutoff: a companion can be visible while the first line's request falls
    after the cutoff.
    """
    if "parcel_companion" not in actions or not len(actions):
        return actions
    parent = actions["action_id"].where(~actions["parcel_companion"], actions["action_id"].str.rsplit("-L", n=1).str[0])
    completed = actions["completed_action"].groupby(parent).transform("any")
    first = actions[~actions["parcel_companion"]].copy()
    first["completed_action"] = completed[first.index]
    first.loc[first["completed_action"], "uncompleted_reason"] = None
    return first


def error_account(frame: pd.DataFrame, selected: pd.Series, baseline_selected: pd.Series, completed_actions: pd.Series) -> dict:
    """Who the ranking gets wrong at the review budget, and how it differs from the return-rate rule.

    `completed_actions` is the number of completed abusive actions per row (private truth). Groups overlap and
    are never summed as if they were disjoint.
    """
    y = frame["y_abuse"] == 1
    false_positive = selected & ~y
    false_negative = ~selected & y
    fp = {"false_positives": int(false_positive.sum())}
    for segment in SEGMENTS:
        fp[segment] = int((false_positive & frame[segment].astype(bool)).sum())
    fp["repeat_genuine_claimant"] = int((false_positive & (frame["genuine_claim_units"] >= 2)).sum())
    fp["none_of_these"] = int((false_positive & ~frame[list(SEGMENTS)].any(axis=1) & (frame["genuine_claim_units"] < 2)).sum())
    fn = {"false_negatives": int(false_negative.sum())}
    for action in ACTION_TYPES:
        fn[action] = int((false_negative & frame[action].astype(bool)).sum())
    if (completed_actions[y] < 1).any():
        raise ValueError("a positive customer has no completed abusive action: label and action counts disagree")
    bucket = pd.cut(completed_actions, [0, 1, 3, np.inf], labels=["1", "2-3", "4+"])
    for label in ("1", "2-3", "4+"):
        fn[f"completed_actions_{label}"] = int((false_negative & (bucket == label)).sum())
        fn[f"positives_with_{label}_actions"] = int((y & (bucket == label)).sum())
    difference = {"selected_by_model_only": int((selected & ~baseline_selected).sum()),
                  "of_which_abusers": int((selected & ~baseline_selected & y).sum()),
                  "selected_by_baseline_only": int((baseline_selected & ~selected).sum()),
                  "of_which_honest": int((baseline_selected & ~selected & ~y).sum())}
    for segment in SEGMENTS:
        difference[f"baseline_only_{segment}"] = int((baseline_selected & ~selected & frame[segment].astype(bool)).sum())
    return {"false_positives": fp, "false_negatives": fn, "model_versus_baseline": difference}


def private_counts(world_ids: list, private_root: Path | None = None) -> pd.DataFrame:
    """Per customer: completed abusive actions and genuine fulfilment-failure units (private truth)."""
    frames = []
    for world_id in world_ids:
        world = load_world(world_id, private_root=private_root)
        actions = opportunity_actions(world.truth["action_truth"])        # a whole-parcel claim is one action
        done = actions[actions["completed_action"]].groupby("customer_id").size().rename("completed_actions")
        units = world.truth["unit_truth"]
        units = units[units["genuine_fulfilment_cause"].notna()].merge(
            world.tables["sales_order"][["order_id", "customer_id"]], on="order_id")
        genuine = units.groupby("customer_id").size().rename("genuine_claim_units")
        frame = world.tables["customer_master"][["customer_id"]].assign(world_id=world_id)
        frame = frame.merge(done, on="customer_id", how="left").merge(genuine, on="customer_id", how="left").fillna(0)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)
