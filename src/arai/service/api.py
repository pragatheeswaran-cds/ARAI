"""HTTP API under /api/v1 (final-spec component 12). The bundled OpenAPI document is the contract.

The API reads results from PostgreSQL only (decision AM-39) and writes three things only: datasets, run
submissions and review notes. It has no route that trains, promotes, refunds, blocks, or edits or deletes a note.
The files it still opens are not data: the active pointer and bundle it verifies, and the bundled contract.
"""
from __future__ import annotations

import base64
import csv
import io
import logging
import os
import secrets
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import unquote

import yaml
from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from arai import bundles
from arai.operational import TABLES
from arai.paths import SPEC_ROOT
from arai.service import auth, datasets, scoring, views, worker
from arai.service.config import ServiceConfig, from_env
from arai.service.oidc import OidcError
from arai.service.store import Conflict, NotFound, Store, request_hash

log = logging.getLogger("arai.api")
PREFIX = "/api/v1"
UPLOAD_FIELDS = ("manifest", *TABLES)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: list | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details or []


STATIC_SUFFIXES = (".js", ".css", ".map", ".png", ".svg", ".ico", ".json", ".txt", ".woff", ".woff2", ".webmanifest")


def _no_nul(value):
    """Text columns cannot hold a NUL byte; a body that carries one is a 422, never a 500 from the database."""
    if isinstance(value, str) and "\x00" in value:
        raise ValueError("must not contain a NUL byte")
    return value


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())
    dataset_id: str
    model_id: str | None = None
    idempotency_key: str = Field(min_length=1, max_length=128)
    _clean = field_validator("dataset_id", "model_id", "idempotency_key")(_no_nul)


class ReviewRequest(BaseModel):
    # contract 2.0.0 (AM-71): the author is the signed-in user; reviewer_name, ignored since 1.16.0, is gone and refused (422)
    model_config = ConfigDict(extra="forbid")
    kind: Literal["note", "open", "request_approval", "approve", "reject", "feedback"] = "note"
    disposition: Literal["needs_investigation", "likely_legitimate", "unresolved"]
    note: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=1, max_length=128)
    _clean = field_validator("note", "idempotency_key")(_no_nul)


class AdminActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(None, max_length=500)
    _clean = field_validator("reason")(_no_nul)


class DevLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user: str = Field(min_length=1, max_length=100)
    _clean = field_validator("user")(_no_nul)


SESSION_ENDED = {
    "idle": "Your session ended after a period without activity. Sign in again.",
    "max_age": "Your session reached its maximum length. Sign in again.",
    "disabled": "This account is disabled. Ask an administrator.",
    "ended_by_admin": "An administrator ended your session. Sign in again.",
}
NEEDED_ROLE = {"read": "viewer", "export": "reviewer", "review": "reviewer", "decide": "approver", "manage": "admin", "administer": "admin"}
AUTH_EVENT_KINDS = ("sign_in", "sign_out", "session_ended", "refused", "export", "role_change", "user_disabled", "user_enabled",
                    "sessions_ended")


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat().replace("+00:00", "Z")


def admin_user_body(row: dict) -> dict:
    return {"user_id": row["id"], "display_name": row["display_name"], "email": row["email"],
            "sign_in": "development_login" if row["issuer"] == auth.DEV_ISSUER else "keycloak", "status": row["status"],
            "roles": [{"role": r["role"], "source": r["source"]} for r in row["roles"]], "open_sessions": int(row["open_sessions"]),
            "created_at": _iso(row["created_at"]), "last_sign_in_at": _iso(row["last_sign_in_at"]), "last_seen_at": _iso(row["last_seen_at"])}


def auth_event_body(row: dict) -> dict:
    return {"event_id": row["id"], "at": _iso(row["at"]), "kind": row["kind"], "user_id": row["user_id"],
            "display_name": row["display_name"], "request_id": row["request_id"], "detail": row["detail"] or {}}


def dataset_body(row: dict) -> dict:
    return {"dataset_id": row["id"], "world_id": row["world_id"], "manifest_hash": row["manifest_hash"],
            "schema_version": row["schema_version"], "cutoff": _iso(row["cutoff"]), "history_start": row["history_start"].isoformat(),
            "purpose": row["purpose"], "validation_status": "accepted", "customer_count": row["customer_count"]}


RUN_SUMMARY_FIELDS = {                             # Run field -> key of the summary scoring recorded; null until the run succeeded
    "review_budget": "review_budget_k", "threshold_score": "threshold_score", "median_score": "median_score",
    "mean_return_rate": "mean_return_rate", "eligible_requested_units": "eligible_requested_units",
    "eligible_purchased_units": "eligible_purchased_units", "graph_edges": "graph_edges",
    "heavy_returner_cutoff": "heavy_returner_cutoff", "community_count": "community_count", "ring_count": "ring_count",
    "styles_with_verdict": "styles_with_verdict"}


