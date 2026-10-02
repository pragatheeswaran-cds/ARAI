# Customer investigation and inspection demo data

## Latest steering - current scope

The user subsequently redirected the project to the [ML development pipeline](../../docs/ml-development-workflow.md). Customer abuse scenarios, legitimate counterexamples, private truth separation and evaluation controls remain relevant. Pending-item inspection snapshots, inspection capacity metrics and the inspection walkthrough below are retained as earlier discussion and are not current generation requirements. Do not implement that expansion as a prerequisite for the ML pipeline. The model's use of labels and inference lifecycle still require decisions.

Status: approved business direction from the user's Q9-Q12 answers on 2026-09-25; detailed generation and evaluation contract proposed below. No data has been generated or performance established by this document.

## Approved demonstration objectives

- Primary workflow: investigate customers for suspected return abuse.
- Separate SKU investigation queue, linked to customer cases, to distinguish product-quality explanations from suspected abuse targeting and mixed/insufficient evidence.
- Secondary workflow: rank pending return items before inspection in a batch demonstration.
- Distinguish abusive behaviour from legitimate heavy returns, defective-product purchases and benign shared households.
- Excess returns alone are an investigation signal, not a synthetic abuse label.
- Demonstrate a separate image-free wardrobing indicator; do not claim transactional evidence confirms wear.
- Generate synthetic data for both customer investigations and pending-item inspection prioritization.

## Proposed simulation design

Generate behaviour and events first; compute detector features from the resulting operational records. Private simulated intent, item condition and coordination membership must not be operational features. Do not assign truth labels by applying the detector's thresholds or its five wardrobing rules.

Separate the following dimensions instead of making one persona determine every outcome:

- Shopping volume and size-bracketing preferences.
- Actual product quality and fit variability.
- Household relationships and separately simulated abusive coordination.
- Explicit abusive actions, including deceptive refund claims and temporary use followed by return.
- Return-item condition, which may differ between items belonging to the same customer.

A high-volume customer may be legitimate. An abusive customer may make legitimate returns. A defective SKU may be bought by both. Shared identifiers must occur in benign and abusive cases. Include low-history customers and low-volume SKUs with insufficient evidence.

The old `serial_returner` population cannot remain abuse-positive solely because of return volume. Preserve excess-return scenarios as investigation examples; revise their truth labels based on explicit simulated actions. Existing population counts and historical metrics must be recomputed after this change, not carried forward as new acceptance criteria.

## Scenario coverage

| Scenario | Operational evidence to simulate | Private truth / counterexample |
|---|---|---|
| Legitimate heavy returner | High volume, multiple sizes, kept items and legitimate returns | No abusive action; overlap abusive customers' raw return rates |
| Defective-product buyer | Returns concentrated on affected SKUs; complaints from unrelated buyers | Product defect, without automatically labelling the buyer abusive |
| Benign household | Shared address/device/payment where plausible, ordinary purchases | Household relationship without abusive coordination |
| Deceptive refund claims | Claims, delivery/receipt chronology and independently generated inconsistencies when observable | Explicit simulated deception; include genuine customers with the same claim reasons |
| Coordinated abuse | Shared identifiers plus coordinated transactions and claims | Private coordination membership; identifiers encode equality, not role prefixes |
| Wardrobing | Repeated occasion-wear purchases, return timing and reasons with variation | Private simulated temporary use; legitimate late returns and occasion-wear purchases overlap |
| Mixed product/customer case | Defective-item returns plus unrelated suspicious transactions | Quality issues explain affected returns, not unrelated abuse |
| Pending-return item | A submitted return eligible for the chosen inspection stage | Later condition/outcome retained outside detector inputs |

These are generation requirements, not assumed real-world Indian prevalence estimates. Counts, distribution parameters and exact event semantics remain to be specified.

## Observation-time contract

Choose an explicit scoring cutoff T and an inspection decision stage before generation.

