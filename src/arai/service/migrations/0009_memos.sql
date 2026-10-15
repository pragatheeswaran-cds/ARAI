-- ARAI metadata schema, version 9: investigation memos (frontend data plan WP7). One row per selected customer of a
-- succeeded run, written after the run's results, each decided once: ok with the gated memo, or unavailable with the
-- reason. A memo is a draft for a reviewer; nothing about a score, a rank or a selection depends on it.

CREATE TABLE run_memos (
    run_id       TEXT NOT NULL REFERENCES runs (id),
    customer_id  TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('ok', 'unavailable')),
    attempts     INTEGER NOT NULL,
    reason       TEXT,                                           -- why it is unavailable: no_api_key, declined, gate: ..., api_error_...
    model        TEXT,
    generated_at TIMESTAMPTZ NOT NULL,
    memo         JSONB,                                          -- {summary, key_evidence[], alternative_explanations[], recommended_action}
    PRIMARY KEY (run_id, customer_id)
);
