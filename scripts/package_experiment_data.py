"""Package the synthetic data of one finished experiment for sharing: data, the configuration that produced it, and its truth.

    uv run python scripts/package_experiment_data.py --experiment EXP-20261005-02 --guide docs/experiment-2-data-guide.md
    uv run python scripts/package_experiment_data.py --experiment EXP-20261005-04 --guide docs/experiment-4-data-guide.md

It reads the experiment's own records to find its worlds and the commit of its contract, checks every file it
packs against the hashes recorded when the world was written, and writes zip files under data/exports/<experiment>/
(ignored by git). Operational data and private truth go into separate archives: truth is what the simulation
knows and a model must never see, so it should never sit beside the tables a model reads.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS, PRIVATE = ROOT / "data" / "artifacts", ROOT / "data" / "private"
TABLES = ("customer_master", "sku_master", "reason_code", "sales_order", "sales_order_line", "return_order", "return_order_line")
CONFIG_PATHS = ("final-spec/contracts", "final-spec/assets", "final-spec/components", "final-spec/DECISIONS.md", "final-spec/README.md",
                "src/arai/settings.py", "src/arai/catalog.py", "src/arai/rng.py", "src/arai/generator", "pyproject.toml", "uv.lock",
                ".python-version")
ACTIONS = ("deceptive_nonreceipt_claim", "deceptive_contents_claim", "temporary_use_return")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def worlds_of(experiment: Path) -> dict:
    """{world_id: role} from the experiment's own records, never from the contract now in the repository."""
    load = lambda name: json.loads((experiment / name).read_text(encoding="utf-8"))  # noqa: E731
    roles = {w: "train" for w in load("config.json")["training_worlds"]}
    roles |= {w: "validation" for w in load("selection.json")["validation_worlds"]}
    roles |= {w: "test" for w in load("reports/test.json")["worlds"]}
    if (experiment / "reports" / "stress.json").is_file():
        roles |= {w["world_id"]: "stress" for w in load("reports/stress.json")["worlds"]}
    truth = experiment / "published" / "truth.parquet"
    if truth.is_file():
        roles[str(pd.read_parquet(truth, columns=["world_id"])["world_id"].iloc[0])] = "demo"
    return roles


def verify_world(world_id: str) -> dict:
    """Check the operational files and the truth files against their manifests; return the operational manifest."""
    base = ARTIFACTS / "worlds" / world_id
    manifest = json.loads((base / "operational" / "manifest.json").read_text(encoding="utf-8"))
    for name in TABLES:
        if sha256(base / "operational" / f"{name}.csv") != manifest["files"][name]["sha256"]:
            raise SystemExit(f"{world_id}: {name}.csv differs from its manifest; not packaged")
    private = json.loads((PRIVATE / world_id / "private-manifest.json").read_text(encoding="utf-8"))
    if private["operational_manifest_sha256"] != sha256(base / "operational" / "manifest.json"):
        raise SystemExit(f"{world_id}: the truth on disk was not written with this world; not packaged")
    for name, entry in private["files"].items():
        if sha256(PRIVATE / world_id / entry["filename"]) != entry["sha256"]:
            raise SystemExit(f"{world_id}: truth table {name} differs from its manifest; not packaged")
    return manifest