def run_body(row: dict, summary: dict | None = None, memos: dict | None = None, refunds: dict | None = None,
             previous: dict | None = None) -> dict:
    """A run as the contract shows it. `summary` is what scoring recorded, given only for a succeeded run; `memos` is how far its
    investigation memos are (null until it succeeded)."""
    summary = summary or {}
    error = None
    if row["error_code"]:
        error = {"error_code": row["error_code"], "message": row["error_message"] or "", "request_id": row["error_request_id"] or row["id"],
                 "details": []}
    return {"run_id": row["id"], "dataset_id": row["dataset_id"], "world_id": row["world_id"], "model_id": row["model_id"],
            "model_kind": row["model_kind"], "status": row["status"], "stage": row["stage"], "progress": float(row["progress"]),
            "cutoff": _iso(row["cutoff"]), "created_at": _iso(row["created_at"]), "completed_at": _iso(row["completed_at"]),
            "error": error, "eligible_count": row["eligible_count"], "excluded_count": row["excluded_count"],
            "selected_count": row["selected_count"], "model_only_count": row["model_only_count"],
            "baseline_only_count": row["baseline_only_count"], "warnings": summary.get("warnings") or [], "memos": memos,
            "stage_log": [{"stage": entry["stage"], "at": entry["at"]} for entry in (row.get("stage_log") or [])],
            "refunds": refunds, "previous_snapshot": previous,
            **{field: summary.get(key) for field, key in RUN_SUMMARY_FIELDS.items()}}


def review_body(row: dict) -> dict:
    return {"review_id": row["id"], "world_id": row["world_id"], "customer_id": row["customer_id"], "run_id": row["run_id"],
            "model_id": row["model_id"], "reviewer_name": row["reviewer_name"], "kind": row["kind"], "disposition": row["disposition"],
            "note": row["note"], "created_at": _iso(row["created_at"]),
            # contract 1.16.0 (AM-69): who wrote it, verified when it was written by a signed-in user
            "author": {"user_id": row.get("author_user_id"), "display_name": row["reviewer_name"],
                       "verified": row.get("author_user_id") is not None},
            # contract 1.15.0 (AM-68): notes follow the customer across snapshots; each says which snapshot it was written on
            "dataset_id": row["dataset_id"], "snapshot_cutoff": _iso(row["snapshot_cutoff"])}


class Service:
    """Shared state of one API process."""

    def __init__(self, config: ServiceConfig):
        self.config, self.store = config, Store(config.database_url)
        self.auth = auth.Auth(config, self.store)
        self._active_cache: tuple | None = None
        self.worker_thread = None

    def _active_signature(self, pointer: dict | None) -> tuple:
        """What the active state looks like on disk: the pointer and every file of the bundles it names."""
        root = Path(self.config.artifact_root)
        entries = []
        for path in [root / "active" / "active.json", *sorted(p for name in (pointer or {}).get("ids", [])
                                                              for p in (root / "bundles" / name).glob("*"))]:
            if path.is_file():
                stat = path.stat()
                entries.append((str(path), stat.st_mtime_ns, stat.st_size))
        return tuple(entries)

    # the active bundle, verified; the pointer file is the authority and the database mirrors it
    def sync_active(self) -> dict:
        pointer = bundles.read_active(self.config.artifact_root)
        if pointer is None:
            self._active_cache = None
            return {"pointer": None, "bundle": None, "error": "no bundle has been activated"}
        signature = self._active_signature({"ids": [i for i in (pointer["baseline_id"], pointer["model_id"]) if i]})
        if self._active_cache and self._active_cache[0] == signature:
            return self._active_cache[1]
        state = self._verify_active(pointer)
        self._active_cache = (signature, state) if state["error"] is None else None
        return state

    def _verify_active(self, pointer: dict) -> dict:
        try:
            baseline = bundles.load_bundle(pointer["baseline_id"], self.config.artifact_root)
            model = bundles.load_bundle(pointer["model_id"], self.config.artifact_root) if pointer["model_id"] else None
        except bundles.BundleError as error:
            return {"pointer": pointer, "bundle": None, "error": str(error)}
        kinds = {baseline.model_id: baseline.kind}
        if model:
            kinds[model.model_id] = model.kind
        self.store.record_active({k: pointer.get(k) for k in ("version", "model_id", "baseline_id", "selection_status", "reason")}, kinds)
        return {"pointer": pointer, "bundle": model or baseline, "error": None}

    def run_body(self, row: dict) -> dict:
        """A run as the contract shows it, with the warnings recorded when it was scored."""
        succeeded = row["status"] == "succeeded" and row["summary"] is not None
        return run_body(row, row["summary"] if row["status"] == "succeeded" else None, views.memo_progress(self.store, row),
                        self.store.run_refunds(row["id"]) if succeeded else None,
                        views.snapshot_comparison(self.store, row) if succeeded else None)

    def succeeded_run(self, run_id: str) -> dict:
        """The run, if its results can be read. Results exist exactly for succeeded runs: both are one transaction."""
        run = self.store.get_run(run_id)
        if run["error_code"] == "output_missing" or (run["status"] == "succeeded" and run["summary"] is None):
            # a run scored before results moved into the database, whose files are gone or not imported yet
            raise ApiError(409, "run_output_missing", "The results of this run are not available. Submit a retry.")
        if run["status"] != "succeeded":
            raise ApiError(409, "run_not_ready", f"Run {run_id} is {run['status']}; results exist only for succeeded runs.")
        return run


