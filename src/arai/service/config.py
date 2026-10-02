"""Runtime configuration from the environment (final-spec component 15). No secret has a default."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from arai import paths

LOCAL_UI_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


@dataclass(frozen=True)
class ServiceConfig:
    database_url: str
    artifact_root: Path
    profile: str = "local"                         # local | vm
    ui_origins: tuple = field(default=LOCAL_UI_ORIGINS)
    worker_id: str = "worker-1"
    poll_seconds: float = 2.0

    def __post_init__(self):
        if self.profile not in ("local", "vm"):
            raise ValueError("APP_PROFILE must be local or vm")


def from_env() -> ServiceConfig:
    """DATABASE_URL is required. The private truth root is deliberately not part of serving configuration."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    origins = tuple(o.strip() for o in os.environ.get("UI_ORIGINS", ",".join(LOCAL_UI_ORIGINS)).split(",") if o.strip())
    return ServiceConfig(database_url=url, artifact_root=Path(os.environ.get("ARTIFACT_ROOT", paths.ARTIFACT_ROOT)),
                         profile=os.environ.get("APP_PROFILE", "local"), ui_origins=origins,
                         worker_id=os.environ.get("WORKER_ID", "worker-1"))
