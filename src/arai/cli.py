"""Command line: `arai generate` and `arai validate` (project-relative paths, final-spec component 15)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from arai.generator import generate_world, write_world
from arai.validation import validate_world


def _generate(args) -> int:
    for seed in args.seed:
        started = time.time()
        world = generate_world(seed, args.customers, abuse_enabled=not args.no_abuse)
        out = write_world(world, args.artifact_root, args.private_root)
        report = validate_world(out["operational"])
        print(f"{world.world_id}: {world.n_customers} customers, {world.summary['sales_order']} orders, "
              f"{world.summary['return_order_line']} return lines in {time.time() - started:.1f}s -> {out['operational']}")
        if not report.accepted:
            print(json.dumps(report.to_dict(), indent=2))
            return 1
    return 0


def _validate(args) -> int:
    report = validate_world(args.directory)
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.accepted else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="arai", description="ARAI synthetic worlds")
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="generate, write and validate one or more worlds")
    generate.add_argument("--seed", type=int, nargs="+", required=True, help="world seeds from contracts/experiment.yaml")
    generate.add_argument("--customers", type=int, default=None, help="override the world size (default: by seed purpose)")
    generate.add_argument("--no-abuse", action="store_true", help="base shopping and honest returns only (diagnostic)")
    generate.add_argument("--artifact-root", type=Path, default=None)
    generate.add_argument("--private-root", type=Path, default=None)
    generate.set_defaults(run=_generate)
    validate = commands.add_parser("validate", help="validate an operational world directory; nonzero exit on rejection")
    validate.add_argument("directory", type=Path)
    validate.set_defaults(run=_validate)
    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
