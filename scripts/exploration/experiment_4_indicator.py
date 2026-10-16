"""Reproduce the measurements behind the rebuilt wardrobing indicator (decision AM-52). Reads only.

    uv run --no-sync python scripts/exploration/experiment_4_indicator.py

The indicator of the code in this repository is computed, in memory, on the training worlds of experiments 2
(generator-config 1.3) and 3 (generator-config 3.0) in data/artifacts, and compared with private truth for
eligible customers. Three tables are printed per simulator:
- each band of the rebuilt indicator and of the timing rule it replaces (stored with those worlds);
- every combination of the three signals, which is the evidence for requiring a late return;
- whether the 43 model features computed by this code equal the stored ones.
Takes several minutes. Nothing is written.
"""
from __future__ import annotations

import json

import pandas as pd

from arai import dataset, paths
from arai import features as F

ARTIFACTS, PRIVATE = paths.REPO_ROOT / "data" / "artifacts", paths.REPO_ROOT / "data" / "private"
SETS = (("generator-config 1.3, W3101-W3110", range(3101, 3111)), ("generator-config 3.0, W4101-W4110", range(4101, 4111)))


def measure(seeds) -> tuple:
    rows, unchanged = [], True
    for seed in seeds:
        world = f"W{seed}"
        tables, manifest = dataset.load_operational(world, ARTIFACTS)
        stored = ARTIFACTS / "features" / world
        reference = F.Reference.from_dict(json.loads((stored / "meta.json").read_text(encoding="utf-8"))["reference"])
        result = F.compute_features(tables, dataset.snapshot_date(manifest), reference)
        old = pd.read_parquet(stored / "features.parquet")
        unchanged &= all((result.features[name].fillna(-9).to_numpy() == old[name].fillna(-9).to_numpy()).all() for name in F.feature_order())
        timing_rule = pd.read_parquet(stored / "wardrobing.parquet")[["customer_id", "status"]].rename(columns={"status": "timing_rule"})
        truth = pd.read_parquet(PRIVATE / world / "customer_truth.parquet")[["customer_id", "temporary_use_return", "y_abuse"]]
        frame = result.wardrobing.merge(result.features[["customer_id", "eligible"]], on="customer_id").merge(truth, on="customer_id") \
            .merge(timing_rule, on="customer_id")
        rows.append(frame[frame["eligible"]].assign(world_id=world))
    return pd.concat(rows, ignore_index=True), unchanged


def line(label: str, flagged: pd.Series, actual: pd.Series) -> str:
    right = int((flagged & actual).sum())
    share = f"{right / flagged.sum():.1%}" if flagged.sum() else "n/a"
    return f"  {label:<44} right {right:>4} of {int(flagged.sum()):>5} ({share:>6})   found {right / actual.sum():.1%}"


def main() -> None:
    for title, seeds in SETS:
        e, unchanged = measure(seeds)
        actual = e["temporary_use_return"].astype(bool)
        print(f"\n{title}: {len(e)} eligible customers, {int(actual.sum())} with a temporary-use return")
        print(f"  the 43 model features equal the stored ones: {unchanged}")
        for name, column in (("rebuilt", "status"), ("timing rule", "timing_rule")):
            for band, values in (("elevated", ["elevated"]), ("possible", ["possible"]), ("either band", ["elevated", "possible"])):
                print(line(f"{name}, {band}", e[column].isin(values), actual))
        honest = e["y_abuse"] == 0
        alerted = e["status"].isin(["elevated", "possible"])
        print(f"  honest customers alerted by the rebuilt indicator: {int((alerted & honest).sum())} of {int(honest.sum())}")
        per_world = e[e["status"] == "elevated"].groupby("world_id")["temporary_use_return"].agg(["sum", "size"])
        print("  rebuilt, elevated, per world: " + ", ".join(f"{int(a)}/{int(b)}" for a, b in per_world.to_numpy()))
        # the three kinds of evidence without the rule that a late return is required
        late = e["late_occasion_return_lines"] >= 1
        excess = (e["occasion_excess_z"] >= F.OCCASION_EXCESS_Z) & (e["occasion_returned_units"] >= F.OCCASION_EXCESS_MIN_UNITS)
        complaint = e["clean_style_complaint_lines"] >= 1
        print("  every combination of the evidence (customers with an item return):")
        returned = e["item_return_lines"] > 0
        for has_late in (False, True):
            for has_excess in (False, True):
                for has_complaint in (False, True):
                    mask = returned & (late == has_late) & (excess == has_excess) & (complaint == has_complaint)
                    label = ", ".join(n for n, on in (("late occasion return", has_late), ("excess", has_excess), ("complaint", has_complaint)) if on)
                    print("  " + line(label or "none of the three", mask, actual))


if __name__ == "__main__":
    main()
