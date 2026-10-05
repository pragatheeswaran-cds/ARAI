"""HTTP API under /api/v1 (final-spec component 12). The bundled OpenAPI document is the contract.

The API reads results from PostgreSQL only (decision AM-39) and writes three things only: datasets, run
submissions and review notes. It has no route that trains, promotes, refunds, blocks, or edits or deletes a note.
The files it still opens are not data: the active pointer and bundle it verifies, and the bundled contract.
"""
from __future__ import annotations

import base64
import logging
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from arai import bundles
from arai.operational import TABLES
from arai.paths import SPEC_ROOT
from arai.service import datasets, scoring, views, worker
from arai.service.config import ServiceConfig, from_env
from arai.service.store import Conflict, NotFound, Store, request_hash

log = logging.getLogger("arai.api")
PREFIX = "/api/v1"
UPLOAD_FIELDS = ("manifest", *TABLES)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: list | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details or []


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())
    dataset_id: str
    model_id: str | None = None
    idempotency_key: str = Field(min_length=1, max_length=128)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewer_name: str = Field(min_length=1, max_length=100)
    disposition: Literal["needs_investigation", "likely_legitimate", "unresolved"]
    note: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=1, max_length=128)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat().replace("+00:00", "Z")


def dataset_body(row: dict) -> dict:
    return {"dataset_id": row["id"], "world_id": row["world_id"], "manifest_hash": row["manifest_hash"],
            "schema_version": row["schema_version"], "cutoff": _iso(row["cutoff"]), "history_start": row["history_start"].isoformat(),
            "purpose": row["purpose"], "validation_status": "accepted", "customer_count": row["customer_count"]}


def run_body(row: dict, warnings: list | None = None) -> dict:
    error = None
    if row["error_code"]:
        error = {"error_code": row["error_code"], "message": row["error_message"] or "", "request_id": row["error_request_id"] or row["id"],
                 "details": []}
    return {"run_id": row["id"], "dataset_id": row["dataset_id"], "world_id": row["world_id"], "model_id": row["model_id"],
            "model_kind": row["model_kind"], "status": row["status"], "stage": row["stage"], "progress": float(row["progress"]),
            "cutoff": _iso(row["cutoff"]), "created_at": _iso(row["created_at"]), "completed_at": _iso(row["completed_at"]),
            "error": error, "eligible_count": row["eligible_count"], "excluded_count": row["excluded_count"],
            "selected_count": row["selected_count"], "model_only_count": row["model_only_count"],
            "baseline_only_count": row["baseline_only_count"], "warnings": warnings or []}


def review_body(row: dict) -> dict:
    return {"review_id": row["id"], "world_id": row["world_id"], "customer_id": row["customer_id"], "run_id": row["run_id"],
            "model_id": row["model_id"], "reviewer_name": row["reviewer_name"], "disposition": row["disposition"], "note": row["note"],
            "created_at": _iso(row["created_at"])}


