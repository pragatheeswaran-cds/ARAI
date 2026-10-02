# ML development workflow

Status: user-confirmed project direction, 2026-09-25. Model approach and detailed contracts remain under discussion.

## Objective

Build an ML-based customer return-abuse detection demonstration for Indian online apparel retail. Distinguish defined abusive behaviours from legitimate heavy returns, defective-product purchases and benign shared households. Product and relationship context support customer detection and explanation.

## User-specified development sequence

Synthetic Data -> Data Validation -> Feature Engineering -> Training Dataset -> Model Training -> Model Evaluation -> Model Selection -> Model Artifact -> Inference Service -> FastAPI -> UI.

| Stage | Required output |
|---|---|
| Synthetic Data | Customer, product, order, return and relationship events; separately stored simulated truth and legitimate counterexamples |
| Data Validation | Schema, chronology, referential-integrity, scenario-coverage and leakage checks |
| Feature Engineering | Reproducible customer features incorporating product context and relevant relationship/behaviour evidence |
| Training Dataset | Versioned feature data, with target use and development/evaluation boundaries explicitly defined |
| Model Training | Reproducible candidate fits under the agreed learning approach |
| Model Evaluation | Detection results and false positives for each legitimate segment on data permitted for that stage |
| Model Selection | Documented comparison using agreed metrics; final test results do not drive selection |
| Model Artifact | Selected fitted model and required transforms, feature schema, configuration and provenance |
| Inference Service | Load and apply the selected artifact under a defined input/output contract |
| FastAPI | Expose inference and necessary workflow operations |
| UI | Customer risk/investigation queue and evidence; linked SKU context supporting interpretation |

The table specifies intended deliverables, not completed implementation. A separate pending-item inspection-routing product is not part of this current development focus. Earlier inspection scenarios remain recorded as prior discussion, not prerequisites for this pipeline.

## Model decision still required

Q14/Q15 update: overall customer abuse risk with separate supporting signals is approved. Models and fitted preprocessing are trained during development and loaded unchanged for inference. Isolation Forest is illustrative, not mandatory. Previous per-batch refitting and mandatory forest assumptions below are historical context only; candidate family, action-based target details and selection criteria remain open.

Update: the user approved option C, a bounded comparison of supervised and unsupervised candidates. See [model comparison plan](../specs/04-model/model-comparison-plan.md). Output targets and fit/serve lifecycle remain unresolved; the text below describes the previous design that must be reconciled.

Existing training specifications define unsupervised Isolation Forest, rules and graph evidence, with synthetic labels reserved for evaluation. They fit within each submitted batch. The user's selected-artifact-to-inference sequence may instead require fitting during development and applying a frozen artifact later. Both the learning approach and fit/serve lifecycle must be explicitly reconciled.

A supervised classifier would use defined synthetic abuse targets for fitting; an unsupervised model would not. Neither approach should use high return volume alone as abuse truth. Synthetic evaluation demonstrates performance in simulated worlds, not real-world fraud adjudication.
