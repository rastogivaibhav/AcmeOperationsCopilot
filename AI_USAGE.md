# AI Tool Usage Notes — candidate review and disclosure

**Current verification record (11 November 2026).** Later GitHub Actions runs supersede the early phase-by-phase testing limits below. [Live PR evaluation](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42983299825) verified Docker/Keycloak/MCP/Ollama, W07 5/5, W08/W09, W13 10/10, the browser, write controls and fixture integrity; the [post-merge source CI](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42984994299) passed. The independent [post-merge integration run](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42984994525) also passed W07/W08/W09, W13 10/10, browser/identity, writes and fixture-integrity gates. The 206-test offline suite and Docker images passed on the PR commit. These records do not imply an independent candidate-led semantic review, production sign-off or that AI-assisted code was human-authored.

**Reading guide:** The work-package sections below document what was known *at the time each increment was initially drafted*. Historical statements that a particular test had not yet run are not descriptions of the current merged repository. See [the measured report](evals/report.md) for the authoritative final observed results.

This initial implementation was generated with AI-assisted code drafting. The assistant proposed the FastAPI, database migration, Compose, Keycloak realm and MCP tool structure using the supplied LLD and work breakdown. It also wrote tests and ran **local static/unit checks**. At the time of the initial draft, it did not run the container stack because Docker and package-index access were unavailable in that authoring environment. The later CI results described above subsequently validated the live stack.

The candidate must review every generated file, make their own engineering decisions, run the full suite in Docker, record defects found, and explain any corrections and assumptions in the interview. Do not claim independent manual review, live test results, production-quality assurance, or human-authored work unless that occurred.

Areas needing human verification: actual Keycloak realm import and token audience, MCP SDK API compatibility, Alembic migration/seed, Docker Compose readiness, role enforcement including negative tests, secure approval flow and model inference. Keep this file truthful as the implementation progresses.


## W06 — assistant-generated implementation and human verification requirements

An AI assistant authored the first pass of OIDC PKCE, Redis BFF sessions, CSRF enforcement, Jinja website, owner-scoped conversations, migration, tests and local smoke scripts. The assessment's developer/owner is responsible for inspecting this code, pinning and testing actual library dependencies, reviewing credential and audience handling, running browser and Docker integration checks and documenting any defects before submission. The assistant used the official Keycloak OIDC endpoints and MCP SDK migration documentation for implementation context, but had not exercised a live Keycloak instance or Docker container **at that initial W06 stage**; these were later covered by GitHub-hosted integration. Do not claim a validated deployment or penetration test on the strength of static tests.


## W07 additions

An AI coding assistant helped draft the tool-selection spike, its test doubles, model/MCP transport adapters, five-case evaluation fixture and runbook. Human review priorities: dynamic calls rather than canned routing, no write execution, schema validation, bounded loops, Keycloak-scoped MCP, secret redaction and non-inflated evaluation claims. Deterministic tests were executed locally; genuine Ollama/MCP integration was **not yet executed at that stage**; the later live GitHub W07 gate passed 5/5.


## W08 additions

AI-assisted code generation was used to draft the LangGraph graph, role-blueprint loader, web chat wiring, PostgreSQL-checkpointer lifecycle, tests and W08 live-smoke script. The assistant also corrected a previously incompatible `httpx2` dependency range. In this environment it ran **64 offline tests**, Python syntax compilation and the browser JavaScript syntax check. **At that W08 draft stage** no Docker image or actual LangGraph/PostgreSQL checkpoint had yet been run. Subsequent GitHub-hosted integration and W08 smoke passed. The developer must validate the runtime, examine the output for policy drift, review all generated code, and document any defects before supplying EY with an assessment.


## W09 additions

AI-assisted engineering drafted the read-only Escalation Summary Skill, Pydantic output contract, versioned YAML inheritance, LangGraph dispatch, nested MCP call trace events, deterministic synthetic tests and live smoke runner. The authoring environment passed **87 offline tests** and Python compilation, but did **not** run Docker or real-model inference **at that stage**. Subsequent GitHub-hosted W09 direct and model-selected Skill tests passed. A candidate submitting this work must review the rubric and security model, exercise all live acceptance gates, record any defects and explain the use of generated code to EY.


## W10 additions

AI-assisted code drafting was used for the verified-role Action Centre, model-visible **proposal-only** tool schemas, authenticated BFF prepare/confirm/cancel endpoints, PostgreSQL approval migration, issue-status MCP tool, transactional issue history/receipt/audit SQL, offline tests and a live smoke runner. The human candidate must review the architecture, decide whether the allowed issue transitions fit the business scenario, run real Keycloak/MCP/PostgreSQL tests, inspect permission denials and measure actual performance. Offline in-process test doubles are **not** evidence of a successful Docker deployment, real LLM tool selection or runtime RBAC.


## W11/W12 AI-assisted engineering record (9 Nov 2026)

AI coding assistance drafted a minimal run-telemetry schema, actor-scoped persistence, OpenTelemetry instrumentation, an Activity Centre and GitHub Actions workflows. Human design constraints retained: no raw access tokens or prompts in diagnostic spans, independent durable business audit, failure/recovery states, explicit read-scoped API access, and no unattended replay of writes. Validation was limited to local Python/static tests and syntax checks; Docker builds and GitHub-hosted execution had yet to be verified **at that phase**. The private GitHub repository was later created and its CI/integration workflows executed.

## W13/W14 AI-assisted engineering record (9 Nov 2026)

AI coding assistance prepared the ten-case evaluation specification, real LangGraph/MCP/Ollama evaluation runner, deterministic scoring rules, negative tests, human-review worksheet, architecture diagram and release-gate checker. It also revised GitHub Actions configuration and submission documentation. Offline tests were executed, and the actual results are recorded in `docs/W13-W14-STATUS.md`. **At the initial W13/W14 draft stage**, real Ollama inference and hosted verification had not yet been established. Later GitHub Actions confirmed all of these structural checks. Automated source-ID checks should not be presented as proof of hallucination-free answers; a human must inspect result quality and the AI-generated source before submission.


## NVIDIA-inspired workflow adaptation, 10 Nov 2026

AI-assisted design and code changes merged through PR #1 are based on the public NVIDIA Intelligent Warehouse, Deep Researcher/AI-Q and NeMo Agent Toolkit patterns (not copied NVIDIA implementation code). They add typed request signals, authenticated Skill and proposal prerequisites, fixture integrity checks and trajectory evaluation. The first measured baseline was W07 3/5, W09 model-selected Skill failed and W13 6/10. Subsequent PR #1 routing/Skill changes and PR #2 customer-name recovery achieved W07 5/5, W09 pass and W13 10/10 on a full live runner. The candidate should still review the generated code and claims independently. See docs/NVIDIA_BLUEPRINT_ADAPTATION.md.


## Final escalation fix and integration record (11 Nov 2026)

An AI coding assistant examined the failed EV04 model-selected escalation call and found the missing customer argument. PR #2 binds an explicitly stated current-turn customer name to the already selected Skill, rejects conflicting names, and keeps all customer/issue data access inside Keycloak-authenticated MCP. Regression tests include denied access and incorrect names. [PR #2](https://github.com/rastogivaibhav/AcmeOperationsCopilot/pull/2) was merged into private `main`. The [full-stack test run](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42983299825) passed EV04 in 8.94 seconds, W13 10/10, W07 5/5 and the separate approval/security/fixture gates. The assistant was involved in drafting and committing these changes; this statement does not attribute them to unaided manual engineering.
