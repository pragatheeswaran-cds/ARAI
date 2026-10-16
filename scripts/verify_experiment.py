"""Check the recorded state of the experiment named by the contract. Reads only; writes and fits nothing.

    uv run --no-sync python scripts/verify_experiment.py                  # every check
    uv run --no-sync python scripts/verify_experiment.py --skip-earlier   # leave out the data of earlier experiments
    uv run --no-sync python scripts/verify_experiment.py --no-recompute   # leave out re-scoring the test worlds

Each line is one claim of the experiment's record with PASS or FAIL. The checks are: the contract is the one the
experiment was trained under; every report was made from one clean commit; worlds were generated in the order the
protocol requires; every world and its truth match the hashes written with them; the recorded test figures come
out again when the frozen model scores the stored test features; the published bundle is that model and the
scoring code has not changed since; and the data of earlier experiments is unchanged.

Re-scoring the test worlds here is a check of a record, not a second test: it selects nothing, writes nothing and
cannot change the recorded outcome.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from arai import bundles, contract, paths
from arai.generator.world import _code_sha256 as generator_code_sha256
from arai.operational import TABLES
from arai.settings import load_settings

ROOT = paths.REPO_ROOT
EARLIER, BACKUP = ROOT / "data", ROOT / "data" / "backups" / "2026-10-05-experiments-1-and-2"
failures = []


def check(claim: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {claim}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        failures.append(claim)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def utc(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def written(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, UTC)


def world_problem(world_id: str, artifacts: Path, private: Path) -> str | None:
    """Why a stored world does not match the hashes written with it, or None when it does."""
    base = artifacts / "worlds" / world_id / "operational"
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    for name in TABLES:
        if sha256(base / f"{name}.csv") != manifest["files"][name]["sha256"]:
            return f"{name}.csv differs from its manifest"
    record = private / world_id / "private-manifest.json"
    if not record.is_file():
        return None if not (private / world_id).exists() else "truth has no manifest"
    recorded = json.loads(record.read_text(encoding="utf-8"))
    if recorded["operational_manifest_sha256"] != sha256(base / "manifest.json"):
        return "truth was written with another operational world"
    for name, entry in recorded["files"].items():
        if sha256(private / world_id / entry["filename"]) != entry["sha256"]:
            return f"truth table {name} differs from its manifest"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-earlier", action="store_true", help="do not check the data of earlier experiments")
    parser.add_argument("--no-recompute", action="store_true", help="do not re-score the test worlds with the frozen model")
    args = parser.parse_args()

    experiment_id, artifacts, private = contract.experiment_id(), paths.ARTIFACT_ROOT, paths.PRIVATE_TRUTH_ROOT
    out = artifacts / "experiments" / experiment_id
    load = lambda name: json.loads((out / name).read_text(encoding="utf-8"))
    settings = load_settings()
    print(f"{experiment_id} in {artifacts.parent}\n")

    # ---- the contract and the commit
    config, dry, selection, test, validation = (load(n) for n in ("config.json", "reports/dry_run.json", "selection.json",
                                                                 "reports/test.json", "reports/validation.json"))
    contract_file = settings.spec_root / "contracts" / "experiment.yaml"
    check("the contract in the repository is the one the experiment was trained under",
          config["experiment_config_sha256"] == sha256(contract_file))
    commits = {report["provenance"]["git_commit"] for report in (dry, validation, test)}
    clean = not any(report["provenance"]["git_tracked_changes"] for report in (dry, validation, test))
    commit = next(iter(commits))
    check("the dry run, the selection and the test were made from one commit with no uncommitted change",
          len(commits) == 1 and clean, commit[:7])
    at_commit = hashlib.sha256(git("show", f"{commit}:final-spec/contracts/experiment.yaml")).hexdigest()
    check("that commit holds this contract", at_commit == config["experiment_config_sha256"])
    committed = datetime.fromisoformat(git("log", "-1", "--format=%cI", commit).decode().strip())

    # ---- the order of the protocol (file times of the world manifests, as the pipeline's own guard reads them)
    manifest = lambda seed: artifacts / "worlds" / f"W{seed}" / "operational" / "manifest.json"
    e = settings.experiment
    first = lambda key: min(written(manifest(s)) for s in e[key])
    check("the contract was committed before any training world was generated", committed <= first("train_seeds"),
          f"commit {committed.astimezone(UTC):%H:%M:%S}Z, first world {first('train_seeds'):%H:%M:%S}Z")
    check("the gate dry run was recorded before any validation world was generated", utc(dry["recorded_at"]) <= first("validation_seeds"),
          f"dry run {dry['recorded_at']}, first world {first('validation_seeds'):%H:%M:%S}Z")
    check("the selection was frozen before any test world was generated", utc(selection["frozen_at"]) <= first("test_seeds"),
          f"frozen {selection['frozen_at']}, first world {first('test_seeds'):%H:%M:%S}Z")
    check("the final test was run after the selection was frozen, and its outcome is recorded once",
          utc(selection["tested_at"]) >= utc(selection["frozen_at"]) and selection["tested_at"] == test["recorded_at"])

    # ---- the worlds
    sealed = [f"W{s}" for key in ("train_seeds", "validation_seeds", "test_seeds", "demo_seeds") for s in e[key]]
    stress = [f"W{s}" for s in e["stress_seeds"]]
    problems = {w: p for w in sealed + stress if (p := world_problem(w, artifacts, private))}
    check(f"all {len(sealed) + len(stress)} worlds and their truth match the hashes written with them", not problems, str(problems or "")[:200])
    generators = {w: json.loads(manifest(w[1:]).read_text(encoding="utf-8"))["generator"] for w in sealed + stress}
    same = {(generators[w]["code_sha256"], generators[w]["config_sha256"]) for w in sealed}
    check("training, validation, test and demonstration worlds come from one generator and one configuration", len(same) == 1)
    check("that generator is the code in the repository and that configuration is the contract's",
          same == {(generator_code_sha256(), settings.config_sha256())})
    check("each stress world records a configuration of its own",
          len({generators[w]["config_sha256"] for w in stress}) == len(stress) and all(generators[w]["code_sha256"] == generator_code_sha256() for w in stress))

    # ---- the selection and the recorded figures
    chosen = selection["selected_model_id"]
    check("the selected model's file is the one frozen at selection",
          sha256(out / "candidates" / chosen / "model.skops") == selection["selected_model_sha256"], chosen)
    check("the final test is recorded as passed", selection["final_test_status"] == "passed" == test["final_test_status"])
    card = {row["ranking"]: row for row in test["scorecard"]}
    model, rule = card[chosen], card["raw_return_rate"]
    print(f"      recorded on the test worlds: model {model['precision']:.4f} ({model['true_positives']} of {model['k']}), "
          f"rule {rule['precision']:.4f} ({rule['true_positives']} of {rule['k']})")
    for segment in contract.segments():
        print(f"      {segment:<26} model {model[segment + '_fpr']:.4f}  rule {rule[segment + '_fpr']:.4f}")
    check("on the recorded figures the model is more precise than the rule and reviews no gate group more often",
          model["precision"] > rule["precision"] and all(model[s + "_fpr"] <= rule[s + "_fpr"] for s in contract.segments()))
    if not args.no_recompute:
        from arai import evaluation, experiment, selection as gate
        frame = experiment._frozen_rankings(out, evaluation.evaluation_frame(test["worlds"], artifacts, private), only=[chosen])
        rankings, selectable = experiment._rankings(only=[chosen])
        again = gate.scorecard(frame, rankings, selectable, require_coverage=False)
        keys = ["k", "true_positives", *(s + "_fpr" for s in contract.segments())]
        # the reports keep ten decimals
        equal = all(abs(float(again.loc[name, key]) - float(card[name][key])) < 1e-9 for name in (chosen, "raw_return_rate") for key in keys)
        check("the frozen model scoring the stored test features gives the recorded figures again", equal and again.loc[chosen, "status"] == "passed",
              f"model {int(again.loc[chosen, 'true_positives'])} of {int(again.loc[chosen, 'k'])}")

    # ---- what is served
    pointer = bundles.read_active(artifacts)
    report = load("published/experiment.json")
    check("the active pointer names this experiment and a promoted model", bool(pointer) and pointer["experiment_id"] == experiment_id
          and bool(pointer["model_id"]), str(pointer and pointer["model_id"]))
    bundle = bundles.load_bundle(pointer["model_id"], artifacts)
    check("the published bundle holds the selected model", sha256(bundles.bundle_root(artifacts) / pointer["model_id"] / "model.skops")
          == selection["selected_model_sha256"])
    check("the scoring code in the repository is the code the bundle was published with", not bundles.code_differs(bundle))
    summary = report["summary"]
    check("the published report states the recorded selection and test outcome", summary["selected_candidate_id"] == chosen
          and summary["final_test_status"] == selection["final_test_status"] and summary["selected_model_id"] == pointer["model_id"])

    # ---- earlier experiments
    if not args.skip_earlier:
        old = bundles.read_active(EARLIER / "artifacts")
        check("the earlier data folder still serves experiment 2", bool(old) and old["experiment_id"] == "EXP-20261005-02", str(old and old["model_id"]))
        worlds = sorted(p.name for p in (EARLIER / "artifacts" / "worlds").iterdir() if (p / "operational" / "manifest.json").is_file())
        problems = {w: p for w in worlds if (p := world_problem(w, EARLIER / "artifacts", EARLIER / "private"))}
        check(f"all {len(worlds)} worlds of experiments 1 to 3 and their truth match the hashes written with them", not problems, str(problems or "")[:200])
        if BACKUP.is_dir():
            compared, differing = 0, []
            for part in ("artifacts", "private"):
                for copy in (BACKUP / part).rglob("*"):
                    if copy.is_file():
                        compared += 1
                        live = EARLIER / part / copy.relative_to(BACKUP / part)
                        if not live.is_file() or sha256(live) != sha256(copy):
                            differing.append(str(copy.relative_to(BACKUP)))
            check(f"every file of experiments 1 and 2 is identical to the backup taken before experiment 3 ({compared} files)",
                  not differing, "; ".join(differing[:5]))
        else:
            print(f"      no backup at {BACKUP}: comparison with it left out")

    print(f"\n{'ALL CHECKS PASSED' if not failures else str(len(failures)) + ' CHECK(S) FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
