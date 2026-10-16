# Design: authentication, roles and verified reviewer identity

Status: **decided; steps 1 and 2 built** (16 Oct 2026). Step 1: development login, roles on every route, CSRF, session
limits, review authors and the second-reviewer rule by user id, contract 1.16.0 (AM-69). Step 2: Keycloak single sign-on
(authorization code flow with PKCE, ID token checked against the realm's keys), roles from Keycloak groups, bootstrap
admins, bearer tokens for scripts, a development realm and a Compose profile, contract 1.17.0 (AM-70). Later steps (an
admin screen for users and roles; removing `reviewer_name` from requests) are not built. Branch `auth-design`, cut from
`gap3-customer-history` (API contract 1.15.0).

## 1. Why

The workbench decides nothing on its own, so its controls are the human ones: a case is opened by one reviewer and
approved or rejected by a different one, and every note and decision is kept, append only, with who made it. Today
that "who" is not verified:

| Today | Where | Consequence |
|---|---|---|
| The reviewer name is free text typed in the page header, kept in the browser's local storage, and sent in every review request (`ReviewRequest.reviewer_name`) | `web/src/App.tsx` (ReviewerProvider), `src/arai/service/api.py` | Anyone can open a case as "Asha" and approve it as "Ravi": the second-reviewer rule (`store.same_reviewer`) compares two typed names |
| The local profile has no login | `APP_PROFILE=local` | Fine on a laptop; not for anything shared |
| The VM profile has one shared username and password for everybody (HTTP Basic, `BASIC_AUTH_USER` and `BASIC_AUTH_PASSWORD`) | `create_app`, `deploy/nginx.conf` | It keeps strangers out, but cannot say which person did what, and cannot be revoked per person |
| Everyone who gets in can do everything: register or delete datasets, start or cancel runs, export the queue, open, approve and reject | every route | No separation between looking, reviewing, approving and operating |

So the four-eyes control, the audit trail and the customer history of contract 1.15.0 all record who someone said
they were. A buyer's security review would stop here. This design makes identity come from a verified login and
gives each person a role.

## 2. Goals and non-goals

Goals:

1. Every request knows the signed-in **user**, from a login the server verified, never from a field the browser sends.
2. **Roles** decide what a user may do, enforced by the server on every route.
3. The **second-reviewer rule** compares user ids, so one person cannot approve their own case under another name.
4. Every review row records the **user id** that wrote it; access is logged.
5. Company **single sign-on** (OpenID Connect) for shared deployments; a **development login** for laptops and demos,
   so a demonstration never needs an identity provider.

Non-goals (separate designs if wanted):

- A settings screen for business rules (review budget, tier and gate thresholds). Those decide who is reviewed and the
  evaluation is measured at their current values; they stay governed decisions, not runtime settings.
- Our own password store. ARAI will not store or reset passwords.
- Fine-grained data permissions (per brand, per region). One tenant, one world list.
- The command-line tools (`arai register`, `db-clean`, `publish`): they run on the host with database access and stay
  outside web authentication, as today.

No score, rank or selection changes. The five hashed scoring files are not touched.

## 3. The approach

### 3.1 Sign-in: OpenID Connect through the server (recommended)

The ARAI server does the sign-in with the company's identity provider (Microsoft Entra ID, Google Workspace, Okta, or
Keycloak when self-hosted), using the OpenID Connect authorization code flow with PKCE:

```
browser            ARAI server                          identity provider
  | GET /auth/login  |                                         |
  |----------------->| state, nonce, PKCE verifier (session)   |
  |<-- 302 ----------|---------------------------------------->| user signs in (and MFA, by the provider's policy)
  | GET /auth/callback?code&state                              |
  |----------------->| exchange code (+ client secret, PKCE) ->|
  |                  |<---------- ID token (a signed JWT) -----|
  |                  | verify JWT: signature by the provider's |
  |                  | published keys (JWKS), iss, aud, exp,   |
  |                  | nonce; map claims to user and roles     |
  |<-- 302 + session cookie (HttpOnly, Secure, SameSite=Lax)   |
  | API calls carry the cookie; the server looks the session up |
```

