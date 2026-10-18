# Design: deploying ARAI on AWS (Phase 4)

Status: **decided; building** (17 Oct 2026, decision row AM-72; amended 18 Oct 2026, AM-73, section 6). The owner chose the variant of section 2.9 with a Vercel address on top (2.4) and a 20 USD budget. Built: `deploy/aws/*`, `vercel.json`, `scripts/ops_ac_05.ps1`, RUNBOOK section 8. Blocked on 17 Oct 2026 by the account's activation: EC2, S3, SSM and CloudFormation answered "not subscribed" for the account, while IAM and STS worked. Implements decision rows D-043 and D-044 (optional secured cloud VM) and runs
acceptance criterion OPS-AC-05, which is still "not run" in the acceptance register. The owner's starting
architecture: EC2 for the backend, RDS for PostgreSQL, S3 for model files, Vercel for the frontend. This document
checks each of those against what the code assumes today, recommends a shape, and lists the steps and the decisions
still open.

AWS account 819717422656, region ap-south-1 (Mumbai), worked from the IAM user `arai-admin` through `aws login`.

## 1. What the code assumes today

Read from `docker-compose.yml`, `Dockerfile`, `deploy/Dockerfile.web`, `deploy/nginx.conf`, `src/arai/service/api.py`,
`src/arai/service/config.py`, `src/arai/bundles.py` and `web/src/api.ts`.

| Assumption | Where | Consequence for the plan |
|---|---|---|
| UI and API share one origin. The UI calls relative `/api/...` with `credentials: "same-origin"`; nginx proxies `/api/` to the API container | `web/src/api.ts:73`, `deploy/nginx.conf` | A frontend on another origin (Vercel) must proxy `/api` to the backend, or the session cookie, CSRF header and sign-in redirects stop working |
| The session cookie is `SameSite=Lax`, `HttpOnly`, and `Secure` on the vm profile; state changes need the CSRF header; CORS allows credentials only for `UI_ORIGINS` | `api.py:393`, `api.py:253` | Works unchanged behind a same-origin proxy. Cross-site cookies would need `SameSite=None` and a code change; not planned |
| The vm profile refuses to start without `BASIC_AUTH_USER`/`BASIC_AUTH_PASSWORD` and checks the shared login inside the app, not only at nginx | `api.py:234` | The shared login survives any proxy in front, including Vercel |
| OIDC: issuer must be https, the callback is `OIDC_REDIRECT_URI` on the UI's origin, Keycloak is reached over the back channel | `config.py`, `.env.example` | Keycloak needs its own https hostname; the redirect URI is whatever host the browser uses for the UI |
| API and worker share one local filesystem, `ARTIFACT_ROOT`: datasets uploaded through the API, model and baseline bundles, run outputs | `api.py:174-199,527-544`, `bundles.py` | API and worker must run on the same machine (or a shared volume). The runtime reads nothing from S3 |
| Models are **skops** files, not pickles, in a bundle folder with `bundle.json`, `files.json` and SHA-256 of every file; `load_bundle` verifies them by path | `bundles.py:125-151,214-234` | S3 cannot be the runtime model store without an adapter. S3 is right for transfer and backup |
| PostgreSQL through `DATABASE_URL` with psycopg 3; schema migrates at startup; one database per experiment | `pyproject.toml:14`, `api.py:240` | RDS PostgreSQL 16 works with no code change; add `?sslmode=require` |
| Keycloak in Compose is `start-dev`, plain http, realm imported from `deploy/keycloak/arai-realm.json` with the client secret `arai-dev-secret` | `docker-compose.yml` | Production needs `start` mode, a database, an https hostname and a new client secret |
| nginx listens on 80 only; the web container binds to loopback | `deploy/nginx.conf`, `docker-compose.yml` | TLS termination is new work: certificates and a 443 server block |
| Uploads up to 500 MB, proxy read timeout 300 s | `deploy/nginx.conf` | Any proxy in front must allow this (Vercel does not, see 2.4) |
| The experiment data (`data/EXP-20261005-04`) is not in git and is not on this machine; reproducing it takes about 40 minutes | RUNBOOK 1.3 | The server is seeded either by copying the folder through S3 or by running the offline pipeline on the server once |

## 2. The proposed architecture, checked

### 2.1 EC2 for the backend: yes

