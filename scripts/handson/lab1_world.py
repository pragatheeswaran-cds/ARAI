"""Lab 1: a synthetic world, and the line between what the product sees and what only the simulator knows.

    uv run --no-sync python scripts/handson/lab1_world.py              # 1,000 customers, about 3 seconds
    uv run --no-sync python scripts/handson/lab1_world.py --seed 9002  # another world

Nothing is written to disk: the world is generated in memory. See docs/implementation-hands-on.md, step 2.
"""
from __future__ import annotations

import argparse

from arai.generator import generate_world


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=9001, help="any seed no experiment uses (9001 and up)")
    args = parser.parse_args()
    world = generate_world(args.seed)

    print(f"World {world.world_id}: {world.n_customers} customers, snapshot date {world.snapshot_date}\n")
    print("OPERATIONAL TABLES: what a retailer would export, and all the product ever reads")
    for name, table in world.tables.items():
        print(f"  {name:<20} {len(table):>7} rows   columns: {', '.join(table.columns[:6])}{', ...' if len(table.columns) > 6 else ''}")

    print("\nPRIVATE TRUTH: what the simulator knows and the product never sees")
    for name, table in world.truth.items():
        print(f"  {name:<20} {len(table):>7} rows")

    truth = world.truth["customer_truth"]
    abusers = int(truth["y_abuse"].sum())
    print(f"\n{abusers} of {len(truth)} customers abused returns at least once ({abusers / len(truth):.1%}).")
    print("That column, y_abuse, is in the truth tables only. No operational table carries it.")
    assert "y_abuse" not in {column for table in world.tables.values() for column in table.columns}

    # one abuser's story, from the operational tables alone
    customer = truth.loc[truth["y_abuse"] == 1, "customer_id"].iloc[0]
    orders = world.tables["sales_order"].query("customer_id == @customer")
    returns = world.tables["return_order_line"].merge(orders[["order_id"]], on="order_id")
    print(f"\nOne abuser, {customer}, as the product sees them: {len(orders)} orders, {len(returns)} return lines.")
    print(returns.groupby("reason_code").size().sort_values(ascending=False).head(5).to_string())
    print("\nTry: run it again with the same seed (the same world, byte for byte) and with another seed (a different one).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
