"""Who is signed in and what they may do (decision AM-69, docs/design/authentication-and-roles.md).

Identity comes from a verified sign-in, never from a name the browser sends: the development login (AUTH_MODE=dev,
laptops and demos: a fixed list of people with their roles), Keycloak single sign-on (AUTH_MODE=oidc, AM-70, oidc.py) or
accounts with a password kept here (AUTH_MODE=password, AM-81). All three create the same users and sessions, so
everything downstream of `resolve` is the same. With single sign-on a script may also send a Keycloak bearer token,
checked on each request (`resolve_bearer`), with no session and no CSRF token.

A password is stored only as a salted scrypt hash. A wrong password and an unknown user name get the same answer after
the same work, and ten wrong passwords in a row lock the name for five minutes whether or not an account of that name
exists, so neither the answer nor the lock says which names are accounts. People, roles and passwords of this mode are
managed by an admin in People & access; a password the person did not choose (an admin's, or the initial one) must be
changed at the next sign-in, and until then the session is served nothing else. In this mode a session that was opened
by another kind of sign-in is not served.

A session is an opaque random cookie (HttpOnly, SameSite=Lax, Secure on the vm profile); the database keeps only its
SHA-256. Its CSRF token is derived from the cookie value, so it is never stored in clear and needs no extra round trip.
Expiry is read against the database clock: idle after `session_idle_minutes` without a request, over after
`session_max_hours` whatever happens. Every route declares the permission it needs in ROUTE_PERMISSIONS; a route that is
missing from it is refused (fail closed) and a test walks every route of the contract against the table.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
from dataclasses import dataclass, field

from psycopg.types.json import Jsonb

from arai.service.config import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, ROLES, USERNAME_PATTERN, ServiceConfig
from arai.service.oidc import Oidc, OidcError, display_name
from arai.service.store import Store, new_id

SESSION_COOKIE = "arai_session"
CSRF_HEADER = "x-csrf-token"
DEV_ISSUER = "dev"
LOCAL_ISSUER = "local"                   # accounts with a password (AM-81); the subject is the user name, casefolded
LOCAL_SOURCE = "local"                   # where such an account's roles come from: an admin, in People & access
MAX_FAILED_SIGN_INS = 10                 # wrong passwords in a row before the account is locked
LOCK_MINUTES = 5
SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_KEY_BYTES = 2 ** 14, 8, 1, 32          # about 16 MB and some tens of milliseconds a check

# what each role may do; a user's permissions are the union over its roles. Admin operates the system and does not review.
PERMISSIONS = {
    "viewer": frozenset({"read"}),
    "reviewer": frozenset({"read", "export", "review"}),
    "approver": frozenset({"read", "export", "review", "decide"}),
    # administer: people and access (contract 2.0.0, AM-71) - the users, the sign-in log, disable and end sessions
    "admin": frozenset({"read", "export", "manage", "administer"}),
}
PUBLIC, SIGNED_IN = "public", "signed_in"
P = "/api/v1"
# (method, route path) -> the permission it needs. Approve and reject also need "decide", checked where the kind is known.
ROUTE_PERMISSIONS = {
    ("GET", f"{P}/health"): PUBLIC,
    ("GET", f"{P}/openapi.json"): PUBLIC,
    ("GET", f"{P}/auth/mode"): PUBLIC,
    ("POST", f"{P}/auth/password-login"): PUBLIC,
    ("POST", f"{P}/me/password"): SIGNED_IN,
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
    ("GET", f"{P}/runs/{{run_id}}/insights"): "read",
    ("GET", f"{P}/runs/{{run_id}}/communities"): "read",
    ("GET", f"{P}/runs/{{run_id}}/decisions"): "read",
    ("POST", f"{P}/runs/{{run_id}}/customers/bulk-reviews"): "review",
    ("GET", f"{P}/runs/{{run_id}}/styles/export"): "export",
    ("GET", f"{P}/notifications"): SIGNED_IN,
    ("POST", f"{P}/notifications/seen"): SIGNED_IN,
    ("GET", f"{P}/runs/{{run_id}}/styles"): "read",
    ("GET", f"{P}/runs/{{run_id}}/styles/{{style_id}}"): "read",
    ("GET", f"{P}/experiments"): "read",
    ("GET", f"{P}/experiments/{{experiment_id}}"): "read",
    ("GET", f"{P}/experiments/{{experiment_id}}/curves"): "read",
    ("GET", f"{P}/experiments/{{experiment_id}}/truth"): "read",
    ("GET", f"{P}/admin/users"): "administer",
    ("POST", f"{P}/admin/users"): "administer",
    ("POST", f"{P}/admin/users/{{user_id}}/password"): "administer",
    ("POST", f"{P}/admin/users/{{user_id}}/roles"): "administer",
    ("POST", f"{P}/admin/users/{{user_id}}/disable"): "administer",
    ("POST", f"{P}/admin/users/{{user_id}}/enable"): "administer",
    ("POST", f"{P}/admin/users/{{user_id}}/end-sessions"): "administer",
    ("GET", f"{P}/admin/auth-events"): "administer",
}


# what a session whose password must be changed first may still call (AM-81)
PASSWORD_CHANGE_ROUTES = frozenset({("GET", f"{P}/me"), ("POST", f"{P}/me/password"), ("POST", f"{P}/auth/logout")})


def hash_password(password: str) -> str:
    """scrypt$<n>$<r>$<p>$<salt>$<key>: a fresh 16-byte salt for every password; the parameters travel with the hash."""
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_KEY_BYTES)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${base64.b64encode(salt).decode()}${base64.b64encode(key).decode()}"


def verify_password(password: str, stored: str) -> bool:
    """Whether the password gives the stored hash, compared in constant time. A stored value that cannot be read is False."""
    try:
        scheme, n, r, p, salt, key = stored.split("$")
        if scheme != "scrypt" or int(n) > 2 ** 17 or int(r) > 16 or int(p) > 4:      # never spend more than a known bound
            return False
        expected = base64.b64decode(key)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# checked when no such account exists, so an unknown user name takes as long as a wrong password
_NOBODY_HASH = hash_password(secrets.token_urlsafe(16))


def password_problem(password: str, *names: str) -> str | None:
    """Why a new password is not accepted, in words a person can act on; None when it is. Length is the rule; the
    account's own names are refused because they are the first guess."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"The password needs at least {PASSWORD_MIN_LENGTH} characters."
    if len(password) > PASSWORD_MAX_LENGTH:
        return f"The password may have at most {PASSWORD_MAX_LENGTH} characters."
    if len(set(password)) < 4:
        return "The password repeats too few different characters."
    if any(len(name) >= 3 and name.casefold() in password.casefold() for name in names if name):   # a one-letter name is in every password
        return "The password must not contain the account's name."
    return None


