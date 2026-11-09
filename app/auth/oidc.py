"""Server-side OIDC BFF: PKCE, state/nonce, Redis sessions and CSRF.

Browser receives only opaque session/state cookies, never OAuth token material.
This is a localhost assessment prototype, not a production auth gateway.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlencode

import httpx2
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from redis.asyncio import Redis

from acme_shared.policies import Principal, effective_role, principal_from_claims
from acme_shared.security import verify_keycloak_jwt
from app.auth.protocol import (build_authorization_url, make_pkce, new_nonce,
                               oauth_cookie_secure, session_redis_key, valid_browser_csrf)

router = APIRouter()

CLIENT_ID = "acme-web"
SESSION_COOKIE = "acme_session"
STATE_COOKIE = "acme_oidc_state"
PENDING_TTL = 600
SESSION_MAX_SECONDS = 1800
COOKIE_SECURE = oauth_cookie_secure(os.getenv("APP_BASE_URL", "http://localhost:8000"))


def base_url() -> str:
    return os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")


def issuer() -> str:
    return os.getenv("KEYCLOAK_ISSUER", "http://localhost:8080/realms/acme").rstrip("/")


def token_endpoint() -> str:
    return os.getenv("KEYCLOAK_TOKEN_URL", "http://keycloak:8080/realms/acme/protocol/openid-connect/token")


def redis_client() -> Redis:
    return Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)


@dataclass(frozen=True)
class AuthContext:
    principal: Principal
    access_token: str
    session_id: str | None = None
    csrf_token: str | None = None
    via_cookie: bool = False


def safe_cookie(response: RedirectResponse, name: str, value: str, age: int):
    response.set_cookie(name, value, httponly=True, secure=COOKIE_SECURE,
                        samesite="lax", max_age=age, path="/")


def _session_record(tokens: dict, csrf_token: str, existing_sub: str | None = None) -> dict:
    access = tokens["access_token"]
    claims = verify_keycloak_jwt(access, audience=CLIENT_ID)
    principal = principal_from_claims(claims)
    if effective_role(principal) is None:
        raise ValueError("No unambiguous business role")
    if existing_sub is not None and existing_sub != principal.sub:
        raise ValueError("Refresh token subject changed")
    now = int(time.time())
    refresh_seconds = min(int(tokens.get("refresh_expires_in", 1800)), SESSION_MAX_SECONDS)
    if refresh_seconds <= 0:
        raise ValueError("Invalid refresh lifetime")
    return {
        "sub": principal.sub,
        "csrf": csrf_token,
        "access_token": access,
        "refresh_token": tokens.get("refresh_token"),
        "access_expiry": min(int(claims["exp"]), now + int(tokens.get("expires_in", 300))),
        "session_expiry": now + refresh_seconds,
    }


async def _exchange(form: dict[str, str]) -> dict:
    try:
        async with httpx2.AsyncClient(timeout=12) as client:
            response = await client.post(token_endpoint(), data=form)
        response.raise_for_status()
        tokens = response.json()
        if not isinstance(tokens, dict) or not tokens.get("access_token"):
            raise ValueError("Token endpoint returned no access token")
        return tokens
    except (httpx2.HTTPError, ValueError) as exc:
        raise HTTPException(502, "Identity provider token exchange failed") from exc


@router.get("/login")
async def login(request: Request):
    state, nonce = new_nonce(), new_nonce()
    verifier, challenge = make_pkce()
    browser_binding = secrets.token_urlsafe(32)
    pending = {"verifier": verifier, "nonce": nonce, "browser_binding": browser_binding}
    store = redis_client()
    try:
        await store.set("bff:oidc:" + state, json.dumps(pending), ex=PENDING_TTL, nx=True)
    finally:
        await store.aclose()
    callback = base_url() + "/auth/callback"
    url = build_authorization_url(issuer(), CLIENT_ID, callback, state, nonce, challenge)
    response = RedirectResponse(url, status_code=303)
    safe_cookie(response, STATE_COOKIE, browser_binding, PENDING_TTL)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/auth/callback")
async def callback(request: Request, code: str | None = None, state: str | None = None,
                   error: str | None = None):
    # One-time state prevents callback replay. Cookie ties initiation to same browser.
    if error or not code or len(code) > 2048 or not state or len(state) > 256:
        raise HTTPException(400, "Sign-in did not complete")
    browser_binding = request.cookies.get(STATE_COOKIE, "")
    if not browser_binding:
        raise HTTPException(400, "Sign-in browser state missing")
    store = redis_client()
    try:
        raw = await store.getdel("bff:oidc:" + state)
        if not raw:
            raise HTTPException(400, "Sign-in state expired or already consumed")
        pending = json.loads(raw)
        if not hmac.compare_digest(browser_binding, pending["browser_binding"]):
            raise HTTPException(400, "Sign-in browser mismatch")
        tokens = await _exchange({
            "grant_type": "authorization_code", "code": code,
            "client_id": CLIENT_ID, "redirect_uri": base_url() + "/auth/callback",
            "code_verifier": pending["verifier"],
        })
        if not tokens.get("id_token"):
            raise HTTPException(502, "Identity provider did not return an ID token")
        try:
            id_claims = verify_keycloak_jwt(tokens["id_token"], audience=CLIENT_ID)
            if not hmac.compare_digest(str(id_claims.get("nonce", "")), pending["nonce"]):
                raise ValueError("OIDC nonce mismatch")
            csrf = secrets.token_urlsafe(32)
            session = _session_record(tokens, csrf)
            if id_claims.get("sub") != session["sub"]:
                raise ValueError("ID/access-token subject mismatch")
        except Exception as exc:
            raise HTTPException(401, "OIDC response validation failed") from exc
        session_id = secrets.token_urlsafe(32)
        ttl = max(1, session["session_expiry"] - int(time.time()))
        await store.set(session_redis_key(session_id), json.dumps(session), ex=ttl)
        response = RedirectResponse("/app", status_code=303)
        safe_cookie(response, SESSION_COOKIE, session_id, ttl)
        response.delete_cookie(STATE_COOKIE, path="/")
        response.headers["Cache-Control"] = "no-store"
        return response
    finally:
        await store.aclose()


async def _refresh_if_needed(store: Redis, sid: str, record: dict) -> dict:
    now = int(time.time())
    if record.get("session_expiry", 0) <= now:
        raise HTTPException(401, "Session expired; sign in again")
    if record.get("access_expiry", 0) > now + 30:
        return record
    # A brief lock avoids concurrent refresh attempts invalidating a rotating refresh token.
    lock_key = session_redis_key(sid) + ":refresh_lock"
    lock_id = secrets.token_urlsafe(12)
    acquired = await store.set(lock_key, lock_id, ex=8, nx=True)
    if not acquired:
        for _ in range(12):
            await asyncio.sleep(0.10)
            latest = await store.get(session_redis_key(sid))
            if latest:
                record = json.loads(latest)
                if record.get("access_expiry", 0) > int(time.time()) + 30:
                    return record
        raise HTTPException(503, "Concurrent session refresh; retry")
    try:
        latest = await store.get(session_redis_key(sid))
        if latest:
            record = json.loads(latest)
            if record.get("access_expiry", 0) > int(time.time()) + 30:
                return record
        if not record.get("refresh_token"):
            raise HTTPException(401, "Sign-in required")
        tokens = await _exchange({"grant_type": "refresh_token", "refresh_token": record["refresh_token"],
                                  "client_id": CLIENT_ID})
        refreshed = _session_record(tokens, record["csrf"], existing_sub=record["sub"])
        # Do not extend beyond the original bounded BFF session lifetime.
        refreshed["session_expiry"] = min(refreshed["session_expiry"], record["session_expiry"])
        ttl = refreshed["session_expiry"] - int(time.time())
        if ttl < 1:
            raise HTTPException(401, "Session expired; sign in again")
        await store.set(session_redis_key(sid), json.dumps(refreshed), ex=ttl)
        return refreshed
    finally:
        # Atomic compare-and-delete so an expired lock cannot release a successor's lock.
        await store.eval(
            "if redis.call('GET', KEYS[1]) == ARGV[1] then "
            "return redis.call('DEL', KEYS[1]) else return 0 end",
            1, lock_key, lock_id,
        )


async def authenticated(request: Request) -> AuthContext:
    """Accept bearer API clients for existing smoke tests or browser BFF cookies.

    If Authorization is present, never fall back to cookies on invalid credentials.
    """
    authorization = request.headers.get("authorization")
    if authorization is not None:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "Bearer authentication required")
        try:
            principal = principal_from_claims(verify_keycloak_jwt(token, audience=CLIENT_ID))
            if effective_role(principal) is None:
                raise ValueError("Missing or ambiguous business role")
        except Exception as exc:
            raise HTTPException(401, "Invalid identity token") from exc
        return AuthContext(principal=principal, access_token=token)

    sid = request.cookies.get(SESSION_COOKIE)
    if not sid or len(sid) > 200:
        raise HTTPException(401, "Sign in required")
    store = redis_client()
    try:
        raw = await store.get(session_redis_key(sid))
        if not raw:
            raise HTTPException(401, "Session expired; sign in again")
        record = json.loads(raw)
        record = await _refresh_if_needed(store, sid, record)
        principal = principal_from_claims(verify_keycloak_jwt(record["access_token"], audience=CLIENT_ID))
        if principal.sub != record["sub"] or effective_role(principal) is None:
            raise HTTPException(401, "Session identity invalid")
        return AuthContext(principal=principal, access_token=record["access_token"],
                           session_id=sid, csrf_token=record["csrf"], via_cookie=True)
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(401, "Invalid session") from exc
    finally:
        await store.aclose()


def require_csrf(request: Request, auth: AuthContext) -> None:
    """Browser requests require synchronizer token; bearer API remains header-authenticated."""
    if not auth.via_cookie:
        return
    if not valid_browser_csrf(
        provided=request.headers.get("x-csrf-token", ""), expected=auth.csrf_token,
        origin=request.headers.get("origin"),
        fetch_site=request.headers.get("sec-fetch-site"), app_origin=base_url(),
    ):
        raise HTTPException(403, "Invalid CSRF token or request origin")


@router.post("/logout")
async def logout(request: Request, auth: Annotated[AuthContext, Depends(authenticated)]):
    require_csrf(request, auth)
    if auth.session_id:
        store = redis_client()
        try:
            await store.delete(session_redis_key(auth.session_id))
        finally:
            await store.aclose()
    # RP-initiated logout: Keycloak ends SSO session as well as local session.
    url = issuer() + "/protocol/openid-connect/logout?" + urlencode({
        "client_id": CLIENT_ID, "post_logout_redirect_uri": base_url() + "/",
    })
    # AJAX uses a JSON response so the browser can perform Keycloak front-channel logout.
    if request.headers.get("accept", "").startswith("application/json"):
        response = JSONResponse({"logout_url": url})
    else:
        response = RedirectResponse(url, status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.headers["Cache-Control"] = "no-store"
    return response
