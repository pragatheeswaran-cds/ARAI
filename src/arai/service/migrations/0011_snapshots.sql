-- ARAI metadata schema, version 11 (decision AM-68): a world is one population of customers and a dataset is one
-- snapshot of it at a cutoff. A customer keeps its identifier in every snapshot of its world, so its notes, decisions
-- and scores follow it from one snapshot to the next; the review workflow (open, approval, decision) runs per snapshot.

ALTER TABLE datasets DROP CONSTRAINT IF EXISTS datasets_world_id_key;
ALTER TABLE datasets ADD CONSTRAINT datasets_world_cutoff UNIQUE (world_id, cutoff);

ALTER TABLE reviews ADD COLUMN dataset_id TEXT REFERENCES datasets (id);   -- the snapshot of the origin run
UPDATE reviews v SET dataset_id = r.dataset_id FROM runs r WHERE r.id = v.run_id;
ALTER TABLE reviews ALTER COLUMN dataset_id SET NOT NULL;
CREATE INDEX reviews_snapshot_workflow ON reviews (world_id, customer_id, dataset_id, kind, created_at, id);

ALTER TABLE experiments ADD COLUMN truth_cutoff TIMESTAMPTZ;   -- the snapshot the truth export describes, when known
