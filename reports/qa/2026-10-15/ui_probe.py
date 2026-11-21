"""QA probe of the ARAI web UI with Playwright: console/network errors, layout overflow, accessible names, URL state, form guards."""
import json
import sys
import time
import uuid
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/")
RUN = sys.argv[2]
OUT = Path(sys.argv[3]); OUT.mkdir(parents=True, exist_ok=True)
API = BASE + "/api/v1"
findings = []


def note(kind, text):
    findings.append((kind, text)); print(f"{kind}: {text}")


# a case left awaiting approval by reviewer "Band Opener", for the approval band
sel = httpx.get(f"{API}/runs/{RUN}/customers", params={"limit": 40}).json()["items"]
BAND = sel[30]["customer_id"]
for kind in ("open", "request_approval"):
    httpx.post(f"{API}/runs/{RUN}/customers/{BAND}/reviews", json={"reviewer_name": "Band Opener", "kind": kind, "disposition": "needs_investigation", "note": "qa band", "idempotency_key": uuid.uuid4().hex})
FRESH = sel[35]["customer_id"]
TOP = sel[0]["customer_id"]
EXP = httpx.get(f"{API}/experiments").json()["items"][0]["experiment_id"]

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium", headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = ctx.new_page()
    console, failed = [], []
    page.on("console", lambda m: console.append(f"{m.type}: {m.text[:200]}") if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: console.append(f"pageerror: {str(e)[:200]}"))
    page.on("response", lambda r: failed.append(f"{r.status} {r.request.method} {r.url}") if r.status >= 400 else None)

    def settle():
        page.wait_for_timeout(200)
        page.wait_for_load_state("networkidle")
        try:
            page.wait_for_function("!document.querySelector('main')?.innerText.includes('Loading...')", timeout=20000)
        except Exception:
            note("BUG?", f"page still says Loading... after 20s at {page.url}")

    def text():
        return page.locator("main").inner_text()

    def a11y(label):
        probs = page.evaluate("""() => {
            const out = [];
            for (const b of document.querySelectorAll('button, a, input, select, textarea')) {
              const name = (b.getAttribute('aria-label') || b.textContent || b.getAttribute('title') || '').trim();
              const labelled = b.id && document.querySelector(`label[for="${b.id}"]`) || b.closest('label');
              if (!name && !labelled && b.type !== 'hidden') out.push(`${b.tagName.toLowerCase()}${b.className ? '.' + String(b.className).split(' ')[0] : ''} without a name`);
            }
            for (const i of document.querySelectorAll('img')) if (!i.hasAttribute('alt')) out.push('img without alt: ' + i.src.slice(-40));
            const ids = [...document.querySelectorAll('[id]')].map(e => e.id); const dup = ids.filter((x, i) => ids.indexOf(x) !== i);
            if (dup.length) out.push('duplicate ids: ' + [...new Set(dup)].slice(0, 5).join(','));
            const h1 = document.querySelectorAll('h1').length; if (h1 !== 1) out.push(`h1 count ${h1}`);
            const tabs = [...document.querySelectorAll('[role=tab]')]; if (tabs.length && !document.querySelector('[role=tablist]')) out.push('tabs without a tablist');
            for (const t of document.querySelectorAll('table')) if (!t.querySelector('th')) out.push('table without headers');
            for (const th of document.querySelectorAll('th')) if (!th.getAttribute('scope')) { out.push('th without scope'); break; }
            return out;
        }""")
        for p in sorted(set(probs)):
            note("A11Y", f"{label}: {p}")
        if "ARAI" not in page.title():
            note("A11Y", f"{label}: document.title is {page.title()!r}")
        return probs

    def overflow(label):
        w = page.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
        if w[0] > w[1] + 2:
            note("LAYOUT", f"{label}: horizontal overflow {w[0]} > {w[1]} at viewport {page.viewport_size['width']}")
        clipped = page.evaluate("""() => { const out = []; for (const e of document.querySelectorAll('main *')) { const s = getComputedStyle(e);
            if (e.scrollWidth > e.clientWidth + 4 && s.overflowX !== 'auto' && s.overflowX !== 'scroll' && s.overflowX !== 'hidden' && e.children.length === 0 && e.textContent.trim().length > 0) out.push(e.tagName + ': ' + e.textContent.trim().slice(0, 40)); } return out.slice(0, 5); }""")
        if clipped:
            note("LAYOUT", f"{label}: text wider than its box at {page.viewport_size['width']}: {clipped}")

    def visit(path, label, shot=None):
        c0, f0 = len(console), len(failed)
        page.goto(BASE + path); settle()
        new_c, new_f = console[c0:], failed[f0:]
        for m in new_c:
            note("CONSOLE", f"{label}: {m}")
        for f in new_f:
            note("NETWORK", f"{label}: {f}")
        a11y(label); overflow(label)
        if shot:
            page.screenshot(path=str(OUT / f"{shot}.png"), full_page=True)
        return text()

    titles = {}
    # ---- pages
    t = visit("/overview", "overview", "qa-01-overview"); titles["overview"] = page.title()
    print("overview mentions W9999 dataset?", "W9999" in t)
    t = visit("/datasets", "datasets", "qa-02-datasets"); titles["datasets"] = page.title()
    print("datasets page lists:", [l for l in t.splitlines() if l.startswith("ds-") or "W9999" in l or "bad world" in l][:5])
    cancel_buttons = page.get_by_role("button", name="Cancel").count(); print("cancel buttons on finished runs:", cancel_buttons)
    if cancel_buttons:
        note("BUG?", "datasets page shows a Cancel button although no run is in progress")
    print("retry buttons:", page.get_by_role("button", name="Retry").count(), "interrupted shown:", "interrupted" in t.lower(), "cancelled shown:", "cancel" in t.lower())
    # register with nothing selected
    btn = page.get_by_role("button", name="Validate and register")
    print("register button enabled with no files:", btn.is_enabled() if btn.count() else "no button")
    if btn.count() and btn.is_enabled():
        btn.click(); settle(); print("message after empty register:", [l for l in text().splitlines() if "file" in l.lower()][:3])
    t = visit(f"/runs/{RUN}/customers", "queue", "qa-03-queue"); titles["queue"] = page.title()
    rows = page.locator("main table tbody tr").count(); print("queue rows", rows)
    # Load more to the end
    clicks = 0
    while page.get_by_role("button", name="Load more").count() and clicks < 10:
        page.get_by_role("button", name="Load more").click(); settle(); clicks += 1
    rows2 = page.locator("main table tbody tr").count(); print("after load more", clicks, "clicks:", rows2)
    if rows2 != 284:
        note("BUG", f"review set loads {rows2} rows after exhausting Load more, expected 284")
    # filter round trip: set filters, reload, back
    page.get_by_label("Show").select_option("all"); settle()
    page.get_by_label("Tier").select_option("MEDIUM") if page.get_by_label("Tier").count() else note("BUG?", "no Tier filter control labelled 'Tier'")
    settle(); url1 = page.url; print("url after filters:", url1)
    page.reload(); settle()
    print("filters survive reload:", page.get_by_label("Show").input_value(), page.get_by_label("Tier").input_value() if page.get_by_label("Tier").count() else None)
    first_scores = [x.strip() for x in page.locator("main table tbody tr").first.inner_text().split("\t")][:6]; print("first MEDIUM row:", first_scores)
    page.go_back(); settle(); print("after back:", page.url)
    if "/customers" not in page.url:
        note("UX", "filter changes do not create history entries: Back after two filter changes leaves the queue entirely")
        page.go_forward(); settle()
    rows_link = page.evaluate("() => [document.querySelectorAll('main table tbody tr').length, document.querySelectorAll('main table tbody tr a.link').length, [...document.querySelectorAll('main table tbody tr')].filter(r => !r.querySelector('a.link')).map(r => r.innerText.slice(0, 80))]")
    print("tbody rows vs customer links:", rows_link)
    print("rows' tiers under tier=MEDIUM:", page.evaluate("() => [...document.querySelectorAll('main table tbody tr')].slice(0,5).map(r => r.innerText.replace(/\\s+/g,' ').slice(0,70))"))
    # contradictory filter: review set + comparison baseline_only
    page.goto(BASE + f"/runs/{RUN}/customers?show=review&comparison=baseline_only"); settle()
    print("review+baseline_only rows:", page.locator("main table tbody tr").count(), "show=", page.get_by_label("Show").input_value(), "empty text:", [l for l in text().splitlines() if "No customer" in l or "no customer" in l][:2])
    # group by ring and search
    page.goto(BASE + f"/runs/{RUN}/customers?group=ring"); settle(); page.screenshot(path=str(OUT / "qa-04-grouped.png"), full_page=True)
    page.goto(BASE + f"/runs/{RUN}/customers?show=cleared"); settle(); print("cleared rows", page.locator("main table tbody tr").count(), "cleared head:", page.locator("main table thead").inner_text().replace("\n", " | ")[:200])
    page.goto(BASE + f"/runs/{RUN}/customers?search=%27%3B+DROP"); settle(); print("search injection empty state:", [l for l in text().splitlines() if "No " in l][:2])
    page.goto(BASE + f"/runs/{RUN}/customers?search=W9999"); settle(); print("search no match rows:", page.locator("main table tbody tr").count())
    # approval band for another reviewer
    page.goto(BASE + f"/runs/{RUN}/customers"); settle()
    page.get_by_label("Reviewer name").fill("Second Person"); settle()
    print("approval band for Second Person:", [l for l in text().splitlines() if "approval" in l.lower()][:3])
    page.get_by_label("Reviewer name").fill("Band Opener"); settle()
    print("approval band hides own:", [l for l in text().splitlines() if "approval" in l.lower()][:3])
    # unknown run / bad ids
    t = visit("/runs/run-doesnotexist/customers", "unknown run", "qa-05-unknown-run"); print("unknown run text:", t[:200].replace("\n", " | "))
    t = visit(f"/runs/{RUN}/customers/W5401-C99999", "unknown customer"); print("unknown customer text:", t[:160].replace("\n", " | "))
    t = visit("/experiments/none", "experiments none"); print("experiments none:", t[:120].replace("\n", " | "))
    t = visit("/this/route/does/not/exist", "unknown route"); print("unknown route:", t[:120].replace("\n", " | "))
    t = visit(f"/runs/{RUN}/customers/{TOP}?tab=bogus", "case bogus tab"); print("bogus tab -> url", page.url, "selected tab:", page.locator("[role=tab][aria-selected=true]").inner_text() if page.locator("[role=tab][aria-selected=true]").count() else None)
    # ---- case page
    t = visit(f"/runs/{RUN}/customers/{FRESH}", "case", "qa-06-case"); titles["case"] = page.title()
    print("case shows copy button:", page.get_by_role("button", name="Copy").count() or page.locator("button[title*='Copy'], button[aria-label*='Copy']").count())
    # decision guards: empty reviewer, empty note
    page.get_by_label("Reviewer name").fill(""); settle()
    add = page.get_by_role("button", name="Add a note only")
    print("note button enabled with blank reviewer and blank note:", add.is_enabled())
    f0 = len(failed); add.click(); settle()
    print("guard message:", [l for l in text().splitlines() if "name" in l.lower() and ("required" in l.lower() or "enter" in l.lower() or "need" in l.lower())][:2], "requests failed:", failed[f0:])
    if failed[f0:]:
        note("BUG?", f"adding a note with a blank reviewer name sent a request that failed: {failed[f0:]}")
    page.get_by_label("Reviewer name").fill("QA UI"); settle()
    f0 = len(failed); page.get_by_role("button", name="Add a note only").click(); settle()
    print("blank note guard:", [l for l in text().splitlines() if "note" in l.lower() and "required" in l.lower()][:2], "failed:", failed[f0:])
    if failed[f0:]:
        note("BUG?", f"adding a blank note sent a request that failed: {failed[f0:]}")
    # hostile note content renders as text
    xss = "<img src=x onerror=document.title='pwned'><b>bold?</b> & 'quotes' \"double\""
    page.get_by_label("Note (required with every action)").fill(xss)
    page.get_by_role("button", name="Add a note only").click(); settle()
    page.get_by_role("tab", name="notes").first.click() if page.get_by_role("tab", name="notes").count() else None
    settle(); nt = text()
    print("xss rendered as text:", xss[:30] in nt, "title:", page.title(), "img injected:", page.locator("main img[src='x']").count())
    if page.title() == "pwned" or page.locator("main img[src='x']").count():
        note("BUG", "a note's HTML is rendered as markup")
    long = "x" * 600
    page.get_by_label("Note (required with every action)").fill(long)
    page.get_by_role("button", name="Add a note only").click(); settle(); overflow("case with a 600-char unbroken note")
    page.screenshot(path=str(OUT / "qa-07-case-notes.png"), full_page=True)
    # open the case, then try approving as the same person through the UI
    page.get_by_label("Note (required with every action)").fill("opening")
    page.get_by_role("button", name="Open case").click(); settle()
    print("state after open:", [l for l in text().splitlines() if "In review" in l][:1])
    page.get_by_label("Note (required with every action)").fill("approving myself")
    f0 = len(failed); page.get_by_role("button", name="Approve", exact=True).click(); settle()
    print("self-approve shown:", [l for l in nt.splitlines() if "different reviewer" in l][:1] or [l for l in text().splitlines() if "different reviewer" in l][:1], failed[f0:])
    # approve as another via UI
    page.get_by_label("Reviewer name").fill("QA UI Two"); settle()
    page.get_by_label("Note (required with every action)").fill("approving as two")
    page.get_by_role("button", name="Approve", exact=True).click(); settle()
    print("approved tile:", [l for l in text().splitlines() if "Approved" in l or "approved" in l][:2])
    print("buttons after approval:", [b.inner_text() for b in page.get_by_role("button").all() if b.is_visible()][:12])
    # slider
    sl = page.locator("input[type=range]")
    if sl.count():
        sl.first.focus(); page.keyboard.press("ArrowLeft"); page.keyboard.press("ArrowLeft"); settle()
        print("slider text:", [l for l in text().splitlines() if "customers" in l and ("would" in l or "queue" in l)][:2])
    # tabs by keyboard: arrow keys?
    page.get_by_role("tab", name="evidence").first.focus(); page.keyboard.press("ArrowRight"); settle()
    print("arrow key moves tab focus/selection:", page.evaluate("() => document.activeElement && document.activeElement.textContent"), "url", page.url[-20:])
    # ---- ring case
    ring = httpx.get(f"{API}/runs/{RUN}/customers", params={"community": "ring", "limit": 1}).json()["items"][0]["customer_id"]
    visit(f"/runs/{RUN}/customers/{ring}?tab=linked+accounts", "ring case", "qa-08-ring")
    links = page.locator("main a.link").count(); print("ring case member links:", links)
    # insufficient-history case
    ins = httpx.get(f"{API}/runs/{RUN}/customers", params={"review_only": "false", "eligibility": "insufficient_history", "limit": 1}).json()["items"][0]["customer_id"]
    t = visit(f"/runs/{RUN}/customers/{ins}", "insufficient history case", "qa-09-insufficient"); print("insufficient case:", [l for l in t.splitlines() if "history" in l.lower() or "not ranked" in l.lower()][:3])
    print("decision buttons on insufficient case:", [b.inner_text() for b in page.get_by_role("button").all() if b.is_visible()][:10])
    # ---- styles
    t = visit(f"/runs/{RUN}/styles", "styles", "qa-10-styles"); titles["styles"] = page.title()
    page.get_by_label("Verdict").select_option("insufficient_support") if page.get_by_label("Verdict").count() else None
    settle(); print("insufficient_support styles rows:", page.locator("main table tbody tr").count(), "empty text:", [l for l in text().splitlines() if "No style" in l][:1])
    page.get_by_label("Verdict").select_option("all"); settle()
    sid = httpx.get(f"{API}/runs/{RUN}/styles").json()["items"][0]["style_id"]
    visit(f"/runs/{RUN}/styles/{sid}", "style detail", "qa-11-style")
    visit(f"/runs/{RUN}/styles/XX-NOPE", "unknown style"); print("unknown style:", text()[:120].replace("\n", " | "))
    # ---- evaluation
    t = visit(f"/experiments/{EXP}", "evaluation", "qa-12-evaluation"); titles["evaluation"] = page.title()
    svgs = page.locator("main svg").count(); print("svg charts:", svgs, "svg with title/aria:", page.locator("main svg[aria-label], main svg[role=img], main svg title").count())
    # ---- phone width
    ctx2 = browser.new_context(viewport={"width": 390, "height": 844}); p2 = ctx2.new_page()
    old = page; page = p2
    page.on("console", lambda m: console.append(f"{m.type}: {m.text[:200]}") if m.type in ("error",) else None)
    for path, label in ((f"/overview", "phone overview"), (f"/runs/{RUN}/customers", "phone queue"), (f"/runs/{RUN}/customers/{TOP}", "phone case"), (f"/runs/{RUN}/styles", "phone styles"), (f"/experiments/{EXP}", "phone evaluation"), ("/datasets", "phone datasets")):
        visit(path, label, "qa-phone-" + label.split()[-1])
    page.goto(BASE + f"/runs/{RUN}/customers/{TOP}"); settle()
    # tap targets smaller than 24px
    small = page.evaluate("""() => [...document.querySelectorAll('button, a, select, input')].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.height < 24 || r.width < 24); }).map(e => e.tagName + ':' + (e.textContent || e.getAttribute('aria-label') || '').trim().slice(0, 20)).slice(0, 8)""")
    if small:
        note("A11Y", f"phone case: controls under 24px: {small}")
    page = old
    # tablet width
    ctx3 = browser.new_context(viewport={"width": 820, "height": 1180}); p3 = ctx3.new_page(); page = p3
    visit(f"/runs/{RUN}/customers?group=ring", "tablet queue grouped", "qa-tablet-queue")
    visit(f"/experiments/{EXP}", "tablet evaluation", "qa-tablet-evaluation")
    page = old
    # keyboard focus visibility on the queue
    page.goto(BASE + f"/runs/{RUN}/customers"); settle()
    page.keyboard.press("Tab"); page.keyboard.press("Tab"); page.keyboard.press("Tab")
    fv = page.evaluate("() => { const e = document.activeElement; const s = getComputedStyle(e); return {tag: e.tagName, text: (e.textContent||'').trim().slice(0,30), outline: s.outlineStyle + ' ' + s.outlineWidth, shadow: s.boxShadow.slice(0,40)}; }")
    print("focused element after 3 tabs:", fv)
    if fv["outline"].startswith("none") and fv["shadow"] == "none":
        note("A11Y", f"no visible focus indicator on {fv}")
    # dark mode
    ctx4 = browser.new_context(viewport={"width": 1440, "height": 1000}, color_scheme="dark"); p4 = ctx4.new_page(); page = p4
    page.goto(BASE + "/overview"); settle(); bg = page.evaluate("() => getComputedStyle(document.body).backgroundColor"); print("dark scheme body bg:", bg)
    page.screenshot(path=str(OUT / "qa-dark-overview.png"))
    page = old
    print("titles per page:", titles)
    if len(set(titles.values())) == 1:
        note("A11Y", f"document.title is the same on every page: {set(titles.values())}")
    browser.close()

print("\n== UI FINDINGS", len(findings))
for k, t in findings:
    print(f"- [{k}] {t}")
(OUT / "ui-findings.json").write_text(json.dumps(findings, indent=1))
