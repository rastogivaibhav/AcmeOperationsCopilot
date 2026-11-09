# Verification notes — W01–W05 source drop

**Executed locally:**
- Python `compileall` on application, MCP, DB and test sources — passed.
- `pytest -q tests` — **20 passed** (recorded in `UNIT_TEST_RESULTS.txt`).
- JSON syntax (`acme-realm.json`) and TOML syntax (`pyproject.toml`) — parsed.
- Compose YAML — parsed, expected 8 services and dependency/healthcheck declarations present.

**Not executed:**
- `docker compose config` or `docker compose up --build` (Docker executable/daemon unavailable).
- Live PostgreSQL migration/seed, Keycloak realm import, OIDC/token issuer checks, or MCP Streamable HTTP calls (no containers running).
- Package installation/lockfile generation (package-index resolution failed because network DNS is unavailable).
- Ollama model provisioning, LangGraph execution, Redis use, or EY complete end-to-end evaluation (later work packages).

**Required manual checks on Docker-enabled host:**
1. `docker compose config` must show eight services with valid interpolated environment.
2. `docker compose up --build` must complete initial model download and realm/database boot.
3. `docker compose exec web python -m app.smoke` must print `LIVE_FOUNDATION_SMOKE_PASS`.
4. Verify a token with wrong audience, an expired token and an unsigned token are rejected at both web and MCP.
5. Verify Sales cannot read Northstar, or create a next action. Verify Admin cannot write without the separate approval receipt. Verify concurrent retries produce one action.
6. Lock exact dependencies and record tested Docker image digests.

**Interpretation:** successful static/unit tests prove that some local source-level contracts are consistent, not that the submitted application works end-to-end. No G0/G1/G2 release gate is marked PASSED.
