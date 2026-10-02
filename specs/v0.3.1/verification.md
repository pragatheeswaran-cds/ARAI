# Draft package verification

Date: 2026-09-25. Result: document checks passed. This is not package approval.

- Parsed both new YAML contracts with duplicate-key rejection.
- Confirmed seven operational tables, schema version 0.3.1, and five delivery states including awaiting_dispatch.
- Checked proposed joint-allocation coefficients against 4% claim, 3% temporary-use, and 0.5% overlap marginals.
- Checked normalized probabilities on illustrative normal and all-1 actionable multiplier mixes. These are algebra checks, not generated samples or measured prevalence.
- Confirmed all nine review findings have corresponding A-01 through A-09 entries.
- Confirmed all 5 original v0.3 files match their pre-edit full-file SHA-256 hashes in [source-hashes.json](source-hashes.json).
- Checked relative Markdown links in the new package and both updated entry-point notices.

New files: README.md, amendment.md, schema.yaml, generator-policy.yaml, source-hashes.json, verification.md under specs/v0.3.1.
Existing files edited: root README.md and specs/README.md, adding a draft/last-signed entry notice only.
Existing signed v0.3 files edited: none.

Not performed: generator implementation, dataset generation, statistical sampling checks, runtime tests, model fitting, API/UI implementation, cloud deployment, or independent validation of the v0.3 embedded signing hash. Full-file preservation hashes are not a new sign-off.

P-01, P-02, P-03 and technical amendments remain proposed. API/UI contract still awaits wireframes; private serialization and exact implementation settings must be fixed before generator acceptance.
