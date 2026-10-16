-- ARAI metadata schema, version 13 (decision AM-70, step 2 of docs/design/authentication-and-roles.md): a Keycloak sign-in
-- in flight. Between the redirect to Keycloak and its answer the server keeps the attempt's state (stored as a hash), its
-- nonce and its PKCE verifier; the answer is accepted once, within ten minutes, and the row is removed.

CREATE TABLE oidc_logins (
    state_hash     TEXT PRIMARY KEY,
    nonce          TEXT NOT NULL,
    code_verifier  TEXT NOT NULL,
    return_to      TEXT NOT NULL DEFAULT '/',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
