# Security, deployment and portability

Version 4.0 (amended 2026-10-05) | Implementation baseline | Component OPS

## Requirements and boundary

Copy/unzip this entire folder anywhere. No previous spec version, sibling archive or laptop path is required. Catalog/profile/festival/codebook/PDF/prototype included. Relative paths from package root. Double-click wireframe/index.html; no install/Internet needed to review.

Implementation uses Python ML/backend, Node React/Vite, PostgreSQL. Select and lock exact compatible versions at bootstrap; verify sklearn/skops pipeline compatibility before accepted artifacts. Author laptop version is not an implicit requirement. Commit Python lock, JS lockfile, migrations, env template and cross-platform entry scripts. Provide Compose API/worker/PostgreSQL/static UI as reference runtime during implementation; this specification does not include a running backend.

Config DATABASE_URL, ARTIFACT_ROOT, PRIVATE_TRUTH_ROOT (offline jobs only), APP_PROFILE=local|vm, UI_ORIGINS, and for the worker only ANTHROPIC_API_KEY and ARAI_MEMO_MODEL (contract 1.11.0, AM-62): the key is never required, has no default, is read by the worker alone, and without it every investigation memo is unavailable by design. An experiment contract may name its own data folder (experiment.yaml data_root, AM-51): the defaults are then artifacts/, private/ and the local database postgres/ under it, the environment variables still override them, and the data of an earlier experiment is neither read nor written. Never commit secrets. Serving process/container must not mount private root. Use relative defaults/explicit env roots and pathlib; no home/drive assumptions. Bundle timezone data where necessary. Pin RNG algorithms and numeric precision; compare canonical output across supported environments.

Local loopback,one worker,no authenticated reviewer claim. Cloud optional after local rehearsal: TLS reverse proxy,shared login/basic auth protecting UI/API,IP allowlist,private PostgreSQL. Rehearse judge IP access and local fallback. Synthetic opaque IDs need no added hash; real data requires separate privacy/keyed-hashing/auth design.

Contract 1.13.0 (AM-64): every response carries X-Content-Type-Options nosniff, X-Frame-Options DENY and Referrer-Policy same-origin, and API responses Cache-Control no-store; a request carrying a NUL byte in its path, query or body is refused with 422; a missing file under assets/ or with a static suffix is a 404 rather than the app shell, so a broken build fails loudly.

Contract 1.14.0 (AM-67): the CSV export carries no note text, and any cell that starts with =, +, -, @, a tab or a carriage return is prefixed with a quote so a spreadsheet does not run it; the case summary is built in the browser from data the page already holds.

Monitor liveness vs scoring readiness, queue depth,duration,error codes,artifact compatibility. Drift reports compare input/score distributions to training; never auto-refit/promote or imply accuracy. Implemented as a per-run report (component 11), the queue depth and the seconds since a worker last reported in Health (the worker is a separate process in the reference runtime), and a restart policy on every Compose service. Measure target-machine P95/full-world runtime. No generation/training at server startup.

Implementation commands must cover validate/generate/features/train/evaluate/select/promote/serve with project-relative paths. Seed/config changes version experiment records. Reviewing package requires no external account/API key.

## Inputs, outputs and dependencies

- Inputs: This folder plus supported toolchain/environment secrets.
- Outputs: Reproducible local runtime; optional secured VM.
- Dependencies: Bundled assets/contracts only.

## Acceptance criteria

| ID | Pass condition and required evidence |
|---|---|
| OPS-AC-01 | Extracted folder in a path with spaces passes tools/verify_package.py without repo siblings. |
| OPS-AC-02 | Wireframe opens offline on another machine/browser without dependency installation. |
| OPS-AC-03 | Fresh supported second environment bootstraps from locks/migrations and reproduces small-world canonical data/score ranks. |
| OPS-AC-04 | Serving cannot read truth; upload cannot escape root. |
| OPS-AC-05 | VM HTTPS/shared-login401/IP block/closed public DB smoke checks pass. |
| OPS-AC-06 | Local rehearsal works without cloud credentials and restores at relocated root. |
| OPS-AC-07 | Health reports queue depth and worker heartbeat; a run reports drift against training; concurrent migration at startup is safe. |

Acceptance status is recorded per criterion in acceptance-register.csv (status, evidence, date, reviewer). Prose requirements are not implementation evidence.