One instance runs Docker Compose with nginx (TLS), the API, the worker and Keycloak. API and worker stay on the same
box because they share the artifact root (section 1). Keycloak joins them because it needs an https hostname and a
database anyway, and a second VM would double the cost for a demo.

- Instance: **t3.large** (2 vCPU, 8 GB) in ap-south-1. 8 GB leaves room for Keycloak (about 1 GB), the API, and the
  worker scoring a 2M-row dataset. t3.medium (4 GB) is the fallback if cost matters more than headroom. x86 is kept so
  the model reproduction claim (RUNBOOK 1.3, "exactly") is not exposed to a different float path on Graviton.
- Disk: root 20 GB plus a separate **50 GB gp3** volume mounted at `/data` for the artifact root, so the instance can be
  rebuilt without touching the data.
- Access: **no SSH port**. Administration through SSM Session Manager with an instance role; no key pair to lose.
- Elastic IP so DNS stays stable across stop and start. The VM is stopped between demo sessions.
- Stack as code: one CloudFormation template under `deploy/aws/` (VPC security groups, instance role, EC2, RDS, S3,
  budget) so the environment can be torn down and rebuilt and the review can read what exists.

### 2.2 RDS for PostgreSQL: yes, with a note on cost

RDS PostgreSQL 16, **db.t4g.micro**, 20 GB gp3, single AZ, not publicly accessible, security group that accepts 5432
only from the EC2 security group, `rds.force_ssl` left on, automated backups 7 days. Two databases on it: `arai` and
`keycloak`.

What it buys over the Compose `db` container: the data survives a VM rebuild, backups are automatic, and the public DB
port check of OPS-AC-05 is satisfied by construction. What it costs: about 15 USD a month that the Compose container
would not. The RDS Free Tier (750 hours of db.t4g.micro a month for 12 months, or the credit-based Free Tier for
accounts opened after July 2025) may cover most of it in the first year. Recommendation: RDS, as proposed.

### 2.3 S3 for model files: yes, as transfer and backup, not as the runtime store

There are no pickle files. The promoted model is a skops bundle that the API and worker read from the artifact
root by path and verify by SHA-256. Pointing the runtime at S3 means an adapter in `bundles.py`, the dataset
registration and the run outputs, and a review of the verification path. That is a code project, not a deployment
step, and it brings nothing for a single VM.

S3 is still used, for three things:

1. **Seeding the server**: the experiment folder (worlds, bundles, published report) is uploaded once from the machine
   that holds it and synced down to `/data` on the VM. The private truth folder is never uploaded.
2. **Backup**: a nightly `aws s3 sync` of `/data/artifacts` to the bucket, and a weekly RDS snapshot export is not
   needed because RDS keeps 7 days of automated backups.
3. **Evidence**: screenshots and logs of the OPS-AC-05 run, referenced from the acceptance register.

Bucket `arai-819717422656-ap-south-1`, private, Block Public Access on, SSE-S3, versioning on, lifecycle that
expires noncurrent versions after 30 days. The EC2 instance role is the only principal with object access besides
`arai-admin`.

### 2.4 Vercel for the frontend: possible, with two real costs; nginx on the VM is the safer default

The UI is a static Vite build that must sit on the same origin as `/api`. On Vercel that is done with a rewrite in
`vercel.json`:

```json
{ "rewrites": [ { "source": "/api/:path*", "destination": "https://arai.<domain>/api/:path*" } ] }
```

Browser to Vercel to the VM. Cookies are set for the Vercel origin, the CSRF header passes through, the Basic login
prompt passes through, and the OIDC callback becomes `https://<vercel-host>/api/v1/auth/callback`, registered on the
Keycloak client, with `UI_ORIGINS` set to the Vercel host. No code change in `web/`.

Two consequences follow from Vercel's own limits, documented at
[vercel.com/docs/limits/overview](https://vercel.com/docs/limits/overview) (proxied request timeout, 30 seconds on
every plan, returning `ROUTER_EXTERNAL_TARGET_ERROR`):

1. **Dataset uploads through the UI will fail.** A 500 MB upload with file hashing on the server does not finish in
   30 seconds, and the limit cannot be raised. Workaround: register datasets from the VM itself with the CLI
   (`arai` has a register command that reads a directory, `cli.py:406`) or with a bearer token straight to
   `https://arai.<domain>`. Scoring runs are asynchronous and polled, so they are unaffected.