def create_app(config: ServiceConfig | None = None, with_worker: bool = False, static_dir: Path | None = None) -> FastAPI:
    """The API, optionally with the single worker and the built UI served from the same origin (local rehearsal)."""
    config = config or from_env()
    if config.oidc_problems():
        raise RuntimeError("AUTH_MODE=oidc needs " + ", ".join(config.oidc_problems()))
    service = Service(config)
    credentials = None
    if config.profile == "vm":
        user, password = os.environ.get("BASIC_AUTH_USER"), os.environ.get("BASIC_AUTH_PASSWORD")
        if not user or not password:
            raise RuntimeError("APP_PROFILE=vm requires BASIC_AUTH_USER and BASIC_AUTH_PASSWORD")
        credentials = (user, password)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service.store.migrate()
        service.sync_active()
        stop = None
        if with_worker:                                   # local profile: the one worker lives in this process
            worker.reconcile(config, service.store)       # also loads published experiments; the API itself reads no data file
            service.worker_thread, stop = worker.start_thread(config, service.store)
        yield
        if stop:
            stop.set()

    app = FastAPI(title="ARAI development API", version="1.12.0", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.service = service
    app.add_middleware(CORSMiddleware, allow_origins=list(config.ui_origins), allow_methods=["GET", "POST", "DELETE"],
                       allow_headers=["content-type", auth.CSRF_HEADER], allow_credentials=True)

    def error_response(status: int, code: str, message: str, request_id: str, details: list | None = None, headers=None):
        return JSONResponse(status_code=status, headers=headers, content={
            "error_code": code, "message": message, "request_id": request_id, "details": details or []})

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex
        if "\x00" in unquote(request.url.path) or "\x00" in unquote(request.url.query):
            return error_response(422, "invalid_request", "The request carries a NUL byte.", request.state.request_id)
        bearer = config.mode == "oidc" and request.headers.get("authorization", "").startswith("Bearer ")
        # a Keycloak bearer token passes the shared login; authorize() checks the token itself (AM-70)
        if credentials and request.method != "OPTIONS" and not bearer:
            supplied = request.headers.get("authorization", "").encode("latin-1", errors="replace")
            expected = b"Basic " + base64.b64encode(f"{credentials[0]}:{credentials[1]}".encode())
            if not secrets.compare_digest(supplied, expected):
                return error_response(401, "authentication_required", "Shared login required.", request.state.request_id,
                                      headers={"WWW-Authenticate": 'Basic realm="ARAI"'})
        try:
            response = await call_next(request)
        except Exception:                                           # never leak a stack, path or secret
            log.exception("request_id=%s unhandled error", request.state.request_id)
            return error_response(500, "internal_error", "Unexpected error. Quote the request id when reporting it.",
                                  request.state.request_id, headers={"x-request-id": request.state.request_id})
        response.headers["x-request-id"] = request.state.request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")          # results and notes are never served from a cache
        return response

    @app.exception_handler(ApiError)
    async def api_error(request: Request, error: ApiError):
        return error_response(error.status, error.code, error.message, request.state.request_id, error.details)

    @app.exception_handler(NotFound)
    async def not_found(request: Request, error: NotFound):
        return error_response(404, "not_found", error.message, request.state.request_id)

    @app.exception_handler(Conflict)
    async def conflict(request: Request, error: Conflict):
        return error_response(409, error.code, error.message, request.state.request_id)

    @app.exception_handler(views.BadCursor)
    async def bad_cursor(request: Request, error: views.BadCursor):
        return error_response(422, "invalid_cursor", str(error), request.state.request_id)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError):
        details = [{"rule_id": "request." + str(e.get("type", "invalid")), "table": None,
                    "row_key": ".".join(str(p) for p in e.get("loc", ())), "count": 1} for e in error.errors()]
        return error_response(422, "invalid_request", "The request does not match the API contract.", request.state.request_id, details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed", 413: "too_large"}.get(error.status_code, "http_error")
        message = {404: "Unknown resource.", 405: "Method not allowed."}.get(error.status_code, "Request refused.")
        return error_response(error.status_code, code, message, getattr(request.state, "request_id", uuid.uuid4().hex))

    def authorize(request: Request):
        """Every route's permission, before anything else (AM-69): public routes pass, others need a live session, a POST or
        DELETE also needs the session's CSRF token, and the user's roles must grant the route's permission. A route missing
        from auth.ROUTE_PERMISSIONS is refused."""
        path = getattr(request.scope.get("route"), "path", "")
        needed = auth.ROUTE_PERMISSIONS.get((request.method, path))
        if needed is None:
            raise ApiError(403, "forbidden", "This route has no declared permission.")
        if needed == auth.PUBLIC:
            return None
        token = request.cookies.get(auth.SESSION_COOKIE)
        header = request.headers.get("authorization", "")
        if not token and config.mode == "oidc" and header.startswith("Bearer "):
            # a script with a Keycloak access token for this API: checked on each request, no session, no CSRF token
            user, reason = service.auth.resolve_bearer(header[7:].strip(), request.state.request_id)
            if user is None:
                raise ApiError(401, "authentication_required", "The bearer token is not valid for this API (" + str(reason) + ").")
            if needed != auth.SIGNED_IN and not user.can(needed):
                service.auth.log("refused", user.id, request.state.request_id, {"status": 403, "permission": needed, "path": path})
                raise ApiError(403, "forbidden", f"This needs the {NEEDED_ROLE[needed]} role.")
            request.state.user = user
            return user
        user, reason = service.auth.resolve(token)
        if user is None:
            if token:
                service.auth.log("refused", None, request.state.request_id, {"status": 401, "reason": reason, "path": path})
            raise ApiError(401, "authentication_required", SESSION_ENDED.get(reason, "Sign in first."))
        if request.method in ("POST", "DELETE") and not auth.Auth.csrf_ok(token, request.headers.get(auth.CSRF_HEADER)):
            service.auth.log("refused", user.id, request.state.request_id, {"status": 403, "reason": "csrf", "path": path})
            raise ApiError(403, "csrf_required", "The request lacks this session's X-CSRF-Token header.")
        if needed != auth.SIGNED_IN and not user.can(needed):
            service.auth.log("refused", user.id, request.state.request_id, {"status": 403, "permission": needed, "path": path})
            raise ApiError(403, "forbidden", f"This needs the {NEEDED_ROLE[needed]} role.")
        request.state.user = user
        return user

    def me_body(user, token: str | None) -> dict:
        return {"user_id": user.id, "display_name": user.display_name, "email": user.email, "roles": list(user.roles),
                "permissions": sorted(user.permissions), "auth_mode": config.mode, "csrf_token": auth.csrf_for(token) if token else "",
                "session_expires_at": _iso(user.expires_at), "idle_minutes": config.session_idle_minutes,
                # contract 1.17.0: where signing out also ends the Keycloak session (null with the development login)
                "sso_logout_url": service.auth.oidc.logout_url() if service.auth.oidc else None}

    api = APIRouter(prefix=PREFIX, dependencies=[Depends(authorize)])
    limit_query = Query(50, ge=1, le=100)

    # ------------------------------------------------------------------ health and contract
    @api.get("/health")
    def health():
        state = service.sync_active()
        pointer, bundle = state["pointer"], state["bundle"]
        if service.worker_thread is not None and not service.worker_thread.is_alive():
            bundle = None                                 # the in-process worker has stopped: runs would queue forever
        return {"alive": True, "scoring_ready": bundle is not None,
                "promoted_model_ready": bool(bundle is not None and pointer and pointer["model_id"]),
                "model_kind": bundle.kind if bundle is not None else None,
                # the worker may be another process: a growing queue with no recent heartbeat means nothing is scoring
                "queue_depth": service.store.queue_depth(),
                "worker_seconds_since_seen": service.store.worker_seconds_since_seen()}

    # ------------------------------------------------------------------ sign-in (AM-69)
    @api.get("/auth/dev-users")
    def dev_users():
        if config.mode != "dev":
            raise ApiError(404, "not_found", "The development login is off on this instance.")
        return {"auth_mode": "dev", "users": service.auth.dev_users()}

    @api.post("/auth/dev-login")
    def dev_login(body: DevLoginRequest, request: Request, response: Response):
        if config.mode != "dev":
            raise ApiError(404, "not_found", "The development login is off on this instance.")
        try:
            signed = service.auth.sign_in_dev(body.user, request.state.request_id)
        except auth.SignInRefused:
            raise ApiError(403, "user_disabled", "This account is disabled. Ask an administrator.") from None
        if signed is None:
            raise ApiError(422, "invalid_request", "Not a user of the development login.")
        user, token = signed
        response.set_cookie(auth.SESSION_COOKIE, token, max_age=config.session_max_hours * 3600, path="/", httponly=True,
                            samesite="lax", secure=config.profile == "vm")
        return me_body(user, token)

    @api.get("/auth/login")
    def oidc_login(return_to: str = Query("/", max_length=500)):
        """Send the browser to Keycloak (AM-70). return_to is a path of this site, never another address."""
        if config.mode != "oidc":
            raise ApiError(404, "not_found", "Single sign-on is off on this instance; use the development login.")
        safe = return_to if return_to.startswith("/") and not return_to.startswith("//") and "\\" not in return_to else "/"
        try:
            return RedirectResponse(service.auth.begin_sso(safe), status_code=302)
        except OidcError as error:
            # a browser navigation, not a script: back to the sign-in page, which says Keycloak cannot be reached
            log.warning("single sign-on unavailable: %s", error.detail)
            return RedirectResponse(f"/?signin_error={error.code}", status_code=302)

    @api.get("/auth/callback")
    def oidc_callback(request: Request, code: str | None = Query(None, max_length=4000), state: str | None = Query(None, max_length=500),
                      error: str | None = Query(None, max_length=200)):
        """Keycloak's answer: a session cookie and back to the page the person came from, or the sign-in page with a reason."""
        if config.mode != "oidc":
            raise ApiError(404, "not_found", "Single sign-on is off on this instance.")
        try:
            if error or not code or not state:
                raise OidcError("sign_in_failed", f"Keycloak answered {error or 'without a code'}")
            _, token, return_to = service.auth.finish_sso(state, code, request.state.request_id)
        except OidcError as failure:
            log.warning("request_id=%s sign-in refused: %s", request.state.request_id, failure)
            return RedirectResponse(f"/?signin_error={failure.code}", status_code=302)
        response = RedirectResponse(return_to, status_code=302)
        response.set_cookie(auth.SESSION_COOKIE, token, max_age=config.session_max_hours * 3600, path="/", httponly=True,
                            samesite="lax", secure=config.profile == "vm")
        return response

    @api.post("/auth/logout", status_code=204)
    def logout(request: Request):
        service.auth.sign_out(request.state.user, request.state.request_id)
        response = Response(status_code=204)
        response.delete_cookie(auth.SESSION_COOKIE, path="/")
        return response

    # ------------------------------------------------------------------ people and access (contract 2.0.0, AM-71; admin only)
    def admin_user(user_id: str) -> dict:
        rows = service.auth.users(user_id)
        if not rows:
            raise ApiError(404, "not_found", "Unknown user.")
        return admin_user_body(rows[0])

    @api.get("/admin/users")
    def admin_users():
        """Everyone who has signed in. Roles are read-only here: they come from Keycloak groups or the development list."""
        return {"items": [admin_user_body(r) for r in service.auth.users()]}

    @api.post("/admin/users/{user_id}/disable")
    def admin_disable(request: Request, user_id: str, body: AdminActionRequest | None = None):
        admin_user(user_id)
        if user_id == request.state.user.id:
            raise ApiError(409, "cannot_disable_self", "An admin cannot disable their own account.")
        service.auth.disable(user_id, request.state.user, request.state.request_id, body.reason if body else None)
        return admin_user(user_id)

    @api.post("/admin/users/{user_id}/enable")
    def admin_enable(request: Request, user_id: str, body: AdminActionRequest | None = None):
        admin_user(user_id)
        service.auth.enable(user_id, request.state.user, request.state.request_id, body.reason if body else None)
        return admin_user(user_id)

    @api.post("/admin/users/{user_id}/end-sessions")
    def admin_end_sessions(request: Request, user_id: str, body: AdminActionRequest | None = None):
        admin_user(user_id)
        service.auth.end_sessions(user_id, request.state.user, request.state.request_id, body.reason if body else None)
        return admin_user(user_id)

    @api.get("/admin/auth-events")
    def admin_auth_events(user_id: str | None = Query(None, max_length=100), kind: str | None = Query(None, max_length=40),
                          cursor: str | None = Query(None, max_length=40), limit: int = limit_query):
        """The sign-in log, newest first. The cursor is the last event id of the page before."""
        if kind is not None and kind not in AUTH_EVENT_KINDS:
            raise ApiError(422, "invalid_request", "Unknown event kind.",
                           [{"rule_id": "request.kind", "table": None, "row_key": kind, "count": 1}])
        if cursor is not None and not cursor.isdigit():
            raise ApiError(422, "invalid_cursor", "The cursor is not one this list issued.")
        rows = service.auth.events(user_id, kind, int(cursor) if cursor else None, limit + 1)
        following = str(rows[limit - 1]["id"]) if len(rows) > limit else None
        return {"items": [auth_event_body(r) for r in rows[:limit]], "next_cursor": following}

    @api.get("/me")
    def me(request: Request):
        return me_body(request.state.user, request.cookies.get(auth.SESSION_COOKIE))

    @api.get("/openapi.json", include_in_schema=False)
    def contract():
        return yaml.safe_load((SPEC_ROOT / "contracts" / "openapi.yaml").read_text(encoding="utf-8"))

    # ------------------------------------------------------------------ datasets
    @api.get("/datasets")
    def list_datasets(cursor: str | None = None, limit: int = limit_query):
        context = {"list": "datasets"}
        after = views.decode_cursor(cursor, context, "time_id")
        rows = service.store.list_datasets((datetime.fromisoformat(after[0]), after[1]) if after else None, limit + 1)
        following = views.encode_cursor(context, [rows[limit - 1]["created_at"].isoformat(), rows[limit - 1]["id"]]) if len(rows) > limit else None
        return {"items": [dataset_body(r) for r in rows[:limit]], "next_cursor": following}

    @api.post("/datasets")
    async def register_dataset(request: Request):
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > datasets.MAX_UPLOAD_BYTES + 1_000_000:
            raise ApiError(413, "too_large", "The upload exceeds the size limit.")
        try:
            form = await request.form()
        except Exception:                                           # noqa: BLE001
            raise ApiError(422, "invalid_upload", "The upload is not valid multipart form data.") from None
        unknown = sorted(set(form.keys()) - set(UPLOAD_FIELDS))
        missing = sorted(set(UPLOAD_FIELDS) - set(form.keys()))
        if unknown or missing or len(form.multi_items()) != len(UPLOAD_FIELDS):
            details = [{"rule_id": "upload.unknown_part", "table": None, "row_key": name, "count": 1} for name in unknown] + \
                      [{"rule_id": "upload.missing_part", "table": name, "row_key": None, "count": 1} for name in missing]
            raise ApiError(422, "invalid_upload", "Upload exactly the manifest and the seven operational tables, each once.", details)
        manifest = form["manifest"]
        if not isinstance(manifest, str):
            manifest = (await manifest.read()).decode("utf-8", errors="replace")
        files = {}
        for name in TABLES:
            part = form[name]
            if isinstance(part, str):
                raise ApiError(422, "invalid_upload", f"{name} must be uploaded as a file.")
            client_name = part.filename or ""
            if any(token in client_name for token in ("/", "\\", "..")):          # the name is never used; a path is still refused
                raise ApiError(422, "invalid_upload", "File names may not contain a path.",
                               [{"rule_id": "upload.path", "table": name, "row_key": None, "count": 1}])
            files[name] = await part.read()
        try:
            # validation and storage take seconds for a full world: off the event loop, so other requests keep being served
            row, created = await run_in_threadpool(datasets.register, service.store, config.artifact_root, manifest, files)
        except datasets.TooLarge:
            raise ApiError(413, "too_large", "The upload exceeds the size or row limit.") from None
        except datasets.Rejected as rejected:
            details = [{"rule_id": v["rule_id"], "table": v["table"], "row_key": v["row_key"], "count": v["count"]}
                       for v in (rejected.report.violations if rejected.report else [])]
            raise ApiError(422, rejected.code, rejected.message, details) from None
        return JSONResponse(status_code=201 if created else 200, content=dataset_body(row))

    @api.get("/datasets/{dataset_id}")
    def get_dataset(dataset_id: str):
        return dataset_body(service.store.get_dataset(dataset_id))

    @api.delete("/datasets/{dataset_id}", status_code=204)
    def delete_dataset(dataset_id: str):
        """Remove a dataset registered by mistake, with its stored files, while no run was scored on it (409 dataset_in_use)."""
        row = service.store.delete_dataset(dataset_id)
        shutil.rmtree(Path(config.artifact_root) / row["artifact_key"], ignore_errors=True)
        return Response(status_code=204)

    # ------------------------------------------------------------------ runs
    @api.post("/runs", status_code=202)
    def submit_run(body: RunRequest):
        service.store.get_dataset(body.dataset_id)                         # unknown dataset: 404
        state = service.sync_active()
        if body.model_id is None:
            if state["pointer"] is None:
                raise ApiError(409, "no_scoring_bundle", "Neither a promoted model nor the baseline is available; scoring is blocked.")
            if state["bundle"] is None:
                raise ApiError(409, "model_not_ready", "The active model failed verification. It is not replaced by the baseline "
                                                       "silently; fix or re-promote it.")
            model_id = state["bundle"].model_id
        else:
            known = service.store.get_model(body.model_id)
            if known is None:
                raise ApiError(409, "model_not_available", "That model has never been activated here and cannot be bound to a run.")
            if known["validity"] != "valid":
                raise ApiError(409, "model_rejected", "That model was rejected and cannot be bound to a run.")
            try:
                bundles.load_bundle(body.model_id, config.artifact_root)
            except bundles.BundleError:
                raise ApiError(409, "model_not_ready", "That model's bundle failed verification.") from None
            model_id = body.model_id
        run, _ = service.store.submit_run(body.dataset_id, model_id, body.idempotency_key,
                                          request_hash({"dataset_id": body.dataset_id, "model_id": body.model_id}))
        return service.run_body(service.store.get_run(run["id"]))

    @api.get("/runs")
    def list_runs(cursor: str | None = None, limit: int = limit_query, dataset_id: str | None = None):
        context = {"list": "runs", "dataset_id": dataset_id}
        after = views.decode_cursor(cursor, context, "time_id")
        rows = service.store.list_runs(dataset_id, (datetime.fromisoformat(after[0]), after[1]) if after else None, limit + 1)
        following = views.encode_cursor(context, [rows[limit - 1]["created_at"].isoformat(), rows[limit - 1]["id"]]) if len(rows) > limit else None
        return {"items": [service.run_body(r) for r in rows[:limit]], "next_cursor": following}

    @api.get("/runs/{run_id}")
    def get_run(run_id: str):
        return service.run_body(service.store.get_run(run_id))

    @api.post("/runs/{run_id}/cancel", status_code=202)
    def cancel_run(run_id: str):
        """Stop a run that has not finished: a queued run at once, a running run at its next stage. Nothing published is touched."""
        return service.run_body(service.store.request_cancel(run_id))

    # ------------------------------------------------------------------ customers
    def queue_filters(request: Request, review_only: bool = True,
                      eligibility: Literal["all", "eligible", "insufficient_history"] = "all", search: str | None = None,
                      evidence: str | None = None,
                      disposition: Literal["all", "unreviewed", "needs_investigation", "likely_legitimate", "unresolved"] = "all",
                      comparison: Literal["all", "model_only", "baseline_only", "both"] = "all",
                      wardrobing: Literal["all", "elevated", "possible", "no_elevated_signal", "insufficient_evidence", "incomplete"] = "all",
                      community: Literal["all", "ring", "household", "none"] = "all",
                      community_id: str | None = Query(None, max_length=200),
                      tier: Literal["all", "HIGH", "MEDIUM", "LOW"] = "all",
                      gate: Literal["all", "ESCALATE", "HOLD", "WARNING", "LOW"] = "all",
                      state: Literal["all", "new", "in_review", "awaiting_approval", "approved", "rejected", "auto_logged"] = "all",
                      cleared_heavy: bool = False,
                      history: Literal["all", "new_in_queue", "repeat_in_queue", "decided_before"] = "all",
                      exclude_mine: bool = False) -> dict:
        """The queue's filters, shared by the list and its export. Filters choose what is shown, never a score or a selection."""
        if "exclude_reviewer" in request.query_params:
            # contract 2.0.0 (AM-71): a typed name is not an identity; refused rather than ignored, so no band shows the wrong cases
            raise ApiError(422, "invalid_request", "exclude_reviewer was removed in contract 2.0.0; use exclude_mine=true.",
                           [{"rule_id": "request.removed_parameter", "table": None, "row_key": "query.exclude_reviewer", "count": 1}])
        if evidence is not None and evidence not in scoring.TAGS:
            raise ApiError(422, "invalid_request", "Unknown evidence tag.",
                           [{"rule_id": "request.evidence", "table": None, "row_key": evidence, "count": 1}])
        return {"review_only": review_only, "eligibility": eligibility, "search": (search or "").strip() or None,
                "evidence": evidence, "disposition": disposition, "comparison": comparison, "wardrobing": wardrobing,
                "community": community, "community_id": (community_id or "").strip() or None, "tier": tier, "gate": gate,
                "state": state, "cleared_heavy": cleared_heavy,
                "history": history,
                # contract 1.16.0: leave out the cases the signed-in user opened (the approval band), by user id, not by name
                "exclude_user_id": getattr(request.state, "user", None).id if exclude_mine and getattr(request.state, "user", None) else None}

    @api.get("/runs/{run_id}/customers")
    def list_customers(run_id: str, cursor: str | None = None, limit: int = limit_query, filters: dict = Depends(queue_filters)):
        run = service.succeeded_run(run_id)
        context = {"list": "customers", "run_id": run_id, **filters}
        after = views.decode_cursor(cursor, context, "int")
        items, following = views.customer_queue(service.store, run, filters, after, limit)
        return {"items": items, "next_cursor": views.encode_cursor(context, following) if following is not None else None}

    @api.get("/runs/{run_id}/customers/export")
    def export_customers(request: Request, run_id: str, filters: dict = Depends(queue_filters)):
        """The filtered queue as CSV for a hand-off to the returns-policy or service team: every row, in queue order."""
        run = service.succeeded_run(run_id)
        service.auth.log("export", request.state.user.id, request.state.request_id,
                         {"run_id": run_id, "filters": {k: v for k, v in filters.items() if v not in (None, False, "all", "")}})
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\r\n")
        writer.writerow(views.EXPORT_COLUMNS)
        after = None
        while True:
            items, after = views.customer_queue(service.store, run, filters, after, 500)
            writer.writerows(views.export_row(item, run) for item in items)
            if after is None:
                break
        name = f"arai-{run['world_id']}-{run_id}-queue.csv"
        return Response(content=buffer.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @api.get("/runs/{run_id}/score-distribution")
    def get_score_distribution(run_id: str):
        """How the eligible customers' scores spread and how large the queue is at any threshold (counts, nothing recomputed)."""
        return views.score_distribution(service.store, service.succeeded_run(run_id))

    def _case_customer(run_id: str, customer_id: str) -> tuple:
        run = service.succeeded_run(run_id)
        # a customer must belong to the run (otherwise 404); its workflow is read in the run's snapshot (AM-68)
        return run, service.store.run_customer(run_id, customer_id, run["world_id"], run["dataset_id"])

    @api.get("/runs/{run_id}/customers/{customer_id}")
    def get_customer_case(run_id: str, customer_id: str):
        run, customer = _case_customer(run_id, customer_id)
        return views.case_body(service.store, run, customer, review_body)

    @api.get("/runs/{run_id}/customers/{customer_id}/reviews")
    def list_reviews(run_id: str, customer_id: str, cursor: str | None = None, limit: int = limit_query):
        run, _ = _case_customer(run_id, customer_id)
        context = {"list": "reviews", "world_id": run["world_id"], "customer_id": customer_id}
        after = views.decode_cursor(cursor, context, "time_id")
        rows = service.store.list_reviews(run["world_id"], customer_id, (datetime.fromisoformat(after[0]), after[1]) if after else None,
                                          limit + 1)
        following = views.encode_cursor(context, [rows[limit - 1]["created_at"].isoformat(), rows[limit - 1]["id"]]) if len(rows) > limit else None
        return {"items": [review_body(r) for r in rows[:limit]], "next_cursor": following}

    @api.post("/runs/{run_id}/customers/{customer_id}/reviews", status_code=201)
    def append_review(request: Request, run_id: str, customer_id: str, body: ReviewRequest):
        user = request.state.user
        if body.kind in ("approve", "reject") and not user.can("decide"):
            service.auth.log("refused", user.id, request.state.request_id, {"status": 403, "permission": "decide"})
            raise ApiError(403, "forbidden", "Approving or rejecting needs the approver role.")
        run, customer = _case_customer(run_id, customer_id)
        if body.kind in ("approve", "reject") and body.disposition == "unresolved":
            raise ApiError(422, "invalid_request", "A decision carries a reading: approve or reject with needs_investigation or "
                                                   "likely_legitimate, not unresolved.",
                           [{"rule_id": "request.decision_disposition", "table": None, "row_key": "disposition", "count": 1}])
        # the author is the signed-in user (AM-69); the stored name is the user's display name at the time of writing
        review = {"world_id": run["world_id"], "dataset_id": run["dataset_id"], "customer_id": customer_id, "run_id": run_id,
                  "model_id": run["model_id"], "reviewer_name": user.display_name, "author_user_id": user.id,
                  "disposition": body.disposition, "note": body.note, "kind": body.kind}
        if not body.note.strip():
            raise ApiError(422, "invalid_request", "A note is required.")
        row, _ = service.store.append_review(review, body.idempotency_key, request_hash(
            {"author": user.id, "disposition": body.disposition, "note": body.note, "kind": body.kind}),
            in_queue=bool(customer["selected_for_review"]))
        return review_body(row)

    # ------------------------------------------------------------------ styles
    @api.get("/runs/{run_id}/styles")
    def list_styles(run_id: str, cursor: str | None = None, limit: int = limit_query,
                    state: Literal["all", "quality", "targeting", "mixed_or_uncertain", "no_elevated_signal", "insufficient_support",
                                   "no_return_evidence"] = "all"):
        service.succeeded_run(run_id)
        context = {"list": "styles", "run_id": run_id, "state": state}
        after = views.decode_cursor(cursor, context, "text")
        items, following = views.style_queue(service.store, run_id, state, after, limit)
        return {"items": items, "next_cursor": views.encode_cursor(context, following) if following is not None else None}

    @api.get("/runs/{run_id}/styles/{style_id}")
    def get_style(run_id: str, style_id: str):
        service.succeeded_run(run_id)
        return {"run_id": run_id, **views.style_detail(service.store, run_id, style_id)}

    # ------------------------------------------------------------------ experiments (offline reports, synthetic only)
    @api.get("/experiments")
    def list_experiments(cursor: str | None = None, limit: int = limit_query):
        context = {"list": "experiments"}
        after = views.decode_cursor(cursor, context, "text")
        rows = service.store.list_experiments(after, limit + 1)
        items = [views.experiment_summary(r["report"]) for r in rows[:limit]]
        return {"items": items, "next_cursor": views.encode_cursor(context, rows[limit - 1]["id"]) if len(rows) > limit else None}

    @api.get("/experiments/{experiment_id}")
    def get_experiment(experiment_id: str):
        report = service.store.get_experiment(experiment_id)["report"]
        return {**report, "summary": views.experiment_summary(report)}

    @api.get("/experiments/{experiment_id}/curves")
    def get_evaluation_curves(experiment_id: str, run_id: str, max_points: int = Query(views.CURVE_POINTS, ge=2, le=20000)):
        """Abusers caught and legitimate heavy returners reviewed at every budget, for a run on the experiment's truth world."""
        experiment = service.store.get_experiment(experiment_id)
        run = service.succeeded_run(run_id)
        if experiment["truth_world_id"] is None or run["world_id"] != experiment["truth_world_id"]:
            raise ApiError(409, "world_mismatch", "Curves need a run scored on the experiment's demonstration world, whose synthetic "
                                                  "truth was published; this run is on another world or no truth was published.")
        if experiment.get("truth_cutoff") is not None and run["cutoff"] != experiment["truth_cutoff"]:
            raise ApiError(409, "world_mismatch", "Curves need a run on the snapshot the synthetic truth describes "
                                                  f"(cutoff {_iso(experiment['truth_cutoff'])[:10]}); this run is on another "
                                                  "snapshot of the same world, whose customers had acted less by then.")
        return views.curves(service.store, experiment, run, max_points)

    @api.get("/experiments/{experiment_id}/truth")
    def get_evaluation_truth(experiment_id: str, cursor: str | None = None, limit: int = limit_query):
        experiment = service.store.get_experiment(experiment_id)
        context = {"list": "truth", "experiment_id": experiment_id}
        after = views.decode_cursor(cursor, context, "int")
        items, following, world = views.truth_page(service.store, experiment, after, limit)
        return {"synthetic_only": True, "world_id": world, "items": items,
                "next_cursor": views.encode_cursor(context, following) if following is not None else None}

    app.include_router(api)

    if static_dir is not None:
        root = Path(static_dir).resolve()

        @app.get("/{path:path}", include_in_schema=False)
        def ui(path: str):
            if path.startswith("api/"):
                raise StarletteHTTPException(status_code=404)
            target = (root / path).resolve()
            if path and target.is_file() and root in target.parents:       # never serve anything outside the built UI
                return FileResponse(target)
            if path.startswith("assets/") or path.rsplit("/", 1)[-1].endswith(STATIC_SUFFIXES):
                raise StarletteHTTPException(status_code=404)              # a missing file is a 404, not the app shell
            return FileResponse(root / "index.html")                       # client-side routes

    return app
