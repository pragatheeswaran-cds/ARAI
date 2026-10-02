# Returns analysis scope discussion

Date: 2026-09-25. Status: ongoing interview, not implementation approval.

Update: business interview concluded with the user's explicit shared-understanding confirmation on2026-09-25. The [v0.2 specification package](../specs/v0.2/README.md) develops the agreed scope into engineering contracts; historical pending-question entries below are retained as discussion history and must be read alongside that package.

## Latest steering - ML pipeline is the focus

The user corrected the interview's drift into inspection operations. The current objective is ML-based identification of customer return abuse through the development pipeline recorded in [ML development workflow](ml-development-workflow.md). Pending-item inspection routing is removed from the current development focus; its prior Q12 approval is retained below as history, not an implementation prerequisite. SKU quality and shared-household context remain important to distinguishing abuse from legitimate returns. Learning approach and frozen-artifact inference lifecycle require clarification against the existing unsupervised per-batch design.

## Confirmed by the user

- Q18 approved: retain the team's 300-SKU apparel catalog, INR prices and category return windows (T-shirt/Shirt/Jeans 30 days; Jacket 45; Dress 60) as simulation assumptions, not claims about Indian retailer standards.
- Q19 approved: twelve months of transaction history, with shorter histories for newer customers and no transactions before signup. Correction to interview wording: the existing 180-day configuration is an evidence-packet cap, not the global transaction-generation window.
- Consolidated scope is in [agreed project scope](agreed-project-scope.md); exact data boundaries and technical contracts remain specification work.

- Q17 approved selection gate at the primary 5% review budget: precision must improve over the raw-return-rate baseline, and false-positive rates must not increase in any of the legitimate-heavy-returner, defective-product-buyer or benign-household segments. Select only among eligible candidates. If no candidate passes, report no acceptable model and revise using development data; do not tune on the final test. Statistical uncertainty and aggregation across worlds must be reported under a fixed protocol, not used to silently relax the gate.

- Q16 approved: compare investigation yield at fixed customer-review capacity, with 5% of eligible customers as the primary budget and 1%/10% sensitivity checks. Report false alerts separately for legitimate heavy returners, defective-product buyers and shared households. For 10,000 eligible customers, the primary budget is 500. Review capacity is not assumed abuse prevalence. Numerical acceptance thresholds, rounding/ties and any benign-segment disqualification limits remain unresolved.

- Q14 approved: overall customer abuse risk with separate supporting evidence signals; no requirement for trained per-abuse-type predictions in the first version.
- Q15 approved: fit candidates during development, select and save the artifact, then load it for inference without retraining. Retraining is a separate explicit operation.
- Algorithm clarification: Isolation Forest was a reference, not a mandated algorithm. Candidate selection must remain open within the approved bounded supervised/unsupervised comparison.

- Model approach: option C approved, comparing supervised and unsupervised candidates before selection; retain the existing anomaly-detection approach as a baseline. See [model comparison plan](../specs/04-model/model-comparison-plan.md). Algorithm family, prediction targets and serving lifecycle are not yet approved.

- Target market: Indian online apparel retail.
- Primary user: Returns Analyst.
- Support both customer investigations and return-item inspection prioritization, with customer investigations as the primary workflow.
- Synthetic data must support the primary customer-investigation workflow.
- Immediate deliverable: a hackathon demonstration.
- Wardrobing was initially considered optional; the user wants to discuss its effort and the broader abuse scope before deciding inclusion.
- Subsequent scope agreement: core customer investigations cover serial-return abuse, refund-claim abuse, and coordinated account rings; wardrobing is a separate explainable suspicion indicator, without image analysis or claims of confirmed wear. The user requested clarification of how synthetic transactional data supports that indicator.
- The demonstration must distinguish suspected abuse from legitimate heavy returners, buyers of defective products, and shared households. This is a demonstration objective, not an achieved result or a promise of perfect separation.
- High return activity alone warrants investigation, not an abuse label. Commercial cost and suspected misconduct are distinct.
- Three people are available; the user intends substantial Astra-assisted implementation guided by specifications. Available person-hours remain unspecified.
- Deadline clarification: demonstration in the first or second week of November; interpreted as November 1-14, 2026 given the session date. Exact date and available person-hours remain unspecified.
- High returns for a specific SKU must raise a SKU-investigation signal. A product-quality issue is an alternative explanation for customer returns; frequent returns must not automatically be attributed to customer misconduct.
- Q9 approved: suspected SKU quality issues reduce suspicion attributable to the affected product's return-volume evidence; independent refund-claim or coordination evidence remains available. SKU issues neither automatically incriminate nor automatically clear buyers. Synthetic scenarios must include customers who encounter a defective product and separately abuse returns. The exact score adjustment remains to be specified and tested.
- Q10 approved: provide a separate SKU investigation queue, linked to customer investigations; customer investigation remains the main screen. SKU explanations distinguish suspected quality issues, suspected abuse targeting, and insufficient or mixed evidence. High return rates trigger investigation rather than establish the explanation.
- Q11 approved: unexplained excess returns are an investigation signal; synthetic abuse truth requires a defined abusive behaviour, not high volume alone. User explicitly requests correct synthetic data and a documented demonstration approach.
- Q12 approved: batch ranking of pending return items before inspection, using historical information available at the decision time; eventual outcomes kept separately for evaluation. User explicitly requests synthetic data for this workflow too.
- Detailed generation requirements and proposed walkthrough are captured in [customer and inspection demo data](../specs/02-data/customer-and-inspection-demo-data.md). Approved business choices and unresolved implementation details are distinguished there.

## Pending decisions

- The behavioural and outcome definitions for synthetic abuse labels, including wardrobing, with overlap and legitimate counterexamples.
- Remaining delivery time and resulting implementation priorities.
- Exact simulated abusive-action definitions remain to be specified; Q11 resolves that return volume alone cannot define abuse truth.
- Exact evidence and score-adjustment rules for SKU quality and abuse targeting, including mixed cases; broad product behaviour is approved in Q9/Q10.
- The depth and timing of the secondary inspection-prioritization workflow.
- Acceptance criteria for ranking quality and treatment of legitimate high-return customers.

## Relationship to existing specifications

The current draft scope includes a wardrobing indicator and says no scope cut has been authorized. Its inclusion remains under discussion; this note does not silently remove it or authorize implementation.

Existing inputs and features support retrospective batch analysis. A prospective inspection-prioritization workflow requires an explicit decision-time data contract to prevent use of later inspection outcomes.