class Service:
    """Shared state of one API process."""

    def __init__(self, config: ServiceConfig):
        self.config, self.store = config, Store(config.database_url)
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
        return run_body(row, (row["summary"] or {}).get("warnings", []) if row["status"] == "succeeded" else None)

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

    app = FastAPI(title="ARAI development API", version="1.2.0", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.service = service
    app.add_middleware(CORSMiddleware, allow_origins=list(config.ui_origins), allow_methods=["GET", "POST"],
                       allow_headers=["content-type"], allow_credentials=False)

    def error_response(status: int, code: str, message: str, request_id: str, details: list | None = None, headers=None):
        return JSONResponse(status_code=status, headers=headers, content={
            "error_code": code, "message": message, "request_id": request_id, "details": details or []})

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex
        if credentials and request.method != "OPTIONS":
            supplied = request.headers.get("authorization", "")
            expected = "Basic " + base64.b64encode(f"{credentials[0]}:{credentials[1]}".encode()).decode()
            if not secrets.compare_digest(supplied, expected):
                return error_response(401, "authentication_required", "Shared login required.", request.state.request_id,
                                      headers={"WWW-Authenticate": 'Basic realm="ARAI"'})
        try:
            response = await call_next(request)
        except Exception:                                           # noqa: BLE001  never leak a stack, path or secret
            log.exception("request_id=%s unhandled error", request.state.request_id)
            return error_response(500, "internal_error", "Unexpected error. Quote the request id when reporting it.",
                                  request.state.request_id, headers={"x-request-id": request.state.request_id})
        response.headers["x-request-id"] = request.state.request_id
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

    api = APIRouter(prefix=PREFIX)
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
                "model_kind": bundle.kind if bundle is not None else None}

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
            row, created = datasets.register(service.store, config.artifact_root, manifest, files)
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

    # ------------------------------------------------------------------ customers
    @api.get("/runs/{run_id}/customers")
    def list_customers(run_id: str, cursor: str | None = None, limit: int = limit_query, review_only: bool = True,
                       eligibility: Literal["all", "eligible", "insufficient_history"] = "all", search: str | None = None,
                       evidence: str | None = None,
                       disposition: Literal["all", "unreviewed", "needs_investigation", "likely_legitimate", "unresolved"] = "all",
                       comparison: Literal["all", "model_only", "baseline_only", "both"] = "all"):
        run = service.succeeded_run(run_id)
        if evidence is not None and evidence not in scoring.TAGS:
            raise ApiError(422, "invalid_request", "Unknown evidence tag.",
                           [{"rule_id": "request.evidence", "table": None, "row_key": evidence, "count": 1}])
        filters = {"review_only": review_only, "eligibility": eligibility, "search": (search or "").strip() or None,
                   "evidence": evidence, "disposition": disposition, "comparison": comparison}
        context = {"list": "customers", "run_id": run_id, **filters}
        after = views.decode_cursor(cursor, context, "int")
        items, following = views.customer_queue(service.store, run, filters, after, limit)
        return {"items": items, "next_cursor": views.encode_cursor(context, following) if following is not None else None}

    def _case_customer(run_id: str, customer_id: str) -> tuple:
        run = service.succeeded_run(run_id)
        return run, service.store.run_customer(run_id, customer_id)        # a customer must belong to the run: otherwise 404

    @api.get("/runs/{run_id}/customers/{customer_id}")
    def get_customer_case(run_id: str, customer_id: str):
        run, customer = _case_customer(run_id, customer_id)
        case = views.customer_case(service.store, run_id, customer)
        reviews = service.store.list_reviews(run["world_id"], customer_id)
        latest = reviews[-1]["disposition"] if reviews else None
        return {"run_id": run_id, "dataset_id": run["dataset_id"], "world_id": run["world_id"], "model_id": run["model_id"],
                "model_kind": run["model_kind"], "cutoff": _iso(run["cutoff"]),
                "customer": views.customer_item(customer, latest),
                "signals": case["signals"], "timeline": case["timeline"], "neighbors": case["neighbors"], "styles": case["styles"],
                "wardrobing": case["wardrobing"], "reviews": [review_body(r) for r in reviews]}

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
    def append_review(run_id: str, customer_id: str, body: ReviewRequest):
        run, _ = _case_customer(run_id, customer_id)
        review = {"world_id": run["world_id"], "customer_id": customer_id, "run_id": run_id, "model_id": run["model_id"],
                  "reviewer_name": body.reviewer_name.strip(), "disposition": body.disposition, "note": body.note}
        if not review["reviewer_name"]:
            raise ApiError(422, "invalid_request", "A reviewer name is required.")
        row, _ = service.store.append_review(review, body.idempotency_key, request_hash(
            {"reviewer_name": body.reviewer_name, "disposition": body.disposition, "note": body.note}))
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
        items = [r["report"]["summary"] for r in rows[:limit]]
        return {"items": items, "next_cursor": views.encode_cursor(context, rows[limit - 1]["id"]) if len(rows) > limit else None}

    @api.get("/experiments/{experiment_id}")
    def get_experiment(experiment_id: str):
        return service.store.get_experiment(experiment_id)["report"]

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
            return FileResponse(root / "index.html")                       # client-side routes

    return app
