# End-to-end test report, 15 Oct 2026

Exploratory QA pass over the running application (`arai local`, API contract 1.12.0, world W5401 scored on
experiment 4). Two probe scripts drove it: `api_probe.py` (validation, workflow rules, pagination, cursor
tampering, consistency rules between fields, concurrency, latency) and `ui_probe.py` (every screen at 1440, 820
and 390 px: console and network errors, accessible names, URL round trips, form guards, hostile input). Both
need a running stack and a scored run; they write test data, so run them against a disposable database.

Severity: **High** = wrong data accepted or wrong state reachable through the API; **Medium** = a screen or rule
does not do what it says; **Low** = polish, hardening or accessibility.

## Bugs

| # | Sev | Area | Finding | How to reproduce | Expected |
|---|---|---|---|---|---|
| 1 | High | Review workflow | A decided case can be decided again without being reopened. Approve and reject are accepted on an approved or rejected case; four concurrent approve/reject calls by four reviewers all return 201 and the last writer wins. | Open a case as A, request approval, approve as B, then `POST .../reviews` with `kind: approve` or `reject` as C. | 409 `case_not_open` (or a dedicated `case_decided`) once a decision exists; only `open` reopens. |
| 2 | High | Dataset registration | The manifest's `world_id` is not checked against the tables. W5401's seven files with a manifest saying `W9999` register as world W9999 (201); so does `world_id: "bad world id"`. Reviews are keyed by world id, so the same customers would carry two separate review histories. | Edit `world_id` in `manifest.json`, upload with the unchanged CSVs. | 422 with a rule naming the mismatch between the manifest and the row ids; a world id pattern. |
| 3 | High | Dataset registration | A cutoff in the future is accepted (`2031-01-01`), with the data otherwise valid. Every sale line then counts as mature and the chronology rules cannot bite. | Set `cutoff` to 2031 and a fresh `world_id`; upload. | 422: the cutoff may not be after the upload time (or after the latest timestamp in the data by more than a grace period). |
| 4 | High | Dataset registration | An empty CSV for any table gives **500 internal_error** (`pandas.errors.EmptyDataError: No columns to parse from file`). | Upload with `return_order_line.csv` of zero bytes. | 422 `validation_failed` with the M/S rule for a missing header. |
| 5 | High | Reviews | A note containing a NUL byte gives **500 internal_error** (`PostgreSQL text fields cannot contain NUL`). | `POST .../reviews` with `"note": "\u0000x"`. | 422 `invalid_request`, or strip the byte. |
| 6 | Medium | Case queue | The "Cleared heavy returners" view filters on the client over 100-row pages of all eligible customers sorted by rank. It opens showing nothing ("0 customer(s) shown, more available") and the reviewer must press Load more repeatedly; after two clicks it shows 3 rows out of several thousand cleared customers. | Show: Cleared heavy returners. | The server filters (a `cleared` or `heavy_outside_queue` flag on the list endpoint) so the first page is full. |
| 7 | Medium | Review workflow | `open` on a case that is already in review is accepted and silently replaces the opener. A opens, B "opens", A approves: approved. The second-reviewer rule can be stepped around in two calls. | Three `POST .../reviews` calls as described. | 409 when the case is already open; or keep the first opener until the case is decided or explicitly reopened. |
| 8 | Medium | Case page | A long unbroken note (600 characters, no spaces) stretches the page to 4,866 px wide at a 1,440 px viewport. See `note-overflow.png`. | Add a note of 600 x's. | `overflow-wrap: anywhere` on note text. |
| 9 | Medium | Review workflow | The second-reviewer comparison is exact and case-sensitive: `qa one` may approve a case opened by `QA One`. (Trailing spaces are trimmed, case is not.) | Open as `QA One`, approve as `qa one`. | Compare names case-insensitively after trimming and collapsing spaces. |
| 10 | Medium | Review workflow | Workflow actions are accepted for customers outside their scope: `open` on a customer who is not selected for review, `feedback` (agree/disagree) on a selected one. The UI hides these buttons; the API does not refuse. | `POST .../reviews` with `kind: open` on a non-selected customer. | 409 with a reason, matching what the UI allows. |
| 11 | Medium | Static serving | Any unknown path, including a missing asset such as `/assets/missing.js`, is answered with `index.html` and status 200. A broken build would fail silently in the browser, and probes see a 200 for everything. | `GET /assets/does-not-exist.js`. | 404 for paths under `/assets/` and for paths with a file extension; the SPA fallback for the rest. |
| 12 | Medium | Case queue | On a run id that does not exist, the page shows the error banner but also the summary line and header strip of the workspace's current run ("284 selected of 5,676 eligible in this run"), which is not the run in the address bar. | Open `/runs/run-doesnotexist/customers`. | Hide the counts and strip, or say they belong to the latest run. |
| 13 | Low | Reviews | `approve` and `reject` accept any disposition, so an approval can carry `unresolved`. | `kind: approve, disposition: unresolved`. | Require a decided disposition with a decision, or drop disposition from decisions. |
| 14 | Low | Datasets & runs | A run cancelled on purpose shows as **interrupted** with the action "Retry with the same dataset and bundle", the same as a crash. | Cancel a queued run. | A `cancelled` label and no retry prompt. |
| 15 | Low | API hardening | No `X-Content-Type-Options`, `X-Frame-Options`/CSP or `Cache-Control` headers on API or page responses; `OPTIONS` answers 405. | `curl -I`. | Standard headers from the API middleware or the reverse proxy. |
| 16 | Low | Accessibility | `document.title` is identical on every page; the unknown-route page has no `h1`; tab lists do not move with arrow keys (Tab and Enter work); on a phone the copy button and the style links in the case page are under 24 px. | `ui_probe.py` A11Y lines. | Per-page titles, roving tabindex on tabs, 24 px minimum targets. |
| 17 | Low | Case queue | Filter changes replace the history entry, so Back after two filter changes leaves the queue entirely. | Change two filters, press Back. | Push a history entry per filter change (or document the choice). |
| 18 | Low | Case API | `timeline[].observed_at` mixes a date (`2026-08-29`) for purchases and a datetime with offset (`2026-09-09T15:55:12+05:30`) for return requests; the contract types it as a plain string. | `GET .../customers/{id}`. | One format, declared in the contract. |
| 19 | Low | Datasets | There is no way to remove a dataset registered by mistake (such as #2 and #3 above) from the UI or API. | Register a wrong snapshot. | A delete for datasets without runs, or an archive flag. |

## What held up

- Pagination: the review set (284) and the full list (10,000) walk without duplicates or gaps; ranks are 1..n; scores never increase along rank; tiers and gates partition the 5,676 eligible customers exactly; comparison counts match the run's counts; a cursor from another filter set, another run or with a tampered position is refused (422).
- Field consistency on every customer: selected ⇔ rank ≤ budget ⇔ tier High; Escalate ⇔ selected and (ring or wardrobing elevated); expectation inside its band; score-distribution bins sum to the eligible count and the selected count.
- Case body: signal source refs all resolve to timeline entries; community members, edges and selected counts agree; breakdown rows agree with the threshold; insufficient-history cases render.
- Search escapes SQL wildcards and injection text; HTML in notes and reviewer names is stored verbatim and rendered as text; blank reviewer and blank note are stopped before any request; the second-reviewer refusal shows the server's words; idempotent replays (runs and reviews, including four concurrent calls on one key) return the same row; different body on a used key gives 409.
- A second scoring run reproduces the first (284 selected, 209 model-only); a run cancelled while queued ends `interrupted` with reason `cancelled`, and its results endpoints answer 409.
- Latency on a 10,000-customer world: every endpoint under 80 ms; the full evaluation report 176 KB.
- Layout at 820 and 390 px: no horizontal overflow on any screen apart from #8; visible focus ring on keyboard navigation; 404 pages for unknown run, customer and style.

## State left behind

The probes created three datasets, two runs and about forty review notes in the local demo database. The three
datasets (W9999, W9998, "bad world id") and the QA notes were removed afterwards; the cancelled run
`run-a3bfb61d46084d59a914` and the second successful run `run-3ce00dc312af46358f76` remain in the Runs list.

## Resolution (same day, API contract 1.13.0, decisions AM-64 and AM-65)

| # | Status | What changed |
|---|---|---|
| 1 | Fixed | `append_review` is a closed state machine: approve, reject and request_approval on a decided case are 409 `case_decided`; a reopen is the only way back. Concurrent decisions resolve to one under the existing per-customer lock. |
| 2 | Fixed | Validation rule M004: generated row identifiers that carry another world id than the manifest reject the snapshot. The manifest's world_id now has a pattern and a length limit. |
| 3 | Fixed | A cutoff more than a day in the future is M001. |
| 4 | Fixed | A file that cannot be read as CSV is M002 instead of a 500. |
| 5 | Fixed | A NUL byte in a body field, the path or the query is a 422 (`invalid_request`). |
| 6 | Fixed | New list filter `cleared_heavy=true`; the view shows full pages from the first one. |
| 7 | Fixed | `open` on a case that is in review or awaiting approval is 409 `case_already_open`; the opener cannot be swapped. |
| 8 | Fixed | Long unbroken text wraps (`overflow-wrap: anywhere` on notes, cells and callouts). |
| 9 | Fixed | Reviewer names compare without regard to case or spacing. |
| 10 | Fixed | The four workflow kinds need a customer selected for review and feedback a customer outside the queue (409 `out_of_scope`). |
| 11 | Fixed | A missing file under `assets/` or with a static suffix is a 404; client-side routes still get the app shell. |
| 12 | Fixed | The queue hides the summary counts when the run in the address bar cannot be loaded. |
| 13 | Fixed | approve and reject with disposition `unresolved` are 422 (`request.decision_disposition`); the UI refuses before sending. |
| 14 | Fixed | A run cancelled on purpose reads **cancelled** with no retry prompt (the API status stays `interrupted` with reason `cancelled`). |
| 15 | Fixed | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` on every response; `Cache-Control: no-store` under `/api/`. |
| 16 | Fixed | Per-page document titles, an h1 on the unknown-route page, arrow-key tabs with one tab stop, 24 px minimum on the copy button and inline links. |
| 17 | Fixed | Filter changes push history entries. |
| 18 | Documented | The contract now states the two formats of `observed_at` (date for purchases, date-time with offset for return requests). The values are unchanged. |
| 19 | Fixed | `DELETE /datasets/{id}` removes a dataset no run was scored on, with its files; the Datasets page offers Remove for those. Runs and notes keep having no delete. |
