"""Check the community kind rule as revised by AM-66 against the first rule of decision D3, on worlds scored with the
active model bundle, and against the generator's relationship truth.

The first rule (AM-57) calls a community a `ring` when any edge has a coordinated claim match, two or more members
are selected for review, or a member has a coordinated claim share above zero. The revision (AM-66) keeps that rule
for communities where some edge shares a payment instrument, and asks more of the others, whose edges share only an
address and a device (the shape of a household): two or more coordinated claim matches, or two or more members
selected for review. This script scores each world with the active bundle (the model's real queue, not a proxy),
recomputes both rules from the scored communities, and tabulates each against the truth: `coordination` when two or
more members share a generated coordination group, else `household`, `shared_location` or `unrelated`. It also counts
communities called ring that hold no abuser at all. Truth is read here, offline, and never in scoring.

    uv run python scripts/community_rule_check.py --world W5201 W5202 W5203 W5204 W5205 W5401
"""
from __future__ import annotations

import argparse
import collections
import json

import pandas as pd

from arai import bundles, paths
from arai import features as F
from arai.operational import read_csv_world
from arai.service import scoring


def first_rule(edges: list, selected: int, matched: int, share_positive: bool) -> str:
    return "ring" if matched >= 1 or selected >= 2 or share_positive else "household"


def check_world(world_id: str, bundle) -> dict:
    tables, manifest = read_csv_world(paths.ARTIFACT_ROOT / "worlds" / world_id / "operational")
    output = scoring.score_snapshot(tables, manifest, bundle)
    private = paths.PRIVATE_TRUTH_ROOT / world_id
    relationship = pd.read_parquet(private / "relationship_truth.parquet").drop_duplicates(["group_id", "customer_id"])
    abusers = set(pd.read_parquet(private / "customer_truth.parquet").query("y_abuse == 1")["customer_id"])
    groups_of = relationship.groupby("customer_id").apply(lambda g: list(zip(g["group_type"], g["group_id"])), include_groups=False)
    customers = output.customers.set_index("customer_id")
    members_of = customers["community_id"].dropna().groupby(customers["community_id"].dropna()).apply(lambda s: list(s.index))
    if "coordinated_claim_share" in output.customers:
        share = output.customers.set_index("customer_id")["coordinated_claim_share"]
    else:                                                         # the scored output keeps no feature columns: recompute them
        features = F.compute_features(tables, scoring.cutoff_date(manifest), bundle.reference).features
        share = features.set_index("customer_id")["coordinated_claim_share"]
    confusion = {"first": collections.Counter(), "revised": collections.Counter()}
    no_abuser_rings = {"first": 0, "revised": 0}
    changed = []
    for row in output.communities.itertuples(index=False):
        members = members_of[row.community_id]
        edges = json.loads(row.edges)
        positive = bool(share is not None and (share.reindex(members).fillna(0) > 0).any())
        kinds = {"first": first_rule(edges, row.selected_count, row.coordinated_claim_matches, positive), "revised": row.kind}
        counts = collections.Counter(pair for member in members for pair in groups_of.get(member, []))
        shared = {kind for (kind, _), n in counts.items() if n >= 2}
        truth_kind = ("coordination" if "coordination" in shared else "household" if "household" in shared
                      else "shared_location" if shared else "unrelated")
        for rule, kind in kinds.items():
            confusion[rule][(kind, truth_kind)] += 1
            no_abuser_rings[rule] += kind == "ring" and not (set(members) & abusers)
        if kinds["first"] != kinds["revised"]:
            changed.append({"community": row.community_id, "size": int(row.size), "selected": int(row.selected_count),
                            "matches": int(row.coordinated_claim_matches), "truth": truth_kind,
                            "abusers": len(set(members) & abusers), "types": sorted({t for e in edges for t in e["types"]})})
    return {"world_id": world_id, "communities": int(len(output.communities)), "selected": int(customers["selected_for_review"].sum()),
            "confusion": {rule: {f"{k} | {t}": n for (k, t), n in sorted(c.items())} for rule, c in confusion.items()},
            "rings_without_an_abuser": no_abuser_rings, "changed_by_the_revision": changed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--world", nargs="+", default=["W5201", "W5202", "W5203", "W5204", "W5205", "W5401"])
    args = parser.parse_args()
    pointer = bundles.read_active(paths.ARTIFACT_ROOT)
    bundle = bundles.load_bundle(pointer["model_id"], paths.ARTIFACT_ROOT)
    reports = [check_world(world, bundle) for world in args.world]
    print(json.dumps(reports, indent=2))
    totals = {"first": collections.Counter(), "revised": collections.Counter()}
    for report in reports:
        for rule in totals:
            totals[rule].update(report["confusion"][rule])
    for rule, total in totals.items():
        print(f"\n{rule} rule, pooled:", dict(sorted(total.items())))
        print(f"  rings without an abuser: {sum(r['rings_without_an_abuser'][rule] for r in reports)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
