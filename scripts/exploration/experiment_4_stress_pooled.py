"""Reproduce the pooled stress-world figures of the experiment 4 record (section 5). Reads only.

    uv run --no-sync python scripts/exploration/experiment_4_stress_pooled.py

The stress report gives one verdict per world, and one world is thin for the claimant groups. Here the frozen
estimators of the experiment score the stored features of the stress worlds in two pools: the seven that vary
the simulation without touching return timing, and the three in which honest customers return late. It prints
precision and the share of each gate group sent for review, beside the return-rate rule. Nothing is fitted or
written.
"""
from __future__ import annotations

from arai import contract, evaluation, experiment, modeling

RANKINGS = ("raw_return_rate", "hgb_leaf15", "hgb_leaf15_w6", "hgb_leaf15_w8", "hgb_leaf15_w6_s3", "hgb_leaf15_w8_s3")
POOLS = (("W5501-W5507: the simulation varied, return timing untouched", [f"W{s}" for s in range(5501, 5508)]),
         ("W5508, W5510, W5511: honest customers return late", ["W5508", "W5510", "W5511"]))


def main() -> None:
    out = modeling.experiment_dir(contract.experiment_id())
    legs = contract.segments()
    for title, worlds in POOLS:
        frame = experiment._frozen_rankings(out, evaluation.evaluation_frame(worlds))
        print(f"\n{title} ({len(frame)} eligible customers)")
        for name in RANKINGS:
            result = evaluation.confusion(frame, evaluation.select(frame, name))
            print(f"  {name:<18} precision {result['precision']:.4f}  "
                  + "  ".join(f"{leg[:14]} {result[leg + '_selected']}/{result[leg + '_size']}={result[leg + '_fpr']:.4f}" for leg in legs))


if __name__ == "__main__":
    main()