1. Historical operational snapshot: only records and field values available by T, including completed historical returns where appropriate.
2. Pending-item snapshot: eligible submitted returns awaiting the chosen inspection stage at T. Eventual condition, inspection verdict and later refund decisions are unavailable.
3. Private future outcomes: simulate and retain later results separately for evaluation. The evaluation world should contain outcomes for every eligible candidate, not just the selected shortlist, so alternative ranking policies can be compared.
4. Private truth: customer actions, product defects, item condition and coordination facts; accessible only to generation and evaluation.

Event occurrence and information availability may differ. Snapshot construction must respect when a field became available, not merely filter by order date. Features, SKU baselines and customer rankings used to prioritize pending items must also be computed as of T. Account lifetime statistics cannot incorporate later activity.

Future truth and outcomes must be inaccessible to feature building, ranking, explanations and any LLM memo. The evaluation stage joins them only after scores and selections are frozen. Historical inspection results, if used, must be available before T and distinguished from the pending item's unknown result.

This adds an as-of batch workflow to the previous retrospective-only design. Exact storage files and schemas are pending; this document does not silently extend the existing seven-file upload contract.

## Proposed demo walkthrough

1. Show the customer queue and its evidence cutoff. Compare the same investigation budget with a raw-return-rate ranking.
2. Open a legitimate heavy-return case and explain the contextual evidence that reduces suspicion; do not hard-code its disposition from the hidden label.
3. Open a defective-product buyer, follow the linked SKU case and show corroborating returns from unrelated customers.
4. Contrast a benign household and an abusive coordination case. Shared identity alone must not decide either case.
5. Open an image-free wardrobing example with the fired signals and the limitation that wear is unconfirmed. Also show a legitimate late-return counterexample.
6. Open a mixed case: product-quality evidence reduces the relevant volume suspicion while unrelated claim/coordination evidence remains visible.
7. Show the pending-item inspection shortlist built at T. Freeze it, then reveal the separate later outcomes in an evaluation view.
8. Show aggregate results, including misses and false positives, rather than inferring accuracy from hand-picked cases.

Curated walkthrough cases explain the system. They are separate from untouched evaluation worlds and are not evidence of aggregate accuracy. If the detector mishandles an example, expose the limitation rather than display a truth-derived score.

## Proposed evaluation

- Customer investigations: compare rankings at equal customer-review capacity; report abuse precision/recall and review rates for each benign segment. Evaluate unexplained excess returns as a signal, not an independent misconduct truth class.
- SKU investigations: assess quality issues, abuse targeting, mixed cases and insufficient-support handling using private SKU truth.
- Wardrobing: evaluate its separate indicator against planted actions, including false alerts on legitimate late returns and size shoppers. Do not treat this as validated wear detection.
- Item inspection: compare the shortlist with random selection and a simple baseline at equal item-inspection capacity. Define the target outcome first; product defects and abusive wear may both need inspection but are different causes.
- Keep customer-review capacity and item-inspection capacity separate; they count different units of work.
- Publish denominators, per-scenario errors and variability across sealed seeds. Fit and tune only on development worlds; do not select favourable evaluation seeds.
- Do not claim realized revenue savings, production accuracy or perfect separation from synthetic results.

## Required checks before accepting generated data

- Referential integrity, quantities, event chronology and historical SKU availability.
- Deterministic reproduction from a pinned seed/configuration/code version and manifest.
- No pending-item outcome or post-T aggregate in the operational snapshot.
- No truth labels, role-coded identifiers or equivalent proxy fields in detector inputs.
- Meaningful overlap between abusive and legitimate behaviour, with all counterexample scenarios present.
- Independent truth for customer actions, product issues and item condition; no automatic inheritance of customer fraud status by every return item.
- Regeneration of affected label totals and evaluation denominators after retiring volume-only abuse labels.
- Separate illustration and evaluation worlds; no claim that passing structural checks validates behavioural realism.

## Remaining decisions before generation

- Exact pending-item stage: return requested, pickup pending, or warehouse received but not inspected.
- Inspection target: suspected abuse only, or all actionable condition problems with cause-specific reporting.
- Population size, date range, category mapping, behavioural parameters, seed protocol and target capacities.
- Explicit simulated-action definitions, snapshot schema and inspection outcome semantics.
- Reconciliation with team customer/SKU masters and existing data/feature contracts.
