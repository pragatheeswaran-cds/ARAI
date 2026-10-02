-- ARAI metadata schema, version 1 (final-spec component 14). Timestamps are UTC; the UI shows IST.
-- Artifact keys are relative to the configured artifact root: no machine path is ever stored.

CREATE TABLE datasets (
    id              TEXT PRIMARY KEY,
    world_id        TEXT NOT NULL UNIQUE,
    manifest_hash   TEXT NOT NULL,
    schema_version  TEXT NOT NULL,
    cutoff          TIMESTAMPTZ NOT NULL,
    history_start   DATE NOT NULL,
    purpose         TEXT NOT NULL,
    customer_count  INTEGER NOT NULL,
    artifact_key    TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE models (
    id            TEXT PRIMARY KEY,              -- the bundle's content hash
    kind          TEXT NOT NULL CHECK (kind IN ('supervised', 'unsupervised', 'baseline_fallback')),
    metadata_key  TEXT NOT NULL,
    validity      TEXT NOT NULL CHECK (validity IN ('valid', 'rejected')),
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE active_model (
    id               INTEGER PRIMARY KEY CHECK (id = 1),      -- singleton
    version          INTEGER NOT NULL,
    model_id         TEXT REFERENCES models (id),             -- null: baseline fallback
    baseline_id      TEXT NOT NULL REFERENCES models (id),
    selection_status TEXT NOT NULL CHECK (selection_status IN ('not_completed', 'selected', 'no_selected_model')),
    reason           TEXT,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE runs (
    id                  TEXT PRIMARY KEY,
    dataset_id          TEXT NOT NULL REFERENCES datasets (id),
    model_id            TEXT NOT NULL REFERENCES models (id),  -- bound at submission, never changed
    status              TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'interrupted')),
    stage               TEXT NOT NULL,
    progress            DOUBLE PRECISION NOT NULL DEFAULT 0,
    retry_of            TEXT REFERENCES runs (id),
    claimed_by          TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    output_key          TEXT,
    error_code          TEXT,
    error_message       TEXT,
    error_request_id    TEXT,
    eligible_count      INTEGER,
    excluded_count      INTEGER,
    selected_count      INTEGER,
    model_only_count    INTEGER,
    baseline_only_count INTEGER
);
CREATE INDEX runs_queue ON runs (status, created_at);
CREATE INDEX runs_dataset ON runs (dataset_id, created_at DESC);

CREATE TABLE experiments (
    id            TEXT PRIMARY KEY,
    config_hash   TEXT NOT NULL,
    report_key    TEXT NOT NULL,
    selection_key TEXT,
    test_key      TEXT,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Notes are append only. There is no update or delete path anywhere in the application.
CREATE TABLE reviews (
    id            TEXT PRIMARY KEY,
    world_id      TEXT NOT NULL,
    customer_id   TEXT NOT NULL,
    run_id        TEXT NOT NULL REFERENCES runs (id),         -- origin run
    model_id      TEXT NOT NULL REFERENCES models (id),       -- origin model
    reviewer_name TEXT NOT NULL,
    disposition   TEXT NOT NULL CHECK (disposition IN ('needs_investigation', 'likely_legitimate', 'unresolved')),
    note          TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX reviews_customer ON reviews (world_id, customer_id, created_at, id);

CREATE TABLE idempotency (
    scope        TEXT NOT NULL,
    key          TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_ref TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, key)
);
