"""Lab 2: the data contract. A snapshot is accepted whole or rejected whole, and a rejection names the rule.

    uv run --no-sync python scripts/handson/lab2_validation.py

Writes a small world into a temporary folder, validates it, breaks it three ways and validates each. The temporary
folder is removed at the end; nothing under data/ is touched. See docs/implementation-hands-on.md, step 3.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pandas as pd

from arai.generator import generate_world, write_world
from arai.validation import validate_world


def _rewrite(directory: Path, table: str, change) -> None:
    """Change one CSV and bring its entry in the manifest up to date, as an honest exporter would."""
    path = directory / f"{table}.csv"
    frame = change(pd.read_csv(path, dtype=str, keep_default_na=False))
    frame.to_csv(path, index=False, lineterminator="\n")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"][table].update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), row_count=len(frame))
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _report(title: str, directory: Path) -> None:
    report = validate_world(directory)
    print(f"\n{title}\n  accepted: {report.accepted}")
    for violation in report.violations[:3]:
        print(f"  rule {violation['rule_id']} on {violation['table']}: {violation['message']} ({violation['count']} rows)")


def main() -> int:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        written = write_world(generate_world(9001), artifact_root=root / "artifacts", private_root=root / "private")
        directory = written["operational"]
        print(f"A generated world was written to a temporary folder: {sorted(p.name for p in directory.iterdir())}")
        _report("1. As generated", directory)

        original = {name: (directory / name).read_bytes() for name in ("sales_order_line.csv", "customer_master.csv", "manifest.json")}
        restore = lambda: [(directory / name).write_bytes(data) for name, data in original.items()]

        _rewrite(directory, "sales_order_line", lambda f: pd.concat([f, f.tail(1).assign(order_id="NO-SUCH-ORDER")]))
        _report("2. One sale line that points at an order which does not exist", directory)
        restore()

        _rewrite(directory, "customer_master", lambda f: f.assign(persona="Loyalist"))
        _report("3. A column the contract does not know (here: a private one)", directory)
        restore()

        (directory / "customer_master.csv").write_text(
            (directory / "customer_master.csv").read_text(encoding="utf-8").replace("unknown", "active", 1), encoding="utf-8", newline="")
        _report("4. A file changed after the manifest was written", directory)
        restore()

        _rewrite(directory, "customer_master", lambda f: f.drop(columns=["region", "email", "phone"]))
        _report("5. Without the optional contact columns (a snapshot from before data contract 1.2)", directory)
    print("\nThe rules are in src/arai/validation.py; the contract they read is final-spec/contracts/data-schema.yaml.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
