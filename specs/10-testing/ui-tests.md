# Ui Tests

DRAFT ? verification specifications only, not implemented or executed tests. Sources: LLD ?5/?9 and referenced canonical specs.

| Test ID | Requirements | Level / concern | Fixture and expected result |
|---|---|---|---|
| UI-001 | UI-REQ-001/003; UI-AC-003 | State integration | For all five screens inject loading, empty array, fetch failure and delayed old-run response; verify distinct messages and preserved run context. Failed upload/job never looks complete; memo failure does not hide evidence. |
| UI-002 | FR-004/007; UI-AC-001/002 | Presentation regression | Score labelled percentile; two passes and delta/evidence/counterfactual visible; memo tier differs from risk tier; wardrobe limitation inline; no-memo and insufficient-SKU states explicit. Do not present source demo numbers as evaluated results. |
| UI-003 | UI-REQ-004/006; UI-AC-004/006; SEC-007 | Input/action safety | Invalid inputs blocked with readable field errors; raw-rate slider cannot alter server run/decision; memo is inert text. 409 never shows success. Approval buttons follow approved lifecycle; Q-007/Q-008/Q-019. |
| UI-004 | UI-REQ-005; UI-AC-005 | Accessibility manual/interaction | Navigate core flows with keyboard; labels/focus/error announcements and non-colour equivalents visible; graph has table alternative. Formal standard and assistive-tech matrix await Q-019. |
| UI-005 | FR-010; UI-AC-007 | Evaluation screen contract | Show k, seed provenance, denominators, intervals and synthetic limitation; no scorecard means not evaluated. No direct dataframe bypass. Scorecard API and metric selection blocked Q-008/Q-009/Q-010. |
