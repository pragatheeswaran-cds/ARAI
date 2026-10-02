"""Browser check of the baseline-fallback state (final-spec component 13, UI-AC-03 and UI-AC-08).

Self-contained: it starts its own temporary instance (embedded PostgreSQL, a copy of the bundles with only the
baseline active, the built UI), scores fixture world W2001 and looks at the pages. Needs `web/dist` and the
development artifacts under data/artifacts.

    uv run python tests/e2e/fallback_check.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import pgserver
import uvicorn
from playwright.sync_api import sync_playwright

from arai import bundles, paths
from arai.operational import TABLES
from arai.service.api import create_app
from arai.service.config import ServiceConfig

PORT = 8011
BASE = f"http://127.0.0.1:{PORT}"
OUT = paths.REPO_ROOT / "reports" / "ui" / "2026-10-02"
results = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append({"check": name, "ok": bool(ok), "detail": str(detail)})
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail) if detail else ""))


work = Path(tempfile.mkdtemp(prefix="arai-fallback-"))
root = work / "artifacts"
shutil.copytree(paths.ARTIFACT_ROOT / "bundles", root / "bundles")
source = next((paths.ARTIFACT_ROOT / "experiments").glob("*/published/experiment.json"))
report = json.loads(source.read_text(encoding="utf-8"))
report["summary"].update(selection_status="no_selected_model", selected_model_id=None, selected_candidate_id=None, final_test_status="not_run")
published = root / "experiments" / report["summary"]["experiment_id"] / "published"
published.mkdir(parents=True)
(published / "experiment.json").write_text(json.dumps(report), encoding="utf-8")
baseline_id = next(p.name for p in (root / "bundles").iterdir() if p.name.startswith("b-"))
bundles.activate(None, baseline_id, "no_selected_model", report["summary"]["experiment_id"], "No candidate passed the gate.", root)

database = pgserver.get_server(work / "pg")
config = ServiceConfig(database_url=database.get_uri(), artifact_root=root, poll_seconds=0.5)
server = uvicorn.Server(uvicorn.Config(create_app(config, with_worker=True, static_dir=paths.REPO_ROOT / "web" / "dist"),
                                       host="127.0.0.1", port=PORT, log_level="warning"))
threading.Thread(target=server.run, daemon=True).start()
try:
    for _ in range(100):
        try:
            if httpx.get(BASE + "/api/v1/health", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.3)
    health = httpx.get(BASE + "/api/v1/health").json()
    check("health reports the baseline, not a promoted model", health["scoring_ready"] and not health["promoted_model_ready"]
          and health["model_kind"] == "baseline_fallback", health)
    world = paths.ARTIFACT_ROOT / "worlds" / "W2001" / "operational"
    files = {name: (f"{name}.csv", (world / f"{name}.csv").read_bytes(), "text/csv") for name in TABLES}
    dataset = httpx.post(BASE + "/api/v1/datasets", data={"manifest": (world / "manifest.json").read_text(encoding="utf-8")}, files=files,
                         timeout=120).json()
    run = httpx.post(BASE + "/api/v1/runs", json={"dataset_id": dataset["dataset_id"], "idempotency_key": "fallback-1"}).json()
    for _ in range(120):
        run = httpx.get(f"{BASE}/api/v1/runs/{run['run_id']}").json()
        if run["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.5)
    check("the baseline run succeeds with complete counts", run["status"] == "succeeded" and run["model_kind"] == "baseline_fallback"
          and run["model_only_count"] == 0 and run["baseline_only_count"] == 0, run["status"])

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})

        def settle():
            page.wait_for_timeout(150)
            page.wait_for_load_state("networkidle")
            page.wait_for_function("!document.querySelector('main')?.innerText.includes('Loading...')", timeout=30000)

        page.goto(BASE + "/overview")
        settle()
        banner = page.locator(".banner").first.inner_text()
        check("banner states the real reason and the active ranking", "No candidate passed the validation gate" in banner
              and "return-rate ranking is active" in banner and "no trained-model result is claimed" in banner, banner[:90])
        text = page.locator("main").inner_text()
        check("overview says the scoring mode is the baseline", "Baseline" in text and "Return-rate ranking" in text)
        check("the model-versus-rule comparison is hidden under fallback", "Model and return-rate rule compared" not in text)
        check("header names the baseline", "Return-rate baseline" in page.locator("header").inner_text())
        page.screenshot(path=str(OUT / "13-fallback-overview.png"), full_page=True)

        page.get_by_role("link", name="Customer queue", exact=True).click()
        settle()
        head = page.locator("main table thead").inner_text()
        check("the score is relabelled as a return-rate percentile", "Return-rate percentile" in head and "Reference percentile" not in head)
        check("no rule column and no comparison filter under fallback", "Return-rate rule" not in head
              and page.get_by_label("Model and return-rate rule").count() == 0)
        page.locator("main table tbody tr a.link").first.click()
        settle()
        text = page.locator("main").inner_text()
        check("case evidence is complete under fallback", "What the record shows" in text and "Return-rate percentile" in text
              and "Wardrobing indicator" in text)
        page.screenshot(path=str(OUT / "14-fallback-case.png"), full_page=True)

        page.get_by_role("link", name="Evaluation").click()
        settle()
        text = page.locator("main").inner_text()
        check("evaluation says no winner and that nothing was promoted", "No winner" in text and "The return-rate baseline is active" in text)

        page.get_by_role("link", name="Datasets & runs").click()
        settle()
        text = page.locator("main").inner_text()
        check("datasets page names the active bundle as the baseline", "Return-rate baseline" in text and "succeeded" in text)
        browser.close()
finally:
    server.should_exit = True
    time.sleep(1.5)
    database.cleanup()
    shutil.rmtree(work, ignore_errors=True)

passed = sum(r["ok"] for r in results)
(OUT / "fallback-result.json").write_text(json.dumps({"checks": results, "passed": passed, "failed": len(results) - passed}, indent=2) + "\n",
                                          encoding="utf-8")
print(f"{passed} of {len(results)} checks passed")
sys.exit(0 if passed == len(results) else 1)
