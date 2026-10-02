# Leakage prevention

Approved model-comparison update: [supervised and unsupervised comparison](../04-model/model-comparison-plan.md) permits training-target access only in the supervised training path. Feature builders, unsupervised fitting, inference and explanations must not access private truth. Final test labels remain sealed until evaluation. LEAK-001's original universal evaluation-only wording applies to the legacy unsupervised path; it does not prohibit the newly approved supervised training path.

Latest steering: pending-item inspection routing is outside the current development focus. The Q12 note below records earlier discussion. Reconcile observation-time features and label access with the learning and inference approach selected for the [ML pipeline](../../docs/ml-development-workflow.md); do not infer authorization for future-outcome features from the scope correction.

Update 2026-09-25: Q12 approves a secondary pre-inspection batch workflow. LEAK-003's retrospective-only description is the previous architecture boundary; the new workflow requires the observation-time contract in [customer and inspection demo data](../02-data/customer-and-inspection-demo-data.md). Later outcomes must remain separate from all detector inputs. Detailed schema and decision-stage choices remain pending; existing retrospective fields must not be reused wholesale.

LEAK-001 (FR-001?FR-010, NFR-004/NFR-008): detector modules must not import generator constants, sealed labels, population, ring_id, household_id, base_return_rate, is_defective or is_ring_target. Ground truth joins occur only after rankings are frozen in M16. Evaluation may measure segments without feeding those labels into fit or selection on sealed seeds.

LEAK-002: preserve complete seed worlds; no transaction-level random split across the same customer/order/community. Namespace reused synthetic customer IDs by seed. No transform fitted on another seed/world is reused silently.

LEAK-003: use only operational snapshots available at run_date. Refund status, receipt, disposition, current account_status and full-history loyalty are unavailable at original return-request time. This system is retrospective batch analysis; a future prospective model needs a new as-of contract. Right-censored return windows require Q-002, not automatic treatment as retained items.

LEAK-004: use identifier equality after hashing only. Ring/household ID prefixes are generator shortcuts even without reading ground_truth. Do not parse ID strings or train on them. Text templates and population-conditioned marketing/status can similarly expose labels.

LEAK-005: shared category means can retain own/community outcomes even after SKU leave-out; Q-006 must define this residual contamination. Do not claim complete leave-community-out protection until both levels are decided. Never double subtract overlapping exclusions.

LEAK-006: keep sealed-seed outputs out of tuning and regenerate no favourable test world. If exposed during selection, declare contamination, record it and obtain a replacement evaluation protocol before publishing. Wardrobing labels mean planted propensity, not observed wear.

Verification: DATA-TEST-002, FEATURE-005, MODEL-001/MODEL-003 and INF-002. Zero findings is required for privacy/label separation checks; real-world accuracy is not established by these controls.
