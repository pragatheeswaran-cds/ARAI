"""Inference, storage and the HTTP API against a real PostgreSQL (final-spec components 11, 12, 14)."""
import json
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pandas as pd
import pytest
import yaml
from fastapi.testclient import TestClient
from openapi_schema_validator import OAS30Validator

from arai import bundles, modeling
from arai.operational import TABLES, read_csv_world
from arai.paths import SPEC_ROOT
from arai.service import datasets, ingest, scoring, views, worker
from arai.service.api import create_app
from arai.service.config import ServiceConfig
from arai.service.store import RESULT_TABLES, Store
from tests.conftest import FIXTURE_SEED

API = "/api/v1"
CONTRACT = yaml.safe_load((SPEC_ROOT / "contracts" / "openapi.yaml").read_text(encoding="utf-8"))


def result_rows(store: Store, run_id: str) -> dict:
    """How many rows each result table holds for a run."""
    with store.transaction() as db:
        return {table: db.execute(f"SELECT count(*) AS n FROM {table} WHERE run_id = %s", (run_id,)).fetchone()["n"]
                for table in RESULT_TABLES}


def conforms(schema_name: str, body) -> None:
    """Validate a response body against the bundled OpenAPI schema (nullable and enum rules included)."""
    document = {"$ref": f"#/components/schemas/{schema_name}", "components": CONTRACT["components"]}
    errors = sorted(OAS30Validator(document).iter_errors(body), key=lambda e: list(e.path))
    assert not errors, f"{schema_name}: " + "; ".join(f"{list(e.path)}: {e.message}" for e in errors[:5])


# the development login's people in tests (AM-69): Tester operates and reviews; the others are named in the review tests
TEST_USERS = (("Tester", ("admin", "reviewer", "approver")), ("Asha", ("reviewer", "approver")), ("Ravi", ("reviewer", "approver")),
              ("Meera", ("reviewer", "approver")), ("A", ("reviewer",)), ('=HYPERLINK("x")', ("reviewer",)),
              *((f"R{i}", ("reviewer", "approver")) for i in range(1, 5)), ("Viewer", ("viewer",)), ("Reviewer", ("reviewer",)),
              ("Admin", ("admin",)))
TEST_NAMES = {name.casefold(): name for name, _ in TEST_USERS}


