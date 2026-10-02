"""PostgreSQL metadata store (final-spec component 14).

Every state change is one transaction. Scoring output lives on the filesystem; this store only ever records a
run as succeeded after its files are complete, so the database can never point at missing results.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

MIGRATIONS = Path(__file__).with_name("migrations")
STAGES = ("queued", "validate", "features", "eligibility", "scoring", "evidence", "publish", "done")


class Conflict(Exception):
    """The request conflicts with stored state (HTTP 409)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


class NotFound(Exception):
    def __init__(self, what: str):
        super().__init__(f"unknown {what}")
        self.message = f"Unknown {what}."


def request_hash(payload: dict) -> str:
    """Hash of the canonical request body, used to tell a repeat from a changed request under the same key."""
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:20]}"


class Store:
    def __init__(self, database_url: str):
        self.database_url = database_url

    @contextmanager
    def transaction(self):
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            with connection.transaction():
                yield connection

    # ------------------------------------------------------------------ schema
    def migrate(self) -> list:
        """Apply versioned migration files in order, each in its own transaction. Returns the versions applied."""
        applied = []
        with self.transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
        for path in sorted(MIGRATIONS.glob("*.sql")):
            with self.transaction() as db:
                db.execute("LOCK TABLE schema_migrations IN EXCLUSIVE MODE")
                if db.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (path.stem,)).fetchone():
                    continue
                db.execute(path.read_text(encoding="utf-8"))
                db.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,))
                applied.append(path.stem)
        return applied

    def schema_version(self) -> str | None:
        with self.transaction() as db:
            row = db.execute("SELECT max(version) AS version FROM schema_migrations").fetchone()
        return row["version"]

    # ------------------------------------------------------------------ datasets
    def register_dataset(self, row: dict) -> tuple:
        """(dataset, created). The same world with the same content returns the existing row; other content conflicts."""
        with self.transaction() as db:
            db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("dataset:" + row["world_id"],))
            existing = db.execute("SELECT * FROM datasets WHERE world_id = %s", (row["world_id"],)).fetchone()
            if existing:
                if existing["manifest_hash"] == row["manifest_hash"]:
                    return existing, False
                raise Conflict("world_content_differs", f"World {row['world_id']} is already registered with different content; "
                                                        "a world's content is immutable.")
            created = db.execute(
                """INSERT INTO datasets (id, world_id, manifest_hash, schema_version, cutoff, history_start, purpose, customer_count, artifact_key)
                   VALUES (%(id)s, %(world_id)s, %(manifest_hash)s, %(schema_version)s, %(cutoff)s, %(history_start)s, %(purpose)s,
                           %(customer_count)s, %(artifact_key)s) RETURNING *""", row).fetchone()
            return created, True

    def dataset_by_world(self, world_id: str) -> dict | None:
        with self.transaction() as db:
            return db.execute("SELECT * FROM datasets WHERE world_id = %s", (world_id,)).fetchone()

    def get_dataset(self, dataset_id: str) -> dict:
        with self.transaction() as db:
            row = db.execute("SELECT * FROM datasets WHERE id = %s", (dataset_id,)).fetchone()
        if not row:
            raise NotFound("dataset")
        return row

    def list_datasets(self, after: tuple | None, limit: int) -> list:
        with self.transaction() as db:
            if after:
                return db.execute("SELECT * FROM datasets WHERE (created_at, id) < (%s, %s) ORDER BY created_at DESC, id DESC LIMIT %s",
                                  (*after, limit)).fetchall()
            return db.execute("SELECT * FROM datasets ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()

    # ------------------------------------------------------------------ models and the active pointer
    def record_active(self, pointer: dict, kinds: dict) -> None:
        """Mirror the verified filesystem pointer into the database (the pointer file stays the authority)."""
        with self.transaction() as db:
            for model_id, kind in kinds.items():
                db.execute("""INSERT INTO models (id, kind, metadata_key, validity) VALUES (%s, %s, %s, 'valid')
                              ON CONFLICT (id) DO NOTHING""", (model_id, kind, f"bundles/{model_id}/bundle.json"))
            db.execute("""INSERT INTO active_model (id, version, model_id, baseline_id, selection_status, reason)
                          VALUES (1, %(version)s, %(model_id)s, %(baseline_id)s, %(selection_status)s, %(reason)s)
                          ON CONFLICT (id) DO UPDATE SET version = EXCLUDED.version, model_id = EXCLUDED.model_id,
                              baseline_id = EXCLUDED.baseline_id, selection_status = EXCLUDED.selection_status,
                              reason = EXCLUDED.reason, updated_at = now()
                          WHERE active_model.version <> EXCLUDED.version""", pointer)

    def reject_model(self, model_id: str, kind: str) -> None:
        """Record a model that must never be bound to a run (an explicitly rejected candidate)."""
        with self.transaction() as db:
            db.execute("""INSERT INTO models (id, kind, metadata_key, validity) VALUES (%s, %s, %s, 'rejected')
                          ON CONFLICT (id) DO UPDATE SET validity = 'rejected'""", (model_id, kind, f"bundles/{model_id}/bundle.json"))

    def get_model(self, model_id: str) -> dict | None:
        with self.transaction() as db:
            return db.execute("SELECT * FROM models WHERE id = %s", (model_id,)).fetchone()

    def active(self) -> dict | None:
        with self.transaction() as db:
            return db.execute("SELECT * FROM active_model WHERE id = 1").fetchone()

    # ------------------------------------------------------------------ runs
    def submit_run(self, dataset_id: str, model_id: str, idempotency_key: str, body_hash: str, retry_of: str | None = None) -> tuple:
        """(run, created). Binding and the idempotency record are written together or not at all."""
        scope = f"runs:{dataset_id}"
        with self.transaction() as db:
            db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (scope + "|" + idempotency_key,))
            seen = db.execute("SELECT * FROM idempotency WHERE scope = %s AND key = %s", (scope, idempotency_key)).fetchone()
            if seen:
                if seen["request_hash"] != body_hash:
                    raise Conflict("idempotency_conflict", "This idempotency key was already used with a different request.")
                return db.execute("SELECT * FROM runs WHERE id = %s", (seen["response_ref"],)).fetchone(), False
            run = db.execute("""INSERT INTO runs (id, dataset_id, model_id, status, stage, retry_of)
                                VALUES (%s, %s, %s, 'queued', 'queued', %s) RETURNING *""",
                             (new_id("run"), dataset_id, model_id, retry_of)).fetchone()
            db.execute("INSERT INTO idempotency (scope, key, request_hash, response_ref) VALUES (%s, %s, %s, %s)",
                       (scope, idempotency_key, body_hash, run["id"]))
            return run, True

    def get_run(self, run_id: str) -> dict:
        with self.transaction() as db:
            row = db.execute("""SELECT r.*, d.world_id, d.cutoff, m.kind AS model_kind FROM runs r
                                JOIN datasets d ON d.id = r.dataset_id JOIN models m ON m.id = r.model_id WHERE r.id = %s""",
                             (run_id,)).fetchone()
        if not row:
            raise NotFound("run")
        return row

    def list_runs(self, dataset_id: str | None, after: tuple | None, limit: int) -> list:
        clauses, values = [], []
        if dataset_id:
            clauses.append("r.dataset_id = %s")
            values.append(dataset_id)
        if after:
            clauses.append("(r.created_at, r.id) < (%s, %s)")
            values += list(after)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self.transaction() as db:
            return db.execute(f"""SELECT r.*, d.world_id, d.cutoff, m.kind AS model_kind FROM runs r
                                  JOIN datasets d ON d.id = r.dataset_id JOIN models m ON m.id = r.model_id {where}
                                  ORDER BY r.created_at DESC, r.id DESC LIMIT %s""", (*values, limit)).fetchall()

    def claim_next_run(self, worker_id: str) -> dict | None:
        """Atomically take the oldest queued run. Two workers can never both own one run."""
        with self.transaction() as db:
            return db.execute("""UPDATE runs SET status = 'running', stage = 'validate', claimed_by = %s, started_at = now()
                                 WHERE id = (SELECT id FROM runs WHERE status = 'queued' ORDER BY created_at, id
                                             FOR UPDATE SKIP LOCKED LIMIT 1)
                                 RETURNING *""", (worker_id,)).fetchone()

    def update_stage(self, run_id: str, stage: str, progress: float) -> None:
        with self.transaction() as db:
            db.execute("UPDATE runs SET stage = %s, progress = %s WHERE id = %s AND status = 'running'", (stage, progress, run_id))

    def finish_run(self, run_id: str, worker_id: str, output_key: str, counts: dict) -> bool:
        """Mark success. Called only after the output directory is complete and in place."""
        with self.transaction() as db:
            done = db.execute("""UPDATE runs SET status = 'succeeded', stage = 'done', progress = 1, completed_at = now(), output_key = %s,
                                     eligible_count = %s, excluded_count = %s, selected_count = %s, model_only_count = %s,
                                     baseline_only_count = %s
                                 WHERE id = %s AND status = 'running' AND claimed_by = %s RETURNING id""",
                              (output_key, counts["eligible_count"], counts["excluded_count"], counts["selected_count"],
                               counts["model_only_count"], counts["baseline_only_count"], run_id, worker_id)).fetchone()
        return done is not None

    def fail_run(self, run_id: str, code: str, message: str, request_id: str) -> None:
        with self.transaction() as db:
            db.execute("""UPDATE runs SET status = 'failed', completed_at = now(), error_code = %s, error_message = %s, error_request_id = %s
                          WHERE id = %s AND status = 'running'""", (code, message, request_id, run_id))

    def interrupt_running(self, worker_id: str) -> list:
        """At startup a run this worker still holds as running belongs to its own earlier process, which died.

        Runs held by another worker identity are left alone: they may be running right now.
        """
        with self.transaction() as db:
            rows = db.execute("""UPDATE runs SET status = 'interrupted', completed_at = now(), error_code = 'interrupted',
                                     error_message = 'The scoring process stopped before this run finished. Submit a retry.',
                                     error_request_id = id
                                 WHERE status = 'running' AND claimed_by = %s RETURNING id""", (worker_id,)).fetchall()
        return [row["id"] for row in rows]

    def run_statuses(self) -> dict:
        """Every run this database knows, with its status."""
        with self.transaction() as db:
            return {row["id"]: row["status"] for row in db.execute("SELECT id, status FROM runs").fetchall()}

    def mark_output_missing(self, run_id: str) -> None:
        with self.transaction() as db:
            db.execute("""UPDATE runs SET status = 'failed', error_code = 'output_missing', error_request_id = id,
                              error_message = 'The published results of this run are no longer on disk. Submit a retry.'
                          WHERE id = %s AND status = 'succeeded'""", (run_id,))

    def queue_depth(self) -> int:
        with self.transaction() as db:
            return db.execute("SELECT count(*) AS n FROM runs WHERE status IN ('queued', 'running')").fetchone()["n"]

    # ------------------------------------------------------------------ reviews (append only)
    def append_review(self, review: dict, idempotency_key: str, body_hash: str) -> tuple:
        scope = f"reviews:{review['world_id']}:{review['customer_id']}"
        with self.transaction() as db:
            db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (scope + "|" + idempotency_key,))
            seen = db.execute("SELECT * FROM idempotency WHERE scope = %s AND key = %s", (scope, idempotency_key)).fetchone()
            if seen:
                if seen["request_hash"] != body_hash:
                    raise Conflict("idempotency_conflict", "This idempotency key was already used with a different note.")
                return db.execute("SELECT * FROM reviews WHERE id = %s", (seen["response_ref"],)).fetchone(), False
            row = db.execute("""INSERT INTO reviews (id, world_id, customer_id, run_id, model_id, reviewer_name, disposition, note)
                                VALUES (%(id)s, %(world_id)s, %(customer_id)s, %(run_id)s, %(model_id)s, %(reviewer_name)s,
                                        %(disposition)s, %(note)s) RETURNING *""", dict(review, id=new_id("rev"))).fetchone()
            db.execute("INSERT INTO idempotency (scope, key, request_hash, response_ref) VALUES (%s, %s, %s, %s)",
                       (scope, idempotency_key, body_hash, row["id"]))
            return row, True

    def list_reviews(self, world_id: str, customer_id: str, after: tuple | None = None, limit: int | None = None) -> list:
        """Notes for a customer of a world, oldest first, whichever run they were written under."""
        values = [world_id, customer_id]
        extra = ""
        if after:
            extra = " AND (created_at, id) > (%s, %s)"
            values += list(after)
        tail = ""
        if limit is not None:
            tail = " LIMIT %s"
            values.append(limit)
        with self.transaction() as db:
            return db.execute(f"SELECT * FROM reviews WHERE world_id = %s AND customer_id = %s{extra} ORDER BY created_at, id{tail}",
                              values).fetchall()

    def latest_dispositions(self, world_id: str) -> dict:
        with self.transaction() as db:
            rows = db.execute("""SELECT DISTINCT ON (customer_id) customer_id, disposition FROM reviews WHERE world_id = %s
                                 ORDER BY customer_id, created_at DESC, id DESC""", (world_id,)).fetchall()
        return {row["customer_id"]: row["disposition"] for row in rows}

    # ------------------------------------------------------------------ experiments
    def upsert_experiment(self, row: dict) -> None:
        with self.transaction() as db:
            db.execute("""INSERT INTO experiments (id, config_hash, report_key, selection_key, test_key)
                          VALUES (%(id)s, %(config_hash)s, %(report_key)s, %(selection_key)s, %(test_key)s)
                          ON CONFLICT (id) DO UPDATE SET config_hash = EXCLUDED.config_hash, report_key = EXCLUDED.report_key,
                              selection_key = EXCLUDED.selection_key, test_key = EXCLUDED.test_key""", row)

    def list_experiments(self, after: str | None, limit: int) -> list:
        with self.transaction() as db:
            if after:
                return db.execute("SELECT * FROM experiments WHERE id > %s ORDER BY id LIMIT %s", (after, limit)).fetchall()
            return db.execute("SELECT * FROM experiments ORDER BY id LIMIT %s", (limit,)).fetchall()

    def get_experiment(self, experiment_id: str) -> dict:
        with self.transaction() as db:
            row = db.execute("SELECT * FROM experiments WHERE id = %s", (experiment_id,)).fetchone()
        if not row:
            raise NotFound("experiment")
        return row
