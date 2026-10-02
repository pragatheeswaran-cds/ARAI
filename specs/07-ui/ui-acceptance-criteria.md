# UI acceptance criteria

DRAFT. All tests planned; none executed against an application.

| ID | Requirement | Observable acceptance | Planned test |
|---|---|---|---|
| UI-AC-001 | UI-REQ-001/FR-004 | Every displayed score says percentile, wardrobing says cannot confirm wear; score tier and memo recommendation are distinct | UI-002 |
| UI-AC-002 | UI-REQ-002/FR-007 | Case detail shows both passes/delta, evidence and computed counterfactual even if memo is null; unsupported prose never substitutes | UI-002 |
| UI-AC-003 | UI-REQ-003 | Every screen distinguishes loading, valid empty, failed and stale run; delayed old-run responses are ignored | UI-001 |
| UI-AC-004 | UI-REQ-004 | Malformed input cannot submit; UI never recalculates scores/actions; demo slider does not mutate run | UI-003 |
| UI-AC-005 | UI-REQ-005 | All core controls usable by keyboard; non-colour labels and table alternatives available; error/status announcements discoverable | UI-004 |
| UI-AC-006 | UI-REQ-006/FR-008 | Self-approval shows refusal without success; severe recommendation remains pending until approved independent-actor lifecycle | UI-003/API-003; blocked Q-007/Q-008 |
| UI-AC-007 | FR-010 | Scorecard shows equal k, source seed set, denominators and intervals; absent evaluation says not evaluated | UI-005; blocked Q-008/Q-009/Q-010 |
