-- ARAI metadata schema, version 3: the scoring worker reports that it is alive, so the API can say when no
-- worker is running (the worker is a separate process in the reference runtime and the API cannot see it otherwise).

CREATE TABLE workers (
    worker_id  TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    seen_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
