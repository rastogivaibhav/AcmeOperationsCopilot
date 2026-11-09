"""Local JWT cryptographic tests. Keycloak live issuer exchange tested by app.smoke."""
import time
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from acme_shared import security


@pytest.fixture
def signed(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class FakeJwks:
        def __init__(self, url, **kwargs):
            pass
        def get_signing_key_from_jwt(self, token):
            return SimpleNamespace(key=key.public_key())

    monkeypatch.setattr(security, "PyJWKClient", FakeJwks)
    monkeypatch.setenv("KEYCLOAK_JWKS_URL", "https://unit.test/jwks")
    monkeypatch.setenv("KEYCLOAK_ISSUER", "http://localhost:8080/realms/acme")
    security._JWKS_CLIENTS.clear()

    def sign(**changes):
        claims = {"sub": "user-1", "iss": "http://localhost:8080/realms/acme",
                  "aud": ["acme-web", "acme-mcp"], "iat": int(time.time()),
                  "exp": int(time.time()) + 3600, "realm_access": {"roles": ["sales_user"]}}
        claims.update(changes)
        return jwt.encode(claims, key, algorithm="RS256")
    return sign


def test_valid_keycloak_jwt(signed):
    claims = security.verify_keycloak_jwt(signed(), "acme-mcp")
    assert claims["sub"] == "user-1"


def test_wrong_audience_rejected(signed):
    with pytest.raises(jwt.InvalidAudienceError):
        security.verify_keycloak_jwt(signed(aud=["acme-web"]), "acme-mcp")


def test_issuer_rejected(signed):
    with pytest.raises(jwt.InvalidIssuerError):
        security.verify_keycloak_jwt(signed(iss="http://evil.invalid"), "acme-mcp")


def test_expired_token_rejected(signed):
    with pytest.raises(jwt.ExpiredSignatureError):
        security.verify_keycloak_jwt(signed(exp=int(time.time())-180), "acme-mcp")
