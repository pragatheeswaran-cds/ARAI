# Problem statement

DRAFT ? NOT APPROVED. Sources: Architecture ??1?2/?6; HLD ??1?3.

Business problem: a high return rate can reflect abuse, defective goods or legitimate size exchange. A rate-only queue can consume limited analyst time and wrongly burden good customers. The product ranks cases for human attention and provides separate product-quality intelligence; it does not adjudicate fraud.

ML problem: unsupervised anomaly ranking of customers within a population, combined with deterministic rules and identity-graph evidence. SKU disambiguation and wardrobing are separate derived indicators. Synthetic population labels are evaluation-only, not training targets. Scores are run-relative percentiles, not calibrated probabilities.

Users: fraud analyst reviewing cases; second reviewer handling severe recommendations; merchandising reviewer examining quality issues; DS evaluator measuring synthetic performance; lead/operator controlling run configuration and provenance. Roles describe workflows, not implemented authentication.

Inputs: seven operational tables, run date and versioned configuration. Outputs: customer/SKU features, two-pass scores, graph/communities, SKU verdicts, evidence packets, optional grounded memos, review/queue logs, run manifests and evaluation scorecards. Success means the comparative claim is supported at a matched review budget with explicit benign-segment harm. Acceptance thresholds remain Q-009.
