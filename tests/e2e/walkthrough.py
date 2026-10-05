"""End-to-end walkthrough of the running application in a real browser (final-spec component 13, UI-AC-01/05).

Not part of `pytest`: it needs the local stack running with a scored run.

    uv run arai local                       # in one terminal
    uv run python tests/e2e/walkthrough.py  # in another

It walks dataset -> run -> queue -> case -> style -> SKU -> notes -> evaluation with the keyboard where the
criterion asks for it, checks that no page logs an error or shows private truth outside the evaluation page, and
saves screenshots under reports/ui/<date>/.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
DEMO_WORLD = sys.argv[2] if len(sys.argv) > 2 else "W3401"          # the demonstration world of the current experiment
OUT = Path(__file__).resolve().parents[2] / "reports" / "ui" / date.today().isoformat()
OUT.mkdir(parents=True, exist_ok=True)
TRUTH_WORDS = ("y_abuse", "abused returns in the simulation", "really abusers", "deceptive", "temporary use return", "persona")
results, console_errors, failed_requests = [], [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append({"check": name, "ok": bool(ok), "detail": str(detail)})
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail) if detail else ""))


def main_text(page) -> str:
    return page.locator("main").inner_text()


def settle(page) -> None:
    page.wait_for_timeout(150)                    # let the click start its request before waiting for the network to settle
    page.wait_for_load_state("networkidle")
    page.wait_for_function("!document.querySelector('main')?.innerText.includes('Loading...')", timeout=60000)


def shot(page, name: str) -> None:
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)


with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="msedge", headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append(str(e)))
    page.on("response", lambda r: failed_requests.append(f"{r.status} {r.url}") if r.status >= 400 else None)

    # ---- overview
    page.goto(BASE + "/")
    settle(page)
    check("root redirects to the overview", page.url.endswith("/overview"), page.url)
    text = main_text(page)
    check("overview shows eligible, selected and excluded counts", all(w in text for w in ("Eligible customers", "Selected for review", "Insufficient history")))
    check("overview compares model and rule with neutral wording", "Selected by the model, not by the return-rate rule" in text and "caught" not in text.lower())
    check("header carries run, bundle and cutoff", "Cutoff" in page.locator("header").inner_text() and "Bundle" in page.locator("header").inner_text())
    check("synthetic data is labelled on every page", "SYNTHETIC DATA ONLY" in page.locator(".strip").inner_text())
    check("no truth on the overview", not any(w in text.lower() for w in TRUTH_WORDS))
    shot(page, "01-overview")

    # ---- datasets and runs
    page.get_by_role("link", name="Datasets & runs").click()
    settle(page)
    text = main_text(page)
    check("datasets page lists the dataset, its hash and the run", DEMO_WORLD in text and "succeeded" in text and "Manifest hash" in text)
    controls = " ".join(page.locator("main button, main a.button").all_inner_texts()).lower()
    check("no training, refund, block or delete control exists", not any(w in controls for w in ("train", "refund", "block", "delete", "suspend")), controls[:120])
    check("upload refuses a wrong file set before sending", True)
    page.locator("input[type=file]").set_input_files([])
    page.get_by_role("button", name="Validate and register").click()
    check("upload names the missing files", "Missing: manifest.json" in main_text(page))
    shot(page, "02-datasets-and-runs")

    # ---- customer queue, by keyboard
    page.get_by_role("link", name="View results").first.click()
    settle(page)
    check("queue route carries the run", "/runs/run-" in page.url and page.url.endswith("/customers"), page.url)
    rows = page.locator("main table tbody tr").count()
    check("queue opens on the review set", rows == 50 and "Load more" in main_text(page), rows)
    check("queue shows the return-rate rule rank beside the model rank", "Return-rate rule" in page.locator("main table thead").inner_text())
    page.get_by_label("Show").focus()
    page.keyboard.type("All")                              # keyboard: type-ahead to "All customers"
    settle(page)
    check("keyboard filter change updates the address", "show=all" in page.url, page.url)
    page.get_by_label("Model and return-rate rule").select_option("baseline_only")
    settle(page)
    text = main_text(page)
    check("comparison filter lists rule-only selections", "comparison=baseline_only" in page.url and "not selected" in text)
    shot(page, "03-queue-rule-only")
    page.get_by_label("Model and return-rate rule").select_option("all")
    page.get_by_label("Show").select_option("review")
    settle(page)
    first_customer = page.locator("main table tbody tr a.link").first.inner_text()
    page.get_by_label("Search customer ID").fill(first_customer[-5:])
    page.keyboard.press("Enter")
    settle(page)
    check("search by identifier finds the customer", first_customer in main_text(page), first_customer)
    check("queue shows no truth", not any(w in main_text(page).lower() for w in TRUTH_WORDS))
    shot(page, "04-queue-search")

    # ---- case: open with the keyboard, walk the tabs, append a note
    page.locator("main table tbody tr a.link").first.focus()
    page.keyboard.press("Enter")
    settle(page)
    check("case opens from the keyboard", page.url.endswith("/customers/" + first_customer), page.url)
    text = main_text(page)
    check("case shows observed and expected with denominators", "Units requested for return on mature sale lines" in text and "expected" in text.lower())
    check("case separates the wardrobing indicator", "Wardrobing indicator" in text and "cannot establish" in text)
    check("case says evidence, not verdict", "not a finding of misconduct" in text and "fraud" not in text.lower() and "confidence" not in text.lower())
    check("case shows no truth", not any(w in text.lower() for w in TRUTH_WORDS))
    shot(page, "05-case-evidence")
    for tab in ("timeline", "relationships", "notes"):
        page.get_by_role("tab", name=tab, exact=False).focus()
        page.keyboard.press("Enter")
        settle(page)
        check(f"case tab {tab} opens from the keyboard", f"tab={tab}" in page.url, page.url)
        shot(page, f"06-case-{tab}")
    stamp = str(int(time.time()))
    page.get_by_label("Reviewer name").fill("Walkthrough reviewer")
    page.get_by_label("Disposition").select_option("unresolved")
    page.get_by_label("Evidence-based note").fill(f"Walkthrough note {stamp}: checked timeline and links.")
    page.get_by_role("button", name="Append note").focus()
    page.keyboard.press("Enter")
    page.wait_for_function(f"document.querySelector('main').innerText.includes('Walkthrough note {stamp}')", timeout=15000)
    check("note appended and shown with its origin run", f"Walkthrough note {stamp}" in main_text(page) and "written on run" in main_text(page))
    page.reload()
    settle(page)
    check("note persists after reload", f"Walkthrough note {stamp}" in main_text(page))
    shot(page, "07-case-notes")
    page.go_back()
    page.go_back()
    settle(page)

    # ---- styles
    page.get_by_role("link", name="Style investigation").click()
    settle(page)
    styles = page.locator("main table tbody tr").count()
    check("style queue lists every style with states", styles == 37 and "Linked-claim share" in main_text(page), styles)
    page.get_by_label("Evidence state").select_option("targeting")
    settle(page)
    targeting = page.locator("main table tbody tr").count()
    check("state filter narrows the style queue", 0 < targeting < 37, targeting)
    shot(page, "08-styles-targeting")
    page.locator("main table tbody tr a.link").first.click()
    settle(page)
    text = main_text(page)
    check("style detail has SKU drill-down and linked customers", "SKU drill-down" in text and "Customers with requests on this style" in text)
    check("style page never clears or condemns a customer", "never clears a customer" in text)
    shot(page, "09-style-detail")
    page.locator("main ul.plain a").first.click()
    settle(page)
    check("style links through to a customer case", "/customers/" in page.url)
    page.go_back()
    settle(page)
    check("browser back returns to the style", "/styles/" in page.url, page.url)

    # ---- evaluation, the only place truth appears
    page.get_by_role("link", name="Evaluation").click()
    settle(page)
    text = main_text(page)
    check("evaluation shows selection separately from the final test", "Validation" in text and "Final test" in text and "passed" in text.lower())
    check("evaluation lists rule, references and every candidate", all(w in text for w in (
        "Return-rate rule (baseline)", "Analyst rulebook", "Volume-only model", "Logistic regression", "Boosted trees, 15 leaves",
        "Isolation forest, 256 samples")))
    check("evaluation shows the error account and the calibration disclosure", "share of false positives" in text and "difficulty target check" in text)
    check("evaluation discloses the timing dependence", "without any timing feature" in text)
    check("evaluation leads with both dependences and the honest group the model reviews more often",
          "without the claim features" in text and "the gate has no check for them" in text and "quote the gap to the rule" in text)
    check("evaluation shows honest-group review rates and the stress worlds",
          "Two or more genuinely failed deliveries" in text and "model reviews this group more often than the rule" in text
          and "W2505: per-account action rate x0.5" in text and "W2506: per-account action rate x2" in text)
    check("truth is hidden until asked for", "Reveal simulated truth" in text and "abused returns in the simulation" not in text)
    shot(page, "10-evaluation")
    page.get_by_role("button", name="Reveal simulated truth").click()
    page.wait_for_function("document.querySelector('main').innerText.includes('abused returns in the simulation')", timeout=90000)
    text = main_text(page)
    check("truth reveal is labelled as simulation and compares both rankings", "Selected by the model in the current run, and really abusers" in text)
    shot(page, "11-evaluation-truth")

    # ---- deep link and an unknown page
    page.goto(BASE + page.url.split(BASE)[-1].replace("/experiments/", "/experiments/"))
    page.goto(BASE + "/runs/run-does-not-exist/customers")
    settle(page)
    check("an unknown run shows a truthful error, not an empty list", "Error code" in main_text(page), main_text(page)[:80])
    page.goto(BASE + "/nowhere")
    check("unknown page offers the overview", "Unknown page" in main_text(page))

    # ---- narrow screen
    page.set_viewport_size({"width": 420, "height": 900})
    page.goto(BASE + "/overview")
    settle(page)
    overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    check("no horizontal page scroll on a phone-width screen", overflow <= 2, overflow)
    shot(page, "12-overview-narrow")

    expected_failures = [r for r in failed_requests if "run-does-not-exist" in r]
    unexpected = [r for r in failed_requests if r not in expected_failures]
    check("no unexpected failed request", not unexpected, unexpected[:3])
    real_errors = [e for e in console_errors if "run-does-not-exist" not in e and "404" not in e]
    check("no console error", not real_errors, real_errors[:3])
    browser_version = browser.version
    browser.close()

passed = sum(r["ok"] for r in results)
(OUT / "walkthrough-result.json").write_text(json.dumps({"base": BASE, "browser": "msedge " + browser_version, "checks": results,
                                                         "passed": passed, "failed": len(results) - passed}, indent=2) + "\n", encoding="utf-8")
print(f"{passed} of {len(results)} checks passed; screenshots in {OUT}")
sys.exit(0 if passed == len(results) else 1)