class SignedInClient(TestClient):
    """A test client with a real session from the development login: every POST and DELETE carries the session's CSRF token.
    A review posted with the reviewer_name of a test user goes through that user's own signed-in client, so the server takes
    the author from that user's session; any other reviewer_name is sent as is and ignored by the server."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user, self.csrf, self.others = None, None, {}

    def sign_in(self, name: str = "Tester") -> "SignedInClient":
        response = super().request("POST", f"{API}/auth/dev-login", json={"user": name})
        assert response.status_code == 200, response.text
        self.user, self.csrf = response.json()["display_name"], response.json()["csrf_token"]
        return self

    def as_user(self, name: str) -> "SignedInClient":
        if name not in self.others:
            self.others[name] = SignedInClient(self.app).sign_in(name)
        return self.others[name]

    def request(self, method, url, **kwargs):
        body = kwargs.get("json")
        if method.upper() == "POST" and str(url).endswith("/reviews") and isinstance(body, dict):
            named = TEST_NAMES.get(str(body.get("reviewer_name") or "").strip().casefold())
            if named and named != self.user:
                return self.as_user(named).request(method, url, **kwargs)
        if method.upper() in ("POST", "DELETE") and self.csrf:
            kwargs["headers"] = {"X-CSRF-Token": self.csrf, **(kwargs.get("headers") or {})}
        return super().request(method, url, **kwargs)


@pytest.fixture
def env(trained, database_url, tmp_path):
    """A serving root with the baseline and one model bundle, the model promoted, and an empty database."""
    root = tmp_path / "artifacts"
    shutil.copytree(trained["artifact_root"] / "experiments", root / "experiments")
    experiment = root / "experiments" / "EXP-TEST"
    quantiles = modeling.feature_quantiles(trained["frame"])             # travel with the bundles, as `arai publish` writes them
    baseline_id = bundles.build_baseline_bundle(experiment, root, feature_quantiles=quantiles)
    model_id = bundles.build_model_bundle(experiment, "logreg_c1", root, feature_quantiles=quantiles)
    bundles.activate(model_id, baseline_id, "selected", "EXP-TEST", None, root)
    config = ServiceConfig(database_url=database_url, artifact_root=root, ui_origins=("http://localhost:5173",), dev_users=TEST_USERS)
    return {"config": config, "root": root, "baseline_id": baseline_id, "model_id": model_id, "experiment": experiment}


@pytest.fixture
def client(env):
    with SignedInClient(create_app(env["config"])) as test_client:
        yield test_client.sign_in("Tester")


def upload_parts(written, **overrides) -> dict:
    directory = written["operational"]
    parts = {name: (f"{name}.csv", (directory / f"{name}.csv").read_bytes(), "text/csv") for name in TABLES}
    parts.update(overrides)
    return parts


def register(client, written) -> dict:
    manifest = (written["operational"] / "manifest.json").read_text(encoding="utf-8")
    response = client.post(f"{API}/datasets", data={"manifest": manifest}, files=upload_parts(written))
    assert response.status_code in (200, 201), response.text
    return response.json()


def scored_run(client, env, written, key="k1", model_id=None) -> dict:
    dataset = register(client, written)
    body = {"dataset_id": dataset["dataset_id"], "idempotency_key": key}
    if model_id:
        body["model_id"] = model_id
    response = client.post(f"{API}/runs", json=body)
    assert response.status_code == 202, response.text
    assert worker.process_one(env["config"], Store(env["config"].database_url)) == response.json()["run_id"]
    run = client.get(f"{API}/runs/{response.json()['run_id']}").json()
    assert run["status"] == "succeeded", run
    return run


def all_pages(client, url, params=None) -> list:
    items, cursor = [], None
    for _ in range(200):
        query = dict(params or {}, limit=100)
        if cursor:
            query["cursor"] = cursor
        page = client.get(url, params=query)
        assert page.status_code == 200, page.text
        items += page.json()["items"]
        cursor = page.json()["next_cursor"]
        if cursor is None:
            return items
    raise AssertionError("pagination did not end")


# ------------------------------------------------------------------ datasets
def test_dataset_registration_is_validated_idempotent_and_immutable(client, written):
    manifest = (written["operational"] / "manifest.json").read_text(encoding="utf-8")
    created = client.post(f"{API}/datasets", data={"manifest": manifest}, files=upload_parts(written))
    assert created.status_code == 201
    conforms("Dataset", created.json())
    again = client.post(f"{API}/datasets", data={"manifest": manifest}, files=upload_parts(written))
    assert again.status_code == 200 and again.json() == created.json()                   # identical content: the same resource
    listing = client.get(f"{API}/datasets").json()
    conforms("DatasetPage", listing)
    assert [d["dataset_id"] for d in listing["items"]] == [created.json()["dataset_id"]]
    conforms("Dataset", client.get(f"{API}/datasets/{created.json()['dataset_id']}").json())

    # a changed file without a manifest update is rejected and nothing is stored
    tampered = upload_parts(written, sales_order=("sales_order.csv", (written["operational"] / "sales_order.csv").read_bytes() + b"\n", "text/csv"))
    rejected = client.post(f"{API}/datasets", data={"manifest": manifest}, files=tampered)
    assert rejected.status_code == 422
    conforms("Error", rejected.json())
    assert any(d["rule_id"] == "M002" for d in rejected.json()["details"])


def test_upload_rejects_unknown_parts_missing_parts_paths_and_bad_manifests(client, written, env):
    manifest = (written["operational"] / "manifest.json").read_text(encoding="utf-8")
    extra = upload_parts(written, customer_truth=("customer_truth.csv", b"customer_id,y_abuse\n", "text/csv"))
    response = client.post(f"{API}/datasets", data={"manifest": manifest}, files=extra)             # a private file
    assert response.status_code == 422 and response.json()["details"][0]["row_key"] == "customer_truth"
    missing = upload_parts(written)
    del missing["reason_code"]
    assert client.post(f"{API}/datasets", data={"manifest": manifest}, files=missing).status_code == 422
    traversal = upload_parts(written, sales_order=("../../sales_order.csv", (written["operational"] / "sales_order.csv").read_bytes(), "text/csv"))
    response = client.post(f"{API}/datasets", data={"manifest": manifest}, files=traversal)
    assert response.status_code == 422 and response.json()["details"][0]["rule_id"] == "upload.path"
    assert client.post(f"{API}/datasets", data={"manifest": "{not json"}, files=upload_parts(written)).status_code == 422
    assert client.get(f"{API}/datasets").json()["items"] == []
    stored = env["root"] / "datasets"
    assert not stored.exists() or not any(stored.iterdir())                                         # nothing left behind


def test_a_world_cannot_be_registered_twice_with_different_content(client, written, tmp_path):
    register(client, written)
    directory = tmp_path / "changed"
    shutil.copytree(written["operational"], directory)
    master = (directory / "customer_master.csv").read_text(encoding="utf-8").replace("unknown", "active", 1)
    (directory / "customer_master.csv").write_text(master, encoding="utf-8", newline="")
    manifest = json.loads((directory / "manifest.json").read_text())
    import hashlib
    manifest["files"]["customer_master"]["sha256"] = hashlib.sha256((directory / "customer_master.csv").read_bytes()).hexdigest()
    parts = {name: (f"{name}.csv", (directory / f"{name}.csv").read_bytes(), "text/csv") for name in TABLES}
    response = client.post(f"{API}/datasets", data={"manifest": json.dumps(manifest)}, files=parts)
    assert response.status_code == 409 and response.json()["error_code"] == "world_content_differs"


def test_csv_upload_gives_the_same_features_as_the_generated_tables(written, world, trained):
    from arai import features as F
    tables, manifest = read_csv_world(written["operational"])
    uploaded = F.compute_features(tables, world.snapshot_date, trained["reference"]).features
    direct = F.compute_features(world.tables, world.snapshot_date, trained["reference"]).features
    pd.testing.assert_frame_equal(uploaded, direct)


# ------------------------------------------------------------------ runs
def test_submission_is_acknowledged_before_scoring_and_is_idempotent(client, env, written):
    dataset = register(client, written)
    body = {"dataset_id": dataset["dataset_id"], "idempotency_key": "submit-1"}
    first = client.post(f"{API}/runs", json=body)
    assert first.status_code == 202
    conforms("Run", first.json())
    run = first.json()
    assert run["status"] == "queued" and run["model_id"] == env["model_id"] and run["model_kind"] == "supervised"
    assert run["eligible_count"] is None and run["completed_at"] is None                      # no result before success
    assert client.get(f"{API}/runs/{run['run_id']}/customers").status_code == 409              # unfinished: conflict, not empty
    repeat = client.post(f"{API}/runs", json=body)
    assert repeat.status_code == 202 and repeat.json()["run_id"] == run["run_id"]              # same key and body: same resource
    changed = client.post(f"{API}/runs", json=dict(body, model_id=env["baseline_id"]))
    assert changed.status_code == 409 and changed.json()["error_code"] == "idempotency_conflict"
    assert client.post(f"{API}/runs", json={"dataset_id": "ds-unknown", "idempotency_key": "x"}).status_code == 404
    assert client.post(f"{API}/runs", json=dict(body, extra="field")).status_code == 422
    assert client.post(f"{API}/runs", json={"dataset_id": dataset["dataset_id"], "idempotency_key": "k" * 129}).status_code == 422

    store = Store(env["config"].database_url)
    stages = []
    assert worker.process_one(env["config"], store, hook=stages.append) == run["run_id"]
    assert stages == ["validate", "features", "eligibility", "scoring", "evidence", "publish"]
    done = client.get(f"{API}/runs/{run['run_id']}").json()
    conforms("Run", done)
    assert done["status"] == "succeeded" and done["progress"] == 1 and done["completed_at"]
    assert done["eligible_count"] + done["excluded_count"] == dataset["customer_count"]
    assert worker.process_one(env["config"], store) is None                                    # nothing left in the queue
    listing = client.get(f"{API}/runs", params={"dataset_id": dataset["dataset_id"]}).json()
    conforms("RunPage", listing)
    assert [r["run_id"] for r in listing["items"]] == [run["run_id"]]


def test_population_counts_and_nullable_fields_reconcile(client, env, written):
    run = scored_run(client, env, written)
    everyone = all_pages(client, f"{API}/runs/{run['run_id']}/customers", {"review_only": "false"})
    conforms("CustomerPage", {"items": everyone, "next_cursor": None})
    assert len(everyone) == run["eligible_count"] + run["excluded_count"]
    assert len({c["customer_id"] for c in everyone}) == len(everyone)                          # no duplicates, no gaps
    eligible = [c for c in everyone if c["eligibility_status"] == "eligible"]
    excluded = [c for c in everyone if c["eligibility_status"] == "insufficient_history"]
    assert len(eligible) == run["eligible_count"] and len(excluded) == run["excluded_count"]
    assert [c["rank"] for c in eligible] == list(range(1, len(eligible) + 1))                  # ranked first, in rank order
    assert sorted(c["customer_id"] for c in excluded) == [c["customer_id"] for c in excluded]  # then unranked by identifier
    for c in excluded:
        assert c["raw_score"] is None and c["risk_score"] is None and c["rank"] is None and c["baseline_rank"] is None
        assert not c["selected_for_review"] and not c["baseline_selected"]
        assert c["support_counts"]["mature_sale_lines"] < 3
    for c in eligible:
        assert 0 <= c["risk_score"] <= 100 and c["support_counts"]["mature_sale_lines"] >= 3
    k = scoring.ranking.budget(len(eligible))
    selected = [c for c in eligible if c["selected_for_review"]]
    assert len(selected) == k == run["selected_count"] and all(c["rank"] <= k for c in selected)
    assert sum(c["baseline_selected"] for c in eligible) == k                                  # the rule gets the same budget
    assert sorted(c["baseline_rank"] for c in eligible) == list(range(1, len(eligible) + 1))
    default = all_pages(client, f"{API}/runs/{run['run_id']}/customers")                       # the queue defaults to the review set
    assert [c["customer_id"] for c in default] == [c["customer_id"] for c in selected]


def test_comparison_filter_partitions_the_selected_customers(client, env, written):
    run = scored_run(client, env, written)
    url = f"{API}/runs/{run['run_id']}/customers"
    parts = {name: all_pages(client, url, {"review_only": "false", "comparison": name}) for name in ("model_only", "baseline_only", "both")}
    assert len(parts["model_only"]) == run["model_only_count"] and len(parts["baseline_only"]) == run["baseline_only_count"]
    assert len(parts["model_only"]) + len(parts["both"]) == run["selected_count"]
    assert len(parts["baseline_only"]) + len(parts["both"]) == run["selected_count"]
    ids = [c["customer_id"] for part in parts.values() for c in part]
    assert len(ids) == len(set(ids))                                                            # the three parts are disjoint
    assert all(c["eligibility_status"] == "eligible" for part in parts.values() for c in part)
    assert all(c["selected_for_review"] and not c["baseline_selected"] for c in parts["model_only"])
    assert all(c["baseline_selected"] and not c["selected_for_review"] for c in parts["baseline_only"])


def test_cursors_are_stable_and_bound_to_their_list(client, env, written):
    run = scored_run(client, env, written)
    url = f"{API}/runs/{run['run_id']}/customers"
    first = client.get(url, params={"review_only": "false", "limit": 7}).json()
    assert len(first["items"]) == 7 and first["next_cursor"]
    second = client.get(url, params={"review_only": "false", "limit": 7, "cursor": first["next_cursor"]}).json()
    assert not {c["customer_id"] for c in first["items"]} & {c["customer_id"] for c in second["items"]}
    paged = all_pages(client, url, {"review_only": "false", "eligibility": "eligible"})
    assert [c["rank"] for c in paged] == list(range(1, len(paged) + 1))
    # a cursor issued for one filter set cannot be used with another, and garbage is refused
    crossed = client.get(url, params={"review_only": "false", "limit": 7, "eligibility": "eligible", "cursor": first["next_cursor"]})
    assert crossed.status_code == 422 and crossed.json()["error_code"] == "invalid_cursor"
    assert client.get(url, params={"cursor": "not-a-cursor"}).status_code == 422
    assert client.get(url, params={"limit": 101}).status_code == 422 and client.get(url, params={"limit": 0}).status_code == 422
    assert client.get(url, params={"evidence": "made_up"}).status_code == 422
    empty = client.get(url, params={"search": "no-such-customer"}).json()
    assert empty == {"items": [], "next_cursor": None}
    tagged = all_pages(client, url, {"review_only": "false", "evidence": "repeat_claims"})
    assert tagged and all("repeat_claims" in c["evidence_tags"] for c in tagged)


def test_case_shows_evidence_with_denominators_and_no_truth(client, env, written, world):
    run = scored_run(client, env, written)
    top = client.get(f"{API}/runs/{run['run_id']}/customers", params={"limit": 5}).json()["items"]
    case = client.get(f"{API}/runs/{run['run_id']}/customers/{top[0]['customer_id']}").json()
    conforms("Case", case)
    assert case["customer"]["rank"] == 1 and case["model_id"] == env["model_id"] and case["world_id"] == world.world_id
    codes = {s["code"]: s for s in case["signals"]}
    support = case["customer"]["support_counts"]
    assert codes["mature_requested_units"]["value"] == support["mature_requested_units"]
    assert codes["mature_requested_units"]["denominator"] == support["mature_purchased_units"]
    assert codes["expected_requested_units"]["denominator"] == support["mature_purchased_units"]
    orders = world.tables["sales_order"]
    own_orders = set(orders.loc[orders["customer_id"] == top[0]["customer_id"], "order_id"])
    purchases = [e for e in case["timeline"] if e["event_type"] == "purchase"]
    assert purchases and {e["source_ref"].split(":")[1].split("/")[0] for e in purchases} == own_orders
    text = json.dumps(case).lower()
    for forbidden in ("y_abuse", "persona", "household_id", "coordination_group", "deceptive", "temporary_use", "fraud", "confidence"):
        assert forbidden not in text
    assert case["wardrobing"]["limitation"] and case["wardrobing"]["status"] in (
        "elevated", "possible", "no_elevated_signal", "insufficient_evidence")
    excluded = [c for c in all_pages(client, f"{API}/runs/{run['run_id']}/customers", {"review_only": "false"})
                if c["eligibility_status"] == "insufficient_history"]
    thin = client.get(f"{API}/runs/{run['run_id']}/customers/{excluded[0]['customer_id']}")
    assert thin.status_code == 200 and thin.json()["customer"]["rank"] is None                  # unranked, evidence still visible
    assert client.get(f"{API}/runs/{run['run_id']}/customers/W9999-C0000").status_code == 404
    assert client.get(f"{API}/runs/run-unknown/customers").status_code == 404


def test_styles_and_sku_drill_down(client, env, written):
    run = scored_run(client, env, written)
    styles = all_pages(client, f"{API}/runs/{run['run_id']}/styles")
    conforms("StylePage", {"items": styles, "next_cursor": None})
    assert [s["style_id"] for s in styles] == sorted(s["style_id"] for s in styles)
    states = {s["state"] for s in styles}
    for state in states:
        part = all_pages(client, f"{API}/runs/{run['run_id']}/styles", {"state": state})
        assert part and all(s["state"] == state for s in part)
    for style in styles:
        if style["state"] == "insufficient_support":
            assert style["damage_share"] is None and not style["quality_signal"] and not style["targeting_signal"]
    detail = client.get(f"{API}/runs/{run['run_id']}/styles/{styles[0]['style_id']}").json()
    conforms("StyleDetail", detail)
    assert detail["skus"] and all(s["style_id"] == styles[0]["style_id"] for s in detail["skus"])
    assert sum(s["purchased_units"] for s in detail["skus"]) == detail["style"]["purchased_units"]
    assert client.get(f"{API}/runs/{run['run_id']}/styles/NOPE").status_code == 404
    assert client.get(f"{API}/runs/{run['run_id']}/styles", params={"state": "bad"}).status_code == 422


# ------------------------------------------------------------------ notes
def test_notes_are_append_only_idempotent_and_cross_runs(client, env, written):
    run_a = scored_run(client, env, written, key="a")
    customer = client.get(f"{API}/runs/{run_a['run_id']}/customers", params={"limit": 1}).json()["items"][0]["customer_id"]
    url_a = f"{API}/runs/{run_a['run_id']}/customers/{customer}/reviews"
    note = {"reviewer_name": "Asha", "disposition": "needs_investigation", "note": "Three claims in one week.", "idempotency_key": "n1"}
    created = client.post(url_a, json=note)
    assert created.status_code == 201
    conforms("Review", created.json())
    assert client.post(url_a, json=note).json()["review_id"] == created.json()["review_id"]     # repeat: the same note
    assert client.post(url_a, json=dict(note, note="changed")).status_code == 409
    assert client.post(url_a, json=dict(note, disposition="fraud", idempotency_key="n2")).status_code == 422
    ignored = client.post(url_a, json=dict(note, reviewer_name="Somebody else", idempotency_key="n3"))
    assert ignored.status_code == 201 and ignored.json()["reviewer_name"] == "Tester"      # the author is the signed-in user
    assert ignored.json()["author"]["verified"] and ignored.json()["author"]["user_id"]

    run_b = scored_run(client, env, written, key="b", model_id=env["baseline_id"])             # a second run of the same world
    assert run_b["run_id"] != run_a["run_id"] and run_b["model_kind"] == "baseline_fallback"
    url_b = f"{API}/runs/{run_b['run_id']}/customers/{customer}/reviews"
    correction = client.post(url_b, json={"reviewer_name": "Ravi", "disposition": "likely_legitimate",
                                          "note": "Address has repeated courier failures.", "idempotency_key": "n1"})
    assert correction.status_code == 409                                # the key is scoped to world and customer, not to the run
    correction = client.post(url_b, json={"reviewer_name": "Ravi", "disposition": "likely_legitimate",
                                          "note": "Address has repeated courier failures.", "idempotency_key": "n4"})
    assert correction.status_code == 201
    notes = client.get(url_b).json()
    conforms("ReviewPage", notes)
    assert [n["reviewer_name"] for n in notes["items"]] == ["Asha", "Tester", "Ravi"]          # the first notes are visible from run B
    assert notes["items"][0]["run_id"] == run_a["run_id"] and notes["items"][0]["model_id"] == env["model_id"]   # origin kept
    assert notes["items"][2]["run_id"] == run_b["run_id"] and notes["items"][2]["model_id"] == env["baseline_id"]
    case = client.get(f"{API}/runs/{run_a['run_id']}/customers/{customer}").json()
    assert len(case["reviews"]) == 3 and case["customer"]["latest_disposition"] == "likely_legitimate"
    reviewed = all_pages(client, f"{API}/runs/{run_a['run_id']}/customers", {"review_only": "false", "disposition": "likely_legitimate"})
    assert [c["customer_id"] for c in reviewed] == [customer]
    unreviewed = all_pages(client, f"{API}/runs/{run_a['run_id']}/customers", {"review_only": "false", "disposition": "unreviewed"})
    assert customer not in {c["customer_id"] for c in unreviewed}
    for method in ("put", "patch", "delete"):                                                  # no edit or delete route exists
        assert getattr(client, method)(f"{url_a}/{created.json()['review_id']}").status_code in (404, 405)


# ------------------------------------------------------------------ fallback, binding, crash
def test_baseline_fallback_ranks_equal_the_rule_and_is_labelled(client, env, written):
    bundles.activate(None, env["baseline_id"], "no_selected_model", "EXP-TEST", "No candidate passed the gate.", env["root"])
    health = client.get(f"{API}/health").json()
    conforms("Health", health)
    assert health == {"alive": True, "scoring_ready": True, "promoted_model_ready": False, "model_kind": "baseline_fallback",
                      "queue_depth": 0, "worker_seconds_since_seen": None}
    run = scored_run(client, env, written)
    assert run["model_kind"] == "baseline_fallback" and run["model_id"] == env["baseline_id"]
    assert run["model_only_count"] == 0 and run["baseline_only_count"] == 0
    for c in all_pages(client, f"{API}/runs/{run['run_id']}/customers", {"review_only": "false", "eligibility": "eligible"}):
        assert c["baseline_rank"] == c["rank"] and c["baseline_selected"] == c["selected_for_review"]
    case = client.get(f"{API}/runs/{run['run_id']}/customers/{client.get(f'{API}/runs/{run['run_id']}/customers').json()['items'][0]['customer_id']}")
    assert case.status_code == 200 and case.json()["signals"]                                   # complete evidence under fallback


def test_a_run_keeps_its_bound_model_through_promotion(client, env, written):
    dataset = register(client, written)
    queued = client.post(f"{API}/runs", json={"dataset_id": dataset["dataset_id"], "idempotency_key": "bound"}).json()
    assert queued["model_id"] == env["model_id"]
    bundles.activate(None, env["baseline_id"], "no_selected_model", "EXP-TEST", "demoted", env["root"])   # promotion changes afterwards
    assert client.get(f"{API}/health").json()["model_kind"] == "baseline_fallback"
    worker.process_one(env["config"], Store(env["config"].database_url))
    done = client.get(f"{API}/runs/{queued['run_id']}").json()
    assert done["status"] == "succeeded" and done["model_id"] == env["model_id"] and done["model_kind"] == "supervised"
    assert Store(env["config"].database_url).get_run(queued["run_id"])["summary"]["model_id"] == env["model_id"]
    later = client.post(f"{API}/runs", json={"dataset_id": dataset["dataset_id"], "idempotency_key": "after"}).json()
    assert later["model_id"] == env["baseline_id"]                                              # new submissions follow the pointer


def test_corrupt_or_missing_or_rejected_models_block_scoring(client, env, written):
    dataset = register(client, written)
    store = Store(env["config"].database_url)
    store.reject_model("m-rejected0000000000000000", "supervised")
    response = client.post(f"{API}/runs", json={"dataset_id": dataset["dataset_id"], "model_id": "m-rejected0000000000000000", "idempotency_key": "r"})
    assert response.status_code == 409 and response.json()["error_code"] == "model_rejected"
    response = client.post(f"{API}/runs", json={"dataset_id": dataset["dataset_id"], "model_id": "m-never-seen", "idempotency_key": "u"})
    assert response.status_code == 409 and response.json()["error_code"] == "model_not_available"
    (bundles.bundle_root(env["root"]) / env["model_id"] / "model.skops").write_bytes(b"corrupt")
    health = client.get(f"{API}/health").json()
    assert health["alive"] and not health["scoring_ready"] and health["model_kind"] is None    # readiness fails, no silent fallback
    response = client.post(f"{API}/runs", json={"dataset_id": dataset["dataset_id"], "idempotency_key": "c"})
    assert response.status_code == 409 and response.json()["error_code"] == "model_not_ready"
    (env["root"] / "active" / "active.json").unlink()
    response = client.post(f"{API}/runs", json={"dataset_id": dataset["dataset_id"], "idempotency_key": "n"})
    assert response.status_code == 409 and response.json()["error_code"] == "no_scoring_bundle"


class Crash(BaseException):
    """Stands in for the process dying: it is not an Exception, so the worker cannot handle it."""


def test_a_crash_publishes_nothing_and_restart_keeps_notes_and_bindings(client, env, written):
    first = scored_run(client, env, written, key="before")
    customer = client.get(f"{API}/runs/{first['run_id']}/customers", params={"limit": 1}).json()["items"][0]["customer_id"]
    client.post(f"{API}/runs/{first['run_id']}/customers/{customer}/reviews",
                json={"reviewer_name": "Asha", "disposition": "unresolved", "note": "kept", "idempotency_key": "keep"})
    crashed = client.post(f"{API}/runs", json={"dataset_id": first["dataset_id"], "idempotency_key": "crash"}).json()
    store = Store(env["config"].database_url)

    def die_while_publishing(stage):
        if stage == "publish":
            raise Crash()
    with pytest.raises(Crash):
        worker.process_one(env["config"], store, hook=die_while_publishing)
    assert client.get(f"{API}/runs/{crashed['run_id']}").json()["status"] == "running"          # as the dead process left it
    assert client.get(f"{API}/runs/{crashed['run_id']}/customers").status_code == 409           # never a partial result

    report = worker.reconcile(env["config"], store)                                             # restart
    assert report["interrupted"] == [crashed["run_id"]]
    interrupted = client.get(f"{API}/runs/{crashed['run_id']}").json()
    conforms("Run", interrupted)
    assert interrupted["status"] == "interrupted" and interrupted["error"]["error_code"] == "interrupted"
    assert result_rows(store, crashed["run_id"]) == dict.fromkeys(RESULT_TABLES, 0)             # nothing was written for it
    assert not (env["root"] / "runs").exists()                                                  # and no result file exists at all
    assert client.get(f"{API}/runs/{first['run_id']}").json()["status"] == "succeeded"          # earlier results untouched
    assert result_rows(store, first["run_id"])["run_customers"] == first["eligible_count"] + first["excluded_count"]
    notes = client.get(f"{API}/runs/{first['run_id']}/customers/{customer}/reviews").json()["items"]
    assert [n["note"] for n in notes] == ["kept"]

    retry = client.post(f"{API}/runs", json={"dataset_id": first["dataset_id"], "model_id": interrupted["model_id"], "idempotency_key": "retry"})
    assert retry.status_code == 202 and retry.json()["run_id"] != crashed["run_id"] and retry.json()["model_id"] == interrupted["model_id"]
    worker.process_one(env["config"], store)
    assert client.get(f"{API}/runs/{retry.json()['run_id']}").json()["status"] == "succeeded"

    # a directory under runs/ (an earlier version's output, or another deployment's) is never deleted by a restart
    foreign = env["root"] / "runs" / "run-of-another-deployment"
    foreign.mkdir(parents=True)
    (foreign / "customers.parquet").write_bytes(b"not ours")
    report = worker.reconcile(env["config"], store)
    assert (foreign / "customers.parquet").is_file() and report["imported"] == [] and report["output_missing"] == []


def test_results_and_success_are_one_transaction(client, env, written, monkeypatch):
    """A failure while the rows are being written leaves a failed run with no row at all, never a partial result."""
    dataset = register(client, written)
    run = client.post(f"{API}/runs", json={"dataset_id": dataset["dataset_id"], "idempotency_key": "half"}).json()
    store = Store(env["config"].database_url)
    write = Store._copy

    def fail_after_the_customers(self, db, table, key, columns, rows):
        if table == "run_styles":
            raise RuntimeError("connection lost while publishing")
        write(self, db, table, key, columns, rows)
    monkeypatch.setattr(Store, "_copy", fail_after_the_customers)
    worker.process_one(env["config"], store)
    failed = client.get(f"{API}/runs/{run['run_id']}").json()
    assert failed["status"] == "failed" and failed["error"]["error_code"] == "scoring_failed" and failed["eligible_count"] is None
    assert result_rows(store, run["run_id"]) == dict.fromkeys(RESULT_TABLES, 0)               # the customers written first are gone
    assert client.get(f"{API}/runs/{run['run_id']}/customers").status_code == 409


def test_the_api_answers_from_postgres_and_opens_no_result_file(client, env, written, monkeypatch):
    """Decision AM-39: after a run is scored, every read is a database read. No Parquet or JSON result file exists or is read."""
    run = scored_run(client, env, written)
    assert not (env["root"] / "runs").exists()

    def forbidden(*args, **kwargs):
        raise AssertionError("the API opened a Parquet file")
    monkeypatch.setattr(pd, "read_parquet", forbidden)
    shutil.rmtree(env["root"] / "datasets")                                 # nor does it need the registered snapshot's files
    assert client.get(f"{API}/runs/{run['run_id']}").json()["warnings"] == []
    everyone = all_pages(client, f"{API}/runs/{run['run_id']}/customers", {"review_only": "false"})
    assert len(everyone) == run["eligible_count"] + run["excluded_count"]
    claimant = all_pages(client, f"{API}/runs/{run['run_id']}/customers", {"review_only": "false", "evidence": "repeat_claims"})[0]
    case = client.get(f"{API}/runs/{run['run_id']}/customers/{claimant['customer_id']}")
    assert case.status_code == 200 and case.json()["timeline"] and case.json()["styles"]
    conforms("Case", case.json())
    assert client.get(f"{API}/runs/{run['run_id']}/customers", params={"search": claimant["customer_id"].lower()[-6:]}).json()["items"]
    assert client.get(f"{API}/runs/{run['run_id']}/customers", params={"search": "%"}).json()["items"] == []   # a wildcard is literal
    style = case.json()["styles"][0]["style_id"]
    detail = client.get(f"{API}/runs/{run['run_id']}/styles/{style}")
    assert detail.status_code == 200 and claimant["customer_id"] in detail.json()["customer_ids"]
    # the results are ordinary rows: scores can be queried and joined in SQL
    with Store(env["config"].database_url).transaction() as db:
        top = db.execute("""SELECT customer_id, (measures->>'raw_return_rate')::float AS rate FROM run_customers
                            WHERE run_id = %s AND selected_for_review ORDER BY rank LIMIT 1""", (run["run_id"],)).fetchone()
    assert top["customer_id"] == everyone[0]["customer_id"] and 0 <= top["rate"] <= 1


def test_results_of_earlier_runs_are_imported_once_from_their_files(client, env, written):
    """Runs scored before results moved into the database keep working: the worker loads their files at startup."""
    run = scored_run(client, env, written, key="old")
    lost = scored_run(client, env, written, key="lost")
    url = f"{API}/runs/{run['run_id']}/customers"
    before = client.get(url, params={"limit": 30}).json()
    case_before = client.get(f"{url}/{before['items'][0]['customer_id']}").json()
    store = Store(env["config"].database_url)
    # put both runs back into the state the earlier version left: files on disk, nothing in the result tables
    output = scoring.score_snapshot(*datasets.load(env["root"], store.get_dataset(run["dataset_id"])),
                                    bundles.load_bundle(run["model_id"], env["root"]))
    directory = env["root"] / "runs" / run["run_id"]
    directory.mkdir(parents=True)
    (directory / "run.json").write_text(json.dumps(dict(output.summary, run_id=run["run_id"])), encoding="utf-8")
    for name in (*ingest.LEGACY_TABLES, *ingest.LEGACY_OPTIONAL):
        getattr(output, name).to_parquet(directory / f"{name}.parquet", index=False)
    (directory / ingest.LEGACY_MARKER).write_text(run["run_id"], encoding="utf-8")
    with store.transaction() as db:
        for table in RESULT_TABLES:
            db.execute(f"DELETE FROM {table}")
        db.execute("UPDATE runs SET summary = NULL")
    assert client.get(url).status_code == 409 and client.get(url).json()["error_code"] == "run_output_missing"   # not imported yet

    report = worker.reconcile(env["config"], store)
    assert report["imported"] == [run["run_id"]] and report["output_missing"] == [lost["run_id"]]
    assert client.get(url, params={"limit": 30}).json() == before                                # the same answers as before
    assert client.get(f"{url}/{before['items'][0]['customer_id']}").json() == case_before
    gone = client.get(f"{API}/runs/{lost['run_id']}").json()                                    # files gone: failed, never an empty success
    assert gone["status"] == "failed" and gone["error"]["error_code"] == "output_missing"
    assert client.get(f"{API}/runs/{lost['run_id']}/customers").status_code == 409
    again = worker.reconcile(env["config"], store)                                              # a second restart imports nothing twice
    assert again["imported"] == [] and again["output_missing"] == [] and directory.is_dir()


def test_a_failed_stage_fails_the_run_with_a_safe_error(client, env, written, monkeypatch):
    dataset = register(client, written)
    run = client.post(f"{API}/runs", json={"dataset_id": dataset["dataset_id"], "idempotency_key": "fail"}).json()

    def broken(*args, **kwargs):
        raise RuntimeError(r"secret path C:\Users\someone\data")
    monkeypatch.setattr(scoring.F, "build_graph", broken)                                       # a graph failure fails the job
    worker.process_one(env["config"], Store(env["config"].database_url))
    failed = client.get(f"{API}/runs/{run['run_id']}").json()
    conforms("Run", failed)
    assert failed["status"] == "failed" and failed["error"]["error_code"] == "scoring_failed"
    assert "secret" not in json.dumps(failed) and "Users" not in json.dumps(failed)
    assert result_rows(Store(env["config"].database_url), run["run_id"]) == dict.fromkeys(RESULT_TABLES, 0)


def test_two_workers_cannot_claim_the_same_run_and_duplicate_submissions_make_one_run(client, env, written):
    dataset = register(client, written)
    store = Store(env["config"].database_url)
    results, barrier = [], threading.Barrier(8)

    def submit():
        barrier.wait()
        results.append(client.post(f"{API}/runs", json={"dataset_id": dataset["dataset_id"], "idempotency_key": "same"}).json()["run_id"])
    threads = [threading.Thread(target=submit) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(set(results)) == 1 and len(client.get(f"{API}/runs").json()["items"]) == 1       # one resource

    claims, barrier = [], threading.Barrier(6)

    def claim(name):
        barrier.wait()
        claims.append(store.claim_next_run(name))
    threads = [threading.Thread(target=claim, args=(f"w{i}",)) for i in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len([c for c in claims if c is not None]) == 1                                       # exactly one owner


# ------------------------------------------------------------------ errors, CORS, profile, boundary
def test_errors_are_distinguished_and_safe(client):
    for path, status in ((f"{API}/datasets/ds-nope", 404), (f"{API}/runs/run-nope", 404), (f"{API}/experiments/EXP-nope", 404),
                         (f"{API}/nothing-here", 404), (f"{API}/datasets?limit=abc", 422)):
        response = client.get(path)
        assert response.status_code == status, path
        conforms("Error", response.json())
        assert response.json()["request_id"] and "Traceback" not in response.text
    assert client.delete(f"{API}/datasets").status_code == 405
    for old in ("/jobs", "/inference-jobs", "/approve", "/train", "/models"):                   # withdrawn or never offered
        assert client.get(API + old).status_code == 404 and client.post(API + old).status_code == 404


def test_cors_allows_only_listed_origins(client):
    allowed = client.options(f"{API}/health", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    denied = client.options(f"{API}/health", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in denied.headers
    plain = client.get(f"{API}/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in plain.headers


def test_vm_profile_requires_the_shared_login(env, monkeypatch):
    monkeypatch.setenv("BASIC_AUTH_USER", "judge")
    monkeypatch.setenv("BASIC_AUTH_PASSWORD", "s3cret")
    config = ServiceConfig(database_url=env["config"].database_url, artifact_root=env["root"], profile="vm", ui_origins=())
    with TestClient(create_app(config)) as vm:
        denied = vm.get(f"{API}/health")
        assert denied.status_code == 401 and denied.headers["www-authenticate"].startswith("Basic")
        assert vm.get(f"{API}/datasets", auth=("judge", "wrong")).status_code == 401
        assert vm.get(f"{API}/health", auth=("judge", "s3cret")).status_code == 200
    monkeypatch.delenv("BASIC_AUTH_PASSWORD")
    with pytest.raises(RuntimeError):
        create_app(config)


def test_the_served_contract_is_the_bundled_one_and_every_route_is_in_it(client):
    served = client.get(f"{API}/openapi.json").json()
    assert served["paths"].keys() == CONTRACT["paths"].keys()
    generated = client.app.openapi()["paths"]                      # what the application really routes
    implemented = {(method, path[len(API):]) for path, item in generated.items() for method in item}
    contracted = {(method, path) for path, item in CONTRACT["paths"].items() for method in item if method != "parameters"}
    assert implemented == contracted                               # nothing missing, nothing extra (no train/refund/block/delete-note)


def test_serving_does_not_import_offline_modules_or_need_private_truth():
    code = ("import sys, os; os.environ['PRIVATE_TRUTH_ROOT'] = 'Z:/does/not/exist'; "
            "import arai.service.api, arai.service.worker; "
            "bad = sorted(m for m in sys.modules if m in ('arai.evaluation', 'arai.selection', 'arai.experiment', 'arai.eda', "
            "'arai.diagnostics', 'arai.feature_eda', 'arai.publishing', 'arai.modeling', 'arai.dataset', 'arai.generator.world')); "
            "print(bad); sys.exit(1 if bad else 0)")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_no_eligible_customer_is_a_valid_empty_ranking(env):
    from tests.helpers import make_tables, simple_order
    skus = [("A", "S1", "Shirt", "M", 0, 30)]
    tables = make_tables(skus, [simple_order("O1", "c1"), simple_order("O2", "c2")],
                         [("O1", 1, "A", 1, "delivered", "2026-01-10"), ("O2", 1, "A", 1, "delivered", "2026-01-10")])
    manifest = {"world_id": "WTINY", "cutoff": "2026-09-09T23:59:59+05:30"}
    output = scoring.score_snapshot(tables, manifest, bundles.load_bundle(env["model_id"], env["root"]))
    assert output.summary["eligible_count"] == 0 and output.summary["selected_count"] == 0 and output.summary["excluded_count"] == 2
    assert output.customers["rank"].isna().all() and not output.customers["selected_for_review"].any()
    assert output.neighbors.empty and output.summary["graph_edges"] == 0                        # an empty graph is valid
    assert output.summary["warnings"]                                                           # and the small population is flagged


def test_artifacts_move_to_another_root_without_stored_paths(client, env, written, tmp_path):
    """Keys in the database are relative to the artifact root, so the root can be copied elsewhere and served from there."""
    run = scored_run(client, env, written)
    first = client.get(f"{API}/runs/{run['run_id']}/customers", params={"limit": 20}).json()
    relocated = tmp_path / "moved somewhere else" / "artifacts"
    shutil.copytree(env["root"], relocated)
    store = Store(env["config"].database_url)
    assert store.get_dataset(run["dataset_id"])["artifact_key"] == f"datasets/{run['dataset_id']}"      # no absolute path stored
    assert store.get_run(run["run_id"])["output_key"] is None                                           # results are rows, not files
    config = ServiceConfig(database_url=env["config"].database_url, artifact_root=relocated, dev_users=TEST_USERS)
    with SignedInClient(create_app(config)) as moved:
        moved.sign_in()
        assert moved.get(f"{API}/health").json()["promoted_model_ready"]
        assert moved.get(f"{API}/runs/{run['run_id']}/customers", params={"limit": 20}).json() == first
        again = moved.post(f"{API}/runs", json={"dataset_id": run["dataset_id"], "idempotency_key": "after-move"})
        assert again.status_code == 202
        assert worker.process_one(config, store) == again.json()["run_id"]
        assert moved.get(f"{API}/runs/{again.json()['run_id']}").json()["status"] == "succeeded"


# ------------------------------------------------------------------ gaps named by the serving review
def test_upload_over_the_size_limit_is_refused_with_413(client, written, monkeypatch):
    monkeypatch.setattr(datasets, "MAX_UPLOAD_BYTES", 1000)
    manifest = (written["operational"] / "manifest.json").read_text(encoding="utf-8")
    response = client.post(f"{API}/datasets", data={"manifest": manifest}, files=upload_parts(written))
    assert response.status_code == 413
    conforms("Error", response.json())
    assert client.get(f"{API}/datasets").json()["items"] == []


def test_forged_and_misshapen_cursors_are_refused_not_crashed(client, env, written):
    from arai.service import views
    run = scored_run(client, env, written)
    filters = {"review_only": True, "eligibility": "all", "search": None, "evidence": None, "disposition": "all", "comparison": "all"}
    context = {"list": "customers", "run_id": run["run_id"], **filters}
    for position in ("abc", -5, 1.5, [1, 2], None, True):
        forged = views.encode_cursor(context, position)
        response = client.get(f"{API}/runs/{run['run_id']}/customers", params={"cursor": forged})
        assert response.status_code == 422 and response.json()["error_code"] == "invalid_cursor", position
    forged = views.encode_cursor({"list": "runs", "dataset_id": None}, "abc")
    assert client.get(f"{API}/runs", params={"cursor": forged}).status_code == 422
    forged = views.encode_cursor({"list": "runs", "dataset_id": None}, ["not-a-time", "x"])
    assert client.get(f"{API}/runs", params={"cursor": forged}).status_code == 422


def test_runs_and_reviews_page_without_gaps_or_duplicates(client, env, written):
    first = scored_run(client, env, written, key="p1")
    second = scored_run(client, env, written, key="p2", model_id=env["baseline_id"])
    third = scored_run(client, env, written, key="p3")
    seen, cursor = [], None
    for _ in range(5):
        page = client.get(f"{API}/runs", params={"limit": 1, **({"cursor": cursor} if cursor else {})}).json()
        seen += [r["run_id"] for r in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == [third["run_id"], second["run_id"], first["run_id"]]                        # newest first, each once
    customer = client.get(f"{API}/runs/{first['run_id']}/customers", params={"limit": 1}).json()["items"][0]["customer_id"]
    url = f"{API}/runs/{first['run_id']}/customers/{customer}/reviews"
    for i in range(3):
        assert client.post(url, json={"reviewer_name": "A", "disposition": "unresolved", "note": f"note {i}", "idempotency_key": f"k{i}"}).status_code == 201
    notes, cursor = [], None
    for _ in range(5):
        page = client.get(url, params={"limit": 1, **({"cursor": cursor} if cursor else {})}).json()
        notes += [n["note"] for n in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert notes == ["note 0", "note 1", "note 2"]                                             # oldest first, each once


def test_the_login_refusal_is_a_contract_error_body(env, monkeypatch):
    monkeypatch.setenv("BASIC_AUTH_USER", "judge")
    monkeypatch.setenv("BASIC_AUTH_PASSWORD", "s3cret")
    config = ServiceConfig(database_url=env["config"].database_url, artifact_root=env["root"], profile="vm", ui_origins=())
    with TestClient(create_app(config)) as vm:
        denied = vm.post(f"{API}/runs", json={"dataset_id": "x", "idempotency_key": "k"})
        assert denied.status_code == 401
        conforms("Error", denied.json())


def test_the_worker_loop_survives_a_database_error(env):
    store = Store(env["config"].database_url)
    store.migrate()
    calls, stop = [], threading.Event()

    class Flaky(Store):
        def claim_next_run(self, worker_id):
            calls.append(worker_id)
            if len(calls) == 1:
                raise RuntimeError("database briefly unreachable")
            stop.set()
            return None
    config = ServiceConfig(database_url=env["config"].database_url, artifact_root=env["root"], poll_seconds=0.01)
    thread = threading.Thread(target=worker.run_forever, args=(config, Flaky(env["config"].database_url), stop))
    thread.start()
    thread.join(timeout=10)
    assert not thread.is_alive() and len(calls) >= 2                       # the first error did not end the loop


def test_restart_interrupts_only_runs_this_worker_held(client, env, written):
    dataset = register(client, written)
    run = client.post(f"{API}/runs", json={"dataset_id": dataset["dataset_id"], "idempotency_key": "held"}).json()
    store = Store(env["config"].database_url)
    assert store.claim_next_run("worker-A")["id"] == run["run_id"]         # worker A is scoring it right now
    other = ServiceConfig(database_url=env["config"].database_url, artifact_root=env["root"], worker_id="worker-B")
    assert worker.reconcile(other, store)["interrupted"] == []             # worker B starting up must not touch it
    assert client.get(f"{API}/runs/{run['run_id']}").json()["status"] == "running"
    same = ServiceConfig(database_url=env["config"].database_url, artifact_root=env["root"], worker_id="worker-A")
    assert worker.reconcile(same, store)["interrupted"] == [run["run_id"]]  # worker A restarting: its own run was lost


def test_a_registered_dataset_whose_files_vanished_is_restored_by_the_same_upload(client, env, written):
    dataset = register(client, written)
    shutil.rmtree(env["root"] / "datasets" / dataset["dataset_id"])
    again = register(client, written)                                       # identical content: same resource, files written again
    assert again == dataset and (env["root"] / "datasets" / dataset["dataset_id"] / "parquet").is_dir()
    run = client.post(f"{API}/runs", json={"dataset_id": dataset["dataset_id"], "idempotency_key": "restored"}).json()
    worker.process_one(env["config"], Store(env["config"].database_url))
    assert client.get(f"{API}/runs/{run['run_id']}").json()["status"] == "succeeded"


def test_health_is_not_ready_when_the_in_process_worker_has_stopped(env):
    app = create_app(env["config"])
    with TestClient(app) as local:
        assert local.get(f"{API}/health").json()["scoring_ready"]
        dead = threading.Thread(target=lambda: None)
        dead.start()
        dead.join()
        app.state.service.worker_thread = dead
        assert not local.get(f"{API}/health").json()["scoring_ready"]


# ------------------------------------------------------------------ the published experiment report
REAL_EXPERIMENT = None
try:
    from arai import contract as _contract
    from arai import paths as _paths
    EXPERIMENT_ID = _contract.experiment_id()
    _candidate = _paths.ARTIFACT_ROOT / "experiments" / EXPERIMENT_ID
    if (_candidate / "reports" / "test.json").is_file() and (_candidate / "published" / "truth.parquet").is_file():
        REAL_EXPERIMENT = _candidate
except Exception:                                                           # noqa: BLE001
    REAL_EXPERIMENT = None


@pytest.mark.skipif(REAL_EXPERIMENT is None, reason="needs the generated experiment under data/artifacts (not in git)")
def test_the_published_experiment_matches_the_contract_and_the_offline_reports(env):
    from arai import publishing
    report = publishing.build_report(REAL_EXPERIMENT, "m-example")
    conforms("Experiment", report)
    validation = json.loads((REAL_EXPERIMENT / "reports" / "validation.json").read_text())
    card = {row["ranking"]: row for row in validation["scorecard"]}
    precision = {m["name"]: m for m in report["baseline_metrics"]}["precision"]
    assert precision["value"] == pytest.approx(card["raw_return_rate"]["precision"], abs=1e-9)
    assert precision["numerator"] == card["raw_return_rate"]["true_positives"] and precision["denominator"] == card["raw_return_rate"]["k"]
    for metric in report["error_account"] + report["wardrobing_metrics"]:
        if metric["denominator"]:                                           # a share is exactly its numerator over its denominator
            assert metric["value"] == pytest.approx(metric["numerator"] / metric["denominator"])
        else:
            assert metric["name"].endswith("(count)") or metric["value"] is None or metric["numerator"] is None
    names = [m["name"] for m in report["reference_metrics"]]
    assert any("without any timing feature" in n for n in names) and any("difficulty target check" in n for n in names)
    recorded = json.loads((REAL_EXPERIMENT / "selection.json").read_text())
    assert report["summary"]["final_test_status"] == recorded["final_test_status"]
    assert report["summary"]["selected_candidate_id"] == recorded["selected_model_id"]
    assert {"review_rate.repeat_genuine_claimant", "review_rate.one_genuine_failure"} <= {m["code"] for m in report["baseline_metrics"]}

    published = env["root"] / "experiments" / EXPERIMENT_ID / "published"
    published.mkdir(parents=True)
    (published / "experiment.json").write_text(json.dumps(report))
    shutil.copyfile(REAL_EXPERIMENT / "published" / "truth.parquet", published / "truth.parquet")
    store = Store(env["config"].database_url)
    with SignedInClient(create_app(env["config"])) as served:
        served.sign_in()
        assert served.get(f"{API}/experiments").json()["items"] == []       # published files are not served until they are loaded
        assert ingest.sync_published(env["config"], store) == [EXPERIMENT_ID]           # the worker does this at startup
        listing = served.get(f"{API}/experiments").json()
        conforms("ExperimentSummaryPage", listing)
        assert EXPERIMENT_ID in [e["experiment_id"] for e in listing["items"]]
        conforms("Experiment", served.get(f"{API}/experiments/{EXPERIMENT_ID}").json())
        truth = served.get(f"{API}/experiments/{EXPERIMENT_ID}/truth", params={"limit": 100}).json()
        conforms("TruthPage", truth)
        assert truth["synthetic_only"] and truth["world_id"] == f"W{_contract._load('experiment.yaml')['demo_seeds'][0]}" and truth["next_cursor"]
        assert all(e["y_abuse"] == 1 for e in truth["items"])               # abusers first
        second = served.get(f"{API}/experiments/{EXPERIMENT_ID}/truth", params={"limit": 100, "cursor": truth["next_cursor"]}).json()
        assert not {e["customer_id"] for e in truth["items"]} & {e["customer_id"] for e in second["items"]}
        assert served.get(f"{API}/experiments/EXP-TEST/truth").status_code == 404     # trained here but never published
        (published / "truth.parquet").unlink()                              # published without a truth export: an empty page
        ingest.sync_published(env["config"], store)
        empty = served.get(f"{API}/experiments/{EXPERIMENT_ID}/truth").json()
        conforms("TruthPage", empty)
        assert empty["items"] == [] and empty["world_id"] is None and empty["next_cursor"] is None


# ------------------------------------------------------------------ gaps named by the principal ML review (2026-10-05)
def test_health_reports_the_queue_and_when_a_worker_was_last_seen(client, env, written):
    """The worker may be another process: the API can only know it is alive from its heartbeat."""
    dataset = register(client, written)
    before = client.get(f"{API}/health").json()
    conforms("Health", before)
    assert before["queue_depth"] == 0 and before["worker_seconds_since_seen"] is None          # no worker has ever reported
    client.post(f"{API}/runs", json={"dataset_id": dataset["dataset_id"], "idempotency_key": "queued"})
    assert client.get(f"{API}/health").json()["queue_depth"] == 1                                # waiting, and nobody to take it
    store = Store(env["config"].database_url)
    worker.process_one(env["config"], store)
    after = client.get(f"{API}/health").json()
    conforms("Health", after)
    assert after["queue_depth"] == 0 and 0 <= after["worker_seconds_since_seen"] < 30           # it reported while scoring
    assert store.migrate() == []                                                                 # migrating again is a no-op


def test_a_login_header_that_is_not_ascii_is_refused_not_crashed(env, monkeypatch):
    monkeypatch.setenv("BASIC_AUTH_USER", "judge")
    monkeypatch.setenv("BASIC_AUTH_PASSWORD", "s3cret")
    config = ServiceConfig(database_url=env["config"].database_url, artifact_root=env["root"], profile="vm", ui_origins=())
    with TestClient(create_app(config)) as vm:
        denied = vm.get(f"{API}/health", headers={"Authorization": "Basic caf\u00e9".encode("latin-1")})
        assert denied.status_code == 401
        conforms("Error", denied.json())


def test_a_run_says_when_its_scores_or_inputs_sit_outside_training(env):
    """Final-spec component 15: the drift report describes; it never corrects, refits or promotes."""
    import numpy as np
    rng = np.random.default_rng(3)
    reference = np.sort(rng.normal(0.0, 1.0, 4000))
    like_training = pd.DataFrame({"raw_return_rate": rng.uniform(0.05, 0.35, 600)})
    manifest = {"feature_quantiles": {"raw_return_rate": [0.05, 0.2, 0.35], "claim_share": None}}
    bundle = bundles.Bundle("b-test", bundles.BASELINE_KIND, manifest, reference, None, env["root"])
    report, notes = scoring.drift(bundle, like_training, rng.normal(0.0, 1.0, 600))
    assert report["checked"] and notes == [] and report["features_outside_training_range"] == []
    assert abs(report["score_share_at_or_above_training_percentile"]["p95"] - 0.05) < 0.03
    shifted = pd.DataFrame({"raw_return_rate": rng.uniform(0.6, 0.9, 600)})
    report, notes = scoring.drift(bundle, shifted, rng.normal(1.5, 1.0, 600))                    # scores and inputs both moved
    assert report["features_outside_training_range"] == ["raw_return_rate"] and len(notes) == 2
    assert report["score_share_at_or_above_training_percentile"]["p95"] > 0.3 and "5% expected" in notes[0]
    report, notes = scoring.drift(bundle, shifted.head(50), rng.normal(1.5, 1.0, 50))            # too few customers to judge
    assert report == {"checked": False, "reason": "fewer than 200 eligible customers"} and notes == []


def test_a_scored_run_records_its_drift_report_and_a_changed_scoring_code(client, env, written, monkeypatch):
    run = scored_run(client, env, written, key="quiet")
    summary = Store(env["config"].database_url).get_run(run["run_id"])["summary"]
    assert summary["drift"]["checked"] and run["warnings"] == []                                 # the training world looks like training
    monkeypatch.setattr(bundles, "code_sha256", lambda: "0" * 64)                                # the code changed after publication
    changed = scored_run(client, env, written, key="changed")
    assert any("scoring code differs" in warning for warning in changed["warnings"])


def test_a_database_dump_restores_to_another_database_and_artifact_root(client, env, written, postgres, tmp_path):
    """STORE-AC-05: the backup is a database dump plus the snapshot and bundle files; restored elsewhere, every answer is the same."""
    import os
    import uuid
    from pathlib import Path

    import pgserver
    import psycopg

    run = scored_run(client, env, written)
    url = f"{API}/runs/{run['run_id']}/customers"
    customer = client.get(url, params={"limit": 1}).json()["items"][0]["customer_id"]
    client.post(f"{url}/{customer}/reviews", json={"reviewer_name": "Asha", "disposition": "unresolved", "note": "kept", "idempotency_key": "n"})
    before = {"queue": client.get(url, params={"limit": 40}).json(), "case": client.get(f"{url}/{customer}").json(),
              "run": client.get(f"{API}/runs/{run['run_id']}").json(), "styles": client.get(f"{API}/runs/{run['run_id']}/styles").json()}

    tool = lambda name: str(Path(pgserver.__file__).parent / "pginstall" / "bin" / (name + (".exe" if os.name == "nt" else "")))  # noqa: E731
    dump = tmp_path / "backup.dump"
    subprocess.run([tool("pg_dump"), "--format=custom", "--file", str(dump), "--dbname", env["config"].database_url],
                   check=True, capture_output=True)
    name = "restored_" + uuid.uuid4().hex[:12]
    with psycopg.connect(postgres, autocommit=True) as connection:
        connection.execute(f'CREATE DATABASE "{name}"')
    base, _, query = postgres.partition("?")                      # the host may be a socket directory: keep the query untouched
    restored_url = base.rsplit("/", 1)[0] + "/" + name + ("?" + query if query else "")
    subprocess.run([tool("pg_restore"), "--no-owner", "--dbname", restored_url, str(dump)], check=True, capture_output=True)
    relocated = tmp_path / "restored somewhere else" / "artifacts"
    shutil.copytree(env["root"], relocated)

    config = ServiceConfig(database_url=restored_url, artifact_root=relocated, dev_users=TEST_USERS)
    with SignedInClient(create_app(config)) as restored:
        restored.sign_in()
        assert restored.get(f"{API}/health").json()["promoted_model_ready"]
        after = {"queue": restored.get(url, params={"limit": 40}).json(), "case": restored.get(f"{url}/{customer}").json(),
                 "run": restored.get(f"{API}/runs/{run['run_id']}").json(), "styles": restored.get(f"{API}/runs/{run['run_id']}/styles").json()}
        assert after == before                                                   # results, notes and bindings all came back
        again = restored.post(f"{API}/runs", json={"dataset_id": run["dataset_id"], "idempotency_key": "after-restore"})
        assert again.status_code == 202 and worker.process_one(config, Store(restored_url)) == again.json()["run_id"]
        assert restored.get(f"{API}/runs/{again.json()['run_id']}").json()["status"] == "succeeded"


# ------------------------------------------------------------------ WP0: what was already computed is served (contract 1.4.0)
def test_a_run_reports_its_queue_edge_and_the_eligible_population(client, env, written):
    run = scored_run(client, env, written)
    conforms("Run", run)
    queue = all_pages(client, f"{API}/runs/{run['run_id']}/customers", {"review_only": "false"})
    eligible = [c for c in queue if c["eligibility_status"] == "eligible"]
    selected = [c for c in queue if c["selected_for_review"]]
    assert run["review_budget"] == run["selected_count"] == len(selected)
    assert run["threshold_score"] == min(c["risk_score"] for c in selected)                   # the last customer inside the budget
    assert all(c["risk_score"] >= run["threshold_score"] for c in selected)
    assert all(c["risk_score"] <= run["threshold_score"] for c in eligible if not c["selected_for_review"])
    requested = sum(c["support_counts"]["mature_requested_units"] for c in eligible)
    purchased = sum(c["support_counts"]["mature_purchased_units"] for c in eligible)
    assert (run["eligible_requested_units"], run["eligible_purchased_units"]) == (requested, purchased)
    assert run["mean_return_rate"] == pytest.approx(requested / purchased)                   # a rate with its counts
    scores = sorted(c["risk_score"] for c in eligible)
    assert run["median_score"] == pytest.approx(pd.Series(scores).median()) and 0 <= run["median_score"] <= 100
    assert isinstance(run["graph_edges"], int) and run["graph_edges"] >= 0
    # a run that has not succeeded has none of these yet
    dataset = client.get(f"{API}/datasets/{run['dataset_id']}").json()
    queued = client.post(f"{API}/runs", json={"dataset_id": dataset["dataset_id"], "idempotency_key": "later"}).json()
    conforms("Run", queued)
    assert all(queued[field] is None for field in ("review_budget", "threshold_score", "median_score", "mean_return_rate",
                                                   "eligible_requested_units", "eligible_purchased_units", "graph_edges"))


def test_the_timeline_carries_its_facts_as_fields_not_only_as_a_sentence(client, env, written, world):
    run = scored_run(client, env, written)
    url = f"{API}/runs/{run['run_id']}/customers"
    with_returns = next(c for c in client.get(url, params={"limit": 20}).json()["items"] if c["support_counts"]["all_requested_units"])
    case = client.get(f"{url}/{with_returns['customer_id']}").json()
    conforms("Case", case)
    purchases = [e for e in case["timeline"] if e["event_type"] == "purchase"]
    returns = [e for e in case["timeline"] if e["event_type"] != "purchase"]
    assert purchases and returns
    codes = set(world.tables["reason_code"]["reason_code"]) if "reason_code" in world.tables else set(scoring.REASON_GROUPS)
    for event in purchases:
        assert event["source_ref"] == f"sales_order_line:{event['order_id']}/{event['order_line_no']}"
        assert event["quantity"] >= 1 and event["size"] and event["line_status"] and event["window_days"] >= 0
        assert event["reason_code"] is None and event["reason_group"] is None and event["day_in_window"] is None
        assert event["item_received"] is None and event["linked_claim"] is None
    ordered = {(e["order_id"], e["order_line_no"]) for e in purchases}
    for event in returns:
        assert (event["order_id"], event["order_line_no"]) in ordered                      # every return points at a purchase shown
        assert event["reason_code"] in codes and event["reason_group"] == scoring.REASON_GROUPS[event["reason_code"]]
        assert (event["event_type"] == "transaction_claim") == (event["reason_group"] == "transaction_claim")
        assert event["quantity"] >= 1 and event["size"] and event["line_status"] and isinstance(event["day_in_window"], int)
        assert isinstance(event["linked_claim"], bool)
        assert event["item_received"] is None or isinstance(event["item_received"], bool)
        assert f"day {event['day_in_window']} of a {event['window_days']}-day window" in event["description"]   # the sentence agrees
    no_item = {e["reason_code"] for e in returns if e["item_received"] is None}
    assert no_item <= {"item_not_received", "empty_package"}                                # null exactly when nothing comes back
    text = json.dumps(case["timeline"]).lower()
    assert "reason_text" not in text                                                        # the customer's free text never travels


def test_neighbours_carry_their_own_result_in_the_run(client, env, written):
    run = scored_run(client, env, written)
    url = f"{API}/runs/{run['run_id']}/customers"
    linked = all_pages(client, url, {"review_only": "false", "evidence": "supported_links"})
    assert linked, "the fixture world has supported relationships"
    case = client.get(f"{url}/{linked[0]['customer_id']}").json()
    conforms("Case", case)
    assert case["neighbors"]
    for neighbor in case["neighbors"]:
        own = client.get(f"{url}/{neighbor['customer_id']}").json()["customer"]
        assert (neighbor["risk_score"], neighbor["rank"], neighbor["selected_for_review"], neighbor["evidence_tags"]) == \
               (own["risk_score"], own["rank"], own["selected_for_review"], own["evidence_tags"])


def test_the_queue_filters_on_the_wardrobing_band(client, env, written):
    run = scored_run(client, env, written)
    url = f"{API}/runs/{run['run_id']}/customers"
    everyone = all_pages(client, url, {"review_only": "false"})
    seen = 0
    for band in ("elevated", "possible", "no_elevated_signal", "insufficient_evidence", "incomplete"):
        part = all_pages(client, url, {"review_only": "false", "wardrobing": band})
        assert all(c["wardrobing_status"] == band for c in part)
        assert len(part) == sum(c["wardrobing_status"] == band for c in everyone)
        seen += len(part)
    assert seen == len(everyone)                                                             # the bands partition the customers
    assert client.get(url, params={"wardrobing": "worn"}).status_code == 422
    # a cursor issued under one band is refused under another
    first = client.get(url, params={"review_only": "false", "wardrobing": "no_elevated_signal", "limit": 1}).json()
    if first["next_cursor"]:
        assert client.get(url, params={"review_only": "false", "wardrobing": "possible", "cursor": first["next_cursor"]}).status_code == 422


def test_the_basket_expectation_band_and_the_cleared_reason_follow_the_stated_rules(client, env, written):
    run = scored_run(client, env, written)
    conforms("Run", run)
    url = f"{API}/runs/{run['run_id']}/customers"
    everyone = all_pages(client, url, {"review_only": "false"})
    eligible = [c for c in everyone if c["eligibility_status"] == "eligible"]
    rates = pd.Series([c["support_counts"]["mature_requested_units"] / c["support_counts"]["mature_purchased_units"] for c in eligible])
    assert run["heavy_returner_cutoff"] == pytest.approx(rates.quantile(0.9, interpolation="linear"))   # the gate's own definition
    heavy_cleared = [c for c in eligible if not c["selected_for_review"]
                     and c["basket_expectation"]["actual_units"] / c["basket_expectation"]["purchased_units"] >= run["heavy_returner_cutoff"]]
    assert heavy_cleared, "the rule reviews a different set than the raw rate does"
    for c in everyone:
        basket = c["basket_expectation"]
        if c["support_counts"]["mature_purchased_units"] == 0:
            assert basket is None
            continue
        assert basket["actual_units"] == c["support_counts"]["mature_requested_units"]
        assert basket["purchased_units"] == c["support_counts"]["mature_purchased_units"]
        if basket["sd"] is not None:
            assert basket["band_low"] == pytest.approx(max(0.0, basket["expected_units"] - 2 * basket["sd"]))
            assert basket["band_high"] == pytest.approx(basket["expected_units"] + 2 * basket["sd"])
            assert basket["z"] == pytest.approx((basket["actual_units"] - basket["expected_units"]) / basket["sd"])   # the model's own z
        if c["eligibility_status"] != "eligible" or c["selected_for_review"]:
            assert c["cleared_reason"] is None
        else:
            assert c["cleared_reason"] in ("size_bracketing", "high_return_styles", "as_basket_predicts", "below_threshold")
    assert sum(c["basket_expectation"]["sd"] is not None for c in eligible) > len(eligible) * 0.9
    assert {c["cleared_reason"] for c in eligible if not c["selected_for_review"]} >= {"as_basket_predicts", "below_threshold"}
    # the reason is the first rule that holds, read off the case's own signals
    for c in [x for x in eligible if not x["selected_for_review"]][:25]:
        case = client.get(f"{url}/{c['customer_id']}").json()
        conforms("Case", case)
        codes = {s["code"]: s for s in case["signals"]}
        assert codes["expected_requested_units"]["value"] == c["basket_expectation"]["expected_units"]
        assert codes["expected_band_low"]["value"] == c["basket_expectation"]["band_low"]
        assert codes["bracketing_kept_units"]["denominator"] == codes["bracketing_units"]["value"]
        bracketing = (codes["bracketing_units"]["value"] or 0) / codes["bracketing_units"]["denominator"]
        expected_rate, z = codes["expected_return_rate"]["value"], codes["residual_z"]["value"]
        rule = ("size_bracketing" if bracketing >= 0.5 else "high_return_styles" if expected_rate >= 0.35
                else "as_basket_predicts" if z is not None and z < 1 else "below_threshold")
        assert c["cleared_reason"] == rule
        if codes["median_return_day"]["value"] is not None:
            assert codes["median_return_day"]["value"] >= 0


def test_the_score_distribution_counts_the_queue_at_every_threshold(client, env, written):
    run = scored_run(client, env, written)
    response = client.get(f"{API}/runs/{run['run_id']}/score-distribution")
    assert response.status_code == 200, response.text
    distribution = response.json()
    conforms("ScoreDistribution", distribution)
    bins = distribution["bins"]
    assert len(bins) == 20 and distribution["bin_width"] == 5 and bins[0]["lower"] == 0 and bins[-1]["upper"] == 100
    assert all(b["upper"] - b["lower"] == 5 for b in bins) and all(bins[i]["upper"] == bins[i + 1]["lower"] for i in range(19))
    assert distribution["eligible_count"] == sum(b["count"] for b in bins) == run["eligible_count"]
    assert sum(b["selected_count"] for b in bins) == run["selected_count"]
    assert distribution["review_budget"] == run["review_budget"] and distribution["threshold_score"] == run["threshold_score"]
    assert bins[0]["at_or_above"] == run["eligible_count"]                                   # a threshold of zero reviews everyone
    for i in range(19):
        assert bins[i]["at_or_above"] == bins[i]["count"] + bins[i + 1]["at_or_above"]        # a running sum from the top bin down
    cut = next(b for b in bins if b["lower"] <= run["threshold_score"] < b["upper"] or (b["upper"] == 100 and run["threshold_score"] == 100))
    assert cut["at_or_above"] >= run["review_budget"] and cut["selected_count"] >= 1          # the budget cut falls inside its bin
    eligible = all_pages(client, f"{API}/runs/{run['run_id']}/customers", {"review_only": "false", "eligibility": "eligible"})
    for b in bins:
        assert b["at_or_above"] == sum(c["risk_score"] >= b["lower"] for c in eligible)      # the same count the UI would make
    queued = client.post(f"{API}/runs", json={"dataset_id": run["dataset_id"], "idempotency_key": "pending"}).json()
    assert client.get(f"{API}/runs/{queued['run_id']}/score-distribution").status_code == 409
    assert client.get(f"{API}/runs/run-unknown/score-distribution").status_code == 404


def test_communities_group_linked_accounts_and_their_kind_follows_the_stated_rule(client, env, written, world):
    run = scored_run(client, env, written)
    conforms("Run", run)
    assert run["community_count"] >= run["ring_count"] >= 1, "the fixture world has coordination groups"
    url = f"{API}/runs/{run['run_id']}/customers"
    everyone = all_pages(client, url, {"review_only": "false"})
    by_id = {c["customer_id"]: c for c in everyone}
    linked = [c for c in everyone if c["community"] is not None]
    assert linked and len({c["community"]["id"] for c in linked}) == run["community_count"]
    # membership: a customer without a supported edge has no community; a community's size is its member count; ids are world-scoped
    for c in [x for x in everyone if x["community"] is None][:10]:
        case = client.get(f"{url}/{c['customer_id']}").json()
        assert case["neighbors"] == [] and case["community"] is None
    for community_id in sorted({c["community"]["id"] for c in linked}):
        members = [c for c in linked if c["community"]["id"] == community_id]
        assert community_id.startswith(run["world_id"] + "-L")
        assert {c["community"]["size"] for c in members} == {len(members)} and len(members) >= 2
        assert len({c["community"]["kind"] for c in members}) == 1
        assert [c["customer_id"] for c in all_pages(client, url, {"review_only": "false", "community_id": community_id})] == \
            [c["customer_id"] for c in members]
    # the case shows the whole group: members with their own results, edges between members only, sums over members
    rings = 0
    for c in linked:
        case = client.get(f"{url}/{c['customer_id']}").json()
        conforms("Case", case)
        group = case["community"]
        assert {"id": group["id"], "kind": group["kind"], "size": group["size"]} == c["community"]
        ids = {m["customer_id"] for m in group["members"]}
        assert c["customer_id"] in ids and len(ids) == group["size"] == len(group["members"])
        assert ids == {x["customer_id"] for x in linked if x["community"]["id"] == group["id"]}
        for m in group["members"]:
            own = by_id[m["customer_id"]]
            assert (m["risk_score"], m["rank"], m["selected_for_review"]) == (own["risk_score"], own["rank"], own["selected_for_review"])
            assert m["mature_requested_units"] == own["support_counts"]["mature_requested_units"]
        assert group["requested_units"] == sum(m["mature_requested_units"] for m in group["members"])
        assert group["purchased_units"] == sum(m["mature_purchased_units"] for m in group["members"])
        assert group["selected_count"] == sum(m["selected_for_review"] for m in group["members"])
        assert group["edges"], "a community is connected"
        for edge in group["edges"]:
            assert edge["a"] < edge["b"] and {edge["a"], edge["b"]} <= ids and len(edge["types"]) >= 2
        # every neighbour of the customer is a member; the edge carries the larger of the two directed match counts
        neighbours = {n["customer_id"]: n for n in case["neighbors"]}
        assert set(neighbours) <= ids
        for n in neighbours.values():
            edge = next(e for e in group["edges"] if {e["a"], e["b"]} == {c["customer_id"], n["customer_id"]})
            assert edge["coordinated_claim_matches"] >= n["coordinated_claim_matches"] and edge["types"] == n["shared_types"]
        assert group["coordinated_claim_matches"] == sum(e["coordinated_claim_matches"] for e in group["edges"])
        # the kind is the stated rule over observed evidence, checked once per community from its members' own cases
        if c["customer_id"] == min(ids):
            cases = [client.get(f"{url}/{m}").json() for m in sorted(ids)]
            share = any((next(s["value"] for s in k["signals"] if s["code"] == "coordinated_claim_share") or 0) > 0 for k in cases)
            if any("payment" in e["types"] for e in group["edges"]):          # decision D3 as revised by AM-66
                ring = group["coordinated_claim_matches"] >= 1 or group["selected_count"] >= 2 or share
            else:                                                               # address and device only: a household's shape
                ring = group["coordinated_claim_matches"] >= 2 or group["selected_count"] >= 2
            assert group["kind"] == ("ring" if ring else "household")
            rings += group["kind"] == "ring"
    assert rings == run["ring_count"]
    # the filters choose what is shown and nothing else
    ring_rows = all_pages(client, url, {"review_only": "false", "community": "ring"})
    household_rows = all_pages(client, url, {"review_only": "false", "community": "household"})
    none_rows = all_pages(client, url, {"review_only": "false", "community": "none"})
    assert all(c["community"]["kind"] == "ring" for c in ring_rows) and all(c["community"]["kind"] == "household" for c in household_rows)
    assert all(c["community"] is None for c in none_rows)
    assert len(ring_rows) + len(household_rows) + len(none_rows) == len(everyone)
    assert client.get(url, params={"community": "gang"}).status_code == 422
    # truth is never read: a coordination group of the generator surfaces as a ring only through its observed claims and links
    truth = world.truth["relationship_truth"]
    coordinated = set(truth.loc[truth["group_type"] == "coordination", "customer_id"])
    assert any(c["customer_id"] in coordinated for c in ring_rows), "a generated coordination group is found as a ring"


def test_a_large_component_is_split_by_louvain_and_no_member_is_left_alone():
    """Two dense cliques joined by one weak edge form one component of 16 members; Louvain splits it, deterministically."""
    import itertools

    members = [f"W9-C{i:05d}" for i in range(16)]
    cliques = [members[:8], members[8:]]
    rows = [(a, b, 2.0) for clique in cliques for a, b in itertools.combinations(clique, 2)] + [(members[7], members[8], 0.1)]
    # the first clique shares a payment instrument, so the first rule of D3 applies to it (AM-66); the second shares an
    # address and a device only
    edges = pd.DataFrame([{"customer_a": a, "customer_b": b,
                           "shared_types": ["address", "payment"] if b in cliques[0] else ["address", "device"],
                           "shared_value_count": 2, "max_value_fanout": 3, "weight": w} for a, b, w in rows])
    neighbors = pd.DataFrame([(x, y, 1 if {x, y} == {members[0], members[1]} else 0) for a, b, _ in rows for x, y in ((a, b), (b, a))],
                             columns=["customer_id", "neighbor_id", "coordinated_claim_matches"])
    customers = pd.DataFrame({"customer_id": members + ["W9-C99999"], "selected_for_review": [True] + [False] * 16,
                              "coordinated_claim_share": [0.5] + [0.0] * 16, "mature_requested_units": 2, "mature_purchased_units": 10})
    communities, membership = scoring._communities("W9", edges, neighbors, customers)
    again, _ = scoring._communities("W9", edges.sample(frac=1, random_state=3), neighbors, customers)
    assert communities["method"].tolist() == ["louvain", "louvain"] and communities["size"].tolist() == [8, 8]
    assert communities["kind"].tolist() == ["ring", "household"]                     # the match and the share sit in the first clique
    assert communities["community_id"].tolist() == again["community_id"].tolist()    # the input order does not matter
    assert sorted(membership.dropna().groupby(membership.dropna()).apply(lambda s: sorted(s.index)).tolist()) == sorted(cliques)
    assert pd.isna(membership["W9-C99999"])                                           # no supported edge, no community
    first = json.loads(communities["edges"].iloc[0])
    assert len(first) == 28 and all(e["a"] < e["b"] and e["a"] in cliques[0] and e["b"] in cliques[0] for e in first)
    assert sum(e["coordinated_claim_matches"] for e in first) == 1 == communities["coordinated_claim_matches"].iloc[0]
    # a part Louvain would leave alone joins its heaviest neighbour's part
    star = pd.DataFrame([{"customer_a": members[0], "customer_b": m, "shared_types": ["address", "payment"], "shared_value_count": 2,
                          "max_value_fanout": 14, "weight": 1.0} for m in members[1:14]])
    star_neighbors = pd.DataFrame([(x, y, 0) for a, b in zip(star["customer_a"], star["customer_b"]) for x, y in ((a, b), (b, a))],
                                  columns=["customer_id", "neighbor_id", "coordinated_claim_matches"])
    parts, _ = scoring._communities("W9", star, star_neighbors, customers)
    assert (parts["size"] >= 2).all() and parts["size"].sum() == 14


def test_tiers_gate_outcomes_and_primary_signals_follow_the_stated_rules_and_the_filters_agree(client, env, written):
    run = scored_run(client, env, written)
    url = f"{API}/runs/{run['run_id']}/customers"
    everyone = all_pages(client, url, {"review_only": "false"})
    cutoff = run["heavy_returner_cutoff"]
    cases = {}
    for c in everyone:
        if c["eligibility_status"] != "eligible":
            assert c["tier"] is None and c["gate_outcome"] is None
            continue
        tier = "HIGH" if c["selected_for_review"] else "MEDIUM" if c["risk_score"] >= 90 else "LOW"        # decision D1
        assert c["tier"] == tier
        if c["selected_for_review"]:                                                                      # decision D2
            ring = c["community"] is not None and c["community"]["kind"] == "ring"
            assert c["gate_outcome"] == ("ESCALATE" if ring or c["wardrobing_status"] == "elevated" else "HOLD")
        else:
            rate = c["support_counts"]["mature_requested_units"] / c["support_counts"]["mature_purchased_units"]
            assert c["gate_outcome"] == ("WARNING" if tier == "MEDIUM" or rate >= cutoff else "LOW")
        # the chips are the customer's own tags, at most three, each with the value of the signal behind it
        tags = [p["tag"] for p in c["primary_signals"]]
        assert len(tags) <= 3 and set(tags) <= set(c["evidence_tags"]) and len(tags) == min(3, len(c["evidence_tags"]))
        assert all(len(p["label"]) < 40 for p in c["primary_signals"])
    assert {c["gate_outcome"] for c in everyone} >= {"HOLD", "WARNING", "LOW"} and {c["tier"] for c in everyone} >= {"HIGH", "MEDIUM", "LOW"}
    # the SQL filters are the same rules: each filter returns exactly the customers the shown field says
    for name, values in (("tier", ("HIGH", "MEDIUM", "LOW")), ("gate", ("ESCALATE", "HOLD", "WARNING", "LOW"))):
        field = "tier" if name == "tier" else "gate_outcome"
        for value in values:
            shown = [c["customer_id"] for c in all_pages(client, url, {"review_only": "false", name: value})]
            assert shown == [c["customer_id"] for c in everyone if c[field] == value], (name, value)
    assert client.get(url, params={"tier": "CRITICAL"}).status_code == 422
    # the breakdown: five families covering the 43 features, delta against the shown score, the counterfactual against the edge
    selected = [c for c in everyone if c["selected_for_review"]]
    cleared = [c for c in everyone if c["eligibility_status"] == "eligible" and not c["selected_for_review"]]
    for c in selected[:15] + cleared[:10] + [x for x in everyone if x["eligibility_status"] != "eligible"][:3]:
        case = client.get(f"{url}/{c['customer_id']}").json()
        conforms("Case", case)
        cases[c["customer_id"]] = case
        breakdown = case["score_breakdown"]
        if c["eligibility_status"] != "eligible":
            assert breakdown is None
            continue
        assert breakdown["method"] == "family_at_typical_values" and breakdown["typical_from"] == "training"
        assert [f["family"] for f in breakdown["families"]] == ["claims", "timing", "expected_vs_actual", "composition", "volume"]
        assert sum(f["feature_count"] for f in breakdown["families"]) == 43
        for f in breakdown["families"]:
            assert f["delta_points"] == pytest.approx(f["score_without"] - c["risk_score"])
            assert f["in_queue_without"] == (f["raw_score_without"] >= breakdown["threshold_raw_score"])
            assert f["tier_without"] == ("HIGH" if f["in_queue_without"] else "MEDIUM" if f["score_without"] >= 90 else "LOW")
        # the chips follow the families: the first chip's family lowers the score at least as much as the second's
        deltas = {f["family"]: f["delta_points"] for f in breakdown["families"]}
        chips = [p for p in case["customer"]["primary_signals"] if p["family"]]
        assert all(deltas[a["family"]] <= deltas[b["family"]] for a, b in zip(chips, chips[1:]))
        assert all(p["family"] is None for p in case["customer"]["primary_signals"][len(chips):])
        # the rules read the case's own signals; report-only
        codes = {s["code"]: s["value"] for s in case["signals"]}
        fired = {r["rule_id"]: r["fired"] for r in case["rules_fired"]}
        assert set(fired) == {"rate_p90", "claims_2", "refund_ratio_p90", "linked_claimant", "late_half"}
        assert fired["claims_2"] == (codes["claim_lines"] >= 2)
        assert fired["linked_claimant"] == (codes["supported_neighbor_count"] >= 1 and codes["claim_lines"] >= 1)
        assert fired["rate_p90"] in (True, False) and fired["refund_ratio_p90"] in (True, False)
    assert any(f["in_queue_without"] is False for cid in cases if cases[cid]["score_breakdown"]
               for f in cases[cid]["score_breakdown"]["families"] if cases[cid]["customer"]["selected_for_review"]), \
        "some selected customer leaves the queue with a family at typical values"
    # the training median of the rate is the bundle's; a cleared customer with a raw rate above it gets a lower score without that family
    quantiles = bundles.load_bundle(run["model_id"], env["root"]).manifest["feature_quantiles"]
    assert all(quantiles[name] for name in ("raw_return_rate", "claim_lines"))


def test_the_attribution_families_partition_the_model_features_and_match_the_offline_ablation():
    from arai import ablation
    from arai import features as F
    from arai.service import attribution
    assert attribution.CLAIM_FEATURES == ablation.CLAIM_FEATURES and attribution.TIMING_FEATURES == ablation.TIMING_FEATURES
    names = [name for _, _, names in attribution.FAMILIES for name in names]
    assert sorted(names) == sorted(F.feature_order()) and len(names) == 43


def test_under_baseline_fallback_only_the_expected_vs_actual_family_moves_the_score(client, env, written):
    run = scored_run(client, env, written, key="fallback", model_id=env["baseline_id"])
    assert run["model_kind"] == "baseline_fallback"
    url = f"{API}/runs/{run['run_id']}/customers"
    median = bundles.load_bundle(env["baseline_id"], env["root"]).manifest["feature_quantiles"]["raw_return_rate"][1]
    for c in all_pages(client, url)[:10]:
        breakdown = client.get(f"{url}/{c['customer_id']}").json()["score_breakdown"]
        assert breakdown["typical_from"] == "training"                           # the baseline bundle carries the rate's quantiles
        for f in breakdown["families"]:
            if f["family"] == "expected_vs_actual":
                assert f["feature_count"] == 1 and f["raw_score_without"] == pytest.approx(median)   # the rate at its training median
                assert f["in_queue_without"] is False and f["tier_without"] != "HIGH"
            else:
                assert f["feature_count"] == 0 and f["raw_score_without"] == pytest.approx(c["raw_score"])
                assert f["delta_points"] == pytest.approx(0.0) and f["in_queue_without"] is True
    assert 0 < median < 1


def test_the_review_workflow_needs_a_second_person_to_decide_and_its_state_is_derived(client, env, written):
    run = scored_run(client, env, written)
    url = f"{API}/runs/{run['run_id']}/customers"
    queue = all_pages(client, url)
    everyone = all_pages(client, url, {"review_only": "false"})
    # before any review: the queue is new, every eligible customer outside it is auto-logged, the unranked are new
    for c in everyone:
        expected = "auto_logged" if c["gate_outcome"] in ("LOW", "WARNING") else "new"
        assert c["workflow"] == {"state": expected, "opened_by": None, "opened_by_user_id": None, "opened_at": None,
                                  "decided_by": None, "decided_at": None}
    assert {c["workflow"]["state"] for c in queue} == {"new"} and any(c["workflow"]["state"] == "auto_logged" for c in everyone)
    first, second = queue[0]["customer_id"], queue[1]["customer_id"]
    reviews = lambda customer: f"{url}/{customer}/reviews"  # noqa: E731
    post = lambda customer, key, **body: client.post(reviews(customer), json={  # noqa: E731
        "reviewer_name": "Asha", "disposition": "needs_investigation", "note": "Looked at the timeline.", "idempotency_key": key, **body})
    # a note never moves the state; the kinds that do need an open first
    assert post(first, "k0").status_code == 201 and client.get(f"{url}/{first}").json()["customer"]["workflow"]["state"] == "new"
    for kind in ("approve", "reject", "request_approval"):
        refused = post(first, "k-" + kind, kind=kind)
        assert refused.status_code == 409 and refused.json()["error_code"] == "case_not_open", kind
    opened = post(first, "k1", kind="open")
    assert opened.status_code == 201 and opened.json()["kind"] == "open"
    conforms("Review", opened.json())
    state = client.get(f"{url}/{first}").json()["customer"]["workflow"]
    assert state["state"] == "in_review" and state["opened_by"] == "Asha" and state["opened_at"] and state["decided_by"] is None
    # the reviewer who opened the case cannot decide it; the message is fixed
    for kind in ("approve", "reject"):
        refused = post(first, "k2-" + kind, kind=kind)
        assert refused.status_code == 409 and refused.json()["error_code"] == "second_reviewer_required"
        assert refused.json()["message"] == "You opened this case. A different reviewer must approve or reject it."
    assert post(first, "k3", kind="request_approval").status_code == 201
    assert client.get(f"{url}/{first}").json()["customer"]["workflow"]["state"] == "awaiting_approval"
    # the approval band: awaiting cases, without the ones this reviewer opened
    band = all_pages(client, url, {"state": "awaiting_approval"})
    assert [c["customer_id"] for c in band] == [first]
    assert all_pages(client, url, {"state": "awaiting_approval", "exclude_reviewer": "Asha"}) == []
    assert [c["customer_id"] for c in all_pages(client, url, {"state": "awaiting_approval", "exclude_reviewer": "Ravi"})] == [first]
    # contract 1.16.0: the same band by the signed-in user's id, not a typed name
    asha, ravi = client.as_user("Asha"), client.as_user("Ravi")
    assert all_pages(asha, url, {"state": "awaiting_approval", "exclude_mine": "true"}) == []
    assert [c["customer_id"] for c in all_pages(ravi, url, {"state": "awaiting_approval", "exclude_mine": "true"})] == [first]
    assert client.get(f"{url}/{first}").json()["customer"]["workflow"]["opened_by_user_id"] == asha.get(f"{API}/me").json()["user_id"]
    decided = post(first, "k4", kind="approve", reviewer_name="Ravi", disposition="likely_legitimate")
    assert decided.status_code == 201
    state = client.get(f"{url}/{first}").json()["customer"]["workflow"]
    assert state["state"] == "approved" and state["opened_by"] == "Asha" and state["decided_by"] == "Ravi" and state["decided_at"]
    assert [c["customer_id"] for c in all_pages(client, url, {"state": "approved"})] == [first]
    # feedback on a cleared case records an opinion without moving it out of the log
    cleared = next(c for c in everyone if c["workflow"]["state"] == "auto_logged")["customer_id"]
    assert post(cleared, "k5", kind="feedback", disposition="likely_legitimate", note="Agree: the basket predicts this.").status_code == 201
    row = client.get(f"{url}/{cleared}").json()["customer"]
    assert row["workflow"]["state"] == "auto_logged" and row["latest_disposition"] == "likely_legitimate"
    # a reopen after a decision goes back into review; a reject by a second person closes it the other way
    assert post(second, "k6", kind="open", reviewer_name="Ravi").status_code == 201
    assert post(second, "k7", kind="reject", reviewer_name="Asha", disposition="likely_legitimate").status_code == 201
    assert client.get(f"{url}/{second}").json()["customer"]["workflow"]["state"] == "rejected"
    assert post(second, "k8", kind="open", reviewer_name="Asha").status_code == 201
    assert client.get(f"{url}/{second}").json()["customer"]["workflow"]["state"] == "in_review"
    # every state filter returns exactly the customers whose workflow says so; the list is still append-only
    for state_name in ("new", "in_review", "awaiting_approval", "approved", "rejected", "auto_logged"):
        shown = [c["customer_id"] for c in all_pages(client, url, {"review_only": "false", "state": state_name})]
        assert shown == [c["customer_id"] for c in all_pages(client, url, {"review_only": "false"}) if c["workflow"]["state"] == state_name]
    history = client.get(reviews(first)).json()["items"]
    assert [r["kind"] for r in history] == ["note", "open", "request_approval", "approve"]
    assert post(first, "k9", note=" ").status_code == 422 and post(first, "k10", kind="close").status_code == 422


def test_workflow_rules_refuse_a_second_open_a_second_decision_and_actions_out_of_scope(client, env, written):
    """Contract 1.13.0: the state machine is closed. One open at a time, one decision until a reopen, names compared without
    case, the workflow kinds for the queue and feedback for the rest, a reading with every decision, no NUL byte anywhere."""
    run = scored_run(client, env, written)
    url = f"{API}/runs/{run['run_id']}/customers"
    queue = all_pages(client, url)
    everyone = all_pages(client, url, {"review_only": "false"})
    first, second = queue[2]["customer_id"], queue[3]["customer_id"]
    post = lambda customer, key, **body: client.post(f"{url}/{customer}/reviews", json={  # noqa: E731
        "reviewer_name": "Asha", "disposition": "needs_investigation", "note": "n", "idempotency_key": key, **body})
    assert post(first, "o1", kind="open").status_code == 201
    twice = post(first, "o2", kind="open", reviewer_name="Ravi")                      # cannot take over an open case
    assert twice.status_code == 409 and twice.json()["error_code"] == "case_already_open"
    for name in ("asha", " ASHA "):                                                      # the opener, however spelled
        refused = post(first, "a-" + name.strip(), kind="approve", reviewer_name=name)
        assert refused.status_code == 409 and refused.json()["error_code"] == "second_reviewer_required", name
    assert post(first, "r1", kind="request_approval").status_code == 201
    again = post(first, "r2", kind="request_approval")
    assert again.status_code == 409 and again.json()["error_code"] == "case_already_open"
    unresolved = post(first, "d0", kind="approve", reviewer_name="Ravi", disposition="unresolved")
    assert unresolved.status_code == 422 and unresolved.json()["details"][0]["rule_id"] == "request.decision_disposition"
    assert post(first, "d1", kind="approve", reviewer_name="Ravi").status_code == 201
    for kind in ("approve", "reject", "request_approval"):                                # decided: nothing but a reopen
        refused = post(first, "d2-" + kind, kind=kind, reviewer_name="Meera")
        assert refused.status_code == 409 and refused.json()["error_code"] == "case_decided", kind
    state = client.get(f"{url}/{first}").json()["customer"]["workflow"]
    assert state["state"] == "approved" and state["decided_by"] == "Ravi"
    assert post(first, "n1", reviewer_name="Meera").status_code == 201                  # a note is always allowed
    assert post(first, "o3", kind="open", reviewer_name="Meera").status_code == 201     # the way back is a reopen
    assert client.get(f"{url}/{first}").json()["customer"]["workflow"]["state"] == "in_review"
    # scope: the workflow kinds belong to the queue, feedback to the customers outside it
    outside = next(c for c in everyone if c["eligibility_status"] == "eligible" and not c["selected_for_review"])["customer_id"]
    refused = post(outside, "s1", kind="open")
    assert refused.status_code == 409 and refused.json()["error_code"] == "out_of_scope"
    refused = post(first, "s2", kind="feedback", disposition="likely_legitimate")
    assert refused.status_code == 409 and refused.json()["error_code"] == "out_of_scope"
    assert post(outside, "s3", kind="feedback", disposition="likely_legitimate").status_code == 201
    # a NUL byte is a 422, never a database error
    nul = post(first, "z1", note="bad\x00byte")
    assert nul.status_code == 422 and nul.json()["error_code"] == "invalid_request"
    assert client.get(url, params={"search": "a\x00b"}).status_code == 422
    # concurrent decisions on one case: one lands, the others meet the decided case
    assert post(second, "c0", kind="open").status_code == 201
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(4) as pool:
        answers = list(pool.map(lambda i: post(second, f"c{i}", kind="approve" if i % 2 else "reject", reviewer_name=f"R{i}").status_code,
                                range(1, 5)))
    assert sorted(answers) == [201, 409, 409, 409]
    decided = client.get(f"{url}/{second}").json()["customer"]["workflow"]
    assert decided["state"] in ("approved", "rejected") and decided["decided_by"].startswith("R")


def test_the_cleared_heavy_returner_view_is_filtered_by_the_server(client, env, written):
    run = scored_run(client, env, written)
    url = f"{API}/runs/{run['run_id']}/customers"
    cutoff = run["heavy_returner_cutoff"]
    everyone = all_pages(client, url, {"review_only": "false"})
    expected = [c["customer_id"] for c in everyone if c["eligibility_status"] == "eligible" and not c["selected_for_review"]
                and c["support_counts"]["mature_purchased_units"] and
                c["support_counts"]["mature_requested_units"] / c["support_counts"]["mature_purchased_units"] >= cutoff]
    shown = all_pages(client, url, {"review_only": "false", "cleared_heavy": "true"})
    assert expected and [c["customer_id"] for c in shown] == expected
    assert all(c["cleared_reason"] for c in shown)                               # every one carries the reason it was left out
    assert all_pages(client, url, {"cleared_heavy": "true"}) == []               # the review set holds no cleared customer


def test_a_dataset_nothing_was_scored_on_can_be_removed_and_one_with_runs_is_kept(client, env, written, tmp_path):
    from arai.generator import generate_world, write_world
    run = scored_run(client, env, written)
    kept = client.delete(f"{API}/datasets/{run['dataset_id']}")
    assert kept.status_code == 409 and kept.json()["error_code"] == "dataset_in_use"
    assert client.get(f"{API}/datasets/{run['dataset_id']}").status_code == 200
    other = write_world(generate_world(FIXTURE_SEED + 1), artifact_root=tmp_path / "artifacts", private_root=tmp_path / "private")
    manifest = (other["operational"] / "manifest.json").read_text(encoding="utf-8")
    created = client.post(f"{API}/datasets", data={"manifest": manifest}, files=upload_parts(other))
    assert created.status_code == 201, created.text
    stored = Path(env["root"]) / "datasets" / created.json()["dataset_id"]
    assert stored.is_dir()
    assert client.delete(f"{API}/datasets/{created.json()['dataset_id']}").status_code == 204
    assert client.get(f"{API}/datasets/{created.json()['dataset_id']}").status_code == 404 and not stored.exists()
    assert client.delete(f"{API}/datasets/{created.json()['dataset_id']}").status_code == 404


def test_the_clean_up_removes_notes_runs_and_datasets_in_the_right_order_and_keeps_the_rest(client, env, written):
    run = scored_run(client, env, written)
    url = f"{API}/runs/{run['run_id']}/customers"
    first = client.get(url, params={"limit": 1}).json()["items"][0]["customer_id"]
    assert client.post(f"{url}/{first}/reviews", json={"reviewer_name": "Asha", "disposition": "unresolved", "note": "n",
                                                      "idempotency_key": "clean-1"}).status_code == 201
    store = Store(env["config"].database_url)
    before = store.counts()
    assert before["runs"] >= 1 and before["reviews"] == 1 and before["result_rows"] > 0 and before["models"] >= 1
    # datasets without runs: nothing goes while the run refers to the dataset
    assert store.wipe(datasets=True)["datasets"] == [] and store.counts()["datasets"] == before["datasets"]
    # notes only
    assert store.wipe(notes=True)["reviews"] == 1 and store.counts()["reviews"] == 0
    assert client.post(f"{url}/{first}/reviews", json={"reviewer_name": "Asha", "disposition": "unresolved", "note": "n",
                                                      "idempotency_key": "clean-1"}).status_code == 201   # the key is free again
    # runs take their results, memos and notes; the dataset, models and experiments stay
    removed = store.wipe(runs=True)
    assert removed["runs"] == before["runs"] and removed["result_rows"] == before["result_rows"] and removed["reviews"] == 1
    after = store.counts()
    assert after["runs"] == 0 and after["result_rows"] == 0 and after["reviews"] == 0 and after["run_memos"] == 0
    assert after["datasets"] == before["datasets"] and after["models"] == before["models"] and after["experiments"] == before["experiments"]
    assert client.get(f"{API}/runs/{run['run_id']}").status_code == 404
    # now the dataset can go, and the files with it (the caller removes them by artifact key)
    gone = store.wipe(datasets=True)["datasets"]
    assert [d["id"] for d in gone] == [run["dataset_id"]] and store.counts()["datasets"] == 0
    assert client.get(f"{API}/datasets/{run['dataset_id']}").status_code == 404
    # scoring still works afterwards: register again and run
    again = register(client, written)
    assert client.post(f"{API}/runs", json={"dataset_id": again["dataset_id"], "idempotency_key": "after-clean"}).status_code == 202


def test_the_revised_kind_rule_asks_more_of_address_and_device_only_groups():
    payment = [{"types": ["device", "payment"]}]
    household = [{"types": ["address", "device"]}, {"types": ["address", "device"]}]
    assert scoring.community_kind(payment, 0, 1, False) == "ring"                 # the first rule stands where a card is shared
    assert scoring.community_kind(payment, 0, 0, True) == "ring"
    assert scoring.community_kind(payment, 1, 0, False) == "household"
    assert scoring.community_kind(household, 1, 1, True) == "household"           # one matching claim is not enough
    assert scoring.community_kind(household, 0, 2, False) == "ring"
    assert scoring.community_kind(household, 2, 0, False) == "ring"


def test_refunds_absent_signals_and_the_queue_export_follow_the_stored_results(client, env, written):
    import csv
    import io
    run = scored_run(client, env, written)
    url = f"{API}/runs/{run['run_id']}/customers"
    everyone = all_pages(client, url, {"review_only": "false"})
    # refunds per customer are the refunded return lines of its own timeline; the claim part is the claim lines among them
    for c in [x for x in everyone if x["selected_for_review"]][:12] + [x for x in everyone if not x["selected_for_review"]][:12]:
        case = client.get(f"{url}/{c['customer_id']}").json()
        conforms("Case", case)
        refunded = [e for e in case["timeline"] if e["event_type"] != "purchase" and e["line_status"] == "refunded"]
        assert c["refunded_inr"] == pytest.approx(sum(e["amount_inr"] or 0 for e in refunded), abs=0.01)
        assert c["claim_refunded_inr"] == pytest.approx(sum(e["amount_inr"] or 0 for e in refunded if e["event_type"] == "transaction_claim"), abs=0.01)
        assert case["customer"]["refunded_inr"] == c["refunded_inr"] and 0 <= c["claim_refunded_inr"] <= c["refunded_inr"]
    # absent signals: only for an eligible customer outside the queue, and exactly the tags it does not carry
    for c in everyone:
        if c["eligibility_status"] == "eligible" and not c["selected_for_review"]:
            assert c["absent_signals"] == [t for t in scoring.TAGS if t not in c["evidence_tags"]]
        else:
            assert c["absent_signals"] is None
    # the run's totals are the sums over the review set and over the rule's set
    body = client.get(f"{API}/runs/{run['run_id']}").json()
    conforms("Run", body)
    for name, key in (("review_set", "selected_for_review"), ("rule_set", "baseline_selected")):
        members = [c for c in everyone if c[key]]
        assert body["refunds"][name]["customers"] == len(members)
        assert body["refunds"][name]["refunded_inr"] == pytest.approx(sum(c["refunded_inr"] for c in members), abs=0.05)
        assert body["refunds"][name]["claim_refunded_inr"] == pytest.approx(sum(c["claim_refunded_inr"] for c in members), abs=0.05)
    # the export is the filtered list, every row, in queue order, with the same values
    answer = client.get(f"{url}/export")
    assert answer.status_code == 200 and answer.headers["content-type"].startswith("text/csv")
    assert "attachment" in answer.headers["content-disposition"] and run["run_id"] in answer.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(answer.text)))
    assert rows[0] == views.EXPORT_COLUMNS
    queue = all_pages(client, url)
    assert [r[1] for r in rows[1:]] == [c["customer_id"] for c in queue]
    first = dict(zip(rows[0], rows[1]))
    assert first["rank"] == str(queue[0]["rank"]) and first["recommendation"] == queue[0]["gate_outcome"]
    assert float(first["refunded_inr"]) == pytest.approx(queue[0]["refunded_inr"])
    everyone_export = list(csv.reader(io.StringIO(client.get(f"{url}/export", params={"review_only": "false", "tier": "MEDIUM"}).text)))
    assert [r[1] for r in everyone_export[1:]] == [c["customer_id"] for c in all_pages(client, url, {"review_only": "false", "tier": "MEDIUM"})]
    assert client.get(f"{url}/export", params={"tier": "high"}).status_code == 422
    # a reviewer name that starts like a formula is exported as text
    target = queue[1]["customer_id"]
    assert client.post(f"{url}/{target}/reviews", json={"reviewer_name": "=HYPERLINK(\"x\")", "kind": "open", "disposition": "needs_investigation",
                                                     "note": "n", "idempotency_key": "export-1"}).status_code == 201
    opened = list(csv.reader(io.StringIO(client.get(f"{url}/export", params={"state": "in_review"}).text)))
    row = dict(zip(opened[0], next(r for r in opened[1:] if r[1] == target)))
    assert row["opened_by"].startswith("'=") and row["status"] == "in_review"


def test_responses_carry_hardening_headers_and_missing_assets_are_not_the_app_shell(client, env):
    answer = client.get(f"{API}/health")
    assert answer.headers["x-content-type-options"] == "nosniff" and answer.headers["x-frame-options"] == "DENY"
    assert answer.headers["cache-control"] == "no-store"
    dist = Path(__file__).resolve().parents[1] / "web" / "dist"
    if not (dist / "index.html").is_file():
        pytest.skip("the UI is not built")
    with TestClient(create_app(env["config"], static_dir=dist)) as served:
        assert served.get("/runs/run-x/customers").status_code == 200                       # a client-side route
        assert served.get("/assets/does-not-exist.js").status_code == 404
        assert served.get("/missing.png").status_code == 404
        assert served.get("/api/v1/nope").json()["error_code"] == "not_found"


def test_the_style_screen_extras_are_sums_over_the_same_lines_as_the_style_states(client, env, written, world):
    run = scored_run(client, env, written)
    url = f"{API}/runs/{run['run_id']}/styles"
    styles = all_pages(client, url)
    conforms("StylePage", {"items": styles, "next_cursor": None})
    customers = {c["customer_id"]: c for c in all_pages(client, f"{API}/runs/{run['run_id']}/customers", {"review_only": "false"})}
    skus = world.tables["sku_master"].drop_duplicates("style_id").set_index("style_id")
    names = {}
    for style in styles:
        assert style["name"].startswith(f"{skus.loc[style['style_id'], 'brand']} {skus.loc[style['style_id'], 'category']}")
        names.setdefault(style["name"], []).append(style["style_id"])
        assert sum(r["units"] for r in style["reason_codes"]) == style["requested_units"]            # the same mature requests
        assert [r["units"] for r in style["reason_codes"]] == sorted((r["units"] for r in style["reason_codes"]), reverse=True)
        assert len({r["code"] for r in style["reason_codes"]}) == len(style["reason_codes"])
        share = style["flagged_returner_share"]
        assert share["denominator"] == style["unique_returners"] and 0 <= share["numerator"] <= share["denominator"]
        assert share["share"] == (share["numerator"] / share["denominator"] if share["denominator"] else None)
        assert style["ring_returners"] <= style["unique_returners"]
        if style["median_return_day"] is not None:
            assert style["median_return_day"] >= 0 and 0 <= style["share_in_last_five_days"] <= 1
        if style["requested_units"] == 0:
            assert style["reason_codes"] == [] and share["numerator"] == 0
    assert all(len(ids) == 1 for ids in names.values()), "a repeated brand and category carries the style id"
    assert any(s["flagged_returner_share"]["numerator"] > 0 for s in styles) and any(s["ring_returners"] > 0 for s in styles)
    # the drawer: returners with their own results, the same customers and order as customer_ids, lines bought and returned
    with_returners = next(s for s in sorted(styles, key=lambda s: -s["unique_returners"]))
    detail = client.get(f"{url}/{with_returners['style_id']}").json()
    conforms("StyleDetail", detail)
    assert detail["customer_ids"] == [r["customer_id"] for r in detail["returners"]] and detail["returners"]
    for r in detail["returners"]:
        own = customers[r["customer_id"]]
        assert (r["risk_score"], r["rank"], r["selected_for_review"], r["tier"], r["community"]) == \
            (own["risk_score"], own["rank"], own["selected_for_review"], own["tier"], own["community"])
        assert r["return_lines"] >= 1 and r["purchased_lines"] >= 0 and r["last_reason_code"]
        assert r["requested_units"] >= 1
    flagged = {r["customer_id"] for r in detail["returners"] if r["selected_for_review"]}
    assert len(flagged) <= detail["style"]["flagged_returner_share"]["numerator"]
    # the median returner score reads against the run's median
    scored = [r["risk_score"] for r in detail["returners"] if r["risk_score"] is not None]
    if len(detail["returners"]) < 50 and scored:
        assert detail["style"]["median_returner_score"] == pytest.approx(pd.Series(scored).median())
    assert run["median_score"] is not None


def test_the_evaluation_curves_count_abusers_and_legitimate_heavy_returners_at_every_budget(client, env, written, world):
    """Synthetic truth joined to a run on the demonstration world, for the evaluation page only; nothing about the run changes."""
    run = scored_run(client, env, written)
    other = scored_run(client, env, written, key="other", model_id=env["baseline_id"])
    truth = world.truth["customer_truth"]
    published = env["root"] / "experiments" / "EXP-TEST" / "published"
    published.mkdir(parents=True)
    report = {"summary": {"experiment_id": "EXP-TEST", "config_hash": "0" * 64, "selection_status": "selected", "selected_model_id": env["model_id"],
                          "selected_candidate_id": "logreg_c1", "final_test_status": "not_run"}}        # a report from before contract 1.10.0
    (published / "experiment.json").write_text(json.dumps(report), encoding="utf-8")
    export = pd.DataFrame({"world_id": run["world_id"], "customer_id": truth["customer_id"], "y_abuse": truth["y_abuse"].astype(int),
                           "action_types": ""}).sort_values(["y_abuse", "customer_id"], ascending=[False, True])
    export.to_parquet(published / "truth.parquet", index=False)
    store = Store(env["config"].database_url)
    assert ingest.sync_published(env["config"], store) == ["EXP-TEST"]
    summary = client.get(f"{API}/experiments/EXP-TEST").json()["summary"]
    conforms("ExperimentSummary", summary)
    assert summary["git_sha"] is None and summary["train_seeds"] == []                      # an older report reads as the contract says
    conforms("ExperimentSummaryPage", client.get(f"{API}/experiments").json())

    curves = client.get(f"{API}/experiments/EXP-TEST/curves", params={"run_id": run["run_id"], "max_points": 20000}).json()
    conforms("Curves", curves)
    customers = all_pages(client, f"{API}/runs/{run['run_id']}/customers", {"review_only": "false", "eligibility": "eligible"})
    abusers = set(truth.loc[truth["y_abuse"] == 1, "customer_id"])
    rate = lambda c: c["support_counts"]["mature_requested_units"] / c["support_counts"]["mature_purchased_units"]  # noqa: E731
    heavy = {c["customer_id"] for c in customers if c["customer_id"] not in abusers and rate(c) >= run["heavy_returner_cutoff"]}
    assert curves["synthetic_only"] and curves["world_id"] == run["world_id"] and curves["review_budget"] == run["review_budget"]
    assert curves["eligible_count"] == len(customers) == len(curves["points"]) == curves["points"][-1]["k"]
    assert curves["abusers"] == len({c["customer_id"] for c in customers} & abusers) and curves["legitimate_heavy_returners"] == len(heavy)
    by_rank = sorted(customers, key=lambda c: c["rank"])
    by_rule = sorted(customers, key=lambda c: c["baseline_rank"])
    for point in curves["points"][:: max(1, len(curves["points"]) // 50)]:
        k = point["k"]
        assert point["model_abusers_caught"] == sum(c["customer_id"] in abusers for c in by_rank[:k])
        assert point["model_legitimate_heavy_reviewed"] == sum(c["customer_id"] in heavy for c in by_rank[:k])
        assert point["baseline_abusers_caught"] == sum(c["customer_id"] in abusers for c in by_rule[:k])
        assert point["baseline_legitimate_heavy_reviewed"] == sum(c["customer_id"] in heavy for c in by_rule[:k])
    at_budget = next(p for p in curves["points"] if p["k"] == run["review_budget"])
    assert at_budget["model_abusers_caught"] >= 1, "the fixture world has abusers in the queue"
    # the default thinning keeps the first point, the budget and the last point, and is monotone like the full curve
    thinned = client.get(f"{API}/experiments/EXP-TEST/curves", params={"run_id": run["run_id"]}).json()
    ks = [p["k"] for p in thinned["points"]]
    assert len(ks) <= 202 and ks[0] == 1 and ks[-1] == curves["eligible_count"] and run["review_budget"] in ks and ks == sorted(ks)
    assert all(a["model_abusers_caught"] <= b["model_abusers_caught"] for a, b in zip(thinned["points"], thinned["points"][1:]))
    # a run on another world, a run that is not ready, and an unknown experiment are refused, never mixed
    assert client.get(f"{API}/experiments/EXP-TEST/curves", params={"run_id": other["run_id"]}).status_code == 200    # same world, other model
    assert client.get(f"{API}/experiments/NOPE/curves", params={"run_id": run["run_id"]}).status_code == 404
    assert client.get(f"{API}/experiments/EXP-TEST/curves").status_code == 422
    with store.transaction() as db:
        db.execute("UPDATE experiments SET truth_world_id = 'W0000' WHERE id = 'EXP-TEST'")
    refused = client.get(f"{API}/experiments/EXP-TEST/curves", params={"run_id": run["run_id"]})
    assert refused.status_code == 409 and refused.json()["error_code"] == "world_mismatch"


# ------------------------------------------------------------------ investigation memos
def test_without_an_api_key_every_memo_is_unavailable_by_design_and_the_run_still_serves(client, env, written):
    run = scored_run(client, env, written)
    assert env["config"].anthropic_api_key is None
    conforms("Run", run)
    assert run["memos"] == {"selected": run["selected_count"], "ok": 0, "unavailable": run["selected_count"], "complete": True}
    url = f"{API}/runs/{run['run_id']}/customers"
    selected = client.get(url, params={"limit": 2}).json()["items"]
    case = client.get(f"{url}/{selected[0]['customer_id']}").json()
    conforms("Case", case)
    memo = case["memo"]
    assert memo["status"] == "unavailable" and memo["reason"] == "no_api_key" and memo["attempts"] == 0 and memo["summary"] is None
    assert memo["model"] == "claude-opus-5-5" and memo["generated_at"]
    cleared = client.get(url, params={"review_only": "false", "tier": "LOW", "limit": 1}).json()["items"][0]
    assert client.get(f"{url}/{cleared['customer_id']}").json()["memo"]["status"] == "not_selected"
    queued = client.post(f"{API}/runs", json={"dataset_id": run["dataset_id"], "idempotency_key": "later"}).json()
    assert queued["memos"] is None                                                          # null until the run succeeded


class _FakeClient:
    """Stands in for the Anthropic client: returns the drafts given, in order, as the SDK would."""

    def __init__(self, drafts):
        self.drafts, self.calls = list(drafts), []

        class _Messages:
            def create(messages_self, **kwargs):
                self.calls.append(kwargs)
                draft = self.drafts.pop(0)
                stop = "refusal" if draft == "refusal" else "end_turn"
                text = "" if draft == "refusal" else (draft if isinstance(draft, str) else json.dumps(draft))
                block = type("Block", (), {"type": "text", "text": text})()
                return type("Response", (), {"stop_reason": stop, "content": [block]})()

        self.beta = type("Beta", (), {"messages": _Messages()})()


def test_memos_pass_a_deterministic_gate_and_retry_once_and_never_name_another_customer(client, env, written, monkeypatch):
    from arai.service import memo as M
    run = scored_run(client, env, written)
    url = f"{API}/runs/{run['run_id']}/customers"
    selected = [c["customer_id"] for c in client.get(url, params={"limit": 4}).json()["items"]]
    cases = {cid: client.get(f"{url}/{cid}").json() for cid in selected}
    # what the model sees: no reviews, no memo, no sentence, and no identifier but the case's own
    inputs = M.case_input(cases[selected[0]])
    text = json.dumps(inputs)
    assert "reviews" not in inputs and "description" not in text and selected[0] in text
    assert not ({m for m in M.CUSTOMER_ID.findall(text)} - {selected[0]})
    numbers = M._numbers(inputs, set())
    score = cases[selected[0]]["customer"]["risk_score"]
    good = {"summary": "Returns well above what the basket predicts; two claims matched by a linked account.",
            "key_evidence": [{"statement": "Risk score", "panel": "expected", "value": score, "denominator": None}],
            "alternative_explanations": ["A household sharing one address."], "recommended_action": cases[selected[0]]["customer"]["gate_outcome"]}
    assert M.gate(good, inputs, selected[0]) == []
    assert any("not a number of the case" in r for r in M.gate(dict(good, key_evidence=[dict(good["key_evidence"][0], value=12345.678)]), inputs, selected[0]))
    assert any("unknown panel" in r for r in M.gate(dict(good, key_evidence=[dict(good["key_evidence"][0], panel="truth")]), inputs, selected[0]))
    assert any("gate outcome" in r for r in M.gate(dict(good, recommended_action="BLOCK"), inputs, selected[0]))
    assert any("another customer" in r for r in M.gate(dict(good, summary=f"Like {selected[1]}."), inputs, selected[0]))
    assert any("too long" in r for r in M.gate(dict(good, summary="x" * 601), inputs, selected[0]))
    assert round(score, 6) in numbers
    # the batch: a good draft, a draft that fails the gate then passes, a refusal twice, and bad JSON twice
    second = dict(good, key_evidence=[{"statement": "Score", "panel": "expected", "value": cases[selected[1]]["customer"]["risk_score"], "denominator": None}],
                  recommended_action=cases[selected[1]]["customer"]["gate_outcome"])
    bad_then_good = [dict(second, recommended_action="BLOCK"), second]
    store = Store(env["config"].database_url)
    drafts = {selected[0]: [good], selected[1]: bad_then_good, selected[2]: ["refusal", "refusal"], selected[3]: ["not json", "{"]}
    with store.transaction() as db:
        db.execute("DELETE FROM run_memos WHERE run_id = %s", (run["run_id"],))
    monkeypatch.setattr(M, "POOL", 1)
    order = []
    fake = _FakeClient([])
    original_memo_for = M.memo_for

    def memo_for(client_, model, case, attempts=M.ATTEMPTS):
        cid = case["customer"]["customer_id"]
        order.append(cid)
        fake.drafts = list(drafts.get(cid, ["refusal", "refusal"]))
        return original_memo_for(fake, model, case, attempts)
    monkeypatch.setattr(M, "memo_for", memo_for)
    config = ServiceConfig(database_url=env["config"].database_url, artifact_root=env["root"], anthropic_api_key="test-key", memo_model="claude-opus-5-5")
    counts = worker.write_memos(config, store, run["run_id"])
    assert set(order) == set(store.selected_customer_ids(run["run_id"])) and counts["ok"] == 2
    assert fake.calls and fake.calls[0]["model"] == "claude-opus-5-5" and fake.calls[0]["fallbacks"] == "default"
    assert fake.calls[0]["output_config"]["format"]["type"] == "json_schema" and M.FALLBACK_BETA in fake.calls[0]["betas"]
    memos = {cid: client.get(f"{url}/{cid}").json()["memo"] for cid in selected}
    assert memos[selected[0]]["status"] == "ok" and memos[selected[0]]["attempts"] == 1 and memos[selected[0]]["summary"] == good["summary"]
    assert memos[selected[1]]["status"] == "ok" and memos[selected[1]]["attempts"] == 2
    assert memos[selected[2]] == {**memos[selected[2]], "status": "unavailable", "attempts": 2, "reason": "declined", "summary": None}
    assert memos[selected[3]]["status"] == "unavailable" and memos[selected[3]]["reason"] == "not_json"
    for cid, m in memos.items():
        conforms("Case", client.get(f"{url}/{cid}").json())
        if m["status"] == "ok":
            assert m["key_evidence"][0]["value"] == cases[cid]["customer"]["risk_score"] and m["model"] == "claude-opus-5-5"
    progress = client.get(f"{API}/runs/{run['run_id']}").json()["memos"]
    assert progress["ok"] == 2 and progress["complete"] is True and progress["selected"] == run["selected_count"]
    # a memo never changes what the run says about anyone
    assert client.get(url, params={"limit": 4}).json()["items"] == [cases[cid]["customer"] for cid in selected]


# ------------------------------------------------------------------ stage log and cancel
def test_the_stage_log_and_the_done_summary_and_a_cancel_at_either_end(client, env, written):
    run = scored_run(client, env, written)
    conforms("Run", run)
    stages = [entry["stage"] for entry in run["stage_log"]]
    assert stages == ["validate", "features", "eligibility", "scoring", "evidence", "publish"]        # each stage once, in order
    times = [pd.Timestamp(entry["at"]) for entry in run["stage_log"]]
    assert times == sorted(times) and times[-1] <= pd.Timestamp(run["completed_at"])
    styles = all_pages(client, f"{API}/runs/{run['run_id']}/styles")
    assert run["styles_with_verdict"] == sum(s["state"] in ("quality", "targeting", "mixed_or_uncertain") for s in styles)
    # a finished run cannot be cancelled
    refused = client.post(f"{API}/runs/{run['run_id']}/cancel")
    assert refused.status_code == 409 and refused.json()["error_code"] == "run_finished"
    # a queued run is interrupted at once
    queued = client.post(f"{API}/runs", json={"dataset_id": run["dataset_id"], "idempotency_key": "q"}).json()
    cancelled = client.post(f"{API}/runs/{queued['run_id']}/cancel")
    assert cancelled.status_code == 202
    conforms("Run", cancelled.json())
    assert cancelled.json()["status"] == "interrupted" and cancelled.json()["error"]["error_code"] == "cancelled"
    assert cancelled.json()["stage_log"] == [] and cancelled.json()["memos"] is None
    store = Store(env["config"].database_url)
    assert worker.process_one(env["config"], store) is None                                           # nothing left to claim
    # a running run stops at its next stage, keeps no result, and the queue log says why
    running = client.post(f"{API}/runs", json={"dataset_id": run["dataset_id"], "idempotency_key": "r"}).json()

    def hook(stage):
        if stage == "features":
            assert client.post(f"{API}/runs/{running['run_id']}/cancel").status_code == 202
            assert client.get(f"{API}/runs/{running['run_id']}").json()["status"] == "running"       # asked, not yet stopped
    assert worker.process_one(env["config"], store, hook=hook) == running["run_id"]
    stopped = client.get(f"{API}/runs/{running['run_id']}").json()
    assert stopped["status"] == "interrupted" and stopped["error"]["error_code"] == "cancelled" and stopped["stage"] == "eligibility"
    assert [e["stage"] for e in stopped["stage_log"]] == ["validate", "features", "eligibility"]
    assert result_rows(store, running["run_id"]) == dict.fromkeys(RESULT_TABLES, 0)
    assert client.get(f"{API}/runs/{running['run_id']}/customers").status_code == 409
    assert client.post(f"{API}/runs/NOPE/cancel").status_code == 404


# ------------------------------------------------------------------ snapshots of one world and a customer's history (AM-68)
def _publish_truth(env, world, world_id: str) -> None:
    truth = world.truth["customer_truth"]
    published = env["root"] / "experiments" / "EXP-TEST" / "published"
    published.mkdir(parents=True, exist_ok=True)
    report = {"summary": {"experiment_id": "EXP-TEST", "config_hash": "0" * 64, "selection_status": "selected", "selected_model_id": env["model_id"],
                          "selected_candidate_id": "logreg_c1", "final_test_status": "not_run"}}
    (published / "experiment.json").write_text(json.dumps(report), encoding="utf-8")
    pd.DataFrame({"world_id": world_id, "customer_id": truth["customer_id"], "y_abuse": truth["y_abuse"].astype(int),
                  "action_types": ""}).to_parquet(published / "truth.parquet", index=False)


def test_snapshots_of_one_world_keep_the_customer_and_its_history(client, env, written, earlier):
    """A later export of the same customers is a new snapshot of the same world. Each snapshot's scores are its own, notes follow
    the customer, the workflow runs per snapshot, and the queue, the case and the run place the customer against the earlier one."""
    import csv
    import io
    first = scored_run(client, env, earlier, key="earlier")
    second = scored_run(client, env, written, key="later")
    assert first["world_id"] == second["world_id"] and first["dataset_id"] != second["dataset_id"] and first["cutoff"] < second["cutoff"]
    assert register(client, earlier)["dataset_id"] == first["dataset_id"]                  # the same snapshot again: the same dataset
    conforms("Run", second)
    conforms("RunPage", client.get(f"{API}/runs").json())
    assert first["previous_snapshot"] is None
    previous = second["previous_snapshot"]
    assert (previous["run_id"], previous["dataset_id"], previous["cutoff"]) == (first["run_id"], first["dataset_id"], first["cutoff"])

    before = {c["customer_id"]: c for c in all_pages(client, f"{API}/runs/{first['run_id']}/customers", {"review_only": "false"})}
    after = all_pages(client, f"{API}/runs/{second['run_id']}/customers", {"review_only": "false"})
    queued_before = {i for i, c in before.items() if c["selected_for_review"]}
    queued_after = {c["customer_id"] for c in after if c["selected_for_review"]}
    assert (previous["repeat"], previous["new"], previous["left"]) == (
        len(queued_before & queued_after), len(queued_after - queued_before), len(queued_before - queued_after))
    assert set(before) <= {c["customer_id"] for c in after}                                  # the same identifiers, more of them later
    for c in after:                                    # each row's previous field is the customer's own row in the earlier run
        seen = c["previous"]
        assert seen["run_id"] == first["run_id"] and seen["present"] == (c["customer_id"] in before)
        if seen["present"]:
            old = before[c["customer_id"]]
            assert (seen["rank"], seen["risk_score"], seen["selected_for_review"]) == (old["rank"], old["risk_score"], old["selected_for_review"])
        else:
            assert seen["rank"] is None and seen["selected_for_review"] is None
    assert all(c["previous"] is None and c["earlier_decision"] is None for c in before.values())
    url = f"{API}/runs/{second['run_id']}/customers"
    new = {c["customer_id"] for c in all_pages(client, url, {"history": "new_in_queue"})}
    repeat = {c["customer_id"] for c in all_pages(client, url, {"history": "repeat_in_queue"})}
    assert new == queued_after - queued_before and repeat == queued_after & queued_before and repeat

    # a case decided on the earlier snapshot: the decision stays with that snapshot, the later case starts its own review
    target = sorted(repeat)[0]
    for number, (name, kind) in enumerate((("Asha", "open"), ("Ravi", "reject"))):
        made = client.post(f"{API}/runs/{first['run_id']}/customers/{target}/reviews",
                           json={"reviewer_name": name, "kind": kind, "disposition": "needs_investigation",
                                 "note": f"{kind} on the earlier snapshot", "idempotency_key": f"earlier-{number}"})
        assert made.status_code == 201, made.text
        conforms("Review", made.json())
        assert (made.json()["dataset_id"], made.json()["snapshot_cutoff"]) == (first["dataset_id"], first["cutoff"])
    case = client.get(f"{API}/runs/{second['run_id']}/customers/{target}").json()
    conforms("Case", case)
    customer = case["customer"]
    assert customer["workflow"]["state"] == "new"                                            # not decided on this snapshot
    assert customer["earlier_decision"]["state"] == "rejected" and customer["earlier_decision"]["decided_by"] == "Ravi"
    assert customer["earlier_decision"]["cutoff"] == first["cutoff"]
    assert [r["snapshot_cutoff"] for r in case["reviews"]] == [first["cutoff"]] * 2         # the notes follow the customer
    history = case["history"]
    assert [h["run_id"] for h in history] == [first["run_id"], second["run_id"]] and [h["current"] for h in history] == [False, True]
    assert history[0]["workflow"]["state"] == "rejected" and history[0]["workflow"]["decided_by"] == "Ravi"
    assert (history[0]["notes"], history[1]["notes"]) == (2, 0) and all(h["present"] for h in history)
    assert (history[0]["rank"], history[1]["rank"]) == (before[target]["rank"], customer["rank"])
    assert history[1]["gate_outcome"] == customer["gate_outcome"] and history[1]["tier"] == customer["tier"]
    assert [c["customer_id"] for c in all_pages(client, url, {"review_only": "false", "history": "decided_before"})] == [target]
    assert client.get(f"{API}/runs/{second['run_id']}", params={}).json()["previous_snapshot"]["rejected_before"] == 1

    # the later snapshot's review is its own: it opens although the earlier one was decided, and the earlier one stays decided
    opened = client.post(f"{API}/runs/{second['run_id']}/customers/{target}/reviews",
                         json={"reviewer_name": "Asha", "kind": "open", "disposition": "unresolved", "note": "back in the queue",
                               "idempotency_key": "later-0"})
    assert opened.status_code == 201 and opened.json()["dataset_id"] == second["dataset_id"]
    assert client.get(f"{API}/runs/{first['run_id']}/customers/{target}").json()["customer"]["workflow"]["state"] == "rejected"
    assert client.get(f"{API}/runs/{second['run_id']}/customers/{target}").json()["customer"]["workflow"]["state"] == "in_review"
    # an account that signed up after the earlier cutoff shows as absent from that snapshot in its history
    later_account = next(c["customer_id"] for c in after if c["customer_id"] not in before)
    absent = client.get(f"{API}/runs/{second['run_id']}/customers/{later_account}").json()["history"]
    assert [h["present"] for h in absent] == [False, True] and absent[0]["rank"] is None

    # the export carries the history columns, read from the same items
    text = client.get(f"{API}/runs/{second['run_id']}/customers/export", params={"review_only": "false", "history": "decided_before"}).text
    rows = list(csv.reader(io.StringIO(text)))
    row = dict(zip(rows[0], rows[1]))
    assert len(rows) == 2 and row["customer_id"] == target and row["previous_cutoff"] == first["cutoff"][:10]
    assert row["previous_rank"] == str(before[target]["rank"]) and row["previous_in_queue"] == "yes"
    assert row["earlier_decision"] == f"rejected on the {first['cutoff'][:10]} snapshot by Ravi" and row["cutoff"] == second["cutoff"][:10]


def test_evaluation_truth_applies_only_to_the_snapshot_it_describes(client, env, written, earlier, world):
    """Truth export rows are the world's own snapshot's; on an earlier snapshot fewer customers had acted, so curves refuse it."""
    first = scored_run(client, env, earlier, key="earlier")
    second = scored_run(client, env, written, key="later")
    target = env["root"] / "worlds" / world.world_id / "operational"
    target.mkdir(parents=True)
    shutil.copy(written["operational"] / "manifest.json", target / "manifest.json")
    _publish_truth(env, world, second["world_id"])
    assert ingest.sync_published(env["config"], Store(env["config"].database_url)) == ["EXP-TEST"]
    refused = client.get(f"{API}/experiments/EXP-TEST/curves", params={"run_id": first["run_id"]})
    assert refused.status_code == 409 and refused.json()["error_code"] == "world_mismatch" and "snapshot" in refused.json()["message"]
    assert client.get(f"{API}/experiments/EXP-TEST/curves", params={"run_id": second["run_id"]}).status_code == 200


# ------------------------------------------------------------------ authentication and roles (contract 1.16.0, AM-69)
def _fill(path: str) -> str:
    return path.replace("{run_id}", "run-x").replace("{customer_id}", "C-x").replace("{dataset_id}", "ds-x") \
               .replace("{style_id}", "S-x").replace("{experiment_id}", "E-x")


def test_every_route_declares_a_permission_and_refuses_a_request_without_a_session(client):
    from arai.service import auth
    anonymous = TestClient(client.app)
    for path, operations in CONTRACT["paths"].items():
        for method in operations:
            if method not in ("get", "post", "delete"):
                continue
            needed = auth.ROUTE_PERMISSIONS.get((method.upper(), f"{API}{path}"))
            assert needed is not None, (method, path)                                   # no route without a declared permission
            if needed == auth.PUBLIC:
                continue
            response = anonymous.request(method.upper(), f"{API}{_fill(path)}", json={} if method == "post" else None)
            assert response.status_code == 401, (method, path, response.status_code)
            conforms("Error", response.json())
            assert response.json()["error_code"] == "authentication_required"
    assert anonymous.get(f"{API}/health").status_code == 200                              # monitoring needs no session


def test_roles_decide_what_each_person_may_do(client, env, written):
    run = scored_run(client, env, written)
    url = f"{API}/runs/{run['run_id']}/customers"
    customer = client.get(url, params={"limit": 1}).json()["items"][0]["customer_id"]
    note = lambda key, **body: {"disposition": "needs_investigation", "note": "n", "idempotency_key": key, **body}  # noqa: E731
    viewer, reviewer, admin = (client.as_user(name) for name in ("Viewer", "Reviewer", "Admin"))
    me = viewer.get(f"{API}/me").json()
    conforms("Me", me)
    assert me["roles"] == ["viewer"] and me["permissions"] == ["read"] and me["idle_minutes"] == 60
    # a viewer reads everything and changes nothing; export is for reviewers and above
    assert viewer.get(url).status_code == 200 and viewer.get(f"{url}/{customer}").status_code == 200
    for refused in (viewer.get(f"{url}/export"), viewer.post(f"{url}/{customer}/reviews", json=note("v1")),
                    viewer.post(f"{API}/runs", json={"dataset_id": run["dataset_id"], "idempotency_key": "v"})):
        assert refused.status_code == 403 and refused.json()["error_code"] == "forbidden", refused.text
        conforms("Error", refused.json())
    assert "reviewer role" in viewer.get(f"{url}/export").json()["message"]
    # a reviewer notes, opens and exports, but does not decide or operate
    assert reviewer.get(f"{url}/export").status_code == 200
    assert reviewer.post(f"{url}/{customer}/reviews", json=note("r1", kind="open")).status_code == 201
    decide = reviewer.post(f"{url}/{customer}/reviews", json=note("r2", kind="approve"))
    assert decide.status_code == 403 and "approver role" in decide.json()["message"]
    assert reviewer.post(f"{API}/runs", json={"dataset_id": run["dataset_id"], "idempotency_key": "r"}).status_code == 403
    # an admin operates and exports, and does not review
    assert admin.post(f"{API}/runs", json={"dataset_id": run["dataset_id"], "idempotency_key": "a"}).status_code == 202
    assert admin.get(f"{url}/export").status_code == 200
    assert admin.post(f"{url}/{customer}/reviews", json=note("a1")).status_code == 403
    # every refusal and every export is in the audit log
    with Store(env["config"].database_url).transaction() as db:
        kinds = [r["kind"] for r in db.execute("SELECT kind FROM auth_events ORDER BY id").fetchall()]
    assert kinds.count("export") == 2 and kinds.count("refused") >= 6 and "sign_in" in kinds


def test_a_post_or_delete_needs_the_session_csrf_token(client, env, written):
    dataset = register(client, written)
    raw = TestClient(client.app)
    raw.cookies.set("arai_session", client.cookies.get("arai_session"))                  # the session without its token
    body = {"dataset_id": dataset["dataset_id"], "idempotency_key": "csrf"}
    for headers in ({}, {"X-CSRF-Token": "not-the-token"}):
        refused = raw.post(f"{API}/runs", json=body, headers=headers)
        assert refused.status_code == 403 and refused.json()["error_code"] == "csrf_required"
    assert raw.delete(f"{API}/datasets/{dataset['dataset_id']}").json()["error_code"] == "csrf_required"
    assert raw.post(f"{API}/runs", json=body, headers={"X-CSRF-Token": client.csrf}).status_code == 202


def test_a_session_ends_when_idle_too_long_past_its_maximum_age_signed_out_or_disabled(client, env):
    store = Store(env["config"].database_url)
    def session(name):
        return SignedInClient(client.app).sign_in(name)
    def age(signed, column, interval):
        with store.transaction() as db:
            db.execute(f"UPDATE sessions SET {column} = now() - interval '{interval}' WHERE user_id = %s AND ended_at IS NULL",
                       (signed.get(f"{API}/me").json()["user_id"],))
    idle = session("Meera")
    age(idle, "last_seen_at", "59 minutes")
    assert idle.get(f"{API}/me").status_code == 200                                        # 59 minutes idle: still in, and touched
    age(idle, "last_seen_at", "61 minutes")
    gone = idle.get(f"{API}/me")
    assert gone.status_code == 401 and "without activity" in gone.json()["message"]
    assert idle.get(f"{API}/me").json()["message"] == "Sign in first."                     # ended once; a dead cookie stays dead
    old = session("Meera")
    with store.transaction() as db:
        db.execute("UPDATE sessions SET expires_at = now() - interval '1 second' WHERE ended_at IS NULL AND user_id = "
                   "(SELECT id FROM users WHERE display_name = 'Meera')")
    assert "maximum length" in old.get(f"{API}/me").json()["message"]
    out = session("Meera")
    assert out.post(f"{API}/auth/logout").status_code == 204
    assert out.get(f"{API}/me").status_code == 401
    disabled = session("Ravi")
    client.app.state.service.auth.disable(disabled.get(f"{API}/me").json()["user_id"])
    assert "disabled" in disabled.get(f"{API}/me").json()["message"]                     # at once, not at the next sign-in
    with store.transaction() as db:
        reasons = sorted(r["ended_reason"] for r in db.execute("SELECT ended_reason FROM sessions WHERE ended_reason IS NOT NULL"))
    assert reasons == ["disabled", "idle", "max_age", "sign_out"]


def test_the_development_login_is_for_laptops_and_single_sign_on_is_step_two(client, env):
    users = client.get(f"{API}/auth/dev-users").json()
    conforms("DevUsers", users)
    assert {"display_name": "Admin", "roles": ["admin"]} in users["users"]
    unknown = TestClient(client.app).post(f"{API}/auth/dev-login", json={"user": "Mallory"})
    assert unknown.status_code == 422
    with pytest.raises(ValueError, match="refused with APP_PROFILE=vm"):
        ServiceConfig(database_url=env["config"].database_url, artifact_root=env["root"], profile="vm", auth_mode="dev")
    defaults = ServiceConfig(database_url="x", artifact_root=env["root"]).dev_users
    assert ("Admin", ("admin",)) in defaults and ("Arjun", ("reviewer",)) in defaults and ("Priya", ("viewer",)) in defaults   # admin does not review
    sso = ServiceConfig(database_url=env["config"].database_url, artifact_root=env["root"], auth_mode="oidc", dev_users=TEST_USERS)
    with TestClient(create_app(sso)) as served:
        assert served.post(f"{API}/auth/dev-login", json={"user": "Tester"}).status_code == 404
        assert served.get(f"{API}/auth/dev-users").status_code == 404
        later = served.get(f"{API}/auth/login")
        assert later.status_code == 503 and later.json()["error_code"] == "single_sign_on_unavailable"
    signed = client.post(f"{API}/auth/dev-login", json={"user": "tester"})                # names compare without regard to case
    conforms("Me", signed.json())
    cookie = signed.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "secure" not in cookie   # Secure on the vm profile only


def test_the_second_reviewer_rule_compares_user_ids_and_names_only_for_older_reviews(client, env, written):
    run = scored_run(client, env, written)
    url = f"{API}/runs/{run['run_id']}/customers"
    first, second = [c["customer_id"] for c in client.get(url, params={"limit": 2}).json()["items"]]
    asha, ravi = client.as_user("Asha"), client.as_user("Ravi")
    body = lambda key, kind, reading="needs_investigation": {"kind": kind, "disposition": reading, "note": "n", "idempotency_key": key}  # noqa: E731
    store = Store(env["config"].database_url)
    assert asha.post(f"{url}/{first}/reviews", json=body("o", "open")).status_code == 201
    # the same person under another name is still the opener
    with store.transaction() as db:
        db.execute("UPDATE users SET display_name = 'Asha Kumar' WHERE display_name = 'Asha'")
    refused = asha.post(f"{url}/{first}/reviews", json=body("a1", "approve"))
    assert refused.status_code == 409 and refused.json()["error_code"] == "second_reviewer_required"
    # a different person who happens to carry the opener's old name is a second reviewer
    with store.transaction() as db:
        db.execute("UPDATE users SET display_name = 'Asha' WHERE display_name = 'Ravi'")
    decided = ravi.post(f"{url}/{first}/reviews", json=body("a2", "approve", "likely_legitimate"))
    assert decided.status_code == 201 and decided.json()["reviewer_name"] == "Asha" and decided.json()["author"]["verified"]
    # an open written before sign-in existed has no user id: its typed name decides, and it reads as unverified
    run_row = store.get_run(run["run_id"])
    with store.transaction() as db:
        db.execute("""INSERT INTO reviews (id, world_id, customer_id, run_id, model_id, reviewer_name, disposition, note, kind, dataset_id)
                      VALUES ('rev-legacy', %s, %s, %s, %s, 'Meera', 'unresolved', 'typed name', 'open', %s)""",
                   (run_row["world_id"], second, run["run_id"], run_row["model_id"], run_row["dataset_id"]))
    legacy = [r for r in client.get(f"{url}/{second}/reviews").json()["items"] if r["review_id"] == "rev-legacy"][0]
    assert legacy["author"] == {"user_id": None, "display_name": "Meera", "verified": False}
    meera = client.as_user("Meera")
    assert meera.post(f"{url}/{second}/reviews", json=body("m1", "approve")).json()["error_code"] == "second_reviewer_required"
    assert client.as_user("R1").post(f"{url}/{second}/reviews", json=body("r1", "approve", "likely_legitimate")).status_code == 201
