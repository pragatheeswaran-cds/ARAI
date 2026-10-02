# Secrets management

SECRETS-001. DRAFT. Potential secrets are provider API credentials and the ingestion hash salt/key. LLD names a hash salt but specifies no storage or rotation method; provider is also unnamed. Select the concrete local mechanism in Q-015 before implementing integrations.

Do not place secrets in versioned config, specs, data, model metadata, prompts, logs, exceptions, UI state or source control. Record a non-secret salt version and provider/model identifier for provenance. Same approved salt scope must preserve equality within a run; cross-run linkage and rotation need explicit policy, not a global hardcoded salt.

A missing provider credential supports evidence-only/offline operation. Missing hashing material must not silently pass raw identifiers downstream or replace the hash with a public fixed constant. Startup behaviour and reprocessing during rotation need Q-015. Source fixture strings are not credentials.

Restrict local file permissions and access according to approved operator scope; no new cloud secret manager is prescribed. Verification: INF-002/INF-004 and startup config fixtures after the mechanism is selected.
