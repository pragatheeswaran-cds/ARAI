# Deployment specification

OPS-004. DRAFT. Preserve HLD ?10: one machine/process group, pandas/DuckDB processing, NetworkX, local Parquet-derived artifacts, FastAPI background tasks and Streamlit. SQLite versus JSONL/no-database persistence conflict is unresolved Q-011. Do not introduce containers, managed queues, cloud databases or multi-agent processing.

Future packaging must pin Python and dependency versions and expose one-command data/run/eval/ui/demo tasks described in LLD ?10. These commands are design intent; no Makefile, runtime config, application or dependency lock exists yet. The source generator mentions Python 3.11+ plus numpy/pandas/pyarrow, not a complete application environment.

Configuration is immutable per run; validate all required keys, weights, seeds, k>0, feature allow-list and artifact compatibility before work. Secrets load from a separately approved local mechanism (Q-015), not committed config. Startup readiness requires readable approved artifacts/config, writable audit storage and known recovery state; the optional model provider is not a readiness dependency. No new health endpoint is invented; health exposure is an API design decision Q-008/Q-014.

Offline mode serves cached memos and creates evidence-only new cases without network. Rehearse on two machines with network disabled. Job status must reflect failures truthfully, including restart/interruption; durable recovery protocol awaits Q-011.

Rollback proposal A-005: select a previously verified complete run bundle plus matching config/environment; retain existing audit history and record rollback event. Do not mix old model with new transforms or thresholds. Operator workflow, retention and recovery timing remain Q-011/Q-014/Q-015. Verification: E2E-003/INF-004.
