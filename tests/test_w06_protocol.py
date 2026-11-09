"""Pure W06 protocol checks; no running Keycloak or Redis claimed."""
import base64
import hashlib
from urllib.parse import parse_qs, urlsplit

from app.auth.protocol import (build_authorization_url, make_pkce,
                               session_redis_key, validate_safe_return_path,
                               oauth_cookie_secure, valid_browser_csrf)


def test_pkce_verifier_challenge_sha256_and_unpredictable():
    verifier, challenge = make_pkce()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected
    assert len(verifier) >= 43
    assert make_pkce()[0] != verifier


def test_authorization_request_is_code_pkce_nonce_state():
    url = build_authorization_url("http://localhost:8080/realms/acme", "acme-web",
                                  "http://localhost:8000/auth/callback", "state-123", "nonce-234", "pkce-345")
    parsed = urlsplit(url)
    p = parse_qs(parsed.query)
    assert parsed.path.endswith("/protocol/openid-connect/auth")
    assert p["response_type"] == ["code"]
    assert p["code_challenge_method"] == ["S256"]
    assert p["state"] == ["state-123"] and p["nonce"] == ["nonce-234"]
    assert p["redirect_uri"] == ["http://localhost:8000/auth/callback"]
    assert p["scope"] == ["openid profile email"]


def test_sessions_are_not_indexed_by_browser_cookie():
    sid = "s3cr3t-session-value"
    key = session_redis_key(sid)
    assert sid not in key
    assert session_redis_key(sid) == key
    assert session_redis_key("another-session") != key


def test_secure_cookie_follows_protocol():
    assert oauth_cookie_secure("https://example.org") is True
    assert oauth_cookie_secure("http://localhost:8000") is False


def test_login_does_not_accept_external_return_urls():
    assert validate_safe_return_path("https://attacker.invalid/") == "/app"
    assert validate_safe_return_path("//attacker.invalid/") == "/app"


def test_browser_csrf_requires_token_and_same_origin():
    good = dict(provided="t-123", expected="t-123", origin="http://localhost:8000",
                fetch_site="same-origin", app_origin="http://localhost:8000")
    assert valid_browser_csrf(**good)
    assert not valid_browser_csrf(**{**good, "provided": "invalid"})
    assert not valid_browser_csrf(**{**good, "origin": "https://evil.invalid"})
    assert not valid_browser_csrf(**{**good, "fetch_site": "cross-site"})
    assert not valid_browser_csrf(**{**good, "expected": None})
