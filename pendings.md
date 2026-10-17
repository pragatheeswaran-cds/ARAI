# Pending items (17 Oct 2026)

What is still open, who it waits on, and where it is described. The work so far is complete and pushed on branch
`year-of-snapshots`. That branch contains every earlier branch: `ccr-488644ae-esclgi`, `gap3-customer-history`,
`auth-design`, `auth-admin` and `lint-cleanup`. 237 Python tests pass, the browser walkthrough passes 71 of 71 and lint
is clean.

## 1. To try on your laptop

| # | Item | How | Done when |
|---|---|---|---|
| 1.1 | Bring a fresh clone to a working demo | `git checkout year-of-snapshots`, then RUNBOOK "Start here": copy `data\EXP-20261005-04` across or regenerate it from seeds (about 40 minutes), then the year of snapshots and `scripts\history_demo.py --load` | The Overview shows 5,676 scored and 284 in the queue for W5401, and the month-by-month figures match the table in RUNBOOK 4.1 (file hashes in `records/2026-10-16-monthly-snapshots.md`) |
| 1.2 | Keycloak single sign-on against a real Keycloak | RUNBOOK 2.6: `docker compose --profile sso up -d keycloak`, the five `$env:` lines, `uv run arai local`; the users and passwords are in RUNBOOK "Start here" | Signing in as `asha`, `priya` and `admin` gives their roles; a person in no ARAI group is refused; Sign out ends the Keycloak session. Tested so far only against an in-process stand-in, because the container could not download the Keycloak image |
| 1.3 | Rehearse on the presentation machine | RUNBOOK section 5, "Full check before a demonstration" | Also completes acceptance items TEST-AC-04 (scoring time on that machine and the baseline fallback there) and OPS-AC-06 (local rehearsal, and a restore after the data folder moves) |

## 2. Decisions for you

| # | Decision | Options |
|---|---|---|
| 2.1 | How the work reaches `main` | `main` (e84c40f) is about 40 commits behind and has one commit of its own ("Remove dummy.txt..."), so it needs a merge, not a fast-forward. One pull request from `year-of-snapshots` brings in everything. Or merge in steps, branch by branch |
| 2.2 | The empty branch `more-experiments` | Delete it, or name the experiment to run on it |
| 2.3 | SEL-AC-05 in the acceptance register | Keep it PASS (two test-informed experiments on new test worlds, earlier results kept). Or mark it PARTIAL, because no final test has ever failed, so keeping a failed test on record has never been exercised |
| 2.4 | Owner sign-off on the acceptance register | Every row reads "owner sign-off pending" (105 PASS, 7 PARTIAL, 1 NOT_RUN) |

## 3. Experiment and model (longer term)

| # | Item | Where |
|---|---|---|
| 3.1 | The 0.75-0.85 development target stays open until this experiment's gate dry run and results are recorded | `final-spec/DECISIONS.md` AM-45; `records/2026-10-05-status-and-open-decisions.md` |
| 3.2 | A gate leg for honest repeat claimants belongs to the next experiment. It needs a revised experiment contract, new worlds, and untouched validation and test seeds | `final-spec/DECISIONS.md` (open items after AM-44); `records/2026-10-05-status-and-open-decisions.md` |
| 3.3 | The training weights use simulation truth (which delivery failures were genuine). Real data has no such label | `records/2026-10-05-experiment-4.md` section 5 |

## 4. Deployment

| # | Item | Where |
|---|---|---|
| 4.1 | VM smoke checks (OPS-AC-05, the only NOT_RUN item): HTTPS, the shared login's 401, the IP block, a closed public database, plus a Keycloak sign-in, a role refusal and session expiry. Needs a VM to be deployed | `final-spec/components/15-security-deployment-portability.md`; RUNBOOK 3.1 and 2.6 |

## 5. Smaller gaps named in the acceptance register (PARTIAL)

Every criterion of the register, PASS or not, is explained in plain words with its evidence and gap in
[docs/acceptance-register-explained.md](docs/acceptance-register-explained.md).

| Item | What is missing |
|---|---|
| GEN-AC-08 | Coverage and support reports before full generation were produced for the fixture; the current generator revision ran fixtures and training worlds in one batch |
| VAL-AC-01 | Validation fixtures for file encoding and the size limit |
| FEAT-AC-04 | Graph construction has no failure path distinct from an empty graph. This touches `features.py`, which is hash-locked, so it would need a new experiment |
| API-AC-02 | No upload fixture at the real 500,000,000-byte or 2,000,000-row limit (the test lowers the limit) |
| TEST-AC-03 | No integration case for a model-mismatch upload at the size limit |
| TEST-AC-04, OPS-AC-06 | The presentation-machine rehearsal (item 1.3) |

VAL-AC-01, API-AC-02 and TEST-AC-03 can be closed with tests alone. GEN-AC-08 needs the generator's reports rerun on
their own; the generator itself would not change.
