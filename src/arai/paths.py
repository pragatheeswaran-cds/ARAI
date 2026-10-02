"""Project-relative locations. Environment variables override the defaults (final-spec component 15)."""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_ROOT = Path(os.environ.get("ARAI_SPEC_ROOT", REPO_ROOT / "final-spec"))
ARTIFACT_ROOT = Path(os.environ.get("ARTIFACT_ROOT", REPO_ROOT / "data" / "artifacts"))
# Private truth never shares a root with anything the serving process can read.
PRIVATE_TRUTH_ROOT = Path(os.environ.get("PRIVATE_TRUTH_ROOT", REPO_ROOT / "data" / "private"))
