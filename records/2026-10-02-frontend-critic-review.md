# Independent review of the front end and deployment files, 2026-10-02

Reviewer: an independent critic agent on the Fable model, briefed as a chief data scientist and product
architect. It worked read-only on commit `f9e3961`, browsed the live local instance (GET only, headless Edge),
and compared the Evaluation page with the offline reports. The text below is the critic's report, lightly
reformatted. Action taken is in `records/2026-10-02-serving-and-ui.md`.

## Verdict

Ready to show a non-ML jury **after fixes**, none of them blockers. Every number on the Evaluation page matches
the offline reports (validation 0.707 against 0.243, final test 0.715 against 0.239, ablation 0.561, the 1 / 5 /
10% budgets, per-world and error-account counts), scopes and "spread, not a significance test" wording are
carried through, no page but Evaluation shows truth or verdict words, the score is labelled a percentile, and
the fallback paths hide the comparison. Two presentation gaps and one live-state defect need fixing first.

## Findings

**MAJOR 1. The development target is not shown as not met.** The page prints "best supervised precision (target
75% to 85%) ... 69.4%" with no judgement; a juror has to compare the numbers. Fix: say "not met" in words, and
add one headline line.

**MAJOR 2. The timing dependence is not prominent.** The 56.1% "without any timing feature" figure and its
callout appear only in the eighth panel, about 4,700 pixels down, and in Limits. The top cards and the chart say
"Model selected / passed / 70.7%" with no caveat. Fix: put the figure in the top row or under the chart.

**MAJOR 3. A dangling "succeeded" run on the live instance.** The run directory was emptied while the service
ran; the run still showed as succeeded with a "View results" link, and every deep link to it returned 409.
Reconciliation repairs this only on restart. Fix: show such a run as unavailable at once.

**Minor.** (4) Score and retry buttons are not disabled during a request and mint a new idempotency key per
click, so a double click creates two runs. (5) "Load more" is not cancelled when the filters change; a late page
appends old-filter rows. (6) "World protocol 10 / 5 / 5" is hard-coded. (7) The limits bullet about abusers
outside the ranking has no scope (it is validation; test worlds are 211 of 1,854). (8) The case page has no
plain statement of why the model and the rule differ: for an honest heavy returner the loudest number argues for
review, and the presenter must point at the zeros (no claim, no late return, no linked account). (9) Tab buttons
have no tab panel or `aria-controls`. (10) The page requests `/experiments/none` before taking the
no-experiment branch. (11) nginx protects nothing under `/`; only the API enforces the shared login in the VM
profile; OPS-AC-05 is not run. (12) `data/` is not in git; a clean clone gives an honest but empty service, as
the README says.

## Walkthrough cases the reviewer found (truth checked privately through the evaluation export)

- Honest heavy returner, rule yes / model no: `W2401-C02658` (rule rank 40, model rank 1,748; 8 of 11 units
  returned, no claim, no late return, no linked account). With longer history: `W2401-C00580`.
- Abuse inside an ordinary return rate, model yes / rule no: `W2401-C07970` (12% return rate, rule rank 3,566,
  model rank 80; two of three return lines are claims, one matched by a linked account). Timing variant:
  `W2401-C06954`.
- Thin history: `W2401-C00057` (two mature lines, not ranked; its one return is a claim matched by three linked
  accounts).
- Linked accounts with same-style claims: `W2401-C07863` (12.5% rate, rule rank 3,534, model rank 148; five
  linked accounts, two with same-style claims within 7 days; style `BE-JKT-02` shows 20 linked claimants).

## Checked and found sound

Experiment report against validation, test, dry-run and ablation reports: all values and numerators match;
scopes name validation, final test and training; spread is labelled as spread. The chart has one axis from zero,
a legend for three roles, direct labels and the full table beneath. The heavy-returner circularity is stated.
Truth words are absent on overview, queue, case and style pages. The score is labelled "not a probability" on
table, case and tooltip; fallback relabels it and hides the comparison. The synthetic-data strip and footer are
on every page. Types are generated from the contract. No raw HTML injection; stale responses are guarded; note
submission reuses its key on retry and rotates it on success. Loading, error, empty and insufficient-history
states are distinct and truthful; deep links and back work; no overflow at 420 pixels. Docker: images contain no
data, only the artifact folder is mounted, the database port is not published, nginx proxies `/api/` on the same
origin; the private truth root is absent from serving configuration; the published truth export covers the
demonstration world only. `.env` is ignored and the template is empty. `arai local` serves the built UI with a
traversal guard; artifact keys are relative.

## Not checked

`npm test`, `npm run build` and `docker compose build` (read-only rule); the VM profile, TLS and login smoke;
writing a note or an upload on the live instance; screen-reader output; print layout.
