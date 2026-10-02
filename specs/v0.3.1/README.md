# v0.3.1 proposed amendment

Date: 2026-09-25. Status: **DRAFT FOR USER REVIEW - NOT SIGNED**.

The user authorized drafting this amendment after the independent v0.3 review. That authorizes this document work, not acceptance of new business choices, implementation, generation, or training. The last recorded sign-off remains [v0.3](../v0.3/decision-log.md). All v0.3 files are preserved byte-for-byte.

Read [amendment.md](amendment.md) for the proposed fixes and three decisions, [schema.yaml](schema.yaml) for the consolidated operational schema draft, and [generator-policy.yaml](generator-policy.yaml) for the precise allocation rules. [verification.md](verification.md) records document checks, not implementation tests.

## Decisions to review

| ID | Recommended choice | Tradeoff |
|---|---|---|
| P-01 | Preserve all four capabilities and the full evaluation protocol; permit a reduced presentation layer at a dated checkpoint | Protects evaluation integrity while avoiding a promise of a fully polished app if time is short |
| P-02 | Keep sealed style/wardrobing metrics report-only; require development behavior checks and report targeting recall/coverage | Gives concrete functionality checks without inventing a performance threshold from synthetic results |
| P-03 | Evaluate style targeting against completed coordinated claims visible by cutoff; retain planned targets separately | Measures observable activity while preserving evidence of campaigns that did not execute |

Each row is PROPOSED. See the exact choices and alternatives in amendment.md. Technical amendments A-01 through A-09 are also draft pending package review; none is recorded as user-approved.

## Reading and authority

Until this package is accepted, it is a proposed resolution of known conflicts, not an implementation baseline. An unresolved contradiction must not be resolved by selecting whichever file is easiest to parse.

On acceptance, the intended precedence is:
1. Accepted, dated v0.3.1 amendment entries for their stated scope.
2. All accepted v0.3 decisions D-001 through D-044 and V02-DEF entries, including their explicit changed values.
3. v0.3 schema and reason mapping where not amended.
4. v0.2 contracts where not amended.
5. Explicitly referenced v0.1 reference data only; historical architecture is not an alternate implementation contract.

This replaces the incomplete "items listed here only" restriction in the v0.3 README upon acceptance. No broad v0.1 applicability or approval statement overrides a later decision.

| Contract area | Proposed effective source |
|---|---|
| Operational tables, delivery states, manifest | v0.3.1/schema.yaml (full draft); A-02 |
| Reason groups and genuine claim-code rates | v0.3/reason-code-mapping.yaml; D-018 through D-021, D-041 |
| Profile reconstruction, overlays, actions | D-003, D-009 through D-017, D-032, D-033, D-042; A-01, A-03, A-04, A-08 |
| Time, maturity, requests, withdrawals | D-005, D-026 through D-029, D-036, D-040; A-02, A-03 |
| Peer expectations and style queue | D-030 and v0.2/features.md; A-05, A-06 |
| Legitimate segments and coverage | D-022 through D-025; customer model gate unchanged |
| Models, split, candidate selection | v0.2/modeling.md and experiment.yaml; D-034, D-035; A-01, A-05 |
| Baseline fallback and artifact lifecycle | D-001; A-07; remaining v0.2/serving.md lifecycle |
| Reviews, privacy, narrative | D-037 through D-039; local vs VM distinction in D-044 |
| Storage, UI, deployment | D-004, D-007, D-043, D-044; API/UI contract still awaits wireframes |
| Scope, delivery, seeds | D-002, D-035, v0.2/delivery.md; P-01/A-09 |

D-030's two-level customer-excluding style/SKU formula remains the proposed effective formula, superseding the single-level formula in v0.2. D-011's 6% heavy-return overlay and 12% household overlay replace the older benign rates. D-034's grouped out-of-fold supervised reference replaces the original in-sample reference. These are existing recorded decisions, not new choices here.

## Acceptance and next slice

Record accepted/changed/rejected IDs, user, date, and hashes of this package in a new acceptance record after the user reviews it. Do not edit the old signed decision log or claim that its embedded hash covers this package.

After acceptance, build the deterministic data slice described in A-09. Wireframe-dependent API/UI work can follow separately. No runtime, data-generation, model-performance, or deployment result is claimed by this draft.
