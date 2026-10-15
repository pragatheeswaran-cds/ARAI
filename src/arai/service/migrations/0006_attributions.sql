-- ARAI metadata schema, version 6: the score with each feature family at typical values, per eligible customer of a
-- run (frontend data plan WP2). Predict-side re-scoring of the frozen pipeline; no score, rank or selection changes.
-- Results are written once: a run scored before this version has no rows here.

CREATE TABLE run_attributions (
    run_id            TEXT NOT NULL REFERENCES runs (id),
    customer_id       TEXT NOT NULL,
    family            TEXT NOT NULL CHECK (family IN ('claims', 'timing', 'expected_vs_actual', 'composition', 'volume')),
    raw_score_without DOUBLE PRECISION NOT NULL,          -- the pipeline's raw score with the family at typical values
    score_without     DOUBLE PRECISION NOT NULL,          -- that raw score as a training reference percentile
    delta_points      DOUBLE PRECISION NOT NULL,          -- score_without minus the customer's risk_score
    in_queue_without  BOOLEAN NOT NULL,                   -- raw_score_without at or above the raw score at rank k
    PRIMARY KEY (run_id, customer_id, family)
);
