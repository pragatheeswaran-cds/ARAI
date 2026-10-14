"""PostgreSQL store (final-spec component 14).

Every state change is one transaction. Run results live here too (decision AM-39): a run's rows are written in
the transaction that marks it succeeded, so a succeeded run always has its results and no other run has any.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

MIGRATIONS = Path(__file__).with_name("migrations")
STAGES = ("queued", "validate", "features", "eligibility", "scoring", "evidence", "publish", "done")
RESULT_TABLES = ("run_customers", "run_styles", "run_skus", "run_neighbors", "run_timeline", "run_customer_styles")


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
            # the API and the worker start together and both migrate: CREATE TABLE IF NOT EXISTS is not safe to race
            db.execute("SELECT pg_advisory_xact_lock(hashtext('arai:migrate'))")
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

    def _copy(self, db, table: str, key: tuple, columns: list, rows) -> None:
        """Bulk-load rows of one table; `key` is the leading (column, value) every row shares."""
        with db.cursor() as cursor:
            with cursor.copy(f"COPY {table} ({', '.join([key[0], *columns])}) FROM STDIN") as copy:
                for row in rows:
                    copy.write_row((key[1], *row))

    def _write_results(self, db, run_id: str, tables: dict) -> None:
        if set(tables) != set(RESULT_TABLES):
            raise ValueError("a run publishes exactly its six result tables")
        for table in RESULT_TABLES:
            columns, rows = tables[table]
            self._copy(db, table, ("run_id", run_id), columns, rows)

    def finish_run(self, run_id: str, worker_id: str, summary: dict, counts: dict, tables: dict) -> bool:
        """Publish the results and mark success in one transaction. False if this worker no longer owns the run."""
        with self.transaction() as db:
            owned = db.execute("SELECT id FROM runs WHERE id = %s AND status = 'running' AND claimed_by = %s FOR UPDATE",
                               (run_id, worker_id)).fetchone()
            if owned is None:
                return False
            self._write_results(db, run_id, tables)
            db.execute("""UPDATE runs SET status = 'succeeded', stage = 'done', progress = 1, completed_at = now(), summary = %s,
                              eligible_count = %s, excluded_count = %s, selected_count = %s, model_only_count = %s,
                              baseline_only_count = %s
                          WHERE id = %s""",
                       (Jsonb(summary), counts["eligible_count"], counts["excluded_count"], counts["selected_count"],
                        counts["model_only_count"], counts["baseline_only_count"], run_id))
        return True

    def runs_without_results(self) -> list:
        """Succeeded runs from before results moved into the database: their rows still have to be imported."""
        with self.transaction() as db:
            rows = db.execute("SELECT id FROM runs WHERE status = 'succeeded' AND summary IS NULL ORDER BY created_at, id").fetchall()
        return [row["id"] for row in rows]

    def import_results(self, run_id: str, summary: dict, tables: dict) -> bool:
        """Load the results of an earlier succeeded run from its files, once. Status and counts stay as recorded."""
        with self.transaction() as db:
            claimed = db.execute("""UPDATE runs SET summary = %s WHERE id = %s AND status = 'succeeded' AND summary IS NULL
                                    RETURNING id""", (Jsonb(summary), run_id)).fetchone()
            if claimed is None:
                return False
            self._write_results(db, run_id, tables)
        return True

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

    def mark_output_missing(self, run_id: str) -> None:
        """An earlier succeeded run whose result files were lost before they could be imported."""
        with self.transaction() as db:
            db.execute("""UPDATE runs SET status = 'failed', error_code = 'output_missing', error_request_id = id,
                              error_message = 'The results of this run were never loaded into the database. Submit a retry.'
                          WHERE id = %s AND status = 'succeeded' AND summary IS NULL""", (run_id,))

    def queue_depth(self) -> int:
        """Runs waiting for the worker or being scored."""
        with self.transaction() as db:
            return db.execute("SELECT count(*) AS n FROM runs WHERE status IN ('queued', 'running')").fetchone()["n"]

    def heartbeat(self, worker_id: str) -> None:
        """The worker says it is alive: at startup, on every pass of its loop and at every stage of a run."""
        with self.transaction() as db:
            db.execute("""INSERT INTO workers (worker_id) VALUES (%s)
                          ON CONFLICT (worker_id) DO UPDATE SET seen_at = now()""", (worker_id,))

    def worker_seconds_since_seen(self) -> float | None:
        """Seconds since any worker last reported; None if no worker ever has."""
        with self.transaction() as db:
            row = db.execute("SELECT extract(epoch FROM now() - max(seen_at)) AS age FROM workers").fetchone()
        return None if row["age"] is None else max(0.0, float(row["age"]))

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

    # ------------------------------------------------------------------ run results (written once, read by the API)
    def run_customers(self, run_id: str, world_id: str, filters: dict, after: int | None, limit: int) -> list:
        """One page of the queue in queue order, each row with the customer's latest disposition in this world.

        Filters only choose what is shown. `search` is a case-insensitive substring of the identifier.
        """
        clauses, values = ["c.run_id = %s"], [world_id, run_id]
        if filters["review_only"]:
            clauses.append("c.selected_for_review")
        if filters["eligibility"] != "all":
            clauses.append("c.eligibility_status = %s")
            values.append(filters["eligibility"])
        if filters["search"]:
            escaped = filters["search"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append("c.customer_id ILIKE %s")
            values.append(f"%{escaped}%")
        if filters["evidence"]:
            clauses.append("%s = ANY (c.evidence_tags)")
            values.append(filters["evidence"])
        if filters.get("wardrobing", "all") != "all":
            clauses.append("c.wardrobing_status = %s")
            values.append(filters["wardrobing"])
        comparison = {"model_only": "c.selected_for_review AND NOT c.baseline_selected",
                      "baseline_only": "c.baseline_selected AND NOT c.selected_for_review",
                      "both": "c.selected_for_review AND c.baseline_selected"}.get(filters["comparison"])
        if comparison:
            clauses.append(comparison)
        if filters["disposition"] == "unreviewed":
            clauses.append("latest.disposition IS NULL")
        elif filters["disposition"] != "all":
            clauses.append("latest.disposition = %s")
            values.append(filters["disposition"])
        if after is not None:
            clauses.append("c.queue_position > %s")
            values.append(after)
        with self.transaction() as db:
            return db.execute(f"""SELECT c.*, latest.disposition AS latest_disposition FROM run_customers c
                                  LEFT JOIN LATERAL (SELECT r.disposition FROM reviews r
                                                     WHERE r.world_id = %s AND r.customer_id = c.customer_id
                                                     ORDER BY r.created_at DESC, r.id DESC LIMIT 1) latest ON true
                                  WHERE {' AND '.join(clauses)} ORDER BY c.queue_position LIMIT %s""", (*values, limit)).fetchall()

    def run_customer(self, run_id: str, customer_id: str) -> dict:
        with self.transaction() as db:
            row = db.execute("SELECT * FROM run_customers WHERE run_id = %s AND customer_id = %s", (run_id, customer_id)).fetchone()
        if not row:
            raise NotFound("customer in this run")
        return row

    def run_timeline(self, run_id: str, customer_id: str) -> list:
        with self.transaction() as db:
            return db.execute("SELECT * FROM run_timeline WHERE run_id = %s AND customer_id = %s ORDER BY seq",
                              (run_id, customer_id)).fetchall()

    def run_neighbors(self, run_id: str, customer_id: str) -> list:
        """The customer's supported edges, each with the neighbour's own result in this run (score, rank, selection, tags)."""
        with self.transaction() as db:
            return db.execute("""SELECT e.*, n.risk_score AS neighbor_risk_score, n.rank AS neighbor_rank,
                                        n.selected_for_review AS neighbor_selected_for_review, n.evidence_tags AS neighbor_evidence_tags
                                 FROM run_neighbors e
                                 LEFT JOIN run_customers n ON n.run_id = e.run_id AND n.customer_id = e.neighbor_id
                                 WHERE e.run_id = %s AND e.customer_id = %s ORDER BY e.neighbor_id COLLATE "C" """,
                              (run_id, customer_id)).fetchall()

    def score_distribution(self, run_id: str, bins: int, top: float) -> list:
        """Eligible customers of a run counted into equal-width score bins over [0, top]; a score of `top` falls in the last bin.

        Rows: {bin (1-based), count, selected_count}, only for bins that hold a customer.
        """
        with self.transaction() as db:
            return db.execute("""SELECT least(width_bucket(risk_score, 0, %s, %s), %s) AS bin, count(*) AS count,
                                        count(*) FILTER (WHERE selected_for_review) AS selected_count
                                 FROM run_customers WHERE run_id = %s AND eligibility_status = 'eligible' AND risk_score IS NOT NULL
                                 GROUP BY bin ORDER BY bin""", (top, bins, bins, run_id)).fetchall()

    def run_customer_styles(self, run_id: str, customer_id: str, limit: int) -> list:
        """The styles a customer returned or claimed on, linked claims first, with each style's evidence."""
        order = 'o.linked_claim_lines DESC, o.claim_lines DESC, o.requested_units DESC, o.style_id COLLATE "C"'
        with self.transaction() as db:
            return db.execute(f"""SELECT s.* FROM (SELECT * FROM run_customer_styles o WHERE o.run_id = %s AND o.customer_id = %s
                                                   ORDER BY {order} LIMIT %s) o
                                  JOIN run_styles s ON s.run_id = o.run_id AND s.style_id = o.style_id
                                  ORDER BY {order}""", (run_id, customer_id, limit)).fetchall()

    def run_styles(self, run_id: str, state: str, after: str | None, limit: int) -> list:
        clauses, values = ["run_id = %s"], [run_id]
        if state != "all":
            clauses.append("state = %s")
            values.append(state)
        if after is not None:
            clauses.append('style_id COLLATE "C" > %s')
            values.append(after)
        with self.transaction() as db:
            return db.execute(f"""SELECT * FROM run_styles WHERE {' AND '.join(clauses)} ORDER BY style_id COLLATE "C" LIMIT %s""",
                              (*values, limit)).fetchall()

    def run_style(self, run_id: str, style_id: str) -> dict:
        with self.transaction() as db:
            row = db.execute("SELECT * FROM run_styles WHERE run_id = %s AND style_id = %s", (run_id, style_id)).fetchone()
        if not row:
            raise NotFound("style in this run")
        return row

    def run_style_skus(self, run_id: str, style_id: str) -> list:
        with self.transaction() as db:
            return db.execute('SELECT * FROM run_skus WHERE run_id = %s AND style_id = %s ORDER BY sku COLLATE "C"',
                              (run_id, style_id)).fetchall()

    def run_style_customers(self, run_id: str, style_id: str, limit: int) -> list:
        """Customers with a request on a style, those with linked claims first."""
        with self.transaction() as db:
            rows = db.execute("""SELECT customer_id FROM run_customer_styles WHERE run_id = %s AND style_id = %s
                                 ORDER BY linked_claim_lines DESC, claim_lines DESC, requested_units DESC, customer_id COLLATE "C"
                                 LIMIT %s""", (run_id, style_id, limit)).fetchall()
        return [row["customer_id"] for row in rows]

    # ------------------------------------------------------------------ experiments (published offline, loaded by the worker)
    def load_experiment(self, row: dict, report: dict, truth_world_id: str | None, truth_rows: list) -> None:
        """Store a published experiment report and replace its truth export, together."""
        with self.transaction() as db:
            db.execute("""INSERT INTO experiments (id, config_hash, report_key, selection_key, test_key, report, truth_world_id)
                          VALUES (%(id)s, %(config_hash)s, %(report_key)s, %(selection_key)s, %(test_key)s, %(report)s, %(truth_world_id)s)
                          ON CONFLICT (id) DO UPDATE SET config_hash = EXCLUDED.config_hash, report_key = EXCLUDED.report_key,
                              selection_key = EXCLUDED.selection_key, test_key = EXCLUDED.test_key, report = EXCLUDED.report,
                              truth_world_id = EXCLUDED.truth_world_id""",
                       dict(row, report=Jsonb(report), truth_world_id=truth_world_id))
            db.execute("DELETE FROM experiment_truth WHERE experiment_id = %s", (row["id"],))
            self._copy(db, "experiment_truth", ("experiment_id", row["id"]), ["position", "customer_id", "y_abuse", "action_types"],
                       truth_rows)

    def list_experiments(self, after: str | None, limit: int) -> list:
        with self.transaction() as db:
            if after:
                return db.execute("SELECT * FROM experiments WHERE report IS NOT NULL AND id > %s ORDER BY id LIMIT %s",
                                  (after, limit)).fetchall()
            return db.execute("SELECT * FROM experiments WHERE report IS NOT NULL ORDER BY id LIMIT %s", (limit,)).fetchall()

    def get_experiment(self, experiment_id: str) -> dict:
        with self.transaction() as db:
            row = db.execute("SELECT * FROM experiments WHERE id = %s AND report IS NOT NULL", (experiment_id,)).fetchone()
        if not row:
            raise NotFound("experiment")
        return row

    def experiment_truth(self, experiment_id: str, after: int | None, limit: int) -> list:
        with self.transaction() as db:
            return db.execute("SELECT * FROM experiment_truth WHERE experiment_id = %s AND position >= %s ORDER BY position LIMIT %s",
                              (experiment_id, after or 0, limit)).fetchall()
