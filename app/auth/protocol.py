"""Pure OIDC/PKCE utilities; do not place tokens or credentials in redirects."""

import base64
import hashlib
import secrets
from urllib.parse import urlencode


def make_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def new_nonce() -> str:
    return secrets.token_urlsafe(24)


def build_authorization_url(issuer: str, client_id: str, redirect_uri: str,
                            state: str, nonce: str, challenge: str) -> str:
    params = {
        "response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri,
        "scope": "openid profile email", "state": state, "nonce": nonce,
        "code_challenge": challenge, "code_challenge_method": "S256",
    }
    return f"{issuer.rstrip('/')}/protocol/openid-connect/auth?{urlencode(params)}"


def session_redis_key(session_id: str) -> str:
    """Do not store raw browser session identifiers as Redis keys."""
    return "bff:session:" + hashlib.sha256(session_id.encode("ascii")).hexdigest()


def oauth_cookie_secure(base_url: str) -> bool:
    return base_url.lower().startswith("https://")


def validate_safe_return_path(value: str | None) -> str:
    """Avoid open redirects; only route to the local workspace after sign-in."""
    return "/app"


def valid_browser_csrf(provided: str, expected: str | None, origin: str | None,
                       fetch_site: str | None, app_origin: str) -> bool:
    """Double requirement: synchronizer token plus browser-origin checks when available."""
    import hmac
    if not expected or not provided:
        return False
    if origin is not None and origin.rstrip("/") != app_origin.rstrip("/"):
        return False
    if fetch_site == "cross-site":
        return False
    return hmac.compare_digest(provided, expected)