- **The JWT is checked once, at sign-in, on the server.** The browser receives only an opaque session cookie: a random
  256-bit value, stored in the database as a hash, `HttpOnly` (page scripts cannot read it), `Secure`, `SameSite=Lax`.
- **Why not hand the JWT to the browser?** A token in JavaScript can be stolen by any script injection, and a JWT
  cannot be withdrawn before it expires. A server session can be ended at once: on sign-out, when an admin disables a
  user, or when the session runs out (proposed: 60 minutes idle, 10 hours at most).
- **API clients and scripts** (`scripts/history_demo.py`, `curl`) may instead send `Authorization: Bearer <access
  token>` issued by the same provider for the ARAI API audience. The server verifies that JWT on each request
  (signature by JWKS, `iss`, `aud`, `exp`, `nbf`, algorithm allow-list RS256/ES256, 60 seconds of clock leeway) and maps
  it to a user exactly as a session.
- **Verification library:** `PyJWT[crypto]` (JWT and JWKS verification) plus `httpx` (already locked) for discovery and
  the code exchange. No home-made cryptography; the `none` algorithm and symmetric algorithms are refused.

### 3.2 Development login (local profile)

`AUTH_MODE=dev` (the default when `APP_PROFILE=local`) shows a sign-in page listing seeded users, for example:

| User | Roles |
|---|---|
| Asha, Ravi, Meera | reviewer and approver |
| Arjun | reviewer |
| Priya | viewer |
| Admin | admin |

Choosing one creates a session exactly as single sign-on would, so everything downstream is the same code. The
server **refuses to start** with `AUTH_MODE=dev` when `APP_PROFILE=vm`. The demo keeps working without an identity
provider, and the second-reviewer rule can be demonstrated truthfully by signing in as two different people.

### 3.3 Roles and permissions

Four roles, cumulative from left to right except admin, which is separate:

| Action | viewer | reviewer | approver | admin |
|---|---|---|---|---|
| Read datasets, runs, queue, cases, styles, evaluation | yes | yes | yes | yes |
| Export the queue as CSV, download a case summary | no | yes | yes | yes |
| Add a note or feedback; open a case; request approval | no | yes | yes | no |
| Approve or reject a case (never one they opened) | no | no | yes | no |
| Register or delete a dataset; start or cancel a run | no | no | no | yes |
| Manage users and roles (step 2) | no | no | no | yes |

- **Where roles come from:** a claim in the identity provider's token (for example the `groups` or `roles` claim),
  mapped by configuration (`AUTH_ROLE_MAP="arai-viewers=viewer,arai-reviewers=reviewer,arai-approvers=approver,
  arai-admins=admin"`) and refreshed at every sign-in. The company's directory stays the one place people are granted
  access. `ARAI_BOOTSTRAP_ADMINS` (a list of e-mail addresses) gives the first admin before groups exist.
- **Admin is deliberately not a reviewer:** whoever operates the system does not also decide cases, unless the
  directory gives them both roles explicitly.
