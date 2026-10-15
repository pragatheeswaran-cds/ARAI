-- ARAI metadata schema, version 8: what the SKU intelligence screen shows beside each style (frontend data plan WP4).
-- Sums and medians over the same mature lines and requests the style states were built from; no state changes.
-- Results are written once: rows of earlier runs keep the new columns null and have no reason rows.

ALTER TABLE run_styles
    ADD COLUMN name                    TEXT,              -- "{brand} {category}", with the style id when that pair is not unique in the run
    ADD COLUMN median_return_day       DOUBLE PRECISION,  -- median day after delivery of the style's requests
    ADD COLUMN share_in_last_five_days DOUBLE PRECISION,  -- share of timed requests made in the last five days of the window
    ADD COLUMN flagged_returners       INTEGER,           -- returners selected for review in this run (denominator: unique_returners)
    ADD COLUMN ring_returners          INTEGER,           -- returners whose community is a ring
    ADD COLUMN median_returner_score   DOUBLE PRECISION;  -- median risk score of the eligible returners (read against Run.median_score)

ALTER TABLE run_customer_styles
    ADD COLUMN return_lines     INTEGER,                  -- the customer's request lines on the style
    ADD COLUMN purchased_lines  INTEGER,                  -- the customer's mature sale lines on the style
    ADD COLUMN last_reason_code TEXT;                     -- reason code of the customer's latest request on the style

CREATE TABLE run_style_reasons (
    run_id       TEXT NOT NULL REFERENCES runs (id),
    style_id     TEXT NOT NULL,
    reason_code  TEXT NOT NULL,
    reason_group TEXT NOT NULL,
    lines        INTEGER NOT NULL,
    units        INTEGER NOT NULL,
    PRIMARY KEY (run_id, style_id, reason_code)
);
