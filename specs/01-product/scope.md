# Scope

## Latest user steering - ML development pipeline

Prioritize customer return-abuse detection through synthetic data, validation, features, training data, training, evaluation, selection, model artifact, inference service, FastAPI and UI. See [ML development workflow](../../docs/ml-development-workflow.md). The earlier pending-item inspection expansion below is no longer part of the current development focus. SKU investigation/context remains supportive of customer detection. Learning approach and fit/serve contracts remain unresolved.

## User-confirmed scope update - 2026-09-25

Customer investigation remains primary, with a linked SKU investigation queue and secondary batch ranking of pending return items before inspection (Q9-Q12). This is an as-of batch extension, not live point-of-return scoring. Wardrobing remains a separate image-free suspicion indicator. Return volume alone is not synthetic abuse truth. See [scope discussion](../../docs/returns-analysis-scope-discussion.md) and [demo data plan](../02-data/customer-and-inspection-demo-data.md). These business approvals do not resolve all draft technical contracts below.

DRAFT. Sources: Architecture third issue ??2?6/?8; HLD ??10?11.

In scope: online-apparel synthetic seven-table batch inputs; validation/quarantine; customer and SKU features; rules, Isolation Forest, weighted graph and Louvain; shrinkage and community-aware second pass; wardrobing indicator; SKU disambiguation; one structured LLM memo behind an independent deterministic gate; FastAPI job service; Streamlit five-screen reviewer app; local artifacts/logs; matched-budget and sealed-seed evaluation; offline demonstration.

Out of scope: supervised fraud classifier, calibrated fraud probability, real-time point-of-return scoring, automatic retailer account actions, physical confirmation of wear, graph neural networks, temporal graph, cross-retailer analysis, distributed data platform, managed deployment, authentication/RBAC production system and general-purpose arbitrary schema ingestion. Seven-table conforming upload remains in scope.

No cut has been authorized. Architecture/deck appendices retain inconsistent cut/buy-back and exclusion language (Q-022); preserve the full-scope primary design pending review. Threshold-slider details and upload transport need approval. Missing customer_master is a blocker, not permission to reduce the contract to six files.
