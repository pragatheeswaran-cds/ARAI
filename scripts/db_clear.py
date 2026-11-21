"""Clear the demo state of an ARAI database reached through DATABASE_URL: notes, runs with their results, datasets.

The embedded instances of `arai local` and `arai baseline-rehearsal` have `arai db-clean` for this; this script is
for every other database: the Docker Compose stack, the demonstration VM, a PostgreSQL named in .env. Models, the
active pointer, the experiment report, people and sessions always stay. Nothing is removed without --yes.

    uv run --no-sync python scripts/db_clear.py                      # report what the database holds (reads .env)
    uv run --no-sync python scripts/db_clear.py --all --dry-run      # what --all would remove
    uv run --no-sync python scripts/db_clear.py --all --yes          # notes, runs and datasets, with the dataset files
    uv run --no-sync python scripts/db_clear.py --runs --world W7001N300 --yes

Inside the Compose stack or on the VM (the container has the package, DATABASE_URL and ARTIFACT_ROOT; the script is
fed on stdin because the image carries only src/):

    docker compose exec -T api uv run --no-sync python - --all --yes < scripts/db_clear.py
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path


def load_dotenv(path: Path) -> None:
    """DATABASE_URL and ARTIFACT_ROOT from .env when the environment does not set them (never overrides)."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--notes", action="store_true", help="remove review notes")
    parser.add_argument("--runs", action="store_true", help="remove runs with their results, memos and the notes written under them")
    parser.add_argument("--datasets", action="store_true", help="remove registered datasets no run refers to, with their files")
    parser.add_argument("--all", action="store_true", help="notes, runs and datasets")
    parser.add_argument("--world", default=None, help="only this world's notes, runs and datasets, e.g. W7001N300")
    parser.add_argument("--dry-run", action="store_true", help="report what would be removed")
    parser.add_argument("--yes", action="store_true", help="actually do it")
    args = parser.parse_args()

    here = Path(globals().get("__file__", "")).resolve()
    load_dotenv(here.parents[1] / ".env" if here.is_file() else Path(".env"))         # fed on stdin: the working directory's .env
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set (environment or .env).")
        return 2
    from arai.service.store import Store
    artifact_root = Path(os.environ.get("ARTIFACT_ROOT", "data/artifacts"))
    store = Store(url)
    before = store.counts()
    host = url.split("@")[-1].split("?")[0]
    print(f"database {host}: datasets {before['datasets']} {before['worlds']}, runs {before['runs']}, result rows {before['result_rows']}, "
          f"notes {before['reviews']}, memos {before['run_memos']}; models {before['models']} and experiments {before['experiments']} stay")

    wants = {"notes": args.notes or args.all, "runs": args.runs or args.all, "datasets": args.datasets or args.all}
    if not any(wants.values()):
        print("Nothing chosen: pass --notes, --runs, --datasets or --all (add --dry-run to look first).")
        return 0
    print("remove:", ", ".join(name for name, on in wants.items() if on) + (f" of world {args.world}" if args.world else ""))
    if wants["runs"] and not wants["notes"]:
        print("(the notes written under the removed runs go with them)")
    if wants["datasets"] and not wants["runs"]:
        print("(only datasets no run was scored on; add --runs to remove scored ones)")
    if args.dry_run or not args.yes:
        print("Dry run; add --yes to do it." if not args.yes else "Dry run.")
        return 0

    removed = store.wipe(notes=wants["notes"], runs=wants["runs"], datasets=wants["datasets"], world_id=args.world)
    for dataset in removed["datasets"]:
        shutil.rmtree(artifact_root / dataset["artifact_key"], ignore_errors=True)
    after = store.counts()
    print(f"removed: notes {removed['reviews']}, runs {removed['runs']} ({removed['result_rows']} result rows, {removed['memos']} memos), "
          f"datasets {len(removed['datasets'])} {[d['world_id'] for d in removed['datasets']]}, stale idempotency records {removed['idempotency']}")
    print(f"now: datasets {after['datasets']}, runs {after['runs']}, notes {after['reviews']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
