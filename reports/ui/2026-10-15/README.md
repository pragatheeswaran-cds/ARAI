# Workbench screens on API contract 1.12.0 (15 Oct 2026)

Screenshots of the built UI served by the API on the fixture world W2001 (seed 2001, 1,000 customers, logistic
regression bundle trained on the fixture for this purpose; not the experiment 4 model). Taken headless at 1440 px
wide with every page's console and network clean, except the deliberate 409 in `09-case-refusal.png`: reviewer
Asha, who opened the case, tries to approve it and the server's refusal is shown as the server words it.

No API key was set, so every investigation memo reads `unavailable` by design; the screens are meant to look right
that way. The evaluation report is a smoke stub with the truth export, so the hero curves draw and the scorecard
tables read n/a.

## Browser walkthrough on W5401 (same day, later)

`tests/e2e/walkthrough.py` was then run against `arai local` serving the regenerated experiment 4 bundle with the
demonstration world W5401 registered and scored (10,000 customers; run `run-ed95a0e2fd3e49a69d4d`). Result:
54 of 54 checks passed; `walkthrough-result.json` holds every check. The walkthrough wrote its own screenshots into
this folder, so `01-overview.png` and `06-case-returns.png` now show W5401 rather than the fixture world, and the
files `02-datasets-and-runs`, `03-queue-rule-only`, `04-queue-search`, `05-case-evidence`, `06-case-linked-accounts`,
`06-case-notes`, `07-case-notes`, `07b-case-refusal`, `08-styles-targeting`, `09-style-detail`, `10-evaluation`,
`11-evaluation-truth` and `12-overview-narrow` come from it. The remaining files are the fixture-world smoke set
described above.

The walkthrough's only expected request failures are the unknown run's 404 and the staged 409 on `/reviews`
(the second-reviewer rule). No API key was set, so memos read `unavailable` here too.
