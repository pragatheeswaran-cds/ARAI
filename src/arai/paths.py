"""Project-relative locations. Environment variables override the defaults (final-spec component 15).

An experiment contract may name its own data folder (experiment.yaml `data_root`), so the worlds, records, bundles
and local database of one experiment never share a folder with those of another (decision AM-51).
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_ROOT = Path(os.environ.get("ARAI_SPEC_ROOT", REPO_ROOT / "final-spec"))


def contract_data_root(spec_root: Path = SPEC_ROOT) -> Path:
    """The data folder the experiment contract names, relative to the repository; `data` when it names none."""
    contract = Path(spec_root) / "contracts" / "experiment.yaml"
    named = yaml.safe_load(contract.read_text(encoding="utf-8")).get("data_root") if contract.is_file() else None
    return REPO_ROOT / (named or "data")


DATA_ROOT = Path(os.environ.get("ARAI_DATA_ROOT", contract_data_root()))
ARTIFACT_ROOT = Path(os.environ.get("ARTIFACT_ROOT", DATA_ROOT / "artifacts"))
# Private truth never shares a root with anything the serving process can read.
PRIVATE_TRUTH_ROOT = Path(os.environ.get("PRIVATE_TRUTH_ROOT", DATA_ROOT / "private"))
POSTGRES_DIR = DATA_ROOT / "postgres"       # the embedded database of `arai local`
