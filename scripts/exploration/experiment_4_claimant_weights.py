"""Reproduce the exploration of training weights on both honest claimant groups (decision AM-53). Reads only.

    uv run --no-sync python scripts/exploration/experiment_4_claimant_weights.py            # the registered weights
    uv run --no-sync python scripts/exploration/experiment_4_claimant_weights.py --all      # every weight explored

Boosted trees with the settings of the registered candidates are fitted out of fold on the ten training worlds
of experiment 2 (generator-config 1.3) and of experiment 3 (generator-config 3.0) in data/artifacts, with a
training weight on honest repeat genuine claimants and on honest customers with one genuine failure. For each
pair of weights it prints the precision at the review budget and the share of each gate group sent for review,
beside the return-rate rule. Each fit takes a few minutes. Nothing is written.
"""
from __future__ import annotations

import argparse

from arai import contract, evaluation, modeling, paths

ARTIFACTS, PRIVATE = paths.REPO_ROOT / "data" / "artifacts", paths.REPO_ROOT / "data" / "private"
REGISTERED = [(0, 0), (4, 0), (6, 0), (8, 0), (6, 2), (6, 3), (8, 3)]
EXPLORED = [(0, 0), (6, 0), (6, 2), (6, 3), (6, 4), (6, 6), (4, 2), (4, 4), (8, 3), (8, 4), (3, 3)]
SETS = (("generator-config 1.3, W3101-W3110", range(3101, 3111)), ("generator-config 3.0, W4101-W4110", range(4101, 4111)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--all", action="store_true", help="every pair of weights explored, not only the registered ones")
    args = parser.parse_args()
    legs = contract.segments()
    template = next(c for c in modeling.candidates() if c.id == "hgb_leaf15")
    for title, seeds in SETS:
        worlds = [f"W{s}" for s in seeds]
        frame = evaluation.evaluation_frame(worlds, ARTIFACTS, PRIVATE)
        folds = modeling.fold_map(worlds)
        rule = evaluation.confusion(frame, evaluation.select(frame, "raw_return_rate"))
        print(f"\n{title}: {len(frame)} eligible customers; " + ", ".join(f"{leg} {rule[leg + '_size']}" for leg in legs))
        print(f"  {'rule':<22} precision {rule['precision']:.4f}  " + "  ".join(f"{leg[:12]} {rule[leg + '_fpr']:.4f}" for leg in legs))
        for repeat, single in (EXPLORED if args.all else REGISTERED):
            weights = {name: weight for name, weight in (("repeat_genuine_claimant", repeat), ("one_genuine_failure", single)) if weight}
            candidate = modeling.Candidate(f"repeat {repeat}, one failure {single}", 1, template.family, True, dict(template.params),
                                           honest_group_weights=weights)
            scores, _ = modeling.out_of_fold(candidate, frame, folds)
            result = evaluation.confusion(frame.assign(_score=scores), evaluation.select(frame.assign(_score=scores), "_score"))
            met = sum(result[leg + "_fpr"] <= rule[leg + "_fpr"] for leg in legs)
            print(f"  {candidate.id:<22} precision {result['precision']:.4f}  " + "  ".join(f"{leg[:12]} {result[leg + '_fpr']:.4f}" for leg in legs)
                  + f"  legs met {met} of {len(legs)}", flush=True)


if __name__ == "__main__":
    main()
