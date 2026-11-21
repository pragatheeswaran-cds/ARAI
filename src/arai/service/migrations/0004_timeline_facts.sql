-- ARAI metadata schema, version 4: the facts behind every timeline sentence become columns, so the UI reads values
-- and never parses text. All nullable: a column that does not apply to an event kind is null, and so is every column
-- of a run scored before this version (results are written once and never updated).

ALTER TABLE run_timeline
    ADD COLUMN order_id      TEXT,          -- the sale order the line belongs to (purchase and return alike)
    ADD COLUMN order_line_no INTEGER,
    ADD COLUMN quantity      INTEGER,       -- units ordered, or units requested for return
    ADD COLUMN size          TEXT,
    ADD COLUMN reason_code   TEXT,          -- return events only; from the codebook, never the customer's free text
    ADD COLUMN reason_group  TEXT,          -- transaction_claim, item_complaint, fit or discretionary
    ADD COLUMN day_in_window INTEGER,       -- return events only: days after delivery at which the request was made
    ADD COLUMN window_days   INTEGER,       -- the line's return window
    ADD COLUMN line_status   TEXT,          -- the sale line's status for a purchase, the return line's for a request
    ADD COLUMN item_received BOOLEAN,       -- return events only; null when the reason needs no item back
    ADD COLUMN linked_claim  BOOLEAN;       -- return events only: a linked account claimed on the same style within 7 days
