"""Runtime configuration from the environment (final-spec component 15). No secret has a default."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from arai import paths

LOCAL_UI_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
# the development login's people (decision AM-69): a display name and its roles; admin is deliberately not a reviewer
# the demo's people: Asha, Ravi and Meera review and approve, Arjun reviews only, Priya (returns operations lead) reads
DEFAULT_DEV_USERS = (("Asha", ("reviewer", "approver")), ("Ravi", ("reviewer", "approver")), ("Meera", ("reviewer", "approver")),
                     ("Arjun", ("reviewer",)), ("Priya", ("viewer",)), ("Admin", ("admin",)))
ROLES = ("viewer", "reviewer", "approver", "admin")
# Keycloak groups to ARAI roles (AM-69, owner's decision: roles live in Keycloak groups)
DEFAULT_ROLE_MAP = (("arai-viewers", "viewer"), ("arai-reviewers", "reviewer"), ("arai-approvers", "approver"), ("arai-admins", "admin"))


@dataclass(frozen=True)
class ServiceConfig:
    database_url: str
    artifact_root: Path
    profile: str = "local"                         # local | vm
    ui_origins: tuple = field(default=LOCAL_UI_ORIGINS)
    worker_id: str = "worker-1"
    poll_seconds: float = 2.0
    anthropic_api_key: str | None = None            # memos are drafted only when set; without it every memo is unavailable by design
    memo_model: str | None = None                   # the model memos are drafted with (default in memo.py)
    # who is signed in (AM-69): dev = the development login (laptops, demos), oidc = Keycloak single sign-on (step 2)
    auth_mode: str | None = None                    # default: dev for the local profile, oidc for the vm profile
    dev_on_vm: bool = False                         # AM-74: the development login on the vm profile, for a public demonstration
                                                    # behind the shared login; personas, not verified people
    dev_users: tuple = DEFAULT_DEV_USERS
    session_idle_minutes: int = 60                  # signed out after this long without a request
    session_max_hours: int = 10                     # signed in again after this long, active or not
    # Keycloak single sign-on (AUTH_MODE=oidc, step 2 of the authentication design)
    oidc_issuer: str | None = None                  # e.g. https://keycloak.example.com/realms/arai
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = field(default=None, repr=False)
    oidc_redirect_uri: str | None = None            # https://<host>/api/v1/auth/callback
    oidc_scopes: str = "openid profile email"
    oidc_api_audience: str = "arai-api"             # the audience scripts' bearer tokens must carry
    oidc_role_claim: str = "groups"
    oidc_role_map: tuple = DEFAULT_ROLE_MAP
    bootstrap_admins: tuple = ()                    # e-mail addresses given admin before any group exists
    oidc_allow_http: bool = False                   # a plain-http issuer, only for a local test Keycloak

    def __post_init__(self):
        if self.profile not in ("local", "vm"):
            raise ValueError("APP_PROFILE must be local or vm")
        if self.mode not in ("dev", "oidc"):
            raise ValueError("AUTH_MODE must be dev or oidc")
        if self.mode == "dev" and self.profile == "vm" and not self.dev_on_vm:
            raise ValueError("AUTH_MODE=dev is the development login and is refused with APP_PROFILE=vm; use oidc, "
                             "or AUTH_DEV_ON_VM=1 for a public demonstration behind the shared login (AM-74)")
        for name, roles in self.dev_users:
            if not name or not roles or set(roles) - set(ROLES):
                raise ValueError(f"development user {name!r}: roles must be among {ROLES}")
        if self.session_idle_minutes < 1 or self.session_max_hours < 1:
            raise ValueError("session limits must be positive")
        if {role for _, role in self.oidc_role_map} - set(ROLES):
            raise ValueError(f"AUTH_ROLE_MAP roles must be among {ROLES}")

    def oidc_problems(self) -> list:
        """What single sign-on still needs; empty when AUTH_MODE=oidc can start (checked when the app is created)."""
        if self.mode != "oidc":
            return []
        missing = [name for name, value in (("OIDC_ISSUER", self.oidc_issuer), ("OIDC_CLIENT_ID", self.oidc_client_id),
                                            ("OIDC_CLIENT_SECRET", self.oidc_client_secret), ("OIDC_REDIRECT_URI", self.oidc_redirect_uri))
                   if not value]
        if self.oidc_issuer and not self.oidc_issuer.startswith("https://") and not self.oidc_allow_http:
            missing.append("an https OIDC_ISSUER (or OIDC_ALLOW_HTTP=1 for a local test Keycloak)")
        return missing

    @property
    def mode(self) -> str:
        return self.auth_mode or ("oidc" if self.profile == "vm" else "dev")


def from_env() -> ServiceConfig:
    """DATABASE_URL is required. The private truth root is deliberately not part of serving configuration."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    origins = tuple(o.strip() for o in os.environ.get("UI_ORIGINS", ",".join(LOCAL_UI_ORIGINS)).split(",") if o.strip())
    dev_users = parse_dev_users(os.environ["AUTH_DEV_USERS"]) if os.environ.get("AUTH_DEV_USERS") else DEFAULT_DEV_USERS
    return ServiceConfig(database_url=url, artifact_root=Path(os.environ.get("ARTIFACT_ROOT", paths.ARTIFACT_ROOT)),
                         profile=os.environ.get("APP_PROFILE", "local"), ui_origins=origins,
                         worker_id=os.environ.get("WORKER_ID", "worker-1"),
                         anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None, memo_model=os.environ.get("ARAI_MEMO_MODEL") or None,
                         auth_mode=os.environ.get("AUTH_MODE") or None, dev_users=dev_users,
                         dev_on_vm=os.environ.get("AUTH_DEV_ON_VM", "") in ("1", "true", "yes"),
                         session_idle_minutes=int(os.environ.get("SESSION_IDLE_MINUTES", "60")),
                         session_max_hours=int(os.environ.get("SESSION_MAX_HOURS", "10")),
                         oidc_issuer=os.environ.get("OIDC_ISSUER") or None, oidc_client_id=os.environ.get("OIDC_CLIENT_ID") or None,
                         oidc_client_secret=os.environ.get("OIDC_CLIENT_SECRET") or None,
                         oidc_redirect_uri=os.environ.get("OIDC_REDIRECT_URI") or None,
                         oidc_scopes=os.environ.get("OIDC_SCOPES", "openid profile email"),
                         oidc_api_audience=os.environ.get("OIDC_API_AUDIENCE", "arai-api"),
                         oidc_role_claim=os.environ.get("AUTH_ROLE_CLAIM", "groups"),
                         oidc_role_map=parse_role_map(os.environ["AUTH_ROLE_MAP"]) if os.environ.get("AUTH_ROLE_MAP") else DEFAULT_ROLE_MAP,
                         bootstrap_admins=tuple(e.strip().casefold() for e in os.environ.get("ARAI_BOOTSTRAP_ADMINS", "").split(",") if e.strip()),
                         oidc_allow_http=os.environ.get("OIDC_ALLOW_HTTP", "") in ("1", "true", "yes"))


def parse_role_map(text: str) -> tuple:
    """AUTH_ROLE_MAP: "arai-viewers=viewer,arai-reviewers=reviewer,arai-approvers=approver,arai-admins=admin"."""
    return tuple((group.strip().lstrip("/"), role.strip()) for group, _, role in (e.partition("=") for e in text.split(",")) if group.strip())


def parse_dev_users(text: str) -> tuple:
    """AUTH_DEV_USERS: "Asha=reviewer;Ravi=reviewer,approver;Admin=admin"."""
    users = []
    for entry in filter(None, (e.strip() for e in text.split(";"))):
        name, _, roles = entry.partition("=")
        users.append((name.strip(), tuple(r.strip() for r in roles.split(",") if r.strip())))
    return tuple(users)
