-- ARAI metadata schema, version 12 (decision AM-69, docs/design/authentication-and-roles.md): who is signed in, what each
-- person may do, and which person wrote each review. Identity comes from a verified sign-in (the development login now,
-- Keycloak single sign-on next), never from a name the browser sends.

CREATE TABLE users (
    id            TEXT PRIMARY KEY,
    issuer        TEXT NOT NULL,                     -- 'dev' for the development login, the Keycloak realm URL for single sign-on
    subject       TEXT NOT NULL,                     -- the stable id the issuer gives the person
    email         TEXT,
    display_name  TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ,
    UNIQUE (issuer, subject)
);

-- roles are refreshed from the identity source at every sign-in (Keycloak groups, or the development user list)
CREATE TABLE user_roles (
    user_id TEXT NOT NULL REFERENCES users (id),
    role    TEXT NOT NULL CHECK (role IN ('viewer', 'reviewer', 'approver', 'admin')),
    source  TEXT NOT NULL,
    PRIMARY KEY (user_id, role)
);

-- a session is an opaque cookie value; only its SHA-256 is stored, as is the CSRF token's
CREATE TABLE sessions (
    id_hash       TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users (id),
    csrf_hash     TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL,              -- created_at + the maximum session age
    ended_at      TIMESTAMPTZ,
    ended_reason  TEXT
);
CREATE INDEX sessions_user ON sessions (user_id) WHERE ended_at IS NULL;

-- append only, like reviews: sign-in, sign-out, expiry, refused requests, exports
CREATE TABLE auth_events (
    id          BIGSERIAL PRIMARY KEY,
    at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind        TEXT NOT NULL,
    user_id     TEXT REFERENCES users (id),
    request_id  TEXT,
    detail      JSONB NOT NULL DEFAULT '{}'
);

ALTER TABLE reviews ADD COLUMN author_user_id TEXT REFERENCES users (id);   -- null for reviews written before sign-in existed
CREATE INDEX reviews_author ON reviews (author_user_id);
