"""Inference, storage and the HTTP API against a real PostgreSQL (final-spec components 11, 12, 14)."""
import json
import shutil
import subprocess
import sys
import threading

import pandas as pd
import pytest
import yaml
from fastapi.testclient import TestClient
from openapi_schema_validator import OAS30Validator

from arai import bundles
from arai.operational import TABLES, read_csv_world
from arai.paths import SPEC_ROOT
from arai.service import datasets, ingest, scoring, worker
from arai.service.api import create_app
from arai.service.config import ServiceConfig
from arai.service.store import RESULT_TABLES, Store

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


@pytest.fixture
def env(trained, database_url, tmp_path):
    """A serving root with the baseline and one model bundle, the model promoted, and an empty database."""
    root = tmp_path / "artifacts"
    shutil.copytree(trained["artifact_root"] / "experiments", root / "experiments")
    experiment = root / "experiments" / "EXP-TEST"
    baseline_id = bundles.build_baseline_bundle(experiment, root)
    model_id = bundles.build_model_bundle(experiment, "logreg_c1", root)
    bundles.activate(model_id, baseline_id, "selected", "EXP-TEST", None, root)
    config = ServiceConfig(database_url=database_url, artifact_root=root, ui_origins=("http://localhost:5173",))
    return {"config": config, "root": root, "baseline_id": baseline_id, "model_id": model_id, "experiment": experiment}


@pytest.fixture
def client(env):
    with TestClient(create_app(env["config"])) as test_client:
        yield test_client


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
    assert client.post(url_a, json=dict(note, reviewer_name="", idempotency_key="n3")).status_code == 422

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
    assert [n["reviewer_name"] for n in notes["items"]] == ["Asha", "Ravi"]                    # the first note is visible from run B
    assert notes["items"][0]["run_id"] == run_a["run_id"] and notes["items"][0]["model_id"] == env["model_id"]   # origin kept
    assert notes["items"][1]["run_id"] == run_b["run_id"] and notes["items"][1]["model_id"] == env["baseline_id"]
    case = client.get(f"{API}/runs/{run_a['run_id']}/customers/{customer}").json()
    assert len(case["reviews"]) == 2 and case["customer"]["latest_disposition"] == "likely_legitimate"
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
    assert implemented == contracted                               # nothing missing, nothing extra (no train/refund/block/delete)


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
    config = ServiceConfig(database_url=env["config"].database_url, artifact_root=relocated)
    with TestClient(create_app(config)) as moved:
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
    from arai import paths as _paths
    from arai import contract as _contract
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
    with TestClient(create_app(env["config"])) as served:
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

    config = ServiceConfig(database_url=restored_url, artifact_root=relocated)
    with TestClient(create_app(config)) as restored:
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
            ring = group["coordinated_claim_matches"] >= 1 or group["selected_count"] >= 2 or share
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
    edges = pd.DataFrame([{"customer_a": a, "customer_b": b, "shared_types": ["address", "device"], "shared_value_count": 2,
                           "max_value_fanout": 3, "weight": w} for a, b, w in rows])
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
