# Acme Operations Copilot — Work Breakdown, Definition of Done and Submission Plan

**Version:** 1.0 — 9 November 2026
**Owner:** Candidate engineering project
**Assessment deadline in recruiter's email:** 9 November 2026
**Status:** Planned — not yet implemented or validated

## 1. Outcome, scope and release gate

Deliver a locally running **identity-aware, tool-using operational assistant** whose role-specific agent sessions share a governed blueprint but obey server-side Keycloak permissions, query seeded PostgreSQL through MCP, use Redis, implement a reusable escalation Skill, provide logs and evaluations and start through Docker Compose.

**Release gates:**
1. `G0`: the whole Compose stack boots, including Keycloak, PostgreSQL, Redis, MCP and local LLM.
2. `G1`: all four mandatory agent capabilities run with real dynamic tool calls and database records.
3. `G2`: three roles authenticate, and prohibited actions are rejected at MCP/backend boundaries.
4. `G3`: 10 executed evaluation cases and tool/request/error/latency logs are available.
5. `G4`: README, architecture, source/ZIP or private GitHub, eval results, AI usage notes complete.
6. `G5` (differentiator): user-scoped checkpoint recovery and idempotent write replay tested.

Do not claim a release gate has passed until there is executable evidence.

## 2. Prioritised backlog

| ID | Priority | Work package | Implementation tasks | Dependencies | Definition of done / evidence |
|---|---|---|---|---|---|
| W01 | P0 | Repository scaffold | Create app/mcp/blueprints/tests/evals, lock dependencies, CI/test scripts | None | Reproducible Python environment, lint and tests execute |
| W02 | P0 | Compose infrastructure | Compose, Postgres, Redis, Keycloak, Ollama, networks, volumes, health checks, model-init | W01 | Clean `docker compose up --build` boots services |
| W03 | P0 | PostgreSQL schema and seeds | Alembic, 5 mandatory business tables, users, representative scenarios, indexes | W02 | Read/write SQL integration tests pass; seeding idempotent |
| W04 | P0 | Keycloak realm and users | Realm, 3 roles, local demo users, OIDC client, tested callback and audience | W02 | Real browser login, valid JWT, invalid-token failure |
| W05 | P0 | MCP server | Real Streamable HTTP server, four baseline tools, strict schemas, parameterised queries | W03, W04 | MCP client calls return correct DB rows; negative auth case |
| W06 | P0 | FastAPI BFF | Login/callback/logout, secure session, /me, conversation API, CSRF | W04 | Role-aware endpoints work; no browser access tokens |
| W07 | P0 | Local model tool calling | Ollama tool-capable model, measured selection spike, bounded timeouts | W02, W05 | Model invokes actual MCP tools across initial 3 prompts |
| W08 | P0 | LangGraph agent loop | Model node, conditional tool routing, response schema, max steps | W05, W07 | Dynamic customer/profile/history/action flows pass |
| W09 | P0 | Escalation Skill | Typed workflow, deterministic risk rubric, evidence, missing information | W05, W08 | Model can invoke Skill; grounded structured result |
| W10 | P0 | RBAC enforcement | API policy, MCP policy, explicit role matrix, customer scope if time | W04, W05, W08 | Sales prohibited; support issue update; admin action commit |
| W11 | P0 | Web experience | Personal workspace, role badge, chat, customer/issue cards, evidence and permission state | W06, W08 | Real end-to-end browser interactions; no mock issue counts |
| W12 | P0 | Observability | JSON logs, OTel spans, trace IDs, tool/error/latency, audit for writes/denials | W08, W10 | Each eval run has traceable tool path, errors and latency |
| W13 | P0 | Eval harness | 10 cases, expected tool policy, DB cross-check, RBAC and action review | W08–W12 | Actual `results.json` + commentary; failures preserved |
| W14 | P0 | Documentation and handover | README, diagrams, security/trade-offs, AI usage, demo guide | W02–W13 | Five EY deliverables present and verified |
| W15 | P1 | Blueprint inheritance | Enterprise/team/role YAML, persona composition, version/hash auditing | W08, W10 | Roles share response contract but differ in tools, securely |
| W16 | P1 | Durable recovery | PostgreSQL checkpointer, task status, resume route, owner verification | W03, W08, W15 | Restart web and resume unfinished task using same thread |
| W17 | P1 | Write durability | Idempotency/operation IDs, optimistic issue version, approval state | W03, W10, W16 | Crash/retry does not double-write; policy rechecked |
| W18 | P1 | Activity Centre | My tasks, incomplete-work banner, tool/audit timeline | W12, W16 | User sees own task status and can resume |
| W19 | P2 | Scheduled recovery worker | Durable queue/leases, due tasks, bounded retry and reauth | W16–W17 | Deferred; not required by EY |
| W20 | P2 | Multi-agent and extra connectors | Specialist subagents, external CRM, vector search, cloud hosting | G4 | Explicitly excluded from submission |

