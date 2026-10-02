# UI requirements

DRAFT. Sources: HLD ??5/7/10; Architecture ??8.3/Appendix B; web-kickoff and web-judge-pitch architecture diagrams. Technology remains Streamlit consuming FastAPI. No application mockups or UI source exist. State and accessibility details are ASSUMPTION ? REQUIRES REVIEW (A-006), with Q-019 approval required.

UI-REQ-001: render five screens from screens.md with persistent selected run context. Label score as within-run risk percentile, never probability or confirmed fraud. Show wardrobing limitation inline wherever the band appears. Distinguish score tier from memo recommendation tier (POLICY-001).

UI-REQ-002: expose evidence, pass1/pass2/delta, linked-account graph and computed counterfactual for case review. Do not allow LLM text to replace numeric evidence, suppress flags, change tiers or issue account actions. Render untrusted prose as text; no executable HTML.

UI-REQ-003: every asynchronous view has loading, success, empty, failed and stale-run states. Disable repeat submit while awaiting acknowledgement; duplicate job handling remains Q-008. A failed fetch cannot be shown as an empty queue. Provider unavailability yields an explicit evidence-only message, not an error page that hides the case.

UI-REQ-004: input validation mirrors API syntax; all scoring/threshold/action rules stay server-side. The proposed raw-rate demo slider is illustrative, uses an approved range/step (TBD Q-019), and never alters the scored run or selects a model. Changing effective scoring configuration requires a new run, not local reranking.

UI-REQ-005: controls have labels, keyboard operation, visible focus, text accompanying colour, accessible error/status announcements and readable tabular alternatives to graph-only evidence. A formal accessibility conformance target is TBD Q-019; no compliance certification is claimed.

UI-REQ-006: show actor fields as local demo identifiers, not authenticated identities. Self-approval refusal remains visible and auditable. Approval/outcome controls cannot be implemented until Q-007/Q-008 define their complete lifecycle.
