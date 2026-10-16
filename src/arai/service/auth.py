"""Who is signed in and what they may do (decision AM-69, docs/design/authentication-and-roles.md).

Identity comes from a verified sign-in, never from a name the browser sends: the development login (AUTH_MODE=dev,
laptops and demos: a fixed list of people with their roles) or Keycloak single sign-on (AUTH_MODE=oidc, AM-70, oidc.py),
which create the same users and sessions, so everything downstream of `resolve` is the same. With single sign-on a script
may also send a Keycloak bearer token, checked on each request (`resolve_bearer`), with no session and no CSRF token.

A session is an opaque random cookie (HttpOnly, SameSite=Lax, Secure on the vm profile); the database keeps only its
SHA-256. Its CSRF token is derived from the cookie value, so it is never stored in clear and needs no extra round trip.
Expiry is read against the database clock: idle after `session_idle_minutes` without a request, over after
`session_max_hours` whatever happens. Every route declares the permission it needs in ROUTE_PERMISSIONS; a route that is
missing from it is refused (fail closed) and a test walks every route of the contract against the table.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field

from psycopg.types.json import Jsonb

from arai.service.config import ServiceConfig
from arai.service.oidc import Oidc, OidcError, display_name
from arai.service.store import Store, new_id

SESSION_COOKIE = "arai_session"
CSRF_HEADER = "x-csrf-token"
DEV_ISSUER = "dev"

# what each role may do; a user's permissions are the union over its roles. Admin operates the system and does not review.
PERMISSIONS = {
    "viewer": frozenset({"read"}),
    "reviewer": frozenset({"read", "export", "review"}),
    "approver": frozenset({"read", "export", "review", "decide"}),
    "admin": frozenset({"read", "export", "manage"}),
}
PUBLIC, SIGNED_IN = "public", "signed_in"
P = "/api/v1"
# (method, route path) -> the permission it needs. Approve and reject also need "decide", checked where the kind is known.
ROUTE_PERMISSIONS = {
    ("GET", f"{P}/health"): PUBLIC,
    ("GET", f"{P}/openapi.json"): PUBLIC,
    ("GET", f"{P}/auth/dev-users"): PUBLIC,
    ("POST", f"{P}/auth/dev-login"): PUBLIC,
    ("GET", f"{P}/auth/login"): PUBLIC,
    ("GET", f"{P}/auth/callback"): PUBLIC,
    ("POST", f"{P}/auth/logout"): SIGNED_IN,
    ("GET", f"{P}/me"): SIGNED_IN,
    ("GET", f"{P}/datasets"): "read",
    ("POST", f"{P}/datasets"): "manage",
    ("GET", f"{P}/datasets/{{dataset_id}}"): "read",
    ("DELETE", f"{P}/datasets/{{dataset_id}}"): "manage",
    ("POST", f"{P}/runs"): "manage",
    ("GET", f"{P}/runs"): "read",
    ("GET", f"{P}/runs/{{run_id}}"): "read",
    ("POST", f"{P}/runs/{{run_id}}/cancel"): "manage",
    ("GET", f"{P}/runs/{{run_id}}/customers"): "read",
    ("GET", f"{P}/runs/{{run_id}}/customers/export"): "export",
    ("GET", f"{P}/runs/{{run_id}}/score-distribution"): "read",
    ("GET", f"{P}/runs/{{run_id}}/customers/{{customer_id}}"): "read",
    ("GET", f"{P}/runs/{{run_id}}/customers/{{customer_id}}/reviews"): "read",
    ("POST", f"{P}/runs/{{run_id}}/customers/{{customer_id}}/reviews"): "review",
    ("GET", f"{P}/runs/{{run_id}}/styles"): "read",
    ("GET", f"{P}/runs/{{run_id}}/styles/{{style_id}}"): "read",
    ("GET", f"{P}/experiments"): "read",
    ("GET", f"{P}/experiments/{{experiment_id}}"): "read",
    ("GET", f"{P}/experiments/{{experiment_id}}/curves"): "read",
    ("GET", f"{P}/experiments/{{experiment_id}}/truth"): "read",
}


def permissions_of(roles) -> frozenset:
    out = frozenset()
    for role in roles:
        out |= PERMISSIONS.get(role, frozenset())
    return out


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def csrf_for(token: str) -> str:
    """The session's CSRF token: derived from the cookie value, so only someone holding the cookie can know it."""
    return hashlib.sha256(("csrf:" + token).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class User:
    id: str
    display_name: str
    email: str | None
    roles: tuple
    session_hash: str = field(repr=False)
    expires_at: object = None

    @property
    def permissions(self) -> frozenset:
        return permissions_of(self.roles)

    def can(self, permission: str) -> bool:
        return permission in self.permissions


SIGN_IN_MINUTES = 10                     # an answer from Keycloak is accepted this long after the redirect, once
BEARER_CACHE_SECONDS = 60


class Auth:
    def __init__(self, config: ServiceConfig, store: Store):
        self.config, self.store = config, store
        self.oidc = Oidc(config) if config.mode == "oidc" else None
        self._bearer: dict = {}                                   # token hash -> (valid until, User)

    # ------------------------------------------------------------------ Keycloak single sign-on (AM-70)
    def begin_sso(self, return_to: str) -> str:
        """Where to send the browser: Keycloak's sign-in page, with this attempt's state, nonce and PKCE challenge."""
        state, nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        url = self.oidc.authorization_url(state, nonce, verifier)
        with self.store.transaction() as db:
            db.execute("DELETE FROM oidc_logins WHERE created_at < now() - make_interval(mins => %s)", (SIGN_IN_MINUTES,))
            db.execute("INSERT INTO oidc_logins (state_hash, nonce, code_verifier, return_to) VALUES (%s, %s, %s, %s)",
                       (_hash(state), nonce, verifier, return_to))
        return url

    def finish_sso(self, state: str, code: str, request_id: str | None = None) -> tuple:
        """(user, cookie token, return_to) for Keycloak's answer to an attempt begun here; OidcError otherwise."""
        with self.store.transaction() as db:
            attempt = db.execute("""DELETE FROM oidc_logins WHERE state_hash = %s RETURNING nonce, code_verifier, return_to,
                                        created_at > now() - make_interval(mins => %s) AS fresh""",
                                 (_hash(state or ""), SIGN_IN_MINUTES)).fetchone()
        if attempt is None or not attempt["fresh"]:
            raise OidcError("sign_in_expired", "unknown, used or expired state")
        tokens = self.oidc.exchange(code, attempt["code_verifier"])
        claims = self.oidc.verify(tokens.get("id_token", ""), audience=self.config.oidc_client_id, nonce=attempt["nonce"])
        roles = self.oidc.roles(claims)
        if not roles:
            self.log("refused", None, request_id, {"status": 403, "reason": "no_role", "subject": claims["sub"]})
            raise OidcError("no_role", f"{claims['sub']} carries no ARAI group")
        user_id = self._upsert_user(self.config.oidc_issuer, claims["sub"], display_name(claims), claims.get("email"), roles, "oidc")
        user, token = self._open_session(user_id, request_id)
        return user, token, attempt["return_to"]

    def resolve_bearer(self, token: str, request_id: str | None = None) -> tuple:
        """(user, None) for a valid Keycloak access token meant for this API, else (None, reason). Checked results are
        kept for a minute (never past the token's expiry), so a script's requests do not each rewrite the user."""
        if self.oidc is None:
            return None, "single sign-on is off"
        key, now = _hash(token), time.time()
        cached = self._bearer.get(key)
        if cached and cached[0] > now:
            return cached[1], None
        try:
            claims = self.oidc.verify(token, audience=self.config.oidc_api_audience)
        except OidcError as error:
            self.log("refused", None, request_id, {"status": 401, "reason": error.code, "bearer": True})
            return None, error.code
        roles = self.oidc.roles(claims)
        if not roles:
            return None, "no_role"
        user_id = self._upsert_user(self.config.oidc_issuer, claims["sub"], display_name(claims), claims.get("email"), roles, "oidc")
        with self.store.transaction() as db:
            status = db.execute("SELECT status FROM users WHERE id = %s", (user_id,)).fetchone()["status"]
        if status != "active":
            return None, "disabled"
        user = User(id=user_id, display_name=display_name(claims), email=claims.get("email"), roles=tuple(roles), session_hash="",
                    expires_at=None)
        self._bearer = {k: v for k, v in self._bearer.items() if v[0] > now}
        self._bearer[key] = (min(now + BEARER_CACHE_SECONDS, float(claims["exp"])), user)
        return user, None

    # ------------------------------------------------------------------ the development login
    def dev_users(self) -> list:
        return [{"display_name": name, "roles": list(roles)} for name, roles in self.config.dev_users]

    def sign_in_dev(self, name: str, request_id: str | None = None) -> tuple | None:
        """(user, cookie token) for a person of the development list, or None. Their roles are the list's, refreshed now."""
        match = next(((n, r) for n, r in self.config.dev_users if n.casefold() == name.strip().casefold()), None)
        if self.config.mode != "dev" or match is None:
            return None
        display, roles = match
        user_id = self._upsert_user(DEV_ISSUER, display.casefold(), display, None, roles, "dev")
        return self._open_session(user_id, request_id)

    # ------------------------------------------------------------------ users and sessions
    def _upsert_user(self, issuer: str, subject: str, display_name: str, email: str | None, roles, source: str) -> str:
        with self.store.transaction() as db:
            row = db.execute("""INSERT INTO users (id, issuer, subject, email, display_name) VALUES (%s, %s, %s, %s, %s)
                                ON CONFLICT (issuer, subject) DO UPDATE SET display_name = EXCLUDED.display_name,
                                    email = coalesce(EXCLUDED.email, users.email)
                                RETURNING id""", (new_id("usr"), issuer, subject, email, display_name)).fetchone()
            db.execute("DELETE FROM user_roles WHERE user_id = %s AND source = %s", (row["id"], source))
            for role in roles:
                db.execute("INSERT INTO user_roles (user_id, role, source) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                           (row["id"], role, source))
        return row["id"]

    def _open_session(self, user_id: str, request_id: str | None) -> tuple:
        token = secrets.token_urlsafe(32)
        with self.store.transaction() as db:
            db.execute("""INSERT INTO sessions (id_hash, user_id, csrf_hash, expires_at)
                          VALUES (%s, %s, %s, now() + make_interval(hours => %s))""",
                       (_hash(token), user_id, _hash(csrf_for(token)), self.config.session_max_hours))
            db.execute("UPDATE users SET last_seen_at = now() WHERE id = %s", (user_id,))
        self.log("sign_in", user_id, request_id, {"mode": self.config.mode})
        return self.resolve(token)[0], token

    def resolve(self, token: str | None) -> tuple:
        """(user, None) for a live session, else (None, reason): missing, unknown, ended, idle, max_age or disabled. A
        session that has run out is ended here, once, and the reason logged."""
        if not token:
            return None, "missing"
        with self.store.transaction() as db:
            row = db.execute("""SELECT s.id_hash, s.user_id, s.last_seen_at, s.expires_at, s.ended_at, now() AS now,
                                       u.display_name, u.email, u.status,
                                       array(SELECT role FROM user_roles r WHERE r.user_id = u.id ORDER BY role) AS roles
                                FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.id_hash = %s""",
                             (_hash(token),)).fetchone()
            if row is None:
                return None, "unknown"
            if row["ended_at"] is not None:
                return None, "ended"
            reason = ("disabled" if row["status"] != "active" else "max_age" if row["now"] >= row["expires_at"]
                      else "idle" if (row["now"] - row["last_seen_at"]).total_seconds() > self.config.session_idle_minutes * 60
                      else None)
            if reason:
                db.execute("UPDATE sessions SET ended_at = now(), ended_reason = %s WHERE id_hash = %s", (reason, row["id_hash"]))
            else:
                db.execute("UPDATE sessions SET last_seen_at = now() WHERE id_hash = %s", (row["id_hash"],))
        if reason:
            self.log("session_ended", row["user_id"], None, {"reason": reason})
            return None, reason
        return User(id=row["user_id"], display_name=row["display_name"], email=row["email"], roles=tuple(row["roles"]),
                    session_hash=row["id_hash"], expires_at=row["expires_at"]), None

    @staticmethod
    def csrf_ok(token: str | None, header: str | None) -> bool:
        return bool(token and header) and hmac.compare_digest(csrf_for(token), header)

    def sign_out(self, user: User, request_id: str | None = None) -> None:
        with self.store.transaction() as db:
            db.execute("UPDATE sessions SET ended_at = now(), ended_reason = 'sign_out' WHERE id_hash = %s AND ended_at IS NULL",
                       (user.session_hash,))
        self.log("sign_out", user.id, request_id, {})

    def disable(self, user_id: str, request_id: str | None = None) -> None:
        """Take a person's access away at once: every open session ends with the next request, and bearer tokens stop."""
        with self.store.transaction() as db:
            db.execute("UPDATE users SET status = 'disabled' WHERE id = %s", (user_id,))
        self._bearer = {k: v for k, v in self._bearer.items() if v[1].id != user_id}
        self.log("user_disabled", user_id, request_id, {})

    def log(self, kind: str, user_id: str | None, request_id: str | None, detail: dict) -> None:
        with self.store.transaction() as db:
            db.execute("INSERT INTO auth_events (kind, user_id, request_id, detail) VALUES (%s, %s, %s, %s)",
                       (kind, user_id, request_id, Jsonb(detail)))
