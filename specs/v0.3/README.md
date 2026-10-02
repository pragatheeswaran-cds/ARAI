# Return-abuse ML pipeline - specification review v0.3

Date: 2026-09-25. Status: SIGNED OFF 2026-09-25 by Pragatheeswaran - D-001 to D-044 and V02-DEF-01 to 17 accepted (DEF-15 changed). Still pending: wireframe-based API contract and frontend spec (D-007).

v0.3 is a review of [v0.2](../v0.2/README.md) and the contracts it references. No existing file was modified; v0.2 and v0.1 remain as written. v0.3 adds:

| File | Purpose |
|---|---|
| [gap-review.md](gap-review.md) | Gaps, contradictions and risks found in v0.2 and its referenced v0.1 contracts, each linked to a decision item |
| [decision-log.md](decision-log.md) | Every question asked, the user's answer (verbatim intent), open items, v0.2 defaults awaiting sign-off, and how each decision will be verified later |
| [schema.yaml](schema.yaml) | Consolidated machine-readable operational schema (decision D-008), replacing prose amendments in v0.2 data.md |
| [reason-code-mapping.yaml](reason-code-mapping.yaml) | Reason-code to feature-group/generator mapping (G-03), decided as D-018 to D-021, pending sign-off |

## Reading order

1. [gap-review.md](gap-review.md) - what is missing and why it matters.
2. [decision-log.md](decision-log.md) - what has been decided, what is open, what you still need to sign.
3. [schema.yaml](schema.yaml) and [reason-code-mapping.yaml](reason-code-mapping.yaml) - concrete contract drafts that apply the decisions.

## Authority and supersession (in force: decision log signed 2026-09-25)

v0.3 amends v0.2; it does not replace it. Where v0.3 is silent, v0.2 applies. Where they conflict, v0.3 wins for the items listed here only:

| Superseded source | Superseded by | Reason |
|---|---|---|
| `specs/02-data/schema.yaml` (v0.1) and the "Operational schema and adapters" table in `v0.2/data.md` | `v0.3/schema.yaml` | D-008 consolidated contract; D-005 delivery model |
| `claim_class`-based feature membership implied in `v0.2/features.md` | `v0.3/reason-code-mapping.yaml` | G-03 ambiguity (only after sign-off) |
| `specs/06-api/openapi.yaml` (v0.1: `/jobs`, `/flagged`, `/case/.../approve`) | Future v0.3 API contract, drafted after the user's wireframes (D-004). Until then, `v0.2/serving.md` endpoint table is the draft reference | Stale v0.1 paths |
| `specs/07-ui/*` Streamlit technology statement | React/Vite SPA over FastAPI (D-004); frontend spec pending wireframes | User decision |
| SQLite persistence in `v0.2/serving.md` and V02-DEF-15 | PostgreSQL; optional GCP/AWS VM profile with HTTPS + login + IP allowlist (D-043, D-044) | Sign-off change |
| Team `customer_master.csv` as a per-world profile source | Reconstructed profile generator under v0.3 (D-003) | Issues listed in G-05 |

Everything else in v0.1 remains historical evidence, as v0.2 already states.

## Freeze rule

Signed 2026-09-25; the spec hash is recorded at the end of the decision log. Any later edit to the decision log changes that hash and must be recorded as a new dated decision entry with a fresh hash.


Per D-006, the user signs [decision-log.md](decision-log.md). Each item is marked ACCEPTED, CHANGED or OPEN, with a date. A slice may start implementation only once all BLOCKING items it depends on are ACCEPTED or CHANGED. This package does not claim any data, model, API or UI was built or tested.
