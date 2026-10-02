# Source of truth and change control

2026-09-25 update: the user explicitly confirmed the [consolidated business scope](../../docs/agreed-project-scope.md). The [v0.2 package](../v0.2/README.md) records subsequent engineering choices. User-approved business decisions outrank conflicting historical v0.1 draft assumptions; engineering defaults are identified as such and do not claim separate user sign-off. Preserve old artifacts as historical sources. No successful implementation or test run is implied.

Approved business requirement > approved architecture decision > approved specification > HLD > LLD > existing implementation.

Architecture & Execution Plan third issue, HLD first issue and LLD first issue are the primary design sources. The missing submission proposal is referenced but cannot be treated as inspected evidence. Approval records were not found. The new specs are drafts and do not outrank existing designs until approved. A source's use of ?frozen? is not proof of approval.

Use source-inventory.md for exact paths and hashes. HLD F1?F10 map to FR-001?FR-010; N1?N8 map to NFR-001?NFR-008. M01?M16 remain the original module identifiers; M17 API and M18 UI are named in LLD ?10 but lack full module sheets.

Do not resolve contradictions just by choosing the newest file. Record the competing statements in gap-analysis.md and open-questions.md, obtain the accountable owner's decision, update canonical specs and tests, and record an approval entry with date/version. Preserve source files.

Q-007 (decision authority), Q-010 (seeds), Q-011 (storage), Q-017 (LLD wording giving implementation precedence), and Q-022 (scope) require explicit review. The hierarchy does not license silently overriding them. The seven-file design is retained, but Q-001 records that the supplied archive does not conform.

Freeze sequence: product/safety decisions ? data and observation semantics ? features/two-pass/ranking ? evaluation and selection ? API/UI lifecycle ? integration acceptance. Approval ledger entries must name scope, approver, timestamp, version/hash, resolved questions and remaining waivers. No ledger entry or freeze is fabricated here.
