"""Package the current experiment's data folder as one archive for team members.

    uv run --no-sync python scripts/package_team_data.py                # writes data/exports/ARAI-data-<experiment>-<date>.zip
    uv run --no-sync python scripts/package_team_data.py --no-database  # without the local demo database

The archive holds data/<experiment>/artifacts (worlds, features, the experiment's records, the published bundles, the
registered snapshots), data/<experiment>/private (the simulation's truth, needed to verify the experiment) and, unless
left out, data/<experiment>/postgres (the local demo database with what is loaded in it). Paths inside the archive start
at data/, so it is unpacked in the repository root. Stop `arai local` first: a running database cannot be copied.

Everything in it is simulated. The private folder is the truth the product itself never reads; it is included because a
team member needs it to check the experiment (scripts/verify_experiment.py) and to keep score in the labs.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

from arai import contract, paths

SKIP_NAMES = {"postmaster.pid", "postmaster.opts", ".handle_pids.json"}      # belong to one running server on one machine
SKIP_PARTS = {"__pycache__", "pg_stat_tmp"}

README = """ARAI data for the team: {experiment}
Packaged {today} from commit {commit} of https://github.com/pragatheeswaran-cds/ARAI (branch main).

WHAT THIS IS
  The data folder of experiment {experiment}. It is not in git. Everything in it is simulated: no real
  customer, order or return appears anywhere, every email address is at example.com and no phone number is a real one.

HOW TO USE IT
  1. Clone the repository and check out main (docs/implementation-hands-on.md, step 0).
  2. Unpack this archive in the repository root, so that this folder exists:
         data\\{experiment}\\artifacts\\bundles
  3. Check it (reads only, about three minutes, should end with ALL CHECKS PASSED):
         uv run --no-sync python scripts\\verify_experiment.py --skip-earlier
     (--skip-earlier leaves out the data of experiments 1 to 3, which is not in this archive.)
  4. Start the product:  uv run arai local   then open http://127.0.0.1:8000

WHAT IS INSIDE
  data\\{experiment}\\artifacts   {artifact_files} files
      worlds        the generated worlds: training, validation, test, stress, the demonstration world W5401 with its
                    eleven earlier monthly snapshots, and W5601N10000, an example world that carries contact details
      features      the frozen features of the training, validation and test worlds
      experiments   the experiment's records: candidates, dry run, selection, the final test, the published report
      bundles       the published model and the return-rate baseline
      active        which bundle is served
      datasets      the snapshots registered in the demo database
  data\\{experiment}\\private     {private_files} files
      the simulation's truth (who abused returns, which claims were genuine). The product never reads this folder.
      It is here so that you can verify the experiment and keep score in the labs. Do not upload it anywhere.
{database_section}
RULES (docs/implementation-hands-on.md, step 0)
  - The final test ran once. Do not run arai test, select, train or publish, and do not generate a world from a
    seed of the contract (5101 to 5511). Use seeds from 9001 up for your own worlds.
  - The truth never reaches the product.
  - src/arai/features.py, dataset.py, modeling.py, bundles.py and ranking.py are locked to the published model.
"""
DATABASE = """  data\\{experiment}\\postgres    {database_files} files
      the local demo database as it stood when this was packaged. Prepared for a demonstration it holds W5401 with
      its twelve monthly snapshots scored, every case of the latest snapshot still Open, and the three August review
      outcomes the demonstration tells (written by scripts\history_demo.py). It was written by PostgreSQL on Windows
      and opens on Windows with the versions in uv.lock. On macOS or Linux, or if the product does not start, delete this folder: arai local then
      creates an empty database, and
          uv run --no-sync python scripts\\history_demo.py --load
      loads the twelve snapshots again in about fifteen minutes (RUNBOOK.md, section 4.1).
"""
NO_DATABASE = """  (no database: arai local creates an empty one on first start. Load the demonstration with
      uv run --no-sync python scripts\\history_demo.py --load      about fifteen minutes; RUNBOOK.md, section 4.1)
"""


def _files(folder: Path) -> list:
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.name not in SKIP_NAMES and not SKIP_PARTS & set(p.parts)
                  and not any(part.startswith(".incoming-") for part in p.parts))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-database", action="store_true", help="leave out the local demo database")
    parser.add_argument("--out", type=Path, default=None, help="archive path (default: data/exports/ARAI-data-<experiment>-<date>.zip)")
    args = parser.parse_args()

    experiment = contract.experiment_id()
    if (paths.POSTGRES_DIR / "postmaster.pid").is_file() and not args.no_database:
        print("The local database is running (postmaster.pid exists). Stop `arai local` first, or pass --no-database.")
        return 1
    parts = {"artifacts": _files(paths.ARTIFACT_ROOT), "private": _files(paths.PRIVATE_TRUTH_ROOT),
             "postgres": [] if args.no_database else _files(paths.POSTGRES_DIR)}
    if not parts["artifacts"] or not (paths.ARTIFACT_ROOT / "bundles").is_dir():
        print(f"{paths.ARTIFACT_ROOT} has no published bundles: nothing to package.")
        return 1
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=paths.REPO_ROOT, capture_output=True, text=True, check=False).stdout.strip()
    today = date.today().isoformat()
    out = args.out or paths.REPO_ROOT / "data" / "exports" / f"ARAI-data-{experiment}-{today}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    section = NO_DATABASE if args.no_database else DATABASE.format(experiment=experiment, database_files=len(parts["postgres"]))
    readme = README.format(experiment=experiment, today=today, commit=commit or "unknown", artifact_files=len(parts["artifacts"]),
                           private_files=len(parts["private"]), database_section=section)
    total = sum(len(files) for files in parts.values())
    done, size = 0, 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        archive.writestr("README-ARAI-DATA.txt", readme)
        if not args.no_database:
            # PostgreSQL will not start without its directories, and several of them are empty: store every one of them
            for folder in sorted(p for p in paths.POSTGRES_DIR.rglob("*") if p.is_dir()):
                archive.writestr(zipfile.ZipInfo(folder.relative_to(paths.REPO_ROOT).as_posix() + "/"), "")
        for files in parts.values():
            for path in files:
                archive.write(path, path.relative_to(paths.REPO_ROOT).as_posix())
                size += path.stat().st_size
                done += 1
                if done % 500 == 0:
                    print(f"  {done} of {total} files", flush=True)
    print(f"{out}: {total} files, {size / 1e9:.2f} GB before compression, {out.stat().st_size / 1e9:.2f} GB in the archive")
    return 0


if __name__ == "__main__":
    sys.exit(main())
