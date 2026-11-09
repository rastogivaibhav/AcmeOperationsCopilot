"""Keycloak RS256/JWKS verification. No passwords or credentials enter LLM prompts."""
import os
import jwt
from jwt import PyJWKClient

_JWKS_CLIENTS: dict[str, PyJWKClient] = {}


def verify_keycloak_jwt(token: str, audience: str) -> dict:
    jwks_url = os.environ.get(
        "KEYCLOAK_JWKS_URL", "http://keycloak:8080/realms/acme/protocol/openid-connect/certs"
    )
    issuer = os.environ.get("KEYCLOAK_ISSUER", "http://localhost:8080/realms/acme")
    if jwks_url not in _JWKS_CLIENTS:
        _JWKS_CLIENTS[jwks_url] = PyJWKClient(jwks_url, cache_keys=True, timeout=5)
    key = _JWKS_CLIENTS[jwks_url].get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        key.key,
        algorithms=["RS256"],
        audience=audience,
        issuer=issuer,
        options={"require": ["sub", "exp", "iat", "iss", "aud"]},
        leeway=10,
    )
