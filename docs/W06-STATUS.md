# W06 — Browser OIDC BFF and identity-aware workspace

**Scope:** FastAPI login/callback/logout, Redis-backed browser sessions, signed Keycloak token validation, CSRF, role-specific view, owner-scoped conversation API.

## Implemented

- `GET /login`: random OIDC state/nonce, PKCE S256, browser-bound correlation cookie, Redis 10-minute one-time state.
- `GET /auth/callback`: consumes state once, validates binding cookie, exchanges code server-side, verifies access/ID token JWT issuer, audience, signature, subject and nonce, starts an opaque Redis session.
- Browser receives only a random HttpOnly SameSite=Lax session cookie. Secure flag is required whenever `APP_BASE_URL` uses HTTPS; intentionally off for the localhost HTTP demo.
- `POST /logout`: CSRF-protected local session deletion plus Keycloak RP-initiated logout redirect.
- Redis session TTL bounded to 30 minutes; access-token refresh is handled server-side with a simple lock. Role permissions are recalculated from a verified current token on every request.
- Existing bearer API remains for smoke tooling; invalid bearer headers cannot fall back to browser sessions.
- `GET /app`: role-specific name, capability labels, identity-aware styling. No fabricated LLM response.
- `GET/POST /api/conversations`, `GET /api/conversations/{id}`: PostgreSQL durable records with per-user owner checks. Messages endpoint returns explicit 501 until W08.
- `POST /api/approvals` additionally requires CSRF for session-cookie clients; admin permission checks preserved.
- Alembic `0002_conversations` migration and offline test contracts.

## Manual Docker verification needed

1. `docker compose up --build` and `docker compose exec web python -m app.smoke` (foundation).
2. `docker compose exec web python -m app.smoke_w06` (owner-scoped conversation API and cross-user isolation).
3. In a real browser, visit `http://localhost:8000`, select **Sign in with Keycloak**, authenticate as each local demo user, verify role/capability changes.
4. In devtools, confirm the browser holds opaque `acme_session` and transient `acme_oidc_state` cookies but no OAuth tokens in Local Storage or JavaScript-readable cookies.
5. Verify `/api/me` for all three accounts; browser session and bearer token cases.
6. Reject callback with wrong/missing `state` and wrong/missing binding cookie; confirm state is one-use.
7. Block `POST /api/conversations` without `X-CSRF-Token` and with mismatched `Origin`. Deny cross-user conversation ID reads (404).
8. Sign out; verify session invalidated and Keycloak login is requested on next visit. Confirm tokens never enter logs.
9. Verify browser login after container restart and Keycloak import. If the `kcdata` volume already contains the old realm, Keycloak may **not** reimport updated attributes. For a disposable demo instance only, reset the realm through Keycloak admin or remove old test volumes after backing up anything needed.

## Security and completion limitations

- The existing public Keycloak demo client retains **Direct Access Grant** for automated W01–W05 smoke testing. Keycloak recommends avoiding this flow; disable it and replace those smoke tests with a dedicated integration client before real deployment.
- The local demo sends a web+MCP dual-audience token. Production should implement resource-specific exchange/delegation and TLS, CSRF origin controls and encrypted session/token storage with operational key rotation.
- Role changes become effective when a fresh access token is issued; privileged writes additionally validate at MCP. Immediate revocation/session admin events are not implemented.
- The refresh lock uses an atomic Redis compare/delete but still requires concurrency testing; browser auth requires runtime integration testing before claiming security correctness.
- No live Docker/Keycloak/Redis/PostgreSQL/MCP or browser integration was possible in this authoring environment. No signed G0/G1/G2 passes are claimed.
- W07 local model tool-calling, W08 graph, W09 Skill, W11 chat, W12 traces, W13 evaluation remain outstanding.
