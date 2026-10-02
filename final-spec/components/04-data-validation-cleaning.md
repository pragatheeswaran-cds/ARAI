# Data validation, cleaning and snapshot clearance

Version 1.0 | Implementation baseline | Component VAL

## Requirements and boundary

Named adapters only: sku_id->sku, color->colour, color_id->colour_id, team booleans->0/1. Preserve originals and log changes. Do not impute impossible dates, delete duplicates/outliers, silently adjust quantity or quarantine label-correlated rows.

Validate limits/encoding/headers; types/enums/nullability; primary keys; references/customer ownership; money/quantity; chronology/availability; status/window/cumulative requests; header sums; catalog/reference conformance; manifest hashes/counts. Structural failure rejects entire world, command exits nonzero. Emit rule_id, table, row key, count, severity and safe example with accepted=false. No accepted manifest on failure.

One immutable snapshot per world. Historical rescoring cannot filter final-state rows by order date; it requires event logs/new snapshot construction. Late requests are rejected but count as requests; ratios cap at two only during features, not raw dates.

Optional missing evidence stays null. Learned feature imputation belongs to training, not cleaning. Behavioral outliers are documented rather than deleted to improve scores. Private labels cannot govern retention. Statistical warnings differ from structural rejections; small samples need denominators.

## Inputs, outputs and dependencies

- Inputs: Raw source adapter outputs and world files.
- Outputs: Canonical data and structured accepted/rejected report.
- Dependencies: Data contracts.

## Acceptance criteria

| ID | Pass condition and required evidence |
|---|---|
| VAL-AC-01 | Each rule class has valid/invalid fixtures; invalid command exits nonzero without accepted publication. |
| VAL-AC-02 | Return aggregation before sales joins prevents duplicated exposure. |
| VAL-AC-03 | Negative values/future availability/unknown category/cross-customer fixtures report correct keys. |
| VAL-AC-04 | Optional missing evidence does not remove customers. |
| VAL-AC-05 | Original hashes and all allowed adapter transforms are recorded. |

Acceptance status: **NOT_RUN**. Record executed results and artifact hashes; prose requirements are not implementation evidence.
