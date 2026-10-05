-- ARAI metadata schema, version 2 (decision AM-39): everything the API serves is read from PostgreSQL.
-- Run results, the published experiment report and the synthetic truth export move from files into tables.
-- A run's rows are written in the transaction that marks it succeeded and are never updated afterwards.

ALTER TABLE runs ADD COLUMN summary JSONB;                    -- what scoring recorded about the run (budget, warnings, graph size)
ALTER TABLE experiments ADD COLUMN report JSONB;              -- the published report, in the API's Experiment shape
ALTER TABLE experiments ADD COLUMN truth_world_id TEXT;       -- the demonstration world of the truth export, if one was published

CREATE TABLE run_customers (
    run_id                 TEXT NOT NULL REFERENCES runs (id),
    queue_position         INTEGER NOT NULL,                  -- ranked customers by rank, then unranked by identifier
    customer_id            TEXT NOT NULL,
    eligibility_status     TEXT NOT NULL CHECK (eligibility_status IN ('eligible', 'insufficient_history')),
    raw_score              DOUBLE PRECISION,                  -- null for customers that are not ranked
    risk_score             DOUBLE PRECISION,
    rank                   INTEGER,
    baseline_rank          INTEGER,
    selected_for_review    BOOLEAN NOT NULL,
    baseline_selected      BOOLEAN NOT NULL,
    mature_sale_lines      INTEGER NOT NULL,
    mature_purchased_units INTEGER NOT NULL,
    mature_requested_units INTEGER NOT NULL,
    all_requested_units    INTEGER NOT NULL,
    evidence_tags          TEXT[] NOT NULL,
    wardrobing_status      TEXT NOT NULL,
    indicator_score        INTEGER,
    measures               JSONB NOT NULL,                    -- every other measured value: model features and evidence
    PRIMARY KEY (run_id, customer_id),
    UNIQUE (run_id, queue_position)
);

CREATE TABLE run_styles (
    run_id             TEXT NOT NULL REFERENCES runs (id),
    style_id           TEXT NOT NULL,
    category           TEXT NOT NULL,
    state              TEXT NOT NULL,
    mature_sale_lines  INTEGER NOT NULL,
    purchased_units    INTEGER NOT NULL,
    requested_units    INTEGER NOT NULL,
    unique_returners   INTEGER NOT NULL,
    quality_units      INTEGER NOT NULL,
    claim_units        INTEGER NOT NULL,
    claim_lines        INTEGER NOT NULL,
    linked_claim_lines INTEGER NOT NULL,
    linked_claimers    INTEGER NOT NULL,
    raw_return_rate    DOUBLE PRECISION,
    shrunk_return_rate DOUBLE PRECISION,
    damage_share       DOUBLE PRECISION,
    claim_share        DOUBLE PRECISION,
    linked_claim_share DOUBLE PRECISION,
    quality_signal     BOOLEAN NOT NULL,
    targeting_signal   BOOLEAN NOT NULL,
    PRIMARY KEY (run_id, style_id)
);

CREATE TABLE run_skus (
    run_id            TEXT NOT NULL REFERENCES runs (id),
    sku               TEXT NOT NULL,
    style_id          TEXT NOT NULL,
    size              TEXT,
    colour            TEXT,
    unit_price        DOUBLE PRECISION,
    mature_sale_lines INTEGER NOT NULL,
    purchased_units   INTEGER NOT NULL,
    requested_units   INTEGER NOT NULL,
    support_status    TEXT NOT NULL,
    PRIMARY KEY (run_id, sku)
);
CREATE INDEX run_skus_style ON run_skus (run_id, style_id);

CREATE TABLE run_neighbors (
    run_id                    TEXT NOT NULL REFERENCES runs (id),
    customer_id               TEXT NOT NULL,
    neighbor_id               TEXT NOT NULL,
    shared_types              TEXT[] NOT NULL,
    shared_value_count        INTEGER NOT NULL,
    supported                 BOOLEAN NOT NULL,
    max_value_fanout          INTEGER NOT NULL,
    coordinated_claim_matches INTEGER NOT NULL,
    PRIMARY KEY (run_id, customer_id, neighbor_id)
);

CREATE TABLE run_timeline (
    run_id      TEXT NOT NULL REFERENCES runs (id),
    seq         INTEGER NOT NULL,                             -- customer, then time, then source key
    customer_id TEXT NOT NULL,
    source_ref  TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    observed_at TEXT NOT NULL,                                -- as recorded: a date for a purchase, local time for a request
    description TEXT NOT NULL,
    amount_inr  DOUBLE PRECISION,
    style_id    TEXT,
    sku         TEXT,
    PRIMARY KEY (run_id, seq)
);
CREATE INDEX run_timeline_customer ON run_timeline (run_id, customer_id, seq);

CREATE TABLE run_customer_styles (
    run_id             TEXT NOT NULL REFERENCES runs (id),
    customer_id        TEXT NOT NULL,
    style_id           TEXT NOT NULL,
    requested_units    INTEGER NOT NULL,
    claim_lines        INTEGER NOT NULL,
    linked_claim_lines INTEGER NOT NULL,
    PRIMARY KEY (run_id, customer_id, style_id)
);
CREATE INDEX run_customer_styles_style ON run_customer_styles (run_id, style_id);

-- Synthetic truth of the demonstration world, exported offline for the evaluation page only.
CREATE TABLE experiment_truth (
    experiment_id TEXT NOT NULL REFERENCES experiments (id),
    position      INTEGER NOT NULL,                           -- abusers first, then by identifier
    customer_id   TEXT NOT NULL,
    y_abuse       INTEGER NOT NULL,
    action_types  TEXT[] NOT NULL,
    PRIMARY KEY (experiment_id, position)
);
