# Goals, scope and domain language

Version 1.0 | Implementation baseline | Component GOAL

## Requirements and boundary

Build an Indian online apparel return-abuse investigation demonstration for November 1-14, 2026. Three-person team; staffing availability is not assumed. A Returns Analyst investigates customers, explains legitimate heavy returns/product defects, and reviews evidence of deceptive claims, coordination and temporary use.

Required: customer ranking; style investigation with SKU drill-down; graph relationship evidence; independent image-free wardrobing indicator; supervised/unsupervised comparison; frozen-artifact inference; FastAPI; React/Vite; PostgreSQL. Labelled raw-return-rate fallback is available if no model qualifies. Preserve 10 training / 5 validation / 5 test / 1 demo worlds. Interactive graph graphics, advanced filters, extensive polish and cloud hosting are stretch presentation work.

Suspected abuse is not confirmed fraud. Commercial Cost can occur without misconduct. A Wardrobing Indicator does not establish wear. A Suspected SKU Quality Issue does not clear unrelated customer abuse. A completed abusive action is a submitted intentional deceptive claim or temporary-use return, regardless of refund success. Eligible customers have >=3 mature sale lines.

Exclude pending-item inspection routing, images, LLM narratives, automatic refunds/account suspension, revenue-savings claims, production customer data, continuous retraining, and employee-profile management. The overall model does not separately predict abuse types. No real-world accuracy, causality or calibrated fraud-probability claims follow from synthetic results.

## Inputs, outputs and dependencies

- Inputs: Business decisions and bundled PDF.
- Outputs: Analyst workflows and exclusions.
- Dependencies: None.

## Acceptance criteria

| ID | Pass condition and required evidence |
|---|---|
| GOAL-AC-01 | Walkthrough covers legitimate heavy returns, defective buyers, benign sharing, deceptive claims, coordination, temporary use and mixed cases without revealing truth on cases. |
| GOAL-AC-02 | No UI/API can suspend accounts, refund orders, generate LLM verdicts or route inspections. |
| GOAL-AC-03 | Review budget is 5% of eligible customers; excluded-history counts and fallback are visible. |
| GOAL-AC-04 | Synthetic and prototype data are clearly labelled; mock values are not evaluated results. |

Acceptance status: **NOT_RUN**. Record executed results and artifact hashes; prose requirements are not implementation evidence.
