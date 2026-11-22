"""Lab 3: from seven tables to one row per customer. Features, eligibility and why a return rate is not enough.

    uv run --no-sync python scripts/handson/lab3_features.py                     # 1,000 customers, a few seconds
    uv run --no-sync python scripts/handson/lab3_features.py --customers 10000   # full size, about half a minute

Generates a world in memory and computes its features. The truth is read at the end only, to show what a ranking by
return rate finds; the features themselves never read it. See docs/implementation-hands-on.md, steps 4 and 5.
"""
from __future__ import annotations

import argparse

import yaml

from arai import features as F
from arai import ranking
from arai.generator import generate_world
from arai.paths import SPEC_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=9001)
    parser.add_argument("--customers", type=int, default=None, help="world size (default 1,000 for a seed outside the contract)")
    args = parser.parse_args()
    world = generate_world(args.seed, args.customers)
    result = F.compute_features(world.tables, world.snapshot_date)
    features = result.features

    contract = yaml.safe_load((SPEC_ROOT / "contracts" / "features.yaml").read_text(encoding="utf-8"))
    model_inputs = [f["name"] for f in contract["ordered_features"]]
    evidence_only = [f["name"] for f in contract["evidence_only"]["features"]]
    print(f"World {world.world_id}: {len(features)} customers, one row each, {features.shape[1]} columns.")
    print(f"  {len(model_inputs)} of them are model inputs, in the order of final-spec/contracts/features.yaml:")
    print("    " + ", ".join(model_inputs[:8]) + ", ...")
    print(f"  {len(evidence_only)} are evidence only, shown to the analyst and never given to the model: {', '.join(evidence_only)}")
    assert all(name in features.columns for name in model_inputs)

    eligible = features[features["eligible"]]
    print(f"\nELIGIBILITY: {len(eligible)} of {len(features)} customers have at least {F.ELIGIBLE_MIN_LINES} mature sale lines and are ranked.")
    print("  The others are 'insufficient history': not ranked, and never treated as low risk.")

    one = eligible.sort_values("residual_z", ascending=False).iloc[0]
    print(f"\nONE CUSTOMER, {one['customer_id']}, the one furthest above what their basket predicts:")
    for name in ("mature_sale_lines", "raw_return_rate", "expected_return_rate", "residual_z", "claim_lines", "late_return_lines"):
        value = one[name]
        print(f"  {name:<22} {value:.3f}" if isinstance(value, float) else f"  {name:<22} {value}")
    print("  raw_return_rate is what they returned; expected_return_rate is what buyers of the same products return.")

    print(f"\nRELATIONSHIPS: {len(result.graph.edges)} pairs of accounts share at least two of address, device and payment method.")

    # ---- the question the whole project answers: is the return rate a good way to choose whom to review?
    truth = world.truth["customer_truth"].set_index("customer_id")["y_abuse"]
    k = ranking.budget(len(eligible))
    by_rate = eligible.sort_values("raw_return_rate", ascending=False).head(k)
    hits = int(truth.loc[by_rate["customer_id"]].sum())
    base = float(truth.loc[eligible["customer_id"]].mean())
    print(f"\nTHE RETURN-RATE RULE on this world (truth read here only, to keep score):")
    print(f"  review budget: {k} customers, 5% of the {len(eligible)} ranked")
    print(f"  abusers among the {k} with the highest return rate: {hits} ({hits / k:.0%})")
    print(f"  abusers among all ranked customers: {base:.1%}")
    print("  So most customers the rule sends for review are honest heavy returners. Step 6 shows what the model does instead.")
    if world.n_customers < 5000:
        print("  (A 1,000-customer world is small: rerun with --customers 10000 for steadier numbers.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
