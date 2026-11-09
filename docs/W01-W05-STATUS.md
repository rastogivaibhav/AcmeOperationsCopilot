# W01–W05 Work Status (2026-11-09)

| ID | Implemented | Checks executed | Still needed before DONE |
|---|---|---|---|
| W01 | pyproject, source structure, Dockerfiles, tests | Python compile; pytest; JSON/TOML parse | Generate dependency lock with online package registry, CI lint |
| W02 | 8 Compose services including two custom images, ready checks, model-init | YAML parsed | Run `docker compose config`, pull/build images, live startup on Docker |
| W03 | Alembic revision, five tables plus scope/approval/audit tables; 3 customers, 9 issues, 8 updates | Structural checks on migration/fixture | Run migration, count rows, verify rerun idempotency and DB transactions |
| W04 | Keycloak realm, 3 roles/users, audience mappers, RS256/JWKS bearer authentication | Unit tests on audience, issuer, expiry; Keycloak JSON validated | Live Keycloak realm import, token acquisition/invalid token and browser OIDC W06 |
| W05 | Streamable HTTP MCP server, four role-gated tools and SQL repo, admin approval gate | Contract checks; code compiled; policy tests | Live MCP protocol smoke, scoped reads, admin approval/write and concurrent duplicate replay |

Current status of G0/G1/G2: **NOT VERIFIED**. W06+ not delivered. Do not submit without verifying actual runtime and completing mandatory functional/evaluation requirements.