def summarise(world_id: str, role: str, manifest: dict) -> dict:
    """One row of WORLDS.csv: what the world holds and what is true in it."""
    counts = {name: manifest["files"][name]["row_count"] for name in TABLES}
    truth = pd.read_parquet(PRIVATE / world_id / "customer_truth.parquet")
    actions = pd.read_parquet(PRIVATE / world_id / "action_truth.parquet")
    products = pd.read_parquet(PRIVATE / world_id / "product_truth.parquet")
    row = {"world_id": world_id, "role": role, "seed": manifest["generator"]["seed"], "cutoff": manifest["cutoff"],
           "customers": counts["customer_master"], "orders": counts["sales_order"], "sale_lines": counts["sales_order_line"],
           "return_requests": counts["return_order"], "return_lines": counts["return_order_line"],
           "abusers_y_abuse_1": int(truth["y_abuse"].sum()), **{f"customers_with_{a}": int(truth[a].sum()) for a in ACTIONS},
           "customers_with_coordinated_action": int(truth["coordinated_action_flag"].sum()),
           "completed_abusive_actions": int(actions["completed_action"].sum()),
           "household_members": int(truth["household_id"].notna().sum()),
           "coordination_group_members": int(truth["coordination_group_id"].notna().sum()),
           "defect_prone_styles": int((products["defect_state"] == "defect_prone").sum()),
           "targeted_styles": int(products["targeted"].sum())}
    features = ARTIFACTS / "features" / world_id / "features.parquet"
    if features.is_file():
        frame = pd.read_parquet(features, columns=["customer_id", "eligible"]).merge(truth[["customer_id", "y_abuse"]], on="customer_id")
        row |= {"eligible_customers": int(frame["eligible"].sum()), "eligible_abusers": int(frame.loc[frame["eligible"], "y_abuse"].sum())}
    row |= {"generator_code_sha256": manifest["generator"]["code_sha256"], "generator_config_sha256": manifest["generator"]["config_sha256"]}
    return row


def extract_configuration(commit: str, target: Path) -> None:
    """The contracts, assets, component specifications and generator code exactly as they were at the experiment's commit."""
    listing = git("ls-tree", "-r", "--name-only", commit, "--", *CONFIG_PATHS).decode().splitlines()
    for name in listing:
        if name.startswith("final-spec/components") and not name.endswith(".md"):
            continue
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(git("show", f"{commit}:{name}"))


