"""Lab 4: scoring a snapshot with the published model, exactly as the service does, and keeping score with the truth.

    uv run --no-sync python scripts/handson/lab4_scoring.py                     # 10,000 customers, about a minute
    uv run --no-sync python scripts/handson/lab4_scoring.py --customers 1000    # quicker, noisier

Needs the experiment's data folder (data/EXP-20261005-04/artifacts with the published bundles): see step 0 of
docs/implementation-hands-on.md. The world is generated in memory from a seed no experiment has used, so this is new
data to the model. Nothing is written to disk. See docs/implementation-hands-on.md, steps 6, 7 and 11.
"""
from __future__ import annotations

import argparse

from arai import bundles, ranking
from arai.generator import generate_world
from arai.service import scoring


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=9001)
    parser.add_argument("--customers", type=int, default=10000)
    args = parser.parse_args()

    bundle = bundles.resolve_active()
    print(f"Active bundle: {bundle.model_id} ({bundle.kind}), {len(bundle.feature_order)} model inputs, from experiment "
          f"{bundle.manifest.get('experiment_id', 'unknown')}")
    world = generate_world(args.seed, args.customers)
    manifest = {"world_id": world.world_id, "cutoff": world.context.s.cutoff.isoformat()}
    output = scoring.score_snapshot(world.tables, manifest, bundle)
    customers, summary = output.customers, output.summary
    print(f"\nScored {world.world_id}: {summary['eligible_count']} ranked, {summary['excluded_count']} with insufficient history, "
          f"{summary['selected_count']} selected for review (budget {summary['review_budget_k']}).")

    queue = customers[customers["selected_for_review"]].sort_values("rank")
    print("\nTHE TOP OF THE QUEUE (what the Risk Queue shows):")
    for row in queue.head(5).itertuples():
        print(f"  rank {int(row.rank):>3}  {row.customer_id}  score {row.risk_score:5.1f}  rule's rank {int(row.baseline_rank):>4}  tags: {row.evidence_tags or 'none'}")
    print("  The score is a percentile against the training worlds, not a probability.")

    # ---- keeping score: the truth is joined here, after every score exists
    truth = world.truth["customer_truth"].set_index("customer_id")["y_abuse"]
    k = summary["review_budget_k"]
    model_hits = int(truth.loc[queue["customer_id"]].sum())
    rule_hits = int(truth.loc[customers[customers["baseline_selected"]]["customer_id"]].sum())
    print(f"\nKEEPING SCORE on this world, same budget of {k} for both:")
    print(f"  the model's queue holds {model_hits} abusers ({model_hits / k:.0%})")
    print(f"  the return-rate rule's queue holds {rule_hits} abusers ({rule_hits / k:.0%})")
    print("  The published result is the same comparison on five sealed test worlds: 76.6% against 21.8%.")
    assert k == ranking.budget(summary["eligible_count"])

    # ---- step 11: contact details change what is shown, never a score
    tables = dict(world.tables, customer_master=world.tables["customer_master"].drop(columns=["region", "email", "phone"]))
    without = scoring.score_snapshot(tables, manifest, bundle)
    same = (customers.set_index("customer_id")["raw_score"].fillna(-1) == without.customers.set_index("customer_id")["raw_score"].fillna(-1)).all()
    print(f"\nCONTACT DETAILS: scored again without phone, email and region. Every score identical: {same}.")
    print(f"  Links shown to the analyst with them: {summary['graph_edges']}; without them: {without.summary['graph_edges']}.")
    print(f"  Groups of linked accounts: {summary['community_count']} (rings: {summary['ring_count']}) against "
          f"{without.summary['community_count']} (rings: {without.summary['ring_count']}).")
    print("  The model reads the three order identifiers only; phone and mailbox links are evidence for the analyst.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
