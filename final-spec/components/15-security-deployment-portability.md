# Security, deployment and portability

Version 1.0 | Implementation baseline | Component OPS

## Requirements and boundary

Copy/unzip this entire folder anywhere. No previous spec version, sibling archive or laptop path is required. Catalog/profile/festival/codebook/PDF/prototype included. Relative paths from package root. Double-click wireframe/index.html; no install/Internet needed to review.

Implementation uses Python ML/backend, Node React/Vite, PostgreSQL. Select and lock exact compatible versions at bootstrap; verify sklearn/skops pipeline compatibility before accepted artifacts. Author laptop version is not an implicit requirement. Commit Python lock, JS lockfile, migrations, env template and cross-platform entry scripts. Provide Compose API/worker/PostgreSQL/static UI as reference runtime during implementation; this specification does not include a running backend.

Config DATABASE_URL, ARTIFACT_ROOT, PRIVATE_TRUTH_ROOT (offline jobs only), APP_PROFILE=local|vm, UI_ORIGINS. Never commit secrets. Serving process/container must not mount private root. Use relative defaults/explicit env roots and pathlib; no home/drive assumptions. Bundle timezone data where necessary. Pin RNG algorithms and numeric precision; compare canonical output across supported environments.

Local loopback,one worker,no authenticated reviewer claim. Cloud optional after local rehearsal: TLS reverse proxy,shared login/basic auth protecting UI/API,IP allowlist,private PostgreSQL. Rehearse judge IP access and local fallback. Synthetic opaque IDs need no added hash; real data requires separate privacy/keyed-hashing/auth design.

Monitor liveness vs scoring readiness, queue depth,duration,error codes,artifact compatibility. Drift reports compare input/score distributions to training; never auto-refit/promote or imply accuracy. Measure target-machine P95/full-world runtime. No generation/training at server startup.

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

Acceptance status: **NOT_RUN**. Record executed results and artifact hashes; prose requirements are not implementation evidence.
