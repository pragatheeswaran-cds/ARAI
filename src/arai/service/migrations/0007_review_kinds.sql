-- ARAI metadata schema, version 7: every review carries a kind (frontend data plan WP6). The table stays append-only;
-- the workflow state of a customer is derived on read from the latest open, request_approval, approve or reject.
-- Rows written before this version are notes.

ALTER TABLE reviews ADD COLUMN kind TEXT NOT NULL DEFAULT 'note'
    CHECK (kind IN ('note', 'open', 'request_approval', 'approve', 'reject', 'feedback'));
CREATE INDEX reviews_workflow ON reviews (world_id, customer_id, kind, created_at, id);
