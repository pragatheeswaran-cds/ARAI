# Use cases

DRAFT. Preconditions: approved dependent specs, valid run/config and local operator environment. No precondition is currently certified.

| ID | Persona | Main flow and result | Requirements | Blockers/details |
|---|---|---|---|---|
| UC-001 | Operator | Submit generated seed/config or registered seven-file upload; receive job ID; poll stages; receive completed run or readable failure. | FR-009 | Q-008 |
| UC-002 | Analyst | Open queue for a completed run; inspect case evidence, pass delta, graph, SKU verdicts and memo/fallback; record review outcome. | FR-001?FR-008 | Q-007/Q-008 |
| UC-003 | Second reviewer | Review queued severe recommendation; distinct actor records decision; self-approval refused and logged. | FR-008 | Q-007/Q-008 |
| UC-004 | Merchandising reviewer | Inspect SKU rates, evidence and quality-versus-target verdict; thin SKU explicitly has no verdict. | FR-005 | Q-016 |
| UC-005 | Evaluator | Freeze candidate selection on development worlds, execute approved sealed protocol once, publish matched-budget scorecard and limitations. | FR-010 | Q-009/Q-010 |
| UC-006 | Analyst/demo reviewer | Inspect unflagged heavy returner and compare raw-rule slider to fixed approved run score without changing business decisions. | FR-001/FR-007 | Q-008/Q-019/Q-022 |

Failure flows: invalid schemas fail the job; row violations quarantine with counts; unready run cannot serve final results; missing provider produces evidence-only cases; privacy leakage blocks publication. UI preserves selected run and distinguishes no cases from failed loading.
