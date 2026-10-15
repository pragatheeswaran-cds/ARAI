-- ARAI metadata schema, version 10: when each stage of a run began, and a cooperative cancel (frontend data plan WP8).
-- stage_log is appended by the worker at every stage change; cancel_requested is set by the API for a running run and
-- read by the worker at its next stage, where it stops and marks the run interrupted (error_code cancelled).

ALTER TABLE runs
    ADD COLUMN stage_log        JSONB NOT NULL DEFAULT '[]',    -- [{stage, at}] in order
    ADD COLUMN cancel_requested BOOLEAN NOT NULL DEFAULT false;
