"""Keycloak single sign-on over OpenID Connect (decision AM-70, step 2 of docs/design/authentication-and-roles.md).

The server does the sign-in: it sends the browser to Keycloak with the authorization code flow and PKCE, exchanges the
code for tokens over the back channel (client id and secret), and checks the ID token - a JWT signed by the realm - with
the realm's published keys (JWKS): signature (RS256, PS256 or ES256 only; never `none`, never a shared secret), issuer,
audience (this client), expiry with 60 seconds of leeway, and the nonce of this very attempt. The browser never receives a
token; it gets ARAI's own session cookie (auth.py).

Scripts may instead send `Authorization: Bearer <access token>` from the same realm. The server checks that JWT the same
way, with the API audience (`arai-api`, added by a Keycloak audience mapper) instead of the client id.

Roles come from a claim of the token (`groups` by default, filled by a Keycloak group membership mapper) through
`oidc_role_map`; a leading "/" (Keycloak's full group path) is ignored. The realm's metadata and keys are fetched lazily
and cached; an unknown key id triggers one refetch at most every minute, so a key rotated in Keycloak is picked up
without a restart.
"""
from __future__ import annotations

import base64
import hashlib
import time
from urllib.parse import urlencode

import httpx
import jwt

ALGORITHMS = ("RS256", "PS256", "ES256")
LEEWAY_SECONDS = 60
DISCOVERY_SECONDS = 3600
JWKS_REFETCH_SECONDS = 60


class OidcError(Exception):
    """A sign-in or token that cannot be accepted. `code` is safe to show; `detail` stays in the log."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


class Oidc:
    def __init__(self, config, http: httpx.Client | None = None):
        self.config = config
        self.http = http or httpx.Client(timeout=10)
        self._discovery: tuple | None = None                  # (fetched_at, document)
        self._keys: dict = {}
        self._keys_fetched = 0.0

    # ------------------------------------------------------------------ the realm's metadata and keys
    def discovery(self) -> dict:
        if self._discovery and time.monotonic() - self._discovery[0] < DISCOVERY_SECONDS:
            return self._discovery[1]
        url = self.config.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration"
        try:
            response = self.http.get(url)
            response.raise_for_status()
            document = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise OidcError("single_sign_on_unavailable", f"discovery at {url} failed: {error}") from None
        if document.get("issuer", "").rstrip("/") != self.config.oidc_issuer.rstrip("/"):
            raise OidcError("single_sign_on_unavailable", f"discovery names issuer {document.get('issuer')!r}, not the configured one")
        self._discovery = (time.monotonic(), document)
        return document

    def _key(self, kid: str | None):
        if kid not in self._keys and time.monotonic() - self._keys_fetched >= JWKS_REFETCH_SECONDS:
            try:
                response = self.http.get(self.discovery()["jwks_uri"])
                response.raise_for_status()
                keys = response.json()["keys"]
            except (httpx.HTTPError, ValueError, KeyError) as error:
                raise OidcError("single_sign_on_unavailable", f"the realm's keys could not be read: {error}") from None
            self._keys = {k.get("kid"): jwt.PyJWK(k) for k in keys if k.get("use", "sig") == "sig" and k.get("alg", "RS256") in ALGORITHMS}
            self._keys_fetched = time.monotonic()
        if kid not in self._keys:
            raise OidcError("invalid_token", f"no published key with id {kid!r}")
        return self._keys[kid]

    def verify(self, token: str, audience: str, nonce: str | None = None) -> dict:
        """The claims of a JWT from the realm, after every check; OidcError otherwise."""
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as error:
            raise OidcError("invalid_token", f"not a JWT: {error}") from None
        if header.get("alg") not in ALGORITHMS:
            raise OidcError("invalid_token", f"algorithm {header.get('alg')!r} is not accepted")
        key = self._key(header.get("kid"))
        try:
            claims = jwt.decode(token, key.key, algorithms=[header["alg"]], audience=audience, issuer=self.discovery()["issuer"],
                                leeway=LEEWAY_SECONDS, options={"require": ["exp", "iat", "iss", "sub", "aud"]})
        except jwt.PyJWTError as error:
            raise OidcError("invalid_token", str(error)) from None
        if nonce is not None and claims.get("nonce") != nonce:
            raise OidcError("invalid_token", "the nonce does not match this sign-in")
        return claims

    # ------------------------------------------------------------------ the code flow
    def authorization_url(self, state: str, nonce: str, verifier: str) -> str:
        query = {"response_type": "code", "client_id": self.config.oidc_client_id, "redirect_uri": self.config.oidc_redirect_uri,
                 "scope": self.config.oidc_scopes, "state": state, "nonce": nonce,
                 "code_challenge": pkce_challenge(verifier), "code_challenge_method": "S256"}
        return self.discovery()["authorization_endpoint"] + "?" + urlencode(query)

    def exchange(self, code: str, verifier: str) -> dict:
        """The token response for an authorization code, over the back channel with the client's secret."""
        try:
            response = self.http.post(self.discovery()["token_endpoint"], data={
                "grant_type": "authorization_code", "code": code, "redirect_uri": self.config.oidc_redirect_uri,
                "client_id": self.config.oidc_client_id, "client_secret": self.config.oidc_client_secret, "code_verifier": verifier})
        except httpx.HTTPError as error:
            raise OidcError("single_sign_on_unavailable", f"token endpoint unreachable: {error}") from None
        if response.status_code != 200:
            raise OidcError("sign_in_failed", f"token endpoint answered {response.status_code}: {response.text[:200]}")
        try:
            return response.json()
        except ValueError:
            raise OidcError("sign_in_failed", "the token endpoint did not answer JSON") from None

    def logout_url(self) -> str | None:
        """Keycloak's end-session address, so signing out of ARAI can also end the Keycloak session; None if it has none."""
        try:
            endpoint = self.discovery().get("end_session_endpoint")
        except OidcError:
            return None
        if not endpoint:
            return None
        home = self.config.oidc_redirect_uri.split("/api/")[0] + "/"
        return endpoint + "?" + urlencode({"client_id": self.config.oidc_client_id, "post_logout_redirect_uri": home})

    # ------------------------------------------------------------------ roles
    def roles(self, claims: dict) -> list:
        groups = claims.get(self.config.oidc_role_claim) or []
        if isinstance(groups, str):
            groups = [groups]
        names = {str(g).lstrip("/") for g in groups}
        roles = sorted({role for group, role in self.config.oidc_role_map if group in names})
        email = str(claims.get("email") or "").casefold()
        if email and email in self.config.bootstrap_admins and "admin" not in roles:
            roles.append("admin")
        return roles


def display_name(claims: dict) -> str:
    return str(claims.get("name") or claims.get("preferred_username") or claims.get("email") or claims["sub"])

