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
from arai.service import scoring, worker
from arai.service.api import create_app
from arai.service.config import ServiceConfig
from arai.service.store import Store

API = "/api/v1"
CONTRACT = yaml.safe_load((SPEC_ROOT / "contracts" / "openapi.yaml").read_text(encoding="utf-8"))


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
    assert health == {"alive": True, "scoring_ready": True, "promoted_model_ready": False, "model_kind": "baseline_fallback"}
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
    summary = json.loads((scoring.output_dir(env["root"], queued["run_id"]) / "run.json").read_text())
    assert summary["model_id"] == env["model_id"]
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
    assert not scoring.output_dir(env["root"], crashed["run_id"]).exists()
    assert not scoring.staging_dir(env["root"], crashed["run_id"]).exists()
    assert client.get(f"{API}/runs/{first['run_id']}").json()["status"] == "succeeded"          # earlier results untouched
    notes = client.get(f"{API}/runs/{first['run_id']}/customers/{customer}/reviews").json()["items"]
    assert [n["note"] for n in notes] == ["kept"]

    retry = client.post(f"{API}/runs", json={"dataset_id": first["dataset_id"], "model_id": interrupted["model_id"], "idempotency_key": "retry"})
    assert retry.status_code == 202 and retry.json()["run_id"] != crashed["run_id"] and retry.json()["model_id"] == interrupted["model_id"]
    worker.process_one(env["config"], store)
    assert client.get(f"{API}/runs/{retry.json()['run_id']}").json()["status"] == "succeeded"

    # a succeeded run whose files vanish is reported as failed after restart, never as succeeded with nothing behind it
    shutil.rmtree(scoring.output_dir(env["root"], first["run_id"]))
    assert worker.reconcile(env["config"], store)["output_missing"] == [first["run_id"]]
    gone = client.get(f"{API}/runs/{first['run_id']}").json()
    assert gone["status"] == "failed" and gone["error"]["error_code"] == "output_missing"


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
    assert not scoring.output_dir(env["root"], run["run_id"]).exists()


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
