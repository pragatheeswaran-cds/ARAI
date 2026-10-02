# Local artifact registry

OPS-002. DRAFT ? ASSUMPTION ? REQUIRES REVIEW (A-005). No hosted registry is specified by the architecture. The MVP registry is a local index of immutable compatible run bundles, using model-artifact-spec.yaml under 04-model as the registration contract.

Proposed statuses: draft ? verified ? frozen ? retired. A failed run is recorded as failed and never made selectable. Register only when artifacts, hashes, schema/feature/config compatibility and deterministic verification pass. Mark frozen only after required acceptance checks and explicit lead approval; Q-009 unresolved means no automatic promotion. Sealed evaluation never selects a different winner.

The unit is the entire run bundle, including transforms, graph, exclusions, thresholds and evidence, not just a forest file. New uploads fit new populations; choosing a registered forest does not authorize scoring unrelated single rows. Keep prior bundles for reproduction subject to retention Q-015. Storage mechanism and atomic pointer updates depend on Q-011. Verification: MODEL-004/INF-004.
