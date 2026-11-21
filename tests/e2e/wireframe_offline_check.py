"""OPS-AC-02: the clickable wireframe opens offline in a browser, with nothing installed for it.

Copies final-spec on its own into a fresh folder whose path contains spaces (as a reader would after extracting the
package), opens wireframe/index.html straight from disk in a browser with the network switched off and every
non-file request refused, and walks the README's routes. Writes the result and screenshots under
reports/ops-ac-02/<date>/.

    uv run python tests/e2e/wireframe_offline_check.py          # Edge on Windows; ARAI_BROWSER names a Chromium instead
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "reports" / "ops-ac-02" / datetime.now().astimezone().date().isoformat()
results: list = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append({"check": name, "passed": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f" ({detail})" if detail and not ok else ""))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="arai offline ") as scratch:
        package = Path(scratch) / "extracted copy" / "final-spec"
        shutil.copytree(REPO / "final-spec", package)                     # the package alone: no repository beside it
        page_url = (package / "wireframe" / "index.html").as_uri()
        outside: list = []
        with sync_playwright() as pw:
            executable = os.environ.get("ARAI_BROWSER")
            browser = pw.chromium.launch(executable_path=executable) if executable else pw.chromium.launch(channel="msedge")
            context = browser.new_context(offline=True, viewport={"width": 1440, "height": 900})

            def refuse(route):
                if not route.request.url.startswith("file:"):
                    outside.append(route.request.url)
                    return route.abort()
                return route.continue_()
            context.route("**/*", refuse)
            page = context.new_page()
            errors: list = []
            page.on("console", lambda m: m.type == "error" and errors.append(m.text))
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(page_url)
            page.wait_for_load_state("load")
            text = lambda: page.locator("main").inner_text()

            check("opens from disk in a path with spaces", " " in page_url.replace("%20", " ") and page.title().startswith("ARAI"), page.title())
            names = page.locator("#nav a").all_inner_texts()
            check("navigation lists the five screens", names == ["Overview", "Datasets & runs", "Customer queue", "Style investigation", "Evaluation"], names)
            for route, word in (("overview", "return-rate"), ("customers", "C-00"), ("styles", "linked"), ("datasets", "run"), ("evaluation", "candidate")):
                page.goto(page_url + "#" + route)
                page.wait_for_timeout(200)
                check(f"{route} screen renders", word.lower() in text().lower(), text()[:120])
                if route == "overview":
                    page.screenshot(path=str(OUT / "overview.png"), full_page=True)
            page.goto(page_url + "#customers/C-005")
            page.wait_for_timeout(200)
            check("a customer case opens", "C-005" in text(), text()[:120])
            page.screenshot(path=str(OUT / "case.png"), full_page=True)
            page.goto(page_url + "#datasets")
            page.wait_for_timeout(200)
            page.get_by_role("button", name="Simulate inference run").click()
            page.wait_for_function("document.querySelector('main').innerText.includes('preview-run-02')", timeout=20000)
            check("a simulated run completes", "preview-run-02" in text())
            page.goto(page_url + "#evaluation")
            page.wait_for_timeout(200)
            before = text()
            page.get_by_role("button", name="Reveal illustrative truth").click()
            page.wait_for_timeout(300)
            check("truth is revealed only on request", text() != before)
            page.select_option("#scenario", "test_failed")
            page.wait_for_timeout(300)
            check("a failed final test shows the banner", page.locator("#banner").is_visible(), page.locator("#banner").inner_text()[:120])
            pdf = page.locator(".footnote a").get_attribute("href")
            check("the original PDF link resolves inside the package", (package / "wireframe" / pdf).resolve().is_file(), pdf)
            check("no request left the machine", not outside, outside[:5])
            check("no console error", not errors, errors[:3])
            version = browser.version
            browser.close()
    passed = sum(r["passed"] for r in results)
    (OUT / "result.json").write_text(json.dumps({
        "criterion": "OPS-AC-02", "executed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "machine": f"{platform.system()} {platform.release()} ({platform.machine()})", "browser": ("chromium " if os.environ.get("ARAI_BROWSER") else "msedge ") + version,
        "mode": "file:// from a copy of final-spec alone, in a path with spaces; browser offline, every non-file request refused",
        "checks": results, "passed": passed, "total": len(results)}, indent=2) + "\n", encoding="utf-8")
    print(f"{passed} of {len(results)} checks passed; result in {OUT}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
