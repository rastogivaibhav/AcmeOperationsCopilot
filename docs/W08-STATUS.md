# W08 — LangGraph Agent Runtime / Browser Chat

Status: **implemented in source, verified with deterministic offline tests; live integration not verified**. Date: 2026-11-09.

## Delivered

- `app/agent/graph.py`: explicit `StateGraph` reasoning/tool loop using Ollama's native tool-call API; conditional tool routing, max six model turns, eight calls, bounded context; returns only actual LLM responses and MCP evidence references.
- `app/agent/blueprint.py` and `blueprints/{enterprise,sales_user,support_user,admin}.yaml`: versioned enterprise rules and role-specific persona/missions, with a **read-only** tool catalogue selected from real MCP schema, never authority granted by YAML.
- `app/main.py`: web application uses long-lived `AsyncPostgresSaver`, unique owner-gated `thread_id`, run-scoped MCP authentication, CSRF on chat writes and Redis per-conversation concurrency lock.
- `app/conversations.py`: owner-checked transcript projection. Each completed user/assistant message pair is written atomically; graph checkpoint retains execution state.
- `app/templates/workspace.html` + `app/static/workspace.js`: actual chat input, investigation selector, verified user persona and evidence/tool status. Untrusted output is inserted with `textContent`, not HTML.
- `app/agent/smoke_w08.py`: LIVE model/MCP/checkpoint test, reopening a separate PostgreSQL checkpoint connection to prove persisted conversation state.
- Fixed inherited W07 `httpx2` pin (`>=0.28,<1.0` → `>=2.5,<3`). MCP SDK 2.x requires the 2.x client API; the former range was incompatible.

## Security and execution constraints

1. The Keycloak bearer token is kept inside the `AuthenticatedMCP` transport in trusted LangGraph run context. The model receives only allowed tool *schemas*, not tokens, roles or credentials.
2. The HTTP route verifies conversation owner **before** opening its graph thread, and rechecks ownership when saving the transcript.
3. Both `Blueprint` loading and `tool_specs_for_profile` reject tool escalation; all W08 agents have **read-only** tool visibility even if an admin has separate permission to approve actions.
4. MCP itself still independently validates the JWT and customer scope. Prompts are not the security boundary.
5. Concurrent turns are rejected with `409` while an active run holds the Redis lease; a bounded total runtime prevents a normal request from exceeding the lease.
6. The role and blueprint version are bound to a new conversation. A changed profile causes a `409` instead of silently processing a previously privileged checkpoint under a new persona.

## Offline checks

- `python -m pytest -q` — **64 passed** in this authoring environment (47 inherited, 17 W08 tests).
- `python -m compileall -q app acme_shared database mcp_server` — passed.
- `node --check app/static/workspace.js` — passed.

These tests exercise schemas, tool restrictions, fake transport orchestration, budgets, prompt composition, routing and security contracts. They **do not** exercise an imported LangGraph package, a real LLM, database checkpoints, or a live Keycloak/MCP transport. Those tests require the Docker runtime below.

## Live verification gate — not executed here

```bash
cp -n .env.example .env
docker compose config
docker compose up --build -d
docker compose exec web python -m app.smoke
docker compose exec web python -m app.smoke_w06
docker compose exec web python -m app.agent.probe
docker compose exec web python -m app.agent.smoke_w08
docker compose cp web:/code/evals/results/w08-live.json ./evals/results/w08-live.json
```

Then open `http://localhost:8000`, log in with the Keycloak demo users documented in the README, create an investigation, ask for Acme Retail's open issues, and confirm that live MCP tool use and evidence are shown. Log out/in and reopen the conversation. Restart the web container and verify the checkpoint is still accessible. Never mark these as passed without executing the tests.

## Known limits / outstanding work

- **W09:** Escalation Summary Skill (typed rubric, risk classification, missing evidence) not implemented.
- **W10:** Support issue update tool/role permissions and admin write confirmation integrated into chat not implemented; the separate admin approval+MCP tool foundation remains available.
- **W12:** Full OpenTelemetry spans and durable agent decision audit trail not implemented. W08 returns per-tool duration/evidence but is not full observability.
- **W13:** End-to-end 10-case agent evaluation and demonstrated answer groundedness not yet executed.
- **W16:** Deterministic workflow resume (interrupted node/approval), exact-once business effects and transcript/checkpoint reconciliation remain pending. W08 checkpoints allow conversation continuity on completed turns; interrupted-run recovery has not been validated.
- Current customer assignment changes on an existing sales conversation require checkpoint invalidation/re-authorisation. W08 blocks *role/blueprint* changes but does **not** yet re-check every old tool result against newly revoked customer scope; do not claim full revocation-safe resume.
- No Docker Engine, installed LangGraph runtime or live Ollama model available in this authoring container; version and API compatibility remain to be tested at the integration gate.
- Demo Keycloak passwords, `start-dev` and local model provisioning must not be used as production defaults.
