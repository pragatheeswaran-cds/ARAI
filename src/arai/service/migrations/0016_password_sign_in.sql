-- ARAI metadata schema, version 16 (decision AM-81): accounts with a password, kept by ARAI (AUTH_MODE=password), for a
-- deployment without Keycloak where each person signs in as themselves. The account is a row of users with issuer
-- 'local' and its user name (compared without regard to case) as subject; its roles are rows of user_roles with source
-- 'local', edited by an admin. Only a salted scrypt hash of the password is stored, never the password.

CREATE TABLE password_credentials (
    user_id        TEXT PRIMARY KEY REFERENCES users (id),
    password_hash  TEXT NOT NULL,                       -- scrypt$<n>$<r>$<p>$<salt, base64>$<key, base64>
    must_change    BOOLEAN NOT NULL DEFAULT false,      -- set by an admin or at creation; until the person chooses their own, nothing else is served
    changed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Wrong passwords are counted by the user name that was typed, whether or not an account of that name exists, so that
-- a lock says nothing about which names are accounts. The name is kept as a hash (people type passwords into the wrong
-- field). Rows untouched for a day are removed at the next sign-in.
CREATE TABLE sign_in_throttle (
    subject_hash     TEXT PRIMARY KEY,                    -- SHA-256 of 'sign-in:' and the name, casefolded
    failed_attempts  INTEGER NOT NULL DEFAULT 0,          -- wrong passwords since the last success or lock
    locked_until     TIMESTAMPTZ,                         -- sign-in under this name refused until then, whatever the password
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