- **Health** (`/api/v1/health`) stays open for monitoring, with no data in it.
- Every route declares the permission it needs in one table in code; a test walks every route of the contract and
  fails if one has no declared permission (the same pattern as today's "every route is in the contract" test).

### 3.4 The second-reviewer rule and the review record

- `reviews` gains `author_user_id` (the signed-in user). `reviewer_name` stays, filled by the **server** from the
  user's display name at the time of writing, so the record still reads naturally and survives a later rename.
- `ReviewRequest.reviewer_name` is no longer trusted: in contract 1.16.0 it becomes optional and ignored (a client that
  still sends it keeps working), and it is removed in 2.0.0.
- The rule becomes: the user of the latest open in this snapshot may not approve or reject it (409
  `second_reviewer_required`, same message as today). Two different people with the same display name are two users;
  one person under two names is one user.
- Reviews written before authentication have no user id. They stay as they are, shown with an **"unverified name"**
  marker; for them the rule falls back to today's name comparison.
- The approval band's filter `exclude_reviewer=<typed name>` becomes `exclude_mine=true`, read from the session.

### 3.5 Protection of state-changing requests

With a cookie session, every `POST` and `DELETE` must also carry `X-CSRF-Token`, matching a token issued with the
session (`GET /api/v1/me` returns it). The dataset upload is a multipart form, which browsers can send across sites
without asking; the header requirement closes that. In production the UI and API share one origin; CORS allows
credentials only for the configured development origin.

### 3.6 Audit

- `auth_events`: sign-in, sign-out, session expiry, refused request (401 and 403), role change, with user, time,
  request id and client address. Append only, like reviews.
- The request log line carries the user id next to the request id.
- Exports record who downloaded what view, as an `auth_events` row of kind `export`.

## 4. What changes, by part

| Part | Change |
|---|---|
| Database, migration 0012 | `users` (id, issuer, subject unique together, email, display_name, status, created_at, last_seen_at); `user_roles` (user_id, role, source); `sessions` (hashed id, user_id, csrf token hash, created_at, last_seen_at, expires_at); `auth_events`; `reviews.author_user_id` (nullable for older rows) with an index |
| Configuration (component 15) | `AUTH_MODE` (dev, oidc); `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` (a secret, environment or secret manager only), `OIDC_REDIRECT_URI`, `OIDC_SCOPES`, `OIDC_API_AUDIENCE`; `AUTH_ROLE_CLAIM`, `AUTH_ROLE_MAP`; `ARAI_BOOTSTRAP_ADMINS`; `SESSION_IDLE_MINUTES`, `SESSION_MAX_HOURS`. No secret has a default, as today |
| Server | `src/arai/service/auth.py`: discovery and JWKS cache (with key rotation), code exchange, JWT checks, sessions, CSRF, the role table and a `require(permission)` dependency on every route. New routes `/auth/login`, `/auth/callback`, `/auth/logout`, `/auth/dev-login` (dev only), `GET /api/v1/me` |
| API contract 1.16.0 | Security schemes (cookie session, bearer token); 401 `authentication_required` and 403 `forbidden` on every protected route; `Review.author` (user id, display name, verified flag); `reviewer_name` optional and ignored in requests; `exclude_mine` on the queue; `GET /me` |
| UI | The header shows the signed-in user, their roles and Sign out, instead of the name box; actions a role cannot take are hidden, with a short reason; a 401 sends the browser to sign-in and returns to the same page; a 403 says which role is needed; notes show "verified" or "unverified name" |
| Basic auth | Kept as an optional outer layer at the proxy for a while (IP allow-list plus shared login), then retired once single sign-on is in place |
| Tests | Token checks (expired, not yet valid, wrong issuer or audience, bad signature, the `none` and symmetric algorithms, key rotation) against a local test key and a fake JWKS; the route-permission walk; CSRF; session idle and maximum age; a disabled user losing access at once; the second-reviewer rule by user id with equal display names; older unverified rows; the browser walkthrough signing in as Asha and then Ravi |
| Specification | Decision row AM-69; components 12, 13, 14 and 15; acceptance criterion OPS-AC-05 rewritten from "shared login 401" to "single sign-on, role refusals and session expiry smoke checks" |
| Demo and scripts | The demo signs in through the development login; `scripts/history_demo.py` signs in as the seeded users so its August outcomes carry real user ids |

## 5. Delivery in steps

| Step | Contents | Can ship alone |
|---|---|---|
| 1 (built, AM-69) | Migration 0012, users and sessions, development login, `GET /me`, the permission table on every route, CSRF, `author_user_id` and the rule by user id; tests | Yes: laptops and demos get real identities and roles |
| 2 (built, AM-70) | OpenID Connect sign-in and bearer tokens, JWKS cache, role mapping from claims, bootstrap admins; tests with a fake provider; realm export and Compose profile | Yes: shared deployments get single sign-on |
| 3 | UI: signed-in header, role-aware actions, 401 and 403 handling, verified markers; the walkthrough signs in as two users | With step 1 |
| 4 | Contract 1.16.0, AM-69, components, RUNBOOK (setting up an identity provider), demo script; Basic auth made optional | With steps 1 to 3 |
| Later | Admin screen for users and roles; contract 2.0.0 removes `reviewer_name` from requests | - |

## 6. Decisions (answered 16 Oct 2026)

| # | Question | Decision |
|---|---|---|
| 1 | Identity provider | **Keycloak** (self-hosted), see 6.1 |
| 2 | Where roles live | **Keycloak groups** (recommended): mapped to ARAI roles at each sign-in |
| 3 | Viewers and export | **Reviewers and above only** export the queue or download a case summary (as proposed) |
| 4 | Admin and reviewing | **Admin stays separate** from reviewing (as proposed) |
| 5 | Session lengths | **Option B**: 60 minutes idle, 10 hours at most (see 6.2) |
| 6 | Basic auth at the proxy | **Kept** as an extra outer layer after single sign-on, see 6.3 |

### 6.1 Keycloak setup this implies

- One realm (for example `arai`) and one **confidential client** `arai` using the authorization code flow with PKCE,
  redirect URI `https://<host>/auth/callback`, post-logout redirect `https://<host>/`.
- Groups `arai-viewers`, `arai-reviewers`, `arai-approvers`, `arai-admins`, and a **Group Membership** mapper on the
  client that puts them in a `groups` claim (full group path off), so `AUTH_ROLE_CLAIM=groups` and
  `AUTH_ROLE_MAP=arai-viewers=viewer,arai-reviewers=reviewer,arai-approvers=approver,arai-admins=admin`.
- An **Audience** mapper adding `arai-api` to access tokens, so scripts' bearer tokens are accepted
  (`OIDC_API_AUDIENCE=arai-api`) and tokens meant for other applications are refused.
- `OIDC_ISSUER=https://<keycloak>/realms/arai`; keys come from that issuer's published JWKS, so a key rotated in
  Keycloak is picked up without a restart.
- Multi-factor authentication, password rules and account lockout are Keycloak's realm policies; ARAI never sees a
  password.
- For tests and step 2, a Keycloak container with a realm export (test users in each group) is added to a separate
  Compose profile, so the sign-in can be rehearsed end to end without a company Keycloak; the laptop demo keeps the
  development login.

### 6.2 Session lengths (decided: option B)

Two limits apply to an ARAI session. **Idle timeout**: after this long without any request, the user is signed out
(it protects a screen left open on a shared desk). **Maximum age**: even while active, the user signs in again after
this long (it limits how long a stolen session cookie works, and, because roles are read from Keycloak groups at
sign-in, it is also the longest a person removed from a group keeps their old role in an open session; disabling the
user inside ARAI ends their sessions at once). When the ARAI session ends but the user's Keycloak session is still
alive, signing in again is a redirect with no password; a note being typed is kept in the browser and the page comes
back after sign-in.

| Option | Idle | Maximum | Fits |
|---|---|---|---|
| A, stricter | 30 minutes | 8 hours | Shared desks, a service or warehouse floor |
| B, proposed | 60 minutes | 10 hours | One working day; a long investigation is not interrupted |
| C, follow Keycloak | B, plus a check with Keycloak every 5 minutes (refresh token) | Keycloak's own | Sign-out in Keycloak, or removal from a group, takes effect within 5 minutes; one more moving part |

### 6.3 Basic auth kept at the proxy

The proxy keeps the shared login and the IP allow-list in front of everything; ARAI's single sign-on runs behind it.
One consequence: HTTP Basic occupies the `Authorization` header at the proxy, so a script cannot send its Keycloak
bearer token in that header through the proxy. Scripts therefore call the API from inside the private network
(directly on the API port, behind the proxy), where the bearer token works; browsers are unaffected. The smoke checks
of OPS-AC-05 cover both layers: no shared login gives 401 at the proxy, no ARAI session gives 401 from ARAI, a missing
role gives 403.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Demos become harder | The development login needs nothing external and is the default on a laptop |
| The identity provider is unreachable | Existing sessions keep working until they expire; the JWKS is cached; sign-in shows a clear error with the request id |
| Key rotation at the provider | The JWKS cache refetches on an unknown key id, at most once a minute |
| Clock skew between servers | 60 seconds of leeway on `exp` and `nbf` |
| Older notes cannot be attributed | They are marked "unverified name"; nothing is rewritten |
| A client still sends `reviewer_name` | Accepted and ignored in 1.16.0, so nothing breaks; the server's identity is what is stored |
