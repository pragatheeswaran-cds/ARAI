# Assumptions

Every entry is **ASSUMPTION ? REQUIRES REVIEW**. These are non-blocking drafting conventions; none supplies a missing scoring formula, business threshold, safety decision or evaluation protocol.

## A-001

ASSUMPTION ? REQUIRES REVIEW: Use draft version 0.1.0 for this SDD set; no source document is newly approved. Specification versioning does not introduce runtime API/schema negotiation.

## A-002

ASSUMPTION ? REQUIRES REVIEW: Describe the MVP as a local single-tenant decision-support demonstration; all real account actions and externally exposed deployments require a separate approved scope.

## A-003

ASSUMPTION ? REQUIRES REVIEW: Use JSON-compatible wire types and non-empty identifiers; reject malformed requests with 422, absent resources with 404, unready run/config conflicts with 409 and unexpected service failures with 500. These complete the documented API for review.

## A-004

ASSUMPTION ? REQUIRES REVIEW: Retain all non-empty data fields as required unless the source explicitly permits missing values. Empty reason_text is allowed; cancelled delivery dates are null. Observed ranges are evidence, not business limits.

## A-005

ASSUMPTION ? REQUIRES REVIEW: Record local run manifests and compatible artifact bundles without adding a hosted experiment tracker or registry. Proposed artifact lifecycle is draft, verified, frozen, retired.

## A-006

ASSUMPTION ? REQUIRES REVIEW: Loading, empty, error, stale-run and keyboard-accessible UI behaviours below are proposed interaction requirements, not claims of existing mockups.

## A-007

ASSUMPTION ? REQUIRES REVIEW: Use full SHA-256 source/data hashes for new spec evidence and future manifests; preserve archived truncated hashes as provenance only. Record unavailable git commit explicitly rather than inventing one.

## A-008

ASSUMPTION ? REQUIRES REVIEW: Report all four benign populations, including normal, and all four abuse populations in evaluation. Undefined metrics return null with a reason, never zero by accident.

## A-009

ASSUMPTION ? REQUIRES REVIEW: OpenAPI nested pass-score, evidence and neighbour shapes, progress in [0,1], strict unknown-property rejection and illustrative loopback port 8000 complete the LLD's partial JSON for review. They are proposals, not existing wire contracts. Nullable SKU statistics represent undefined values; their exact conditions remain Q-016.

## A-010

ASSUMPTION ? REQUIRES REVIEW: Arithmetic unit fixtures may use absolute tolerance 1e-6 when comparing unrounded numeric values. Display rounding is separate; this is not a business acceptance tolerance or a cross-environment determinism allowance.