**Critical path:** W01 → W02 → W03/W04 → W05 → W07 → W08 → W09/W10 → W11/W12 → W13 → W14.

Blueprint and recovery work are only allowed to delay final packaging if EY's mandatory requirements and evaluation evidence are already complete.

## 3. Order of implementation and checkpoints

### Wave A — Bootstrap and risk spike
- Repo, Python dependencies, service health, model provisioning, seeded database, Keycloak realm.
- Build a minimal endpoint that verifies a real Keycloak token.
- Use an MCP client to call a real customer tool and confirm response is sourced from PostgreSQL.
- Test three tool-calling prompts with the selected local model.

**Stop/go:** If the model, login, or MCP fails, fix these foundations first. Do not build UI polish.

### Wave B — Functional application
- Complete MCP contracts and agent graph.
- Deliver reusable Skill and typed summaries.
- Implement role permissions and two write tools (issue status; admin next action).
- Wire server-rendered workspace and chat.

**Stop/go:** Every required capability accessible via UI/API with actual tool logs.

### Wave C — Evidence and packaging
- Add request/span IDs, audit, latency and error paths.
- Execute the entire 10-case evaluation; fix high-severity failures and rerun.
- Write README, architecture diagram, AI usage notes, measured results.
- Verify clean checkout `docker compose up` and synthetic demo accounts.

**Stop/go:** G0–G4 passed with evidence; freeze mandatory submission.

### Wave D — Differentiators, only when P0 stable
- Role blueprint versioning and activity UI.
- Persist LangGraph checkpoints and explicit resume.
- Prove idempotency against crash/retry.

**Stop/go:** G5 passed; add to 15-minute demo. Otherwise document as future work, not as implemented.

## 4. Scenario-based acceptance checklist

- [ ] `docker compose up` starts website, Keycloak, Redis, PostgreSQL, MCP and local LLM without extra hidden commands.
- [ ] All containers use pinned images/dependencies and reasonable readiness probes.
- [ ] Keycloak uses actual authentication with three distinct user accounts.
- [ ] Wrong-audience, expired or forged tokens are rejected.
- [ ] Sales role can read and obtain recommendations but cannot commit a next action or update an issue.
- [ ] Support role can read and update an issue, and cannot create an admin-only next action.
- [ ] Admin can create a next action after explicit confirmation, with an operation receipt.
- [ ] Model dynamically chooses tools; prompt-only canned responses do not substitute for tool execution.
- [ ] All four EY-mandated business capabilities are demonstrated.
- [ ] At least one actual MCP server and reusable Skill are independently verifiable.
- [ ] Database has the five required tables and representative seeded records.
- [ ] Redis is actively used for TTL-scoped state/cache and isolated per session.
- [ ] Every answer distinguishes facts, recommendations and missing data, with source IDs.
- [ ] Tool logs, request/response traces, error logs and latency data are available.
- [ ] Exactly 10 evaluation cases executed; actual metrics and failures retained.
- [ ] README, architecture diagram, eval commentary, AI usage notes and complete source are present.
- [ ] No live API keys, personal data, EY pack or secret `.env` committed to public GitHub.
- [ ] Private repo access or ZIP delivery tested.
- [ ] 15-minute walkthrough rehearsed using the actual running local system.

**P1 differentiation checklist**
- [ ] Shared enterprise and per-role blueprint versions captured for each request.
- [ ] User A cannot load User B's conversation or checkpoint.
- [ ] Interrupted conversation resumes after web container restart.
- [ ] Role revocation blocks resume/actions previously permitted.
- [ ] A retried successful write does not produce duplicates.
- [ ] Activity Centre displays persisted real events, not mocked trace cards.

