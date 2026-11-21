"""Check the community kind rule (frontend data plan WP1, decision D3) against the generator's relationship truth.

The rule at scoring time reads observed evidence only: an edge with a coordinated claim match, two or more members
selected for review, or a member with a coordinated claim share above zero makes a community a `ring`; otherwise it is
a `household`. This script generates training worlds, scores them with the baseline ranking (the rule's "selected"
input is the top 5% of the raw return rate, so no bundle is needed), groups the supported edges exactly as
`arai.service.scoring._communities` does, and tabulates the kind against the private truth: a community is
`coordination` when two or more members share a generated coordination group, else `household` or `shared_location`
when they share one of those, else `unrelated`. Truth is read here, offline, and nowhere in scoring.

    uv run python scripts/community_check.py --seed 5101 5102
"""
from __future__ import annotations

import argparse
import collections
import json


from arai import features as F
from arai import ranking
from arai.generator import generate_world
from arai.service import scoring


def check_world(seed: int) -> dict:
    world = generate_world(seed)
    reference = F.fit_reference([(world.tables, world.snapshot_date)])
    result = F.compute_features(world.tables, world.snapshot_date, reference)
    customers = result.features.sort_values("customer_id").reset_index(drop=True)
    eligible = customers["eligible"].to_numpy(dtype=bool)
    ids, rates = customers.loc[eligible, "customer_id"].to_numpy(), customers.loc[eligible, "raw_return_rate"].to_numpy()
    k = ranking.budget(int(eligible.sum()))
    rank = ranking.rank_world(world.world_id, ids, rates)
    customers["selected_for_review"] = False
    customers.loc[eligible, "selected_for_review"] = rank <= k
    neighbors = scoring._neighbors(result)
    communities, membership = scoring._communities(world.world_id, result.graph.edges, neighbors, customers)

    truth = world.truth["relationship_truth"].drop_duplicates(["group_id", "customer_id"])
    groups_of = truth.groupby("customer_id").apply(lambda g: list(zip(g["group_type"], g["group_id"])), include_groups=False)
    members_of = membership.dropna().groupby(membership.dropna()).apply(lambda s: list(s.index))
    confusion = collections.Counter()
    for row in communities.itertuples(index=False):
        counts = collections.Counter(pair for member in members_of[row.community_id] for pair in groups_of.get(member, []))
        shared = {kind for (kind, _), n in counts.items() if n >= 2}
        truth_kind = ("coordination" if "coordination" in shared else "household" if "household" in shared
                      else "shared_location" if shared else "unrelated")
        confusion[(row.kind, truth_kind)] += 1
    coordination_groups = truth.loc[truth["group_type"] == "coordination", "group_id"].nunique()
    found = sum(n for (kind, t), n in confusion.items() if t == "coordination")
    return {"world_id": world.world_id, "customers": len(customers), "edges": len(result.graph.edges),
            "communities": len(communities), "methods": communities["method"].value_counts().to_dict(),
            "sizes": {int(size): int(n) for size, n in communities["size"].value_counts().sort_index().items()},
            "coordination_groups_generated": int(coordination_groups), "communities_with_a_coordination_pair": int(found),
            "confusion": {f"{kind} | {t}": int(n) for (kind, t), n in sorted(confusion.items())}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--seed", type=int, nargs="+", default=[5101, 5102])
    args = parser.parse_args()
    reports = [check_world(seed) for seed in args.seed]
    print(json.dumps(reports, indent=2))
    total = collections.Counter()
    for report in reports:
        total.update(report["confusion"])
    rings = {key: n for key, n in total.items() if key.startswith("ring")}
    households = {key: n for key, n in total.items() if key.startswith("household")}
    print("\nrule says ring:     ", dict(sorted(rings.items())))
    print("rule says household:", dict(sorted(households.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
