-- ARAI metadata schema, version 5: groups of linked accounts. A community is a connected component of a run's
-- supported edges (split by Louvain only when large), with the observable kind the stated rule gives it. Results are
-- written once: a run scored before this version has no community rows and a null community_id on every customer.

CREATE TABLE run_communities (
    run_id                    TEXT NOT NULL REFERENCES runs (id),
    community_id              TEXT NOT NULL,                 -- world prefix and a hash of the sorted member ids
    kind                      TEXT NOT NULL CHECK (kind IN ('ring', 'household')),
    method                    TEXT NOT NULL CHECK (method IN ('components', 'louvain')),
    size                      INTEGER NOT NULL,
    selected_count            INTEGER NOT NULL,              -- members selected for review in this run
    requested_units           INTEGER NOT NULL,              -- sum of the members' mature_requested_units
    purchased_units           INTEGER NOT NULL,              -- sum of the members' mature_purchased_units
    coordinated_claim_matches INTEGER NOT NULL,              -- over the community's edges
    edges                     JSONB NOT NULL,                -- [{a, b, types[], coordinated_claim_matches}] between members
    PRIMARY KEY (run_id, community_id)
);

ALTER TABLE run_customers ADD COLUMN community_id TEXT;      -- null when the customer has no supported edge
CREATE INDEX run_customers_community ON run_customers (run_id, community_id);