2. **The IP allowlist of D-044 cannot be enforced at the VM for UI traffic**, because requests arrive from Vercel's
   edge, whose addresses are not fixed. Either the allowlist moves to Vercel (Deployment Protection, Pro plan), or
   the owner amends D-044 to "TLS + shared login + single sign-on" for the Vercel path and the allowlist stays only
   on the VM's own hostname. This is a decision for the owner and should be written into DECISIONS.md either way.

The alternative is what the repository already builds: `deploy/Dockerfile.web` serves the UI from nginx on the VM.
Zero changes, uploads work, the allowlist works, one hostname, and OPS-AC-05 runs exactly as written.

**Recommendation.** Serve the UI from nginx on the VM for OPS-AC-05 and for anyone who uploads data. If a Vercel
address is wanted for the demo (a nicer URL, previews per branch), add it as a second origin on top of the same
backend: it costs one `vercel.json` and one extra redirect URI on the Keycloak client, and the two caveats above apply
to that address only. Both can run at once.

### 2.5 DNS and TLS

A hostname is required, because Let's Encrypt and Keycloak both need one. Three options, in order of preference:

1. A domain the owner buys or owns, hosted in **Route 53** (about 0.50 USD a month for the zone; a `.com` registration
   is about 14 USD a year). Certificates by certbot with the Route 53 DNS-01 plugin, so port 80 need not be open to
   the world and the allowlist stays strict. Hostnames `arai.<domain>` (UI and API) and `auth.<domain>` (Keycloak).
2. A free dynamic DNS name (DuckDNS). Certificates by HTTP-01, which needs port 80 open to everyone for the challenge;
   nginx serves only the redirect and `/.well-known/` there. Two names are needed, so two DuckDNS hosts.
3. Self-signed certificates. Browsers warn, Keycloak's issuer check works only after importing the CA into the API
   container, and the demo looks unfinished. Not recommended.

### 2.6 Network and security groups