def verify_configuration(extracted: Path, manifests: dict) -> None:
    """The extracted configuration must reproduce the configuration hash recorded in the manifest of an unmodified world."""
    spec = importlib.util.spec_from_file_location("settings_at_commit", extracted / "src" / "arai" / "settings.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module                               # dataclasses look their module up while it is being defined
    spec.loader.exec_module(module)
    checked = 0
    for world_id, manifest in manifests.items():
        seed = manifest["generator"]["seed"]
        try:
            expected = module.load_settings(seed, spec_root=extracted / "final-spec").config_sha256()
        except Exception as error:                                # noqa: BLE001
            raise SystemExit(f"the configuration at this commit cannot be loaded: {error}") from None
        if expected == manifest["generator"]["config_sha256"]:
            checked += 1
    if not checked:
        raise SystemExit("the configuration at this commit reproduces the configuration hash of none of the worlds; wrong commit?")
    others = "" if checked == len(manifests) else " (the others were generated under another experiment contract with the same generator settings)"
    print(f"configuration verified: it reproduces the recorded configuration hash of {checked} of {len(manifests)} worlds{others}")


def write_zip(path: Path, entries: list, stored: tuple = (".parquet", ".skops")) -> dict:
    """entries: (archive name, source path). Already-compressed formats are stored, text is deflated."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, source in entries:
            method = zipfile.ZIP_STORED if str(source).endswith(stored) else zipfile.ZIP_DEFLATED
            archive.write(source, name, compress_type=method)
    return {"file": path.name, "bytes": path.stat().st_size, "entries": len(entries), "sha256": sha256(path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--guide", type=Path, required=True, help="the data guide to place at the top of every archive")
    parser.add_argument("--records", type=Path, nargs="*", default=[], help="dated records to include with the configuration")
    args = parser.parse_args()
    global ARTIFACTS, PRIVATE
    own = ROOT / "data" / args.experiment                   # from experiment 4 on, an experiment has a data folder of its own
    if (own / "artifacts").is_dir():
        ARTIFACTS, PRIVATE = own / "artifacts", own / "private"
    experiment = ARTIFACTS / "experiments" / args.experiment
    commit = json.loads((experiment / "reports" / "dry_run.json").read_text(encoding="utf-8"))["provenance"]["git_commit"]
    roles = worlds_of(experiment)
    order = {"train": 0, "validation": 1, "test": 2, "demo": 3, "stress": 4}
    worlds = sorted(roles, key=lambda w: (order[roles[w]], w))
    manifests = {w: verify_world(w) for w in worlds}
    print(f"{args.experiment}: {len(worlds)} worlds verified against their manifests; contract commit {commit[:8]}")

    out = ROOT / "data" / "exports" / args.experiment
    out.mkdir(parents=True, exist_ok=True)
    prefix = "ARAI-" + args.experiment
    summary = pd.DataFrame([summarise(w, roles[w], manifests[w]) for w in worlds])
    guide = args.guide.resolve()
    archives = []
    with tempfile.TemporaryDirectory() as scratch:
        scratch = Path(scratch)
        summary.to_csv(scratch / "WORLDS.csv", index=False, lineterminator="\n")
        extract_configuration(commit, scratch / "configuration")
        verify_configuration(scratch / "configuration", manifests)
        top = [("DATA-GUIDE.md", guide), ("WORLDS.csv", scratch / "WORLDS.csv")]
        place = lambda w: f"{roles[w]}/{w}"  # noqa: E731

        archives.append(write_zip(out / f"{prefix}-1-operational-csv.zip", top + [
            (f"operational-csv/{place(w)}/{p.name}", p) for w in worlds for p in sorted((ARTIFACTS / "worlds" / w / "operational").iterdir())]))
        archives.append(write_zip(out / f"{prefix}-2-operational-parquet.zip", top + [
            (f"operational-parquet/{place(w)}/{p.name}", p) for w in worlds for p in sorted((ARTIFACTS / "worlds" / w / "parquet").iterdir())]
            + [(f"operational-parquet/{place(w)}/manifest.json", ARTIFACTS / "worlds" / w / "operational" / "manifest.json") for w in worlds]))
        archives.append(write_zip(out / f"{prefix}-3-private-truth.zip", top + [
            (f"private-truth/{place(w)}/{p.name}", p) for w in worlds for p in sorted((PRIVATE / w).iterdir())]))
        configuration = [(f"configuration/{p.relative_to(scratch / 'configuration').as_posix()}", p)
                         for p in sorted((scratch / "configuration").rglob("*")) if p.is_file() and "__pycache__" not in p.parts]
        records = [(f"records/{p.name}", p.resolve()) for p in args.records]
        archives.append(write_zip(out / f"{prefix}-4-configuration.zip", top + configuration + records))
        results = [(f"experiment-records/{p.relative_to(experiment).as_posix()}", p) for p in sorted(experiment.rglob("*"))
                   if p.is_file() and p.suffix in (".json",) and "published" not in p.parts]
        featured = [w for w in worlds if (ARTIFACTS / "features" / w).is_dir()]          # the demonstration world is scored, never featurised offline
        features = [(f"features/{place(w)}/{p.name}", p) for w in featured for p in sorted((ARTIFACTS / "features" / w).iterdir())]
        archives.append(write_zip(out / f"{prefix}-5-features-and-results.zip", top + features + results))

    package = {"experiment_id": args.experiment, "packaged_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "contract_commit": commit, "worlds": {w: roles[w] for w in worlds}, "archives": archives,
               "note": "Synthetic data from one simulator. Private truth is in its own archive: keep it away from anything a model reads."}
    (out / "PACKAGE.json").write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
    summary.to_csv(out / "WORLDS.csv", index=False, lineterminator="\n")
    (out / "DATA-GUIDE.md").write_bytes(guide.read_bytes())
    for archive in archives:
        print(f"  {archive['file']:<52} {archive['bytes'] / 1e6:8.1f} MB  {archive['entries']:>4} files  sha256 {archive['sha256'][:16]}...")
    print("written to", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
