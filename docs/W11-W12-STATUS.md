# W11/W12 — Agent observability, activity centre and CI automation

**Work completed:** Source implementation, offline validation and package assembly.
**Runtime status:** Not yet validated under Docker or on GitHub-hosted runners.

## Delivered

- Alembic `0004_observability`: `agent_runs`, `agent_tool_events`; owner/time indexes and bounded metadata; retains no raw prompt or bearer token.
- Agent execution instrumentation: per-request correlation ID, run ID, trace ID, execution duration, evidence count, sanitised tool status/duration, terminal state and safe error codes.
- OpenTelemetry SDK, opt-in console exporter (`OTEL_TRACES_EXPORTER=console`) with agent/tool spans. No raw arguments or prompts emitted.
- Recovery detection: runs stranded across process crashes for more than 20 minutes become `interrupted` on the next web-service startup; LangGraph checkpoints remain intact.
- Business audit listing and policy-denial events for rejected action preparations; existing successful MCP business mutations already write transactional audit events.
- Owner-scoped APIs: `GET /api/activity/summary`, `GET /api/activity/runs`, `GET /api/activity/runs/{id}`, `GET /api/activity/audit`. Another user's run returns 404.
- Browser Activity Centre: recent agent runs, timings, tool events, symbolic evidence refs, and business audit outcomes. No `innerHTML` use.
- `app.telemetry.smoke_w11` live smoke checks identity-scoped activity using real Keycloak, PostgreSQL and HTTP endpoints, saves `evals/results/w11-live.json` if executed.
- GitHub workflows: `.github/workflows/ci.yml` executes offline tests, syntax checks, Compose config validation and Docker builds on push/PR; `.github/workflows/integration.yml` provides manually triggered end-to-end test (model pull, Keycloak/MCP, controlled writes, LangGraph/Skill probes and reports).

## Limitations

1. The current environment cannot run Docker. A passing pytest suite is **not** an end-to-end deployment proof.
2. A GitHub repository has **not** been created because the connected GitHub integration does not expose repository creation. `scripts/publish_github.sh` can publish after authenticated GitHub CLI setup on the user's machine.
3. GitHub-hosted CPU runners may be slow for local Ollama `qwen2.5:3b` inference; model tool-selection and end-to-end evaluations must be judged on actual results, never greened by skipping tests.
4. Recovery detection is not an autonomous scheduler. User-driven continuation via LangGraph checkpoints remains; automatically resuming writes is deliberately excluded.
5. PostgreSQL telemetry is a diagnostic record, not a tamper-proof enterprise SIEM. Formal retention, centralised secure export, field-level data classification and cross-service span propagation remain production work.
6. The web agent and MCP are instrumented differently: web spans + durable MCP-result events; fully distributed cross-service OTLP tracing is an enhancement, not a proven end-to-end feature.

## Offline validation

```bash
python -m pytest -q tests
node --check app/static/workspace.js
sh scripts/verify_static.sh
```

## GitHub-hosted validation

1. Create a **private** repository until the assessment publication restriction is lifted.
2. Push the repository root containing `.github/workflows/`.
3. Inspect **Actions → Acme Copilot CI**. Its two jobs verify dependencies/code and build both Docker images.
4. Use **Actions → Acme Copilot Live Compose Integration → Run workflow** for the resource-intensive full-stack gate.
5. Download the `acme-live-evaluation` artifact and inspect failed steps. No metrics are claimed until the run is green.