- `sg-web`: 443 from the allowlisted IPs (and, under option 2 of 2.5, 80 from anywhere). Nothing else inbound.
- `sg-db`: 5432 from `sg-web` only. The RDS instance is not publicly accessible.
- Outbound from the VM: 443 to anywhere (Let's Encrypt, Docker Hub, the Anthropic API if memos are enabled, S3).
- Instance role: `AmazonSSMManagedInstanceCore` plus read and write on the one bucket. No access keys on the VM.
- Secrets (`POSTGRES` passwords, `BASIC_AUTH_PASSWORD`, `OIDC_CLIENT_SECRET`, optional `ANTHROPIC_API_KEY`) live in
  SSM Parameter Store as SecureString and are rendered into `/opt/arai/.env` (mode 600) by the bring-up script.

### 2.7 Keycloak in production mode

`quay.io/keycloak/keycloak:26` with `start` (not `start-dev`): `KC_DB=postgres` on the RDS `keycloak` database,
`KC_HOSTNAME=https://auth.<domain>`, `KC_HTTP_ENABLED=true` and `KC_PROXY_HEADERS=xforwarded` behind nginx. The realm
export is imported once with `--import-realm`, then: new client secret for `arai`, redirect URIs set to the real
callback addresses, the four groups kept, real people created with temporary passwords and a required password
change, the test users of the development realm deleted. The bootstrap admin password is rotated after first login.

### 2.8 Monthly cost, approximate, ap-south-1 on-demand

| Item | Running 24/7 | VM stopped between sessions |
|---|---|---|
| EC2 t3.large | about 68 USD | 0 |
| EBS 70 GB gp3 | about 6 USD | about 6 USD |
| Public IPv4 (Elastic IP) | about 4 USD | about 4 USD |
| RDS db.t4g.micro + 20 GB | about 17 USD | about 17 USD (or stop it too, up to 7 days at a time) |
| Route 53 zone | 0.50 USD | 0.50 USD |
| S3, Parameter Store, data transfer | under 2 USD | under 2 USD |
| Vercel | Hobby free for non-commercial use, otherwise Pro 20 USD per member | same |
| **Total** | **about 95 USD** | **about 30 USD** |

Prices are to be confirmed with the pricing API before launch; Free Tier credits for a new account reduce the first
months. A budget alert at the chosen monthly amount is created first, before any resource.

### 2.9 The cost-effective variant (recommended for a demo on the Free plan)

Checked on 17 Oct 2026 with the Free Tier API: the account is on the **Free account plan**, status not started, with
**100 USD of credits expiring 17 Apr 2027**, and five one-time activities worth 20 USD each (launch an EC2 instance,
set up a cost budget, create an RDS or Aurora database, use a Bedrock playground model, create a Lambda web app). A
Free plan account cannot be billed beyond its credits: when they run out or the plan expires, services stop, and the
account must be upgraded to a paid plan to continue. The 12-month legacy Free Tier does not apply to this account.

The variant keeps the architecture of 2.1 to 2.7 but removes what costs money without changing the demo:

| Change from the base plan | Saves (per month) | Trade-off |
|---|---|---|
| PostgreSQL as the Compose `db` container on the VM's data volume instead of RDS; nightly `pg_dump` to S3 | about 17 USD | the database dies with the VM unless restored from the dump (a few MB: runs, reviews, sign-in log) |
| t3.medium (2 vCPU, 4 GB) with 2 GB swap and Keycloak's heap capped at 512 MB, instead of t3.large | about 34 USD when running | less headroom while the worker scores a 2M-row dataset; fall back to t3.large if scoring pages |
| VM stopped outside demo sessions, started by one command | most of the compute cost | a 2 minute start before each session |
| No Elastic IP; a boot script updates the DNS name with the instance's current public address | about 4 USD when stopped | none visible to users |
| DuckDNS names instead of a bought domain and Route 53 | 0.50 USD plus 14 USD a year | port 80 open to everyone for certificate renewal (redirect and ACME only); Route 53 domain purchase may not be allowed on the Free plan |
| UI from nginx on the VM; no Vercel | nothing in money | one URL, uploads and allowlist work (see 2.4) |

Resulting cost, approximate, ap-south-1 on-demand:

| Mode | EC2 t3.medium | EBS 40 GB gp3 | Public IPv4 | S3, Parameter Store | Total |
|---|---|---|---|---|---|
| Running 24/7 | about 33 USD | about 4 USD | about 4 USD | under 1 USD | **about 41 USD** |
| Up about 60 hours a month | about 3 USD | about 4 USD | under 1 USD | under 1 USD | **about 8 USD** |

The 100 USD of credits cover two and a half months always-on, or the whole six months of the plan if the VM runs only
during sessions. Three of the five activities happen anyway (EC2, budget) or are cheap (an RDS database can be created
for the credit and deleted the same hour); they add up to 60 USD. The other two take minutes in the console.

## 3. Repository changes

Small, and all under `deploy/` and `docs/` except one new script:

1. `deploy/aws/stack.yaml`: CloudFormation for security groups, instance role, EC2 with the data volume and Elastic IP,
   RDS, S3 bucket, budget. Parameters: allowlist CIDRs, instance type, hostnames.
2. `deploy/aws/bringup.sh`: run on the VM through SSM: install Docker, mount `/data`, fetch secrets from Parameter
   Store into `.env`, obtain certificates, `docker compose -f docker-compose.yml -f deploy/aws/compose.vm.yml up -d`.
3. `deploy/aws/compose.vm.yml`: override that removes the `db` service, sets `DATABASE_URL` to RDS with
   `sslmode=require`, runs Keycloak in production mode, mounts `/data/artifacts`, and binds nginx to 80 and 443.
4. `deploy/nginx.vm.conf`: 80 to 443 redirect (and the ACME location under option 2), the 443 server for
   `arai.<domain>` with the existing `/api/` and static locations, the 443 server for `auth.<domain>` to Keycloak,
   security headers, `proxy_set_header X-Forwarded-*`.
5. `vercel.json` at the repository root, only if the Vercel address is wanted: the rewrite above, root directory
   `web`, build `npm ci && npm run build`, output `dist`. The build reads `../final-spec/contracts/openapi.yaml`, so
   the Vercel project root must be the repository, not `web/`.
6. `scripts/ops_ac_05.ps1`: the smoke checks of OPS-AC-05 as a script that writes its evidence: HTTP redirects to HTTPS;
   an unauthenticated request gets 401; a request from a non-allowlisted address times out (run from a Cloud Shell or a
   phone hotspot); the RDS endpoint does not answer from outside; Keycloak sign-in as a viewer succeeds; a viewer is
   refused a reviewer action with 403; a session expires after `SESSION_IDLE_MINUTES`.
7. Docs: RUNBOOK section 8 "AWS deployment: start, stop, rebuild"; DECISIONS.md row for this design and, if chosen,
   the D-044 amendment for the Vercel path; `acceptance-register.csv` row OPS-AC-05 with the evidence paths.

Nothing changes under `src/` or `web/src/`.

## 4. Steps, in order

| Step | What | Who | Needs |
|---|---|---|---|
| 4.0 | MFA on root and `arai-admin`; budget alert | owner (MFA), Claude (budget) | the monthly amount |
| 4.1 | S3 bucket, Parameter Store secrets, instance role, security groups, RDS, EC2 with Elastic IP (CloudFormation) | Claude | allowlist IPs, instance size |
| 4.2 | DNS records for `arai.` and `auth.` pointing at the Elastic IP | owner or Claude (if the zone is in Route 53) | the hostname decision |
| 4.3 | Bring-up on the VM through SSM: Docker, data volume, certificates, Compose stack with Keycloak in production mode | Claude | 4.1 and 4.2 |
| 4.4 | Seed the data: upload the experiment folder to S3 from the machine that holds it, sync to `/data` on the VM; or run the offline pipeline on the VM (about 40 minutes) | owner (upload) then Claude | location of `data/EXP-20261005-04` |
| 4.5 | Keycloak: realm import, new client secret, redirect URIs, real users in their groups, delete test users | Claude, owner sets own password | the user list |
| 4.6 | Optional: Vercel project with the rewrite; add its callback to the Keycloak client and `UI_ORIGINS` | owner creates the Vercel project, Claude the config | the Vercel decision |
| 4.7 | OPS-AC-05 smoke checks, evidence to S3 and `reports/ops-ac-05/`, acceptance register, RUNBOOK section 8, DECISIONS row | Claude | 4.3 to 4.5 |
| 4.8 | AMI snapshot of the finished VM; stop the VM until the next session | Claude | 4.7 |

Steps 4.0 and 4.1 can start as soon as the allowlist, the instance size and the budget amount are known. 4.2 and
everything after it wait for the hostname.

## 5. Decisions still open for the owner

1. **Hostname**: a domain in Route 53 (recommended), DuckDNS, or self-signed.
2. **Allowlist**: the public IPv4 addresses of every team member and judge, and whether any change daily.
3. **Instance size and schedule**: t3.large stopped between sessions (recommended), or another size; the dates the VM
   must be up.
4. **Memos**: unavailable on the VM as the vm profile intends (recommended for the demo, no key on the server), or the
   Anthropic API key in Parameter Store for the worker.
5. **Keycloak users**: name, e-mail and group for each person; at least one admin e-mail for `ARAI_BOOTSTRAP_ADMINS`.
6. **Frontend**: nginx on the VM only (recommended for OPS-AC-05), or nginx plus a Vercel address with the two caveats
   of 2.4, which also needs the D-044 amendment.
7. **Budget**: the monthly amount for the alert.
8. **Where the experiment data is**: the folder is not on this machine; the server is seeded from wherever it is, or
   regenerated on the server.

## 6. Amendments of 18 October 2026 (AM-73)

The account was activated on 18 October 2026 (Free plan, 120 USD of credits after the budget activity, expiring
18 April 2027). The owner then set two requirements that change section 2.9: the URL must be reachable by anyone,
and it must stay up continuously for at least three months, after which the VM may be stopped between sessions.

**Public access, no allowlist.** The IP allowlist of D-044 cannot apply to an audience that is not known in advance.
D-044 is amended for the whole deployment, not only the Vercel path: access control is TLS, the shared login checked
inside the API (`APP_PROFILE=vm` refuses to start without it), Keycloak sign-in for every action, nginx request limits
(10 sign-in requests a minute and 20 API requests a second per address, 20 connections per address), security
headers, and no public Keycloak admin console (`/admin` answers 404; administration is `kcadm.sh` inside the container
over SSM). The security group was already 80 and 443 from anywhere; the allowlist lived only in nginx and is removed
there. OPS-AC-05 loses the "non-allowlisted address is blocked" check and gains "admin console hidden" and "sign-in
rate limited".

**No Vercel.** With a public hostname on the VM the Vercel address adds nothing and costs a second API process. The
`api_vercel` service, `API_HOST`, `VERCEL_HOST` and `vercel.json` are removed; two hostnames remain, `APP_HOST` and
`AUTH_HOST`.

**Database: PostgreSQL on the VM, not RDS and not Supabase.** Supabase was tried on 18 October (project
`ndrkejdmaiisdtttsdky`, database `arai_local_db`, works from the laptop; RUNBOOK 3.2) and dropped for the VM: its
direct host is IPv6-only, the free Supabase plan cannot buy the IPv4 add-on, and its pooler serves only the `postgres`
database. RDS was then priced with the pricing API (db.t4g.micro 0.021 USD an hour plus 0.131 USD per GB-month in
ap-south-1, about 18 USD a month) and dropped for cost: three always-on months with RDS cost about 258 USD over the
six months, against 160 USD of credits; with PostgreSQL on the VM they cost about 150 USD. The nightly `pg_dump` to S3
remains the recovery path.

**Instance size.** The first stack creation failed: the Free account plan accepts only Free Tier eligible instance
types, and t3.medium is not one (`describe-instance-types --filters free-tier-eligible=true` lists t3.micro, t3.small,
t4g.micro, t4g.small, t8i.micro, t8i.small, c7i-flex.large and m7i-flex.large in ap-south-1). The always-on size is
therefore **t3.small** (2 GB, 0.0224 USD an hour) with the 2 GB swap of the first-boot script; c7i-flex.large (4 GB,
0.0848 USD an hour, about 71 USD a month) and m7i-flex.large (8 GB, 0.1008) stay allowed in the template for a heavy
scoring session, by stopping the VM, changing the type and starting it again. The demonstration world is small
enough for 2 GB.

**Schedule and budget.** Always on from bring-up to about 18 January 2027 (about 25 USD a month: t3.small 0.0224 USD
an hour, 46 GB gp3, one public IPv4 address at 0.005 USD an hour), then stopped between sessions (about 8 USD a
month); about 100 USD over the six months against 160 USD of credits. The budget alert is raised from 20 to 45 USD a month so it fires only on a real overrun. The two remaining
Free Tier activities (Bedrock playground, Lambda web app) are worth 40 USD more and are done from the console.

**No Keycloak on the VM (AM-74).** On a 2 GB instance Keycloak is the largest process (600 to 750 MB) and, with one
shared login for the whole audience, verifies nothing the demonstration needs. The VM runs the development login
instead: after the shared login the sign-in page lists personas with their roles and the visitor picks one. Sessions,
CSRF, role checks and the sign-in log are unchanged; the identity is a persona, not a verified person, so whoever
holds the shared login can act as Admin. The code refused this combination on purpose (AM-70); it now allows it only
with the explicit `AUTH_DEV_ON_VM=1`, so the guard stays for anyone who does not opt in. Keycloak, the realm and the
`oidc` path stay in the repository for the local profile and for a later real deployment. The VM has one hostname,
four containers (db, api, worker, web) with memory limits, and about 0.9 GB in use at idle.

**Still open at the time of writing.** The DuckDNS name and token. Memos stay unavailable on the VM (no key on the
server). Section 5 is otherwise closed.

## 7. Deployment plan (18 October 2026)

What exists, what remains, in order, with who does each step and how long it takes. RUNBOOK section 8 has the commands.

### 7.1 Done

| Item | Evidence |
|---|---|
| AWS account activated; Free plan ACTIVE; credits 120 USD plus 20 for the RDS activity (the instance was created and deleted the same hour) | `aws freetier get-account-plan-state` |
| Budget `arai-monthly` at 45 USD with alerts at 50 and 80 percent actual and 100 percent forecast | `aws budgets describe-budget` |
| Default VPC `vpc-0874079aa7935a35e`, public subnet `subnet-02b0ffa3cdefd06bc` (ap-south-1a) | `describe-vpcs`, `describe-subnets` |
| Template validated locally; instance type t3.small (the only Free Tier eligible size that fits the credits) | `deploy/aws/stack.yaml` |
| Repository changes for a public VM without Vercel and without Keycloak (AM-73, AM-74) | commits on `deploy-and-snapshots` |
| Tests: Python suite, front-end 30 of 30, type check, ruff; the vm sign-in path end to end, 14 of 14 | RUNBOOK section 5 |
| **19 Oct 2026: steps 1 to 8 of 7.2 done.** Stack `arai-demo` (instance `i-0d72a5fcfd56077c6`, t3.small); parameters; release; bring-up (two fixes on the way: httpx as a runtime dependency, AUTH_DEV_ON_VM passed to the containers); seed data 1.5 GB; W5401 and its eleven earlier snapshots registered and scored (284 selected of 5,676 eligible in September), the August outcomes recorded; OPS-AC-05 7 of 7 automated checks pass, two manual checks pending the owner | https://arai-demo.duckdns.org, `reports/ops-ac-05/2026-10-19/result.json`, acceptance register |

### 7.2 Remaining steps

| Step | What | Who | Takes |
|---|---|---|---|
| 1 | **Create the stack** `arai-demo` (the command of RUNBOOK 8.3, step 1; the owner runs it because Claude Code's permission mode blocks infrastructure applies). Creates the instance, the data volume, the bucket, the role and the security group. Starts the always-on clock, about 1.20 USD a day. | owner | 4 min |
| 2 | **DuckDNS**: one subdomain (for example `arai-demo`) at duckdns.org; the token from the same page. | owner | 5 min |
| 3 | **Parameters** in Parameter Store: `APP_HOST`, `DUCKDNS_DOMAINS`, `LE_EMAIL`, `DUCKDNS_TOKEN`, `POSTGRES_PASSWORD` and the shared login `BASIC_AUTH_USER` / `BASIC_AUTH_PASSWORD` (generated unless the owner names them), `ANTHROPIC_API_KEY` as `-` (memos off), optionally `AUTH_DEV_USERS`. RUNBOOK 8.2. | Claude | 5 min |
| 4 | **Release**: `git archive` of the committed tree to `s3://arai-819717422656-ap-south-1/release/arai.tar.gz`. RUNBOOK 8.3, step 2. | Claude | 2 min |
| 5 | **Bring-up** over SSM Run Command (RUNBOOK 8.3, step 3): the script waits for DNS, obtains the certificate, writes `.env`, builds the images and starts db, api, worker and web. First run builds the API image on the t3.small. | Claude | 15 to 25 min |
| 6 | **Seed the data**: `aws s3 sync` of `data/EXP-20261005-04/artifacts` (worlds, bundles, the published experiment; never `private/`, never `datasets/`) from this laptop to `seed/artifacts`, then down to `/data/artifacts` on the VM and a restart of api and worker. RUNBOOK 8.4. | Claude | 10 to 20 min, depends on upload bandwidth |
| 7 | **Register and score** W5401 and its twelve monthly snapshots against the VM (RUNBOOK section 4, with the shared login and a persona session), so the customer-history screens have a year. | Claude | about 15 min on a t3.small |
| 8 | **OPS-AC-05**: `scripts\ops_ac_05.ps1` from the laptop, the two manual checks with screenshots, the result under `reports\ops-ac-05\<date>\`, the row in `final-spec/acceptance-register.csv`. | Claude, owner does the two manual checks | 20 min |
| 9 | **Hand-over**: the URL and the shared login to the owner; RUNBOOK 8.6 for stop, start, backups and restore. Optional AMI snapshot of the finished VM. | Claude | 5 min |

Steps 2 and 3 can happen while step 1 runs; step 5 needs 1 to 4; 6 to 9 follow in order. From the stack command to a
working public URL is about one hour of wall-clock time, most of it waiting on builds and uploads.

### 7.3 Operating plan

- **Always on** from bring-up to about 18 January 2027: about 25 USD a month. Nightly backup at 02:30 UTC to the bucket.
  Certificate renewal by cron. DuckDNS refresh every five minutes, so a reboot or a resize keeps the name.
- **After that**: stop between sessions (about 8 USD a month); start takes two minutes and needs nothing else.
- **A heavy scoring session**: stop, change the type to c7i-flex.large, start, score, and resize back (RUNBOOK 8.6).
- **Budget alerts** go to the account e-mail at 22.50 and 36 USD actual spend and at a 45 USD forecast.
- **Rotate the shared login** by changing the two parameters and re-running bring-up (RUNBOOK 8.7).
- **Rebuild from nothing**: delete the stack (the bucket is kept, the data volume is snapshotted), create it again, run
  bring-up, restore the last dump and sync the artifacts back (RUNBOOK 8.9). About one hour.

### 7.4 Inputs still needed from the owner

1. The DuckDNS subdomain and token (step 2).
2. The Let's Encrypt contact e-mail (`LE_EMAIL`).
3. Whether to choose the shared login or let it be generated.
