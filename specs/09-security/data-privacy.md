# Data privacy

PRIV-001. DRAFT. The supplied dataset is synthetic but handling rules must not rely on that fact. Device/address/payment identifiers are linkable sensitive data. Customer_id is an internal pseudonymous join key; its linkage still needs protection. Free-text return reasons can contain PII and malicious instructions even when sample values do not.

| Surface | Permitted | Forbidden |
|---|---|---|
| Ingestion boundary | Raw operational fields transiently for validation/hash/keyword work | Sending raw fields to model provider |
| Feature/graph artifacts | Salted equality tokens, approved aggregate features, internal join keys | Raw identity values, customer free text, sealed labels |
| UI case view | Internal customer keys, scores and derived evidence | Raw device/address/payment identifiers; untrusted HTML |
| Provider packet | Derived counts/types/values, approved reason enums, no entity identifiers | Customer/SKU/identity values and customer free text |
| Routine logs/API errors | Safe run/job IDs, rule/error codes, counts, version metadata | Full request bodies, raw values, text, credentials/salts |
| Evaluation workspace | Sealed labels after score freeze | Feeding labels into detector or production-case logs |

Quarantine must preserve redacted row lineage and reason counts, not accidentally retain raw fields in shared logs. If raw forensic quarantine is required, ownership/access/retention must be approved Q-015. Redaction must cover serialized artifacts and failed prompts, not just happy-path logs.

Retention/deletion periods, salt rotation and encryption are TBD Q-015; do not invent periods. Real data collection/consent/legal requirements are not established by synthetic demonstration. This document defines project handling expectations, not a legal compliance claim.

Verification: scan fixture raw values and injected/free text across clean outputs, packet, provider request, logs, errors and UI; zero forbidden occurrences (INF-002).
