"""PostgreSQL store (final-spec component 14).

Every state change is one transaction. Run results live here too (decision AM-39): a run's rows are written in
the transaction that marks it succeeded, so a succeeded run always has its results and no other run has any.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

MIGRATIONS = Path(__file__).with_name("migrations")
STAGES = ("queued", "validate", "features", "eligibility", "scoring", "evidence", "publish", "done")
RESULT_TABLES = ("run_customers", "run_styles", "run_skus", "run_neighbors", "run_timeline", "run_customer_styles", "run_communities",
                 "run_attributions", "run_style_reasons")


COMMUNITY_FIELDS = "k.kind AS community_kind, k.size AS community_size"   # of the community a customer row belongs to
# the tier and gate-outcome rules as SQL over a customer row c joined to its community k; views.tier and views.gate_outcome
# are the same rules in Python, and the service test checks that the two agree on every customer of a run
TIER_SQL = {"HIGH": "c.selected_for_review",
            "MEDIUM": "c.eligibility_status = 'eligible' AND NOT c.selected_for_review AND c.risk_score >= %(medium_from)s",
            "LOW": "c.eligibility_status = 'eligible' AND NOT c.selected_for_review AND c.risk_score < %(medium_from)s"}
_ESCALATE = "(coalesce(k.kind, '') = 'ring' OR c.wardrobing_status = 'elevated')"
_WARNING = "(c.risk_score >= %(medium_from)s OR (%(heavy_cutoff)s IS NOT NULL AND (c.measures->>'raw_return_rate')::double precision >= %(heavy_cutoff)s))"
# review kinds (frontend data plan WP6): a note or feedback never changes the workflow; the other four are its events
REVIEW_KINDS = ("note", "open", "request_approval", "approve", "reject", "feedback")
WORKFLOW_KINDS = ("open", "request_approval", "approve", "reject")
SECOND_REVIEWER_MESSAGE = "You opened this case. A different reviewer must approve or reject it."
CASE_NOT_OPEN_MESSAGE = "Open the case first: approval, rejection and a request for approval follow an open."
CASE_ALREADY_OPEN_MESSAGE = "This case is already open. Approve or reject it, request approval, or add a note."
APPROVAL_ALREADY_REQUESTED_MESSAGE = "Approval was already requested for this case; a different reviewer approves or rejects it."
CASE_DECIDED_MESSAGE = "This case was already decided. Reopen it before deciding again."
OUT_OF_SCOPE_MESSAGE = ("Open, request approval, approve and reject apply to a customer selected for review; feedback applies to the "
                        "customers outside the queue.")


def snapshot_conflict_message(world_id: str, cutoff) -> str:
    return (f"World {world_id} already has a snapshot at cutoff {cutoff} with different content; a snapshot's content is "
            "immutable. A later export of the same customers is a new snapshot with its own cutoff.")


def same_reviewer(a: str, b: str) -> bool:
    """Reviewer names are free text: the second-reviewer rule compares them without regard to case or spacing."""
    return " ".join(a.split()).casefold() == " ".join(b.split()).casefold()
# the latest workflow event and the latest open of a customer in this snapshot of its world (decision AM-68: the workflow
# runs per snapshot, notes span them), joined to a customer row c; placeholders in order: world, snapshot, world, snapshot
WORKFLOW_JOINS = """LEFT JOIN LATERAL (SELECT w.kind, w.reviewer_name, w.created_at FROM reviews w
                                      WHERE w.world_id = %s AND w.dataset_id = %s AND w.customer_id = c.customer_id
                                        AND w.kind IN ('open', 'request_approval', 'approve', 'reject')
                                      ORDER BY w.created_at DESC, w.id DESC LIMIT 1) wf ON true
                   LEFT JOIN LATERAL (SELECT o.reviewer_name, o.author_user_id, o.created_at FROM reviews o
                                      WHERE o.world_id = %s AND o.dataset_id = %s AND o.customer_id = c.customer_id AND o.kind = 'open'
                                      ORDER BY o.created_at DESC, o.id DESC LIMIT 1) opened ON true"""
WORKFLOW_FIELDS = ("wf.kind AS workflow_kind, wf.reviewer_name AS workflow_reviewer, wf.created_at AS workflow_at, "
                   "opened.reviewer_name AS opened_by, opened.author_user_id AS opened_by_user_id, opened.created_at AS opened_at")
# the state rule as SQL (views.workflow is the same rule in Python): with no event, a customer the gate leaves at LOW or
# WARNING (eligible and not selected) is auto_logged and every other customer is new
_NO_EVENT = "wf.kind IS NULL"
STATE_SQL = {"in_review": "wf.kind = 'open'", "awaiting_approval": "wf.kind = 'request_approval'", "approved": "wf.kind = 'approve'",
             "rejected": "wf.kind = 'reject'",
             "auto_logged": f"{_NO_EVENT} AND c.eligibility_status = 'eligible' AND NOT c.selected_for_review",
             "new": f"{_NO_EVENT} AND NOT (c.eligibility_status = 'eligible' AND NOT c.selected_for_review)"}
# a customer's place against earlier snapshots of its world (decision AM-68); %(previous_run)s is the reference run of the
# previous snapshot (null when there is none), %(world_id)s and %(cutoff)s the current snapshot's
_IN_PREVIOUS_QUEUE = ("EXISTS (SELECT 1 FROM run_customers p WHERE p.run_id = %(previous_run)s AND p.customer_id = c.customer_id "
                      "AND p.selected_for_review)")
_DECIDED_BEFORE = ("EXISTS (SELECT 1 FROM datasets d WHERE d.world_id = %(world_id)s AND d.cutoff < %(cutoff)s AND "
                   "(SELECT w.kind FROM reviews w WHERE w.world_id = d.world_id AND w.dataset_id = d.id AND w.customer_id = c.customer_id "
                   "AND w.kind IN ('open', 'request_approval', 'approve', 'reject') ORDER BY w.created_at DESC, w.id DESC LIMIT 1) "
                   "IN ('approve', 'reject'))")
HISTORY_SQL = {"new_in_queue": f"c.selected_for_review AND NOT {_IN_PREVIOUS_QUEUE}",
               "repeat_in_queue": f"c.selected_for_review AND {_IN_PREVIOUS_QUEUE}",
               "decided_before": _DECIDED_BEFORE}
GATE_SQL = {"ESCALATE": f"c.selected_for_review AND {_ESCALATE}", "HOLD": f"c.selected_for_review AND NOT {_ESCALATE}",
            "WARNING": f"c.eligibility_status = 'eligible' AND NOT c.selected_for_review AND {_WARNING}",
            "LOW": f"c.eligibility_status = 'eligible' AND NOT c.selected_for_review AND NOT {_WARNING}"}


class Cancelled(Exception):
    """The run's cancel was requested; the worker stops at the stage that saw it."""


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
        """(dataset, created). A dataset is one snapshot of a world, at its cutoff (decision AM-68): the same snapshot with the
        same content returns the existing row, the same snapshot with other content conflicts, another cutoff of the same
        world is a new snapshot."""
        with self.transaction() as db:
            db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("dataset:" + row["world_id"],))
            existing = db.execute("SELECT * FROM datasets WHERE world_id = %s AND cutoff = %s::timestamptz",
                                  (row["world_id"], row["cutoff"])).fetchone()
            if existing:
                if existing["manifest_hash"] == row["manifest_hash"]:
                    return existing, False
                raise Conflict("world_content_differs", snapshot_conflict_message(row["world_id"], row["cutoff"]))
            created = db.execute(
                """INSERT INTO datasets (id, world_id, manifest_hash, schema_version, cutoff, history_start, purpose, customer_count, artifact_key)
                   VALUES (%(id)s, %(world_id)s, %(manifest_hash)s, %(schema_version)s, %(cutoff)s, %(history_start)s, %(purpose)s,
                           %(customer_count)s, %(artifact_key)s) RETURNING *""", row).fetchone()
            return created, True

    def delete_dataset(self, dataset_id: str) -> dict:
        """Remove a registered dataset no run was scored on; returns its row so the caller can remove its files. A dataset with
        runs is kept (409 dataset_in_use): runs, their results and review notes refer to it."""
        with self.transaction() as db:
            db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("dataset-delete:" + dataset_id,))
            row = db.execute("SELECT * FROM datasets WHERE id = %s", (dataset_id,)).fetchone()
            if not row:
                raise NotFound("dataset")
            used = db.execute("SELECT count(*) AS n FROM runs WHERE dataset_id = %s", (dataset_id,)).fetchone()["n"]
            if used:
                raise Conflict("dataset_in_use", f"{used} run(s) were scored on this dataset; a dataset with runs is kept.")
            db.execute("DELETE FROM datasets WHERE id = %s", (dataset_id,))
        return row

    # ------------------------------------------------------------------ refunds paid, from the stored timeline (contract 1.14.0)
    def refund_totals(self, run_id: str, customer_ids: list) -> dict:
        """customer_id -> {refunded, claim_refunded, known}: refunds paid on the customer's return lines with status refunded,
        and the part paid on transaction-claim lines. `known` is false for a run scored before line statuses were stored.
        A customer with no return line is absent from the result (nothing refunded)."""
        if not customer_ids:
            return {}
        with self.transaction() as db:
            rows = db.execute("""SELECT customer_id,
                                        coalesce(sum(amount_inr) FILTER (WHERE line_status = 'refunded'), 0) AS refunded,
                                        coalesce(sum(amount_inr) FILTER (WHERE line_status = 'refunded'
                                                                           AND event_type = 'transaction_claim'), 0) AS claim_refunded,
                                        bool_and(line_status IS NOT NULL) AS known
                                 FROM run_timeline WHERE run_id = %s AND customer_id = ANY(%s) AND event_type <> 'purchase'
                                 GROUP BY customer_id""", (run_id, list(customer_ids))).fetchall()
        return {row["customer_id"]: row for row in rows}

    def run_refunds(self, run_id: str) -> dict | None:
        """Refunds paid to the review set and to the set the return-rate rule would select, for the Overview; None for a run
        scored before line statuses were stored."""
        with self.transaction() as db:
            known = db.execute("""SELECT bool_and(line_status IS NOT NULL) AS known FROM run_timeline
                                  WHERE run_id = %s AND event_type <> 'purchase'""", (run_id,)).fetchone()["known"]
            if known is False:
                return None
            out = {}
            for name, column in (("review_set", "selected_for_review"), ("rule_set", "baseline_selected")):
                row = db.execute(f"""SELECT (SELECT count(*) FROM run_customers WHERE run_id = %s AND {column}) AS customers,
                                            coalesce(sum(t.amount_inr) FILTER (WHERE t.line_status = 'refunded'), 0) AS refunded,
                                            coalesce(sum(t.amount_inr) FILTER (WHERE t.line_status = 'refunded'
                                                                                 AND t.event_type = 'transaction_claim'), 0) AS claims
                                     FROM run_timeline t JOIN run_customers c ON c.run_id = t.run_id AND c.customer_id = t.customer_id
                                     WHERE t.run_id = %s AND t.event_type <> 'purchase' AND c.{column}""", (run_id, run_id)).fetchone()
                out[name] = {"customers": int(row["customers"]), "refunded_inr": round(float(row["refunded"]), 2),
                             "claim_refunded_inr": round(float(row["claims"]), 2)}
        return out

    # ------------------------------------------------------------------ demo housekeeping (arai db-clean)
    def counts(self) -> dict:
        """How much the database holds, for the clean-up command's report: datasets, runs, result rows, reviews, memos."""
        with self.transaction() as db:
            out = {name: db.execute(f"SELECT count(*) AS n FROM {name}").fetchone()["n"]
                   for name in ("datasets", "runs", "reviews", "run_memos", "models", "experiments")}
            out["result_rows"] = sum(db.execute(f"SELECT count(*) AS n FROM {name}").fetchone()["n"] for name in RESULT_TABLES)
            out["worlds"] = [r["world_id"] for r in db.execute("SELECT DISTINCT world_id FROM datasets ORDER BY world_id").fetchall()]
        return out

    def wipe(self, notes: bool = False, runs: bool = False, datasets: bool = False, world_id: str | None = None) -> dict:
        """Remove demo state, in one transaction: review notes, runs with their results and memos, registered datasets.

        Models, the active pointer, experiments and the worker heartbeat stay. `world_id` narrows every part to one world.
        Runs cannot go without the notes written under them (a note names its origin run), so `runs` also removes those
        notes; datasets cannot go while a run refers to them, so `datasets` without `runs` removes only datasets with no
        run. Returns what was removed, with the artifact keys of the removed datasets so the caller can delete their files.
        """
        removed = {"reviews": 0, "runs": 0, "result_rows": 0, "memos": 0, "datasets": [], "idempotency": 0}
        scope = " WHERE world_id = %s" if world_id else ""
        values = (world_id,) if world_id else ()
        with self.transaction() as db:
            if notes:
                removed["reviews"] += db.execute(f"DELETE FROM reviews{scope}", values).rowcount
            if runs:
                gone = [r["id"] for r in db.execute(f"SELECT id FROM runs{scope}", values).fetchall()]
                if gone:
                    removed["reviews"] += db.execute("DELETE FROM reviews WHERE run_id = ANY(%s)", (gone,)).rowcount
                    removed["memos"] += db.execute("DELETE FROM run_memos WHERE run_id = ANY(%s)", (gone,)).rowcount
                    for name in RESULT_TABLES:
                        removed["result_rows"] += db.execute(f"DELETE FROM {name} WHERE run_id = ANY(%s)", (gone,)).rowcount
                    db.execute("UPDATE runs SET retry_of = NULL WHERE retry_of = ANY(%s)", (gone,))
                    removed["runs"] += db.execute("DELETE FROM runs WHERE id = ANY(%s)", (gone,)).rowcount
            if datasets:
                rows = db.execute(f"""SELECT id, world_id, artifact_key FROM datasets d{scope}{' AND' if scope else ' WHERE'}
                                     NOT EXISTS (SELECT 1 FROM runs r WHERE r.dataset_id = d.id)""", values).fetchall()
                for row in rows:
                    db.execute("DELETE FROM datasets WHERE id = %s", (row["id"],))
                    removed["datasets"].append({"id": row["id"], "world_id": row["world_id"], "artifact_key": row["artifact_key"]})
            # idempotency records whose answer no longer exists
            removed["idempotency"] = db.execute("""DELETE FROM idempotency WHERE response_ref NOT IN (SELECT id FROM runs)
                                                   AND response_ref NOT IN (SELECT id FROM reviews)""").rowcount
        return removed

    def dataset_by_snapshot(self, world_id: str, cutoff: str) -> dict | None:
        with self.transaction() as db:
            return db.execute("SELECT * FROM datasets WHERE world_id = %s AND cutoff = %s::timestamptz", (world_id, cutoff)).fetchone()

    # ------------------------------------------------------------------ snapshots of a world and a customer's history (AM-68)
    def snapshots(self, world_id: str) -> list:
        """Every snapshot of a world with a succeeded run, oldest cutoff first, each with its reference run: the latest
        succeeded run on that snapshot."""
        with self.transaction() as db:
            return db.execute("""SELECT DISTINCT ON (d.cutoff) d.id AS dataset_id, d.cutoff, r.id AS run_id, r.model_id, m.kind AS model_kind
                                 FROM datasets d JOIN runs r ON r.dataset_id = d.id AND r.status = 'succeeded'
                                 JOIN models m ON m.id = r.model_id
                                 WHERE d.world_id = %s ORDER BY d.cutoff, r.created_at DESC, r.id DESC""", (world_id,)).fetchall()

    def previous_rows(self, run_id: str, dataset_id: str, world_id: str, customer_ids: list) -> dict:
        """customer_id -> the customer's row in the run `run_id` of an earlier snapshot, with the last workflow event of that
        snapshot. Customers who were not in that snapshot are absent."""
        if not customer_ids:
            return {}
        with self.transaction() as db:
            rows = db.execute(f"""SELECT c.customer_id, c.rank, c.risk_score, c.selected_for_review, c.eligibility_status,
                                         wf.kind AS workflow_kind, wf.reviewer_name AS workflow_reviewer, wf.created_at AS workflow_at
                                  FROM run_customers c {WORKFLOW_JOINS}
                                  WHERE c.run_id = %s AND c.customer_id = ANY(%s)""",
                              (world_id, dataset_id, world_id, dataset_id, run_id, list(customer_ids))).fetchall()
        return {row["customer_id"]: row for row in rows}

    def earlier_decisions(self, world_id: str, cutoff, customer_ids: list) -> dict:
        """customer_id -> the latest snapshot before `cutoff` whose workflow ended in a decision: {kind, reviewer_name,
        created_at, cutoff}. A snapshot whose last workflow event is an open or a request for approval ended undecided."""
        if not customer_ids:
            return {}
        with self.transaction() as db:
            rows = db.execute("""SELECT DISTINCT ON (customer_id) customer_id, kind, reviewer_name, created_at, cutoff FROM (
                                     SELECT DISTINCT ON (w.customer_id, w.dataset_id) w.customer_id, w.kind, w.reviewer_name,
                                            w.created_at, d.cutoff
                                     FROM reviews w JOIN datasets d ON d.id = w.dataset_id
                                     WHERE w.world_id = %s AND d.cutoff < %s AND w.customer_id = ANY(%s)
                                       AND w.kind IN ('open', 'request_approval', 'approve', 'reject')
                                     ORDER BY w.customer_id, w.dataset_id, w.created_at DESC, w.id DESC) last
                                 WHERE kind IN ('approve', 'reject') ORDER BY customer_id, cutoff DESC""",
                              (world_id, cutoff, list(customer_ids))).fetchall()
        return {row["customer_id"]: row for row in rows}

    def snapshot_comparison(self, run_id: str, previous_run_id: str, world_id: str, cutoff) -> dict:
        """The review set against the previous snapshot's: customers in both, new to it, gone from it; and how many customers
        of the current review set were decided in an earlier snapshot, by decision."""
        with self.transaction() as db:
            row = db.execute("""SELECT count(*) FILTER (WHERE c.selected_for_review AND p.selected_for_review) AS repeat,
                                       count(*) FILTER (WHERE c.selected_for_review AND NOT coalesce(p.selected_for_review, false)) AS new,
                                       count(*) FILTER (WHERE p.selected_for_review AND NOT coalesce(c.selected_for_review, false)) AS left
                                FROM (SELECT customer_id, selected_for_review FROM run_customers WHERE run_id = %s) c
                                FULL JOIN (SELECT customer_id, selected_for_review FROM run_customers WHERE run_id = %s) p
                                  ON p.customer_id = c.customer_id""", (run_id, previous_run_id)).fetchone()
            queued = [r["customer_id"] for r in db.execute("SELECT customer_id FROM run_customers WHERE run_id = %s AND selected_for_review",
                                                           (run_id,)).fetchall()]
        decided = self.earlier_decisions(world_id, cutoff, queued)
        return {"repeat": row["repeat"], "new": row["new"], "left": row["left"],
                "approved_before": sum(d["kind"] == "approve" for d in decided.values()),
                "rejected_before": sum(d["kind"] == "reject" for d in decided.values())}

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
            return db.execute("""UPDATE runs SET status = 'running', stage = 'validate', claimed_by = %s, started_at = now(),
                                     stage_log = jsonb_build_array(jsonb_build_object('stage', 'validate', 'at', now()))
                                 WHERE id = (SELECT id FROM runs WHERE status = 'queued' ORDER BY created_at, id
                                             FOR UPDATE SKIP LOCKED LIMIT 1)
                                 RETURNING *""", (worker_id,)).fetchone()

    def update_stage(self, run_id: str, stage: str, progress: float) -> None:
        """Record the stage and when it began. Raises Cancelled when a cancel was requested, so the worker stops here."""
        with self.transaction() as db:
            row = db.execute("""UPDATE runs SET stage = %s, progress = %s,
                                    stage_log = CASE WHEN stage = %s THEN stage_log
                                                     ELSE stage_log || jsonb_build_object('stage', %s::text, 'at', now()) END
                                WHERE id = %s AND status = 'running' RETURNING cancel_requested""",
                             (stage, progress, stage, stage, run_id)).fetchone()
        if row and row["cancel_requested"]:
            raise Cancelled(run_id)

    def request_cancel(self, run_id: str) -> dict:
        """Cancel a run: a queued run is interrupted at once; a running run is asked to stop at its next stage. Returns the run.
        A run that has finished raises Conflict (run_finished)."""
        with self.transaction() as db:
            row = db.execute("SELECT status FROM runs WHERE id = %s FOR UPDATE", (run_id,)).fetchone()
            if row is None:
                raise NotFound("run")
            if row["status"] == "queued":
                db.execute("""UPDATE runs SET status = 'interrupted', completed_at = now(), error_code = 'cancelled',
                                  error_message = 'Cancelled before scoring started.', error_request_id = id, cancel_requested = true
                              WHERE id = %s""", (run_id,))
            elif row["status"] == "running":
                db.execute("UPDATE runs SET cancel_requested = true WHERE id = %s", (run_id,))
            else:
                raise Conflict("run_finished", f"Run {run_id} is {row['status']}; only a queued or running run can be cancelled.")
        return self.get_run(run_id)

    def cancel_run(self, run_id: str, worker_id: str) -> None:
        """The worker stopped a running run at a stage because its cancel was requested. No result was written."""
        with self.transaction() as db:
            db.execute("""UPDATE runs SET status = 'interrupted', completed_at = now(), error_code = 'cancelled',
                              error_message = 'Cancelled while scoring. No partial result was kept.', error_request_id = id
                          WHERE id = %s AND status = 'running' AND claimed_by = %s""", (run_id, worker_id))

    def _copy(self, db, table: str, key: tuple, columns: list, rows) -> None:
        """Bulk-load rows of one table; `key` is the leading (column, value) every row shares."""
        with db.cursor() as cursor:
            with cursor.copy(f"COPY {table} ({', '.join([key[0], *columns])}) FROM STDIN") as copy:
                for row in rows:
                    copy.write_row((key[1], *row))

    def _write_results(self, db, run_id: str, tables: dict) -> None:
        if set(tables) != set(RESULT_TABLES):
            raise ValueError("a run publishes exactly its nine result tables")
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
    def append_review(self, review: dict, idempotency_key: str, body_hash: str, in_queue: bool | None = None) -> tuple:
        """(review, created). Append-only. The workflow rules hold under one lock per customer of a world, so concurrent
        calls see each other's events in order:

        - open needs a case that is not open (409 case_already_open while it is in review or awaiting approval);
        - request_approval, approve and reject need an open case (409 case_not_open), one that is not yet decided
          (409 case_decided; a reopen comes first), and approval cannot be requested twice (409 case_already_open);
        - the reviewer who made the latest open can neither approve nor reject (409 second_reviewer_required, a fixed
          message the UI shows as it is); names compare without regard to case or spacing;
        - when `in_queue` is given, the four workflow kinds apply only to a customer selected for review and feedback only
          to the others (409 out_of_scope). A note is always allowed."""
        scope = f"reviews:{review['world_id']}:{review['customer_id']}"
        snapshot = review["dataset_id"]                                      # the workflow runs per snapshot (AM-68)
        with self.transaction() as db:
            db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (scope,))                # one customer's reviews at a time
            seen = db.execute("SELECT * FROM idempotency WHERE scope = %s AND key = %s", (scope, idempotency_key)).fetchone()
            if seen:
                if seen["request_hash"] != body_hash:
                    raise Conflict("idempotency_conflict", "This idempotency key was already used with a different note.")
                return db.execute("""SELECT v.*, d.cutoff AS snapshot_cutoff FROM reviews v JOIN datasets d ON d.id = v.dataset_id
                                     WHERE v.id = %s""", (seen["response_ref"],)).fetchone(), False
            kind = review["kind"]
            if in_queue is not None and ((kind in WORKFLOW_KINDS and not in_queue) or (kind == "feedback" and in_queue)):
                raise Conflict("out_of_scope", OUT_OF_SCOPE_MESSAGE)
            if kind in WORKFLOW_KINDS:
                latest = db.execute("""SELECT kind, reviewer_name FROM reviews WHERE world_id = %s AND customer_id = %s
                                         AND dataset_id = %s AND kind = ANY(%s) ORDER BY created_at DESC, id DESC LIMIT 1""",
                                    (review["world_id"], review["customer_id"], snapshot, list(WORKFLOW_KINDS))).fetchone()
                state = latest["kind"] if latest else None                       # the latest workflow event is the state
                if kind == "open":
                    if state in ("open", "request_approval"):
                        raise Conflict("case_already_open", CASE_ALREADY_OPEN_MESSAGE)
                else:
                    if state is None:
                        raise Conflict("case_not_open", CASE_NOT_OPEN_MESSAGE)
                    if state in ("approve", "reject"):
                        raise Conflict("case_decided", CASE_DECIDED_MESSAGE)
                    if kind == "request_approval" and state == "request_approval":
                        raise Conflict("case_already_open", APPROVAL_ALREADY_REQUESTED_MESSAGE)
                    opened = db.execute("""SELECT reviewer_name, author_user_id FROM reviews WHERE world_id = %s AND customer_id = %s AND dataset_id = %s
                                           AND kind = 'open' ORDER BY created_at DESC, id DESC LIMIT 1""",
                                        (review["world_id"], review["customer_id"], snapshot)).fetchone()
                    # the same person by user id (AM-69); an open written before sign-in existed has no user id, so its name decides
                    same = (opened["author_user_id"] == review.get("author_user_id") if opened["author_user_id"]
                            else same_reviewer(opened["reviewer_name"], review["reviewer_name"]))
                    if kind != "request_approval" and same:
                        raise Conflict("second_reviewer_required", SECOND_REVIEWER_MESSAGE)
            row = db.execute("""WITH added AS (
                                    INSERT INTO reviews (id, world_id, customer_id, run_id, model_id, reviewer_name, disposition, note, kind,
                                                         dataset_id, author_user_id)
                                    VALUES (%(id)s, %(world_id)s, %(customer_id)s, %(run_id)s, %(model_id)s, %(reviewer_name)s,
                                            %(disposition)s, %(note)s, %(kind)s, %(dataset_id)s, %(author_user_id)s) RETURNING *)
                                SELECT added.*, d.cutoff AS snapshot_cutoff FROM added JOIN datasets d ON d.id = added.dataset_id""",
                             dict({"author_user_id": None, **review}, id=new_id("rev"))).fetchone()
            db.execute("INSERT INTO idempotency (scope, key, request_hash, response_ref) VALUES (%s, %s, %s, %s)",
                       (scope, idempotency_key, body_hash, row["id"]))
            return row, True

    def list_reviews(self, world_id: str, customer_id: str, after: tuple | None = None, limit: int | None = None) -> list:
        """Notes for a customer of a world, oldest first, whichever run and snapshot they were written under; each row carries
        the cutoff of its snapshot."""
        values = [world_id, customer_id]
        extra = ""
        if after:
            extra = " AND (v.created_at, v.id) > (%s, %s)"
            values += list(after)
        tail = ""
        if limit is not None:
            tail = " LIMIT %s"
            values.append(limit)
        with self.transaction() as db:
            return db.execute(f"""SELECT v.*, d.cutoff AS snapshot_cutoff FROM reviews v JOIN datasets d ON d.id = v.dataset_id
                                  WHERE v.world_id = %s AND v.customer_id = %s{extra} ORDER BY v.created_at, v.id{tail}""",
                              values).fetchall()

    # ------------------------------------------------------------------ run results (written once, read by the API)
    def run_customers(self, run_id: str, world_id: str, filters: dict, after: int | None, limit: int, rules: dict | None = None,
                      dataset_id: str | None = None) -> list:
        """One page of the queue in queue order, each row with the customer's latest disposition in this world and its workflow
        in this snapshot (`dataset_id`).

        Filters only choose what is shown. `search` is a case-insensitive substring of the identifier. `rules` holds
        the run's numbers the tier, gate and history filters read (medium_from, heavy_cutoff, previous_run, world_id, cutoff).
        """
        clauses, values = ["c.run_id = %s"], [world_id, run_id]
        rules = rules or {}
        if filters.get("state", "all") != "all":
            clauses.append(STATE_SQL[filters["state"]])
        if filters.get("exclude_reviewer"):
            clauses.append("coalesce(opened.reviewer_name, '') <> %s")
            values.append(filters["exclude_reviewer"])
        if filters.get("exclude_user_id"):                      # the cases the signed-in user did not open (AM-69)
            clauses.append("coalesce(opened.author_user_id, '') <> %s")
            values.append(filters["exclude_user_id"])
        for name, table in (("tier", TIER_SQL), ("gate", GATE_SQL), ("history", HISTORY_SQL)):
            if filters.get(name, "all") != "all":
                clause = table[filters[name]]
                values += [rules[key] for key in re.findall(r"%\((\w+)\)s", clause)]       # one value per placeholder, in order
                clauses.append(re.sub(r"%\(\w+\)s", "%s", clause))
        if filters["review_only"]:
            clauses.append("c.selected_for_review")
        if filters.get("cleared_heavy"):                      # eligible, outside the queue, at or above the run's heavy-returner cutoff
            clauses.append("c.eligibility_status = 'eligible' AND NOT c.selected_for_review AND %s IS NOT NULL "
                           "AND (c.measures->>'raw_return_rate')::double precision >= %s")
            values += [rules.get("heavy_cutoff"), rules.get("heavy_cutoff")]
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
        if filters.get("community", "all") == "none":
            clauses.append("c.community_id IS NULL")
        elif filters.get("community", "all") != "all":
            clauses.append("k.kind = %s")
            values.append(filters["community"])
        if filters.get("community_id"):
            clauses.append("c.community_id = %s")
            values.append(filters["community_id"])
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
            joins = WORKFLOW_JOINS
            return db.execute(f"""SELECT c.*, latest.disposition AS latest_disposition, {COMMUNITY_FIELDS}, {WORKFLOW_FIELDS}
                                  FROM run_customers c
                                  LEFT JOIN run_communities k ON k.run_id = c.run_id AND k.community_id = c.community_id
                                  LEFT JOIN LATERAL (SELECT r.disposition FROM reviews r
                                                     WHERE r.world_id = %s AND r.customer_id = c.customer_id
                                                     ORDER BY r.created_at DESC, r.id DESC LIMIT 1) latest ON true
                                  {joins}
                                  WHERE {' AND '.join(clauses)} ORDER BY c.queue_position LIMIT %s""",
                              (world_id, world_id, dataset_id, world_id, dataset_id, *values[1:], limit)).fetchall()

    def run_customer(self, run_id: str, customer_id: str, world_id: str | None = None, dataset_id: str | None = None) -> dict:
        """The customer's result row, with the kind and size of the community it belongs to and, given the world and snapshot,
        the latest workflow event and open of its reviews in that snapshot (null columns without one)."""
        with self.transaction() as db:
            row = db.execute(f"""SELECT c.*, {COMMUNITY_FIELDS}, {WORKFLOW_FIELDS} FROM run_customers c
                                 LEFT JOIN run_communities k ON k.run_id = c.run_id AND k.community_id = c.community_id
                                 {WORKFLOW_JOINS}
                                 WHERE c.run_id = %s AND c.customer_id = %s""",
                             (world_id, dataset_id, world_id, dataset_id, run_id, customer_id)).fetchone()
        if not row:
            raise NotFound("customer in this run")
        return row

    # ------------------------------------------------------------------ memos (written after the run succeeded, one row per selected customer)
    def selected_customer_ids(self, run_id: str) -> list:
        with self.transaction() as db:
            rows = db.execute("SELECT customer_id FROM run_customers WHERE run_id = %s AND selected_for_review ORDER BY queue_position",
                              (run_id,)).fetchall()
        return [row["customer_id"] for row in rows]

    def write_memo(self, run_id: str, row: dict) -> None:
        """Store a decided memo; a second decision for the same customer replaces the first (a restart that redoes memos)."""
        with self.transaction() as db:
            db.execute("""INSERT INTO run_memos (run_id, customer_id, status, attempts, reason, model, generated_at, memo)
                          VALUES (%(run_id)s, %(customer_id)s, %(status)s, %(attempts)s, %(reason)s, %(model)s, %(generated_at)s, %(memo)s)
                          ON CONFLICT (run_id, customer_id) DO UPDATE SET status = EXCLUDED.status, attempts = EXCLUDED.attempts,
                              reason = EXCLUDED.reason, model = EXCLUDED.model, generated_at = EXCLUDED.generated_at, memo = EXCLUDED.memo""",
                       dict(row, run_id=run_id, memo=Jsonb(row["memo"]) if row["memo"] is not None else None))

    def run_memo(self, run_id: str, customer_id: str) -> dict | None:
        with self.transaction() as db:
            return db.execute("SELECT * FROM run_memos WHERE run_id = %s AND customer_id = %s", (run_id, customer_id)).fetchone()

    def memo_counts(self, run_id: str) -> dict:
        """{ok, unavailable}: how many memos of a run are decided either way."""
        with self.transaction() as db:
            rows = db.execute("SELECT status, count(*) AS n FROM run_memos WHERE run_id = %s GROUP BY status", (run_id,)).fetchall()
        counts = {"ok": 0, "unavailable": 0}
        for row in rows:
            counts[row["status"]] = int(row["n"])
        return counts

    def run_attributions(self, run_id: str, customer_id: str) -> list:
        """The customer's score with each feature family at typical values, in family order; empty for an unranked customer."""
        with self.transaction() as db:
            return db.execute("SELECT * FROM run_attributions WHERE run_id = %s AND customer_id = %s ORDER BY family",
                              (run_id, customer_id)).fetchall()

    def run_community(self, run_id: str, community_id: str) -> dict | None:
        """One community of a run with its members' own results, members in queue order; None if the run has no such community."""
        with self.transaction() as db:
            row = db.execute("SELECT * FROM run_communities WHERE run_id = %s AND community_id = %s", (run_id, community_id)).fetchone()
            if row is None:
                return None
            row["members"] = db.execute("""SELECT customer_id, risk_score, rank, selected_for_review, eligibility_status,
                                                  mature_requested_units, mature_purchased_units, evidence_tags
                                           FROM run_customers WHERE run_id = %s AND community_id = %s ORDER BY queue_position""",
                                        (run_id, community_id)).fetchall()
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

    def run_style_reasons(self, run_id: str, style_ids: list) -> dict:
        """style_id -> its reason rows, most units first (the order they were written in)."""
        if not style_ids:
            return {}
        with self.transaction() as db:
            rows = db.execute("""SELECT * FROM run_style_reasons WHERE run_id = %s AND style_id = ANY (%s)
                                 ORDER BY style_id, units DESC, lines DESC, reason_code""", (run_id, list(style_ids))).fetchall()
        out = {style_id: [] for style_id in style_ids}
        for row in rows:
            out[row["style_id"]].append(row)
        return out

    def run_style_returners(self, run_id: str, style_id: str, limit: int) -> list:
        """Customers with a request on a style, those with linked claims first, each with its own result and community in the run."""
        with self.transaction() as db:
            return db.execute(f"""SELECT o.customer_id, o.requested_units, o.claim_lines, o.linked_claim_lines, o.return_lines, o.purchased_lines,
                                         o.last_reason_code, c.risk_score, c.rank, c.selected_for_review, c.eligibility_status, c.community_id,
                                         {COMMUNITY_FIELDS}
                                  FROM run_customer_styles o
                                  JOIN run_customers c ON c.run_id = o.run_id AND c.customer_id = o.customer_id
                                  LEFT JOIN run_communities k ON k.run_id = c.run_id AND k.community_id = c.community_id
                                  WHERE o.run_id = %s AND o.style_id = %s
                                  ORDER BY o.linked_claim_lines DESC, o.claim_lines DESC, o.requested_units DESC, o.customer_id COLLATE "C"
                                  LIMIT %s""", (run_id, style_id, limit)).fetchall()

    def run_style_customers(self, run_id: str, style_id: str, limit: int) -> list:
        """Customers with a request on a style, those with linked claims first."""
        with self.transaction() as db:
            rows = db.execute("""SELECT customer_id FROM run_customer_styles WHERE run_id = %s AND style_id = %s
                                 ORDER BY linked_claim_lines DESC, claim_lines DESC, requested_units DESC, customer_id COLLATE "C"
                                 LIMIT %s""", (run_id, style_id, limit)).fetchall()
        return [row["customer_id"] for row in rows]

    # ------------------------------------------------------------------ experiments (published offline, loaded by the worker)
    def load_experiment(self, row: dict, report: dict, truth_world_id: str | None, truth_rows: list, truth_cutoff: str | None = None) -> None:
        """Store a published experiment report and replace its truth export, together."""
        with self.transaction() as db:
            db.execute("""INSERT INTO experiments (id, config_hash, report_key, selection_key, test_key, report, truth_world_id, truth_cutoff)
                          VALUES (%(id)s, %(config_hash)s, %(report_key)s, %(selection_key)s, %(test_key)s, %(report)s, %(truth_world_id)s,
                                  %(truth_cutoff)s)
                          ON CONFLICT (id) DO UPDATE SET config_hash = EXCLUDED.config_hash, report_key = EXCLUDED.report_key,
                              selection_key = EXCLUDED.selection_key, test_key = EXCLUDED.test_key, report = EXCLUDED.report,
                              truth_world_id = EXCLUDED.truth_world_id, truth_cutoff = EXCLUDED.truth_cutoff""",
                       dict(row, report=Jsonb(report), truth_world_id=truth_world_id, truth_cutoff=truth_cutoff))
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

    def curve_points(self, experiment_id: str, run_id: str, heavy_cutoff: float | None) -> list:
        """Per rank k of a run on the truth world, how many abusers and legitimate heavy returners the model's first k and the
        return-rate rule's first k contain. Rows {k, model_abusers, model_heavy, baseline_abusers, baseline_heavy}, k ascending.

        A legitimate heavy returner is a non-abuser whose raw return rate is at or above the run's heavy-returner cutoff
        (the gate's own definition). Counts over stored rows and the synthetic truth export; nothing is recomputed.
        """
        with self.transaction() as db:
            return db.execute("""WITH joined AS (
                                     SELECT c.rank, c.baseline_rank, t.y_abuse,
                                            CASE WHEN t.y_abuse = 0 AND %s IS NOT NULL
                                                      AND (c.measures->>'raw_return_rate')::double precision >= %s THEN 1 ELSE 0 END AS heavy
                                     FROM run_customers c JOIN experiment_truth t ON t.experiment_id = %s AND t.customer_id = c.customer_id
                                     WHERE c.run_id = %s AND c.eligibility_status = 'eligible' AND c.rank IS NOT NULL),
                                 by_model AS (SELECT rank AS k, sum(y_abuse) OVER (ORDER BY rank) AS abusers, sum(heavy) OVER (ORDER BY rank) AS heavy
                                              FROM joined),
                                 by_rule AS (SELECT baseline_rank AS k, sum(y_abuse) OVER (ORDER BY baseline_rank) AS abusers,
                                                    sum(heavy) OVER (ORDER BY baseline_rank) AS heavy FROM joined)
                                 SELECT m.k, m.abusers AS model_abusers, m.heavy AS model_heavy, r.abusers AS baseline_abusers, r.heavy AS baseline_heavy
                                 FROM by_model m JOIN by_rule r ON r.k = m.k ORDER BY m.k""",
                              (heavy_cutoff, heavy_cutoff, experiment_id, run_id)).fetchall()

    def experiment_truth(self, experiment_id: str, after: int | None, limit: int) -> list:
        with self.transaction() as db:
            return db.execute("SELECT * FROM experiment_truth WHERE experiment_id = %s AND position >= %s ORDER BY position LIMIT %s",
                              (experiment_id, after or 0, limit)).fetchall()
