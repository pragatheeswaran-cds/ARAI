# Project scope for shared-understanding review

Date: 2026-09-25. Captures business decisions approved during the interview. This is not a declaration that every technical specification is ready for implementation.

Shared understanding explicitly confirmed by the user: "we have same understanding now". Detailed engineering specifications are in [v0.2](../specs/v0.2/README.md); confirmation of business scope is not a claim that technical tests have run.

## Goal and deliverable

A hackathon demonstration for Indian online apparel retail, targeted for the first or second week of November 2026. Three people will work with substantial Astra-assisted, specification-driven implementation.

The Returns Analyst investigates suspected customer abuse. The demonstration must distinguish abusive behaviour from legitimate heavy returns, defective-product purchases and benign shared households. High return volume alone is not abuse.

## Development workflow

Synthetic Data -> Data Validation -> Feature Engineering -> Training Dataset -> Model Training -> Model Evaluation -> Model Selection -> Model Artifact -> Inference Service -> FastAPI -> UI.

## Detection and analyst experience

- Overall customer abuse risk with supporting signals, rather than trained predictions for every abuse type in version one.
- Defined simulated abusive actions support truth labels. Unexplained excess returns are an investigation signal; deceptive refund claims, coordinated abuse and suspected wardrobing supply the agreed scenario families, with exact action definitions to be specified.
- A separate, linked SKU investigation queue supports quality, abuse-targeting and mixed/insufficient-evidence explanations.
- Product-quality evidence reduces the related return-volume suspicion without clearing unrelated abusive behaviour.
- Wardrobing is a separate image-free suspicion indicator; it does not confirm physical wear.
- Pending-item inspection routing is outside the current ML development focus following the user's correction.

## Data and learning

- Start from the team's 300-SKU apparel catalog, INR pricing and 30/45/60-day category return windows as simulation assumptions.
- Generate twelve months of transaction history; respect customer signup, product availability and scoring cutoffs.
- Include overlapping behaviours, legitimate counterexamples and mixed customer/product cases; do not make the detector's own rules define truth labels.
- Compare supervised and unsupervised candidates. Isolation Forest is a reference, not mandatory.
- Use development labels only as allowed for training/selection; keep final evaluation labels isolated.
- Fit and select during development, package the selected model and preprocessing, and load that frozen artifact for inference. Retraining is a separate explicit operation.

## Evaluation agreement

- Primary review capacity: top 5% of eligible customers; sensitivity checks at 1% and 10%.
- Compare identical populations and budgets against raw-return-rate ranking.
- A candidate qualifies only with higher precision and no higher false-positive rate in each legitimate-heavy-returner, defective-product-buyer and benign-household segment.
- Report recall by abusive behaviour, legitimate-segment errors and uncertainty. Synthetic success is not proof of real-world accuracy or revenue recovery.
- If no model qualifies, report that result; do not choose a winner by tuning on the final test.

## Next specification work

Specify concrete abusive actions, observation windows, generation profiles, schemas/mappings, independent data splits, candidate families, fitted feature transformations, reproducibility, artifact lifecycle, API/UI contracts and acceptance checks. Preserve the agreed business decisions while resolving these engineering details. Existing drafts and sample generators have known gaps; this scope does not certify them as complete or runnable.

## Supporting documents

- [Interview decisions](returns-analysis-scope-discussion.md)
- [ML workflow](ml-development-workflow.md)
- [Model comparison plan](../specs/04-model/model-comparison-plan.md)
- [Retail simulation policy](../specs/02-data/retail-simulation-policy.yaml)
- [Synthetic scenarios and walkthrough](../specs/02-data/customer-and-inspection-demo-data.md), with the inspection expansion explicitly marked outside current scope