## 5. Work ownership and proof artifacts

| Workstream | Primary ownership | Evidence produced |
|---|---|---|
| Platform/DevOps | Compose and integration | `compose.yaml`, Dockerfiles, first-run logs |
| Data | Schema/seeding/queries | Migration, seed test, SQL verification |
| IAM/Security | Keycloak/RBAC/MCP trust | Realm export, auth tests, denied-write trace |
| Agent engineering | LangGraph/LLM/Skill | Tool traces, typed outputs, risk rubric |
| Full-stack | FastAPI/website | Browser demo across three roles |
| Reliability | Recovery/idempotency | Restart and duplicate-write tests |
| Quality | Eval/test runner | `evals/results.json`, `evals/report.md` |
| Technical communication | README/diagram/AI notes | Complete submission package |

This is a functional ownership map, not a claim that a team has been assigned or code has been written.

## 6. Review gates and responsibility

**G0 Integration Gate:** healthy service graph and successful Keycloak/MCP/LLM handshake.
**G1 Capability Gate:** model-selected customer tools, escalation Skill, admin next-action persistence.
**G2 Security Gate:** actual RBAC failures and successes with database verification.
**G3 Evidence Gate:** 10 actual eval cases, tool and error traces and latency measurements.
**G4 Handover Gate:** run-from-clean README and all five EY deliverables; no confidential attachment leakage.
**G5 Recovery Gate (optional):** checkpoint persistence, correct resume and idempotent write receipt.

**Reviewer rule:** Never mark a gate `PASS` solely because code looks correct. Run the test and retain its output.

## 7. Assessor demo script (15 minutes)

| Time | Demo | Assessment criterion |
|---|---|---|
| 0–3 min | Context, component diagram, local Compose stack | Business understanding and architecture |
| 3–6 min | Sales sign-in and customer-issue question | Real identity, tool selection, grounding |
| 6–9 min | Support sign-in and issue history/update | Skill and role-controlled write |
| 9–12 min | Admin sign-in and approved next action | Idempotent, audited business action |
| 12–15 min | Tool/latency logs, eval results and resume if complete | Observability, engineering judgement |

**Panel Q&A readiness:** know trade-offs of local model, the exact Keycloak/MCP trust boundary, why Redis is not durable task state, LangGraph `thread_id`/resume semantics, idempotency and failure handling, and which code AI assistants generated and how it was verified.

## 8. Main project risks

- **Deadline:** Recruiter's 9 November date overrides any speculative development schedule; submit a complete P0 rather than an unfinished full architecture.
- **Inconsistent assessment instructions:** Pack says five days on cover and 48 hours on deliverables page. Confirm but do not delay core.
- **Local inference:** Tool-call support and CPU performance may be unacceptable until tested; model choice is empirical.
- **Identity:** Keycloak hostname/audience, session redirects and MCP authorisation often fail only at integration time; prioritise early.
- **Recovery:** An interrupted LangGraph node can rerun after `interrupt()`, hence write operations need idempotency.
- **Observability:** Traces and audit events serve different purposes; both needed for strong evidence.
- **Ponytail/minimalism:** Keep scope small; no distributed agent platform or speculative components.

## 9. Exact submission manifest

```text
acme-operations-copilot/
  README.md
  ARCHITECTURE.md
  AI_USAGE.md
  compose.yaml
  Dockerfile.web
  Dockerfile.mcp
  .env.example
  pyproject.toml  # or locked requirements files
  app/
    main.py
    auth/
    agent/
    skills/
    observability/
    templates/
    static/
  mcp_server/
    server.py
    tools.py
    policies.py
  blueprints/
    enterprise.yaml
    sales.yaml
    support.yaml
    admin.yaml
  database/
    migrations/
    seed.py
  infrastructure/
    keycloak/realm.json
  tests/
  evals/
    cases.json
    results.json
    report.md
  docs/
    LLD.md
    architecture.mmd
```

**No file in this plan is assumed to exist in an actual Git repository yet.** This is the implementation blueprint from which code, tests and the submission should be built.
