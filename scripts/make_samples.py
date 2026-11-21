"""Write the small sample snapshots under samples/ (see samples/README.md): the files a visitor uploads to try ARAI.

Everything is regenerated from the seeds, so the folders are reproducible and carry no private truth: the generator's
truth tables go to a temporary folder that is deleted before this script returns. Running it again rewrites the same
bytes.

    uv run --no-sync python scripts/make_samples.py              # writes samples/01-... to samples/05-...
    uv run --no-sync python scripts/make_samples.py --check      # validates each folder instead (4 accepted, 1 rejected)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"

# name, seed, customers (None: the fixture default of 1,000), abuse on, earlier cutoff (None: the world's own)
VARIANTS = [
    ("01-ordinary-300", 7001, 300, True, None),
    ("02-honest-only-300", 7002, 300, False, None),
    ("03-history-1000-june", 7004, None, True, date(2026, 6, 9)),
    ("04-history-1000-september", 7004, None, True, None),
]
REJECTED = ("05-rejected-orphan-line", "01-ordinary-300")      # a copy of the ordinary world with one sales order removed


def write_variants(work: Path) -> None:
    from arai import snapshots
    from arai.generator.world import generate_world, write_world
    artifact_root, private_root = work / "artifacts", work / "private"
    for name, seed, customers, abuse, as_of in VARIANTS:
        if as_of is None:
            world = generate_world(seed, customers, abuse_enabled=abuse)
            out = write_world(world, artifact_root, private_root)
        else:
            world = snapshots.build_earlier(f"W{seed}", as_of)
            out = snapshots.write_earlier(world, as_of, artifact_root, private_root)
        target = SAMPLES / name
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(out["operational"], target)
        print(f"{name}: world {world.world_id}, {len(world.tables['customer_master'])} customers -> {target.relative_to(ROOT)}")


def write_rejected() -> None:
    """The ordinary world minus its last sales order, with the manifest kept truthful about the file it describes.

    The order's lines still reference it, so validation refuses the snapshot with the referential rule (F001) and the
    page shows how a rejection reads. Nothing is stored for a rejected snapshot."""
    name, source = REJECTED
    target = SAMPLES / name
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(SAMPLES / source, target)
    orders = target / "sales_order.csv"
    lines = orders.read_bytes().splitlines(keepends=True)
    orders.write_bytes(b"".join(lines[:-1]))
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"]["sales_order"]["sha256"] = hashlib.sha256(orders.read_bytes()).hexdigest()
    manifest["files"]["sales_order"]["row_count"] = len(lines) - 2            # header and the removed order
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{name}: {source} without its last sales order (one orphan line) -> {target.relative_to(ROOT)}")


def check() -> int:
    from arai.validation import validate_world
    failures = 0
    for folder in sorted(p for p in SAMPLES.iterdir() if p.is_dir()):
        report = validate_world(folder)
        expected = folder.name != REJECTED[0]
        rules = sorted({v["rule_id"] for v in report.to_dict()["violations"]})
        ok = report.accepted == expected and (expected or rules == ["F001"])
        failures += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {folder.name}: {'accepted' if report.accepted else 'rejected ' + ','.join(rules)}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="validate the folders that exist instead of writing them")
    args = parser.parse_args()
    if args.check:
        return check()
    SAMPLES.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="arai-samples-") as work:
        write_variants(Path(work))
    write_rejected()
    return check()


if __name__ == "__main__":
    sys.exit(main())