def permissions_of(roles) -> frozenset:
    out = frozenset()
    for role in roles:
        out |= PERMISSIONS.get(role, frozenset())
    return out


def _actor(by) -> dict:
    return {"by": by.id, "by_name": by.display_name} if by is not None else {}


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
    must_change_password: bool = False       # AM-81: an admin set this password; only the change is served until it is replaced

    @property
    def permissions(self) -> frozenset:
        return permissions_of(self.roles)

    def can(self, permission: str) -> bool:
        return permission in self.permissions


class SignInRefused(Exception):
    """A sign-in that is not accepted: `code` is safe to show (user_disabled, invalid_credentials, too_many_attempts)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


SIGN_IN_MINUTES = 10                     # an answer from Keycloak is accepted this long after the redirect, once
BEARER_CACHE_SECONDS = 60


class AccountError(Exception):
    """An account action that cannot be done as asked: `code` and `message` are safe to show."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


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
        grants = self.oidc.grants(claims)
        if not grants:
            self.log("refused", None, request_id, {"status": 403, "reason": "no_role", "subject": claims["sub"]})
            raise OidcError("no_role", f"{claims['sub']} carries no ARAI group")
        user_id, status = self._upsert_user(self.config.oidc_issuer, claims["sub"], display_name(claims), claims.get("email"), grants,
                                            request_id)
        if status != "active":
            self.log("refused", user_id, request_id, {"status": 403, "reason": "user_disabled"})
            raise OidcError("user_disabled", f"{claims['sub']} is disabled in ARAI")
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
        grants = self.oidc.grants(claims)
        if not grants:
            return None, "no_role"
        roles = sorted(role for role, _ in grants)
        user_id, status = self._upsert_user(self.config.oidc_issuer, claims["sub"], display_name(claims), claims.get("email"), grants,
                                            request_id)
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
        """(user, cookie token) for a person of the development list, or None. Their roles are the list's, refreshed now.
        SignInRefused for a person an admin has disabled."""
        match = next(((n, r) for n, r in self.config.dev_users if n.casefold() == name.strip().casefold()), None)
        if self.config.mode != "dev" or match is None:
            return None
        display, roles = match
        user_id, status = self._upsert_user(DEV_ISSUER, display.casefold(), display, None, [(r, "dev") for r in roles], request_id)
        if status != "active":
            self.log("refused", user_id, request_id, {"status": 403, "reason": "user_disabled"})
            raise SignInRefused("user_disabled")
        return self._open_session(user_id, request_id)

    # ------------------------------------------------------------------ accounts with a password (AM-81)
    def seed_password_users(self) -> list:
        """Create the configured accounts that do not exist yet; the names created. An account that exists is left alone:
        its password and roles belong to the database from then on. The initial password opens only the accounts with the
        admin role, and must be replaced at their first sign-in; the other accounts get no usable password until an admin
        gives them one, so knowing the initial password never lets one person sign in as another."""
        if self.config.mode != "password":
            return []
        created = []
        for name, roles in self.config.password_users:
            try:
                self.create_account(name, name, roles, self.config.initial_password if "admin" in roles else None, check_password=False)
                created.append(name)
            except AccountError as error:
                if error.code != "user_exists":
                    raise
        return created

    def create_account(self, username: str, display_name: str | None, roles, password: str | None, by: User | None = None,
                       request_id: str | None = None, check_password: bool = True) -> str:
        """A new account; its user id. The password is one the person did not choose, so it must be changed at the first
        sign-in; None gives the account no usable password until an admin sets one. A persona of the development login
        with the same name becomes this account, so the notes and decisions recorded under it stay with the person."""
        username = username.strip()
        display = (display_name or "").strip() or username
        roles = sorted(set(roles))
        if not re.fullmatch(USERNAME_PATTERN, username):
            raise AccountError("invalid_username", "A user name has 2 to 50 letters, digits, dots, dashes or underscores and starts "
                                                   "with a letter or a digit.")
        if not roles or set(roles) - set(ROLES):
            raise AccountError("invalid_roles", "Give at least one role among " + ", ".join(ROLES) + ".")
        problem = password_problem(password, username, display) if check_password and password is not None else None
        if problem:
            raise AccountError("weak_password", problem)
        subject, hashed = username.casefold(), hash_password(password if password is not None else secrets.token_urlsafe(32))
        with self.store.transaction() as db:
            db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("arai-account:" + subject,))
            if db.execute("SELECT 1 FROM users WHERE issuer = %s AND subject = %s", (LOCAL_ISSUER, subject)).fetchone():
                raise AccountError("user_exists", f"There is already an account named {username}.")
            adopted = db.execute("""UPDATE users SET issuer = %s, display_name = %s WHERE issuer = %s AND subject = %s
                                    RETURNING id""", (LOCAL_ISSUER, display, DEV_ISSUER, subject)).fetchone()
            user_id = adopted["id"] if adopted else new_id("usr")
            if adopted:
                db.execute("DELETE FROM user_roles WHERE user_id = %s", (user_id,))
                db.execute("UPDATE sessions SET ended_at = now(), ended_reason = 'ended_by_admin' WHERE user_id = %s AND ended_at IS NULL",
                           (user_id,))
            else:
                db.execute("INSERT INTO users (id, issuer, subject, display_name) VALUES (%s, %s, %s, %s)",
                           (user_id, LOCAL_ISSUER, subject, display))
            for role in roles:
                db.execute("INSERT INTO user_roles (user_id, role, source) VALUES (%s, %s, %s)", (user_id, role, LOCAL_SOURCE))
            db.execute("INSERT INTO password_credentials (user_id, password_hash, must_change) VALUES (%s, %s, true)", (user_id, hashed))
            self._clear_failures(db, subject)
        self.log("user_created", user_id, request_id, {**(_actor(by) or {"by_name": "configuration"}), "roles": roles,
                                                       **({"from": "development login"} if adopted else {})})
        return user_id

    # wrong passwords, counted by the name that was typed (see migration 0016): the same for a name with and without an account
    @staticmethod
    def _throttle_key(subject: str) -> str:
        return _hash("sign-in:" + subject)

    def _serialize(self, db, subject: str) -> None:
        """One sign-in or password check at a time for a name, so the count cannot be raced past its limit."""
        db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("arai-sign-in:" + self._throttle_key(subject),))

    def _locked(self, db, subject: str) -> bool:
        db.execute("DELETE FROM sign_in_throttle WHERE updated_at < now() - interval '1 day'")
        row = db.execute("SELECT locked_until IS NOT NULL AND locked_until > now() AS locked FROM sign_in_throttle WHERE subject_hash = %s",
                         (self._throttle_key(subject),)).fetchone()
        return bool(row and row["locked"])

    def _count_failure(self, db, subject: str) -> bool:
        """One more wrong password for the name; whether the name is locked now."""
        return db.execute("""
            INSERT INTO sign_in_throttle AS t (subject_hash, failed_attempts) VALUES (%(key)s, 1)
            ON CONFLICT (subject_hash) DO UPDATE SET
                locked_until = CASE WHEN t.failed_attempts + 1 >= %(max)s THEN now() + make_interval(mins => %(mins)s) ELSE t.locked_until END,
                failed_attempts = CASE WHEN t.failed_attempts + 1 >= %(max)s THEN 0 ELSE t.failed_attempts + 1 END,
                updated_at = now()
            RETURNING locked_until IS NOT NULL AND locked_until > now() AS locked""",
                          {"key": self._throttle_key(subject), "max": MAX_FAILED_SIGN_INS, "mins": LOCK_MINUTES}).fetchone()["locked"]

    def _clear_failures(self, db, subject: str) -> None:
        db.execute("DELETE FROM sign_in_throttle WHERE subject_hash = %s", (self._throttle_key(subject),))

    def sign_in_password(self, username: str, password: str, request_id: str | None = None) -> tuple:
        """(user, cookie token) for the account's password; SignInRefused otherwise. A name without an account and a wrong
        password are told apart nowhere: the same code, the same work (a hash is always computed), the same count toward
        the same lock. A locked name is refused whatever the password. The session is opened in the transaction that
        checked the password, so a change or a reset of the password cannot fall between the two."""
        if self.config.mode != "password":
            raise SignInRefused("invalid_credentials")
        subject, token = username.strip().casefold(), None
        with self.store.transaction() as db:
            self._serialize(db, subject)
            row = db.execute("""SELECT u.id, u.status, c.password_hash FROM users u JOIN password_credentials c ON c.user_id = u.id
                                WHERE u.issuer = %s AND u.subject = %s""", (LOCAL_ISSUER, subject)).fetchone()
            right = verify_password(password, row["password_hash"] if row else _NOBODY_HASH) and row is not None
            if self._locked(db, subject):
                outcome = "locked"
            elif not right:
                outcome = "wrong_and_locked" if self._count_failure(db, subject) else "wrong"
            elif row["status"] != "active":
                outcome = "disabled"
            else:
                self._clear_failures(db, subject)
                token = self._insert_session(db, row["id"])
                outcome = "ok"
        user_id = row["id"] if row else None
        if outcome == "locked":
            self.log("refused", user_id, request_id, {"status": 429, "reason": "too_many_attempts"})
            raise SignInRefused("too_many_attempts")
        if outcome in ("wrong", "wrong_and_locked"):
            self.log("refused", user_id, request_id, {"status": 401, "reason": "invalid_credentials",
                                                      **({"locked_minutes": LOCK_MINUTES} if outcome == "wrong_and_locked" else {})})
            raise SignInRefused("invalid_credentials")
        if outcome == "disabled":                  # said only to someone who knows the password
            self.log("refused", user_id, request_id, {"status": 403, "reason": "user_disabled"})
            raise SignInRefused("user_disabled")
        self.log("sign_in", user_id, request_id, {"mode": self.config.mode})
        user = self.resolve(token)[0]
        if user is None:                           # disabled or ended in the instant since: nobody is signed in
            raise SignInRefused("invalid_credentials")
        return user, token

    def change_own_password(self, user: User, current: str, new: str, request_id: str | None = None) -> None:
        """The signed-in person replaces their password, proving the current one. Their other sessions end; this one stays.
        A wrong current password counts toward the same lock as a wrong sign-in, and the wrong one that locks the name
        also ends this session: a browser left open is not a place to guess from."""
        ended, session_ended = 0, False
        with self.store.transaction() as db:
            row = db.execute("""SELECT c.password_hash, u.subject, u.display_name FROM password_credentials c
                                JOIN users u ON u.id = c.user_id WHERE c.user_id = %s""", (user.id,)).fetchone()
            if row is None:
                raise AccountError("no_password", "This account has no password in ARAI.")
            self._serialize(db, row["subject"])
            row = db.execute("""SELECT c.password_hash, u.subject, u.display_name FROM password_credentials c
                                JOIN users u ON u.id = c.user_id WHERE c.user_id = %s FOR UPDATE OF c""", (user.id,)).fetchone()
            right = verify_password(current, row["password_hash"])
            if self._locked(db, row["subject"]):
                problem = ("too_many_attempts", f"Too many wrong passwords. Try again in {LOCK_MINUTES} minutes.")
            elif not right:
                problem = ("wrong_password", "The current password is not right.")
                if self._count_failure(db, row["subject"]):
                    session_ended = bool(db.execute("""UPDATE sessions SET ended_at = now(), ended_reason = 'too_many_attempts'
                                                       WHERE id_hash = %s AND ended_at IS NULL""", (user.session_hash,)).rowcount)
            elif hmac.compare_digest(current.encode("utf-8"), new.encode("utf-8")):
                problem = ("weak_password", "The new password must differ from the current one.")
            else:
                reason = password_problem(new, row["subject"], row["display_name"])
                problem = ("weak_password", reason) if reason else None
            if problem is None:
                db.execute("UPDATE password_credentials SET password_hash = %s, must_change = false, changed_at = now() WHERE user_id = %s",
                           (hash_password(new), user.id))
                self._clear_failures(db, row["subject"])
                ended = db.execute("""UPDATE sessions SET ended_at = now(), ended_reason = 'password_changed'
                                      WHERE user_id = %s AND ended_at IS NULL AND id_hash <> %s""", (user.id, user.session_hash)).rowcount
        if problem:
            if problem[0] in ("wrong_password", "too_many_attempts"):
                self.log("refused", user.id, request_id, {"status": 429 if problem[0] == "too_many_attempts" else 403, "reason": problem[0],
                                                          **({"session_ended": True} if session_ended else {})})
            raise AccountError(*problem)
        self.log("password_changed", user.id, request_id, {"sessions_ended": ended})

    def reset_password(self, user_id: str, new: str, by: User | None = None, request_id: str | None = None) -> None:
        """An admin gives a person a new password to pass on. Every session of the person ends, a lock is lifted, and the
        person must choose their own password at the next sign-in."""
        with self.store.transaction() as db:
            row = db.execute("""SELECT u.subject, u.display_name FROM password_credentials c JOIN users u ON u.id = c.user_id
                                WHERE c.user_id = %s FOR UPDATE OF c""", (user_id,)).fetchone()
            if row is None:
                raise AccountError("no_password", "This account has no password in ARAI; it signs in another way.")
            reason = password_problem(new, row["subject"], row["display_name"])
            if reason:
                raise AccountError("weak_password", reason)
            db.execute("UPDATE password_credentials SET password_hash = %s, must_change = true, changed_at = now() WHERE user_id = %s",
                       (hash_password(new), user_id))
            self._clear_failures(db, row["subject"])
            ended = db.execute("""UPDATE sessions SET ended_at = now(), ended_reason = 'ended_by_admin'
                                  WHERE user_id = %s AND ended_at IS NULL""", (user_id,)).rowcount
        self.log("password_reset", user_id, request_id, {**_actor(by), "sessions_ended": ended})

    def set_roles(self, user_id: str, roles, by: User | None = None, request_id: str | None = None) -> None:
        """An admin sets the roles of an account with a password. They apply at the person's next request. Roles of a
        Keycloak or development-login person are not ARAI's to change."""
        roles = sorted(set(roles))
        if not roles or set(roles) - set(ROLES):
            raise AccountError("invalid_roles", "Give at least one role among " + ", ".join(ROLES) + ".")
        with self.store.transaction() as db:
            db.execute("SELECT pg_advisory_xact_lock(hashtext('arai-roles'))")       # one role edit at a time: the last-admin rule
            if not db.execute("SELECT 1 FROM users WHERE id = %s AND issuer = %s FOR UPDATE", (user_id, LOCAL_ISSUER)).fetchone():
                raise AccountError("roles_not_editable", "This person's roles come from their sign-in and are not edited in ARAI.")
            before = sorted(r["role"] for r in db.execute("DELETE FROM user_roles WHERE user_id = %s RETURNING role", (user_id,)).fetchall())
            if "admin" in before and "admin" not in roles and not db.execute(
                    """SELECT 1 FROM user_roles r JOIN users u ON u.id = r.user_id
                       WHERE r.role = 'admin' AND u.status = 'active' AND u.issuer = %s LIMIT 1""", (LOCAL_ISSUER,)).fetchone():
                raise AccountError("last_admin", "This is the only active admin; give another account the admin role first.")
            for role in roles:
                db.execute("INSERT INTO user_roles (user_id, role, source) VALUES (%s, %s, %s)", (user_id, role, LOCAL_SOURCE))
        if before != roles:
            self.log("role_change", user_id, request_id, {**_actor(by), "from": [f"{r} ({LOCAL_SOURCE})" for r in before],
                                                          "to": [f"{r} ({LOCAL_SOURCE})" for r in roles]})

    # ------------------------------------------------------------------ users and sessions
    def _upsert_user(self, issuer: str, subject: str, display_name: str, email: str | None, grants, request_id: str | None = None) -> tuple:
        """(user id, status). A person signs in through one issuer, so the roles of this sign-in replace all earlier ones;
        a change is logged as role_change (AM-71)."""
        with self.store.transaction() as db:
            row = db.execute("""INSERT INTO users (id, issuer, subject, email, display_name) VALUES (%s, %s, %s, %s, %s)
                                ON CONFLICT (issuer, subject) DO UPDATE SET display_name = EXCLUDED.display_name,
                                    email = coalesce(EXCLUDED.email, users.email)
                                RETURNING id, status, (xmax = 0) AS created""", (new_id("usr"), issuer, subject, email, display_name)).fetchone()
            before = sorted((r["role"], r["source"]) for r in db.execute(
                "DELETE FROM user_roles WHERE user_id = %s RETURNING role, source", (row["id"],)).fetchall())
            for role, source in grants:
                db.execute("INSERT INTO user_roles (user_id, role, source) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                           (row["id"], role, source))
        after = sorted(set(grants))
        if not row["created"] and before != after:
            self.log("role_change", row["id"], request_id, {"from": [f"{r} ({s})" for r, s in before], "to": [f"{r} ({s})" for r, s in after]})
        return row["id"], row["status"]

    def _insert_session(self, db, user_id: str) -> str:
        """A new session for the user inside the caller's transaction; the cookie value."""
        token = secrets.token_urlsafe(32)
        db.execute("""INSERT INTO sessions (id_hash, user_id, csrf_hash, expires_at)
                      VALUES (%s, %s, %s, now() + make_interval(hours => %s))""",
                   (_hash(token), user_id, _hash(csrf_for(token)), self.config.session_max_hours))
        db.execute("UPDATE users SET last_seen_at = now() WHERE id = %s", (user_id,))
        return token

    def _open_session(self, user_id: str, request_id: str | None) -> tuple:
        with self.store.transaction() as db:
            token = self._insert_session(db, user_id)
        self.log("sign_in", user_id, request_id, {"mode": self.config.mode})
        return self.resolve(token)[0], token

    def resolve(self, token: str | None) -> tuple:
        """(user, None) for a live session, else (None, reason): missing, unknown, ended, idle, max_age or disabled. A
        session that has run out is ended here, once, and the reason logged."""
        if not token:
            return None, "missing"
        with self.store.transaction() as db:
            row = db.execute("""SELECT s.id_hash, s.user_id, s.last_seen_at, s.expires_at, s.ended_at, s.ended_reason, now() AS now,
                                       u.display_name, u.email, u.status, u.issuer,
                                       array(SELECT role FROM user_roles r WHERE r.user_id = u.id ORDER BY role) AS roles,
                                       coalesce((SELECT c.must_change FROM password_credentials c WHERE c.user_id = u.id), false)
                                           AS must_change
                                FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.id_hash = %s""",
                             (_hash(token),)).fetchone()
            if row is None:
                return None, "unknown"
            if row["ended_at"] is not None:
                # ended by an admin: say so; an expired or signed-out session simply needs a new sign-in
                return None, row["ended_reason"] if row["ended_reason"] in ("disabled", "ended_by_admin", "password_changed", "sign_in_changed", "too_many_attempts") else "ended"
            # AM-81: where people sign in with a password, a session opened by another kind of sign-in (a persona of the
            # development login, from before the instance was switched) is not served
            reason = ("sign_in_changed" if self.config.mode == "password" and row["issuer"] != LOCAL_ISSUER
                      else "disabled" if row["status"] != "active" else "max_age" if row["now"] >= row["expires_at"]
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
                    session_hash=row["id_hash"], expires_at=row["expires_at"], must_change_password=bool(row["must_change"])), None

    @staticmethod
    def csrf_ok(token: str | None, header: str | None) -> bool:
        return bool(token and header) and hmac.compare_digest(csrf_for(token), header)

    def sign_out(self, user: User, request_id: str | None = None) -> None:
        with self.store.transaction() as db:
            db.execute("UPDATE sessions SET ended_at = now(), ended_reason = 'sign_out' WHERE id_hash = %s AND ended_at IS NULL",
                       (user.session_hash,))
        self.log("sign_out", user.id, request_id, {})

    # ------------------------------------------------------------------ people and access (contract 2.0.0, AM-71)
    def disable(self, user_id: str, by: User | None = None, request_id: str | None = None, reason: str | None = None) -> None:
        """Take a person's access away at once: every open session ends now, bearer tokens stop, and signing in again is
        refused until an admin enables them. Roles are not touched. Where ARAI keeps the accounts (AM-81), the last
        active admin cannot be disabled: nobody would be left to enable anyone."""
        with self.store.transaction() as db:
            if self.config.mode == "password":
                db.execute("SELECT pg_advisory_xact_lock(hashtext('arai-roles'))")
                admin = "SELECT 1 FROM user_roles r JOIN users u ON u.id = r.user_id WHERE r.role = 'admin' AND u.status = 'active' AND u.issuer = %s"
                if db.execute(admin + " AND u.id = %s", (LOCAL_ISSUER, user_id)).fetchone() and not db.execute(
                        admin + " AND u.id <> %s LIMIT 1", (LOCAL_ISSUER, user_id)).fetchone():
                    raise AccountError("last_admin", "This is the only active admin; give another account the admin role first.")
            db.execute("UPDATE users SET status = 'disabled' WHERE id = %s", (user_id,))
            ended = db.execute("""UPDATE sessions SET ended_at = now(), ended_reason = 'disabled'
                                  WHERE user_id = %s AND ended_at IS NULL""", (user_id,)).rowcount
        self._forget_bearer(user_id)
        self.log("user_disabled", user_id, request_id, {**_actor(by), "sessions_ended": ended, **({"reason": reason} if reason else {})})

    def enable(self, user_id: str, by: User | None = None, request_id: str | None = None, reason: str | None = None) -> None:
        """Let a disabled person sign in again. Sessions that ended when they were disabled stay ended."""
        with self.store.transaction() as db:
            db.execute("UPDATE users SET status = 'active' WHERE id = %s", (user_id,))
        self.log("user_enabled", user_id, request_id, {**_actor(by), **({"reason": reason} if reason else {})})

    def end_sessions(self, user_id: str, by: User | None = None, request_id: str | None = None, reason: str | None = None) -> int:
        """Sign a person out everywhere now (a lost laptop, a role changed in Keycloak that should apply before their session
        would expire). They may sign in again; a bearer token stays valid until it expires, so disable to stop scripts."""
        with self.store.transaction() as db:
            ended = db.execute("""UPDATE sessions SET ended_at = now(), ended_reason = 'ended_by_admin'
                                  WHERE user_id = %s AND ended_at IS NULL""", (user_id,)).rowcount
        self._forget_bearer(user_id)
        self.log("sessions_ended", user_id, request_id, {**_actor(by), "sessions_ended": ended, **({"reason": reason} if reason else {})})
        return ended

    def _forget_bearer(self, user_id: str) -> None:
        self._bearer = {k: v for k, v in self._bearer.items() if v[1].id != user_id}

    def users(self, user_id: str | None = None) -> list:
        """Everyone who has signed in or has an account, by name: roles with where each comes from, status, last request, open sessions."""
        with self.store.transaction() as db:
            return db.execute("""
                SELECT u.id, u.issuer, u.display_name, u.email, u.status, u.created_at, u.last_seen_at,
                       coalesce((SELECT json_agg(json_build_object('role', r.role, 'source', r.source) ORDER BY r.role)
                                 FROM user_roles r WHERE r.user_id = u.id), '[]'::json) AS roles,
                       (SELECT count(*) FROM sessions s WHERE s.user_id = u.id AND s.ended_at IS NULL
                            AND s.expires_at > now()
                            AND s.last_seen_at > now() - make_interval(mins => %(idle)s)) AS open_sessions,
                       (SELECT max(s.created_at) FROM sessions s WHERE s.user_id = u.id) AS last_sign_in_at,
                       coalesce((SELECT c.must_change FROM password_credentials c WHERE c.user_id = u.id), false) AS must_change,
                       coalesce((SELECT t.locked_until > now() FROM sign_in_throttle t WHERE u.issuer = %(local)s
                                     AND t.subject_hash = encode(sha256(convert_to('sign-in:' || u.subject, 'UTF8')), 'hex')), false) AS locked
                FROM users u WHERE %(id)s::text IS NULL OR u.id = %(id)s
                ORDER BY lower(u.display_name), u.id LIMIT 1000""",
                              {"idle": self.config.session_idle_minutes, "id": user_id, "local": LOCAL_ISSUER}).fetchall()

    def events(self, user_id: str | None = None, kind: str | None = None, before: int | None = None, limit: int = 50) -> list:
        """The sign-in log, newest first: sign-ins, sign-outs, ended sessions, refusals, exports, role changes, admin actions."""
        with self.store.transaction() as db:
            return db.execute("""
                SELECT e.id, e.at, e.kind, e.user_id, u.display_name, e.request_id, e.detail FROM auth_events e
                LEFT JOIN users u ON u.id = e.user_id
                WHERE (%(user)s::text IS NULL OR e.user_id = %(user)s) AND (%(kind)s::text IS NULL OR e.kind = %(kind)s)
                  AND (%(before)s::bigint IS NULL OR e.id < %(before)s)
                ORDER BY e.id DESC LIMIT %(limit)s""", {"user": user_id, "kind": kind, "before": before, "limit": limit}).fetchall()

    def log(self, kind: str, user_id: str | None, request_id: str | None, detail: dict) -> None:
        with self.store.transaction() as db:
            db.execute("INSERT INTO auth_events (kind, user_id, request_id, detail) VALUES (%s, %s, %s, %s)",
                       (kind, user_id, request_id, Jsonb(detail)))
