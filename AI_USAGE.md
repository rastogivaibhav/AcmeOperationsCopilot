# AI Tool Usage Notes — Candidate must review before submitting

This initial implementation was generated with AI-assisted code drafting. The assistant proposed the FastAPI, database migration, Compose, Keycloak realm and MCP tool structure using the supplied LLD and work breakdown. It also wrote tests and ran **local static/unit checks**. It did **not** run the container stack or conduct live integration/security tests, because Docker and package-index access were unavailable in its environment.

The candidate must review every generated file, make their own engineering decisions, run the full suite in Docker, record defects found, and explain any corrections and assumptions in the interview. Do not claim independent manual review, live test results, production-quality assurance, or human-authored work unless that occurred.

Areas needing human verification: actual Keycloak realm import and token audience, MCP SDK API compatibility, Alembic migration/seed, Docker Compose readiness, role enforcement including negative tests, secure approval flow and model inference. Keep this file truthful as the implementation progresses.


## W06 — assistant-generated implementation and human verification requirements

An AI assistant authored the first pass of OIDC PKCE, Redis BFF sessions, CSRF enforcement, Jinja website, owner-scoped conversations, migration, tests and local smoke scripts. The assessment's developer/owner is responsible for inspecting this code, pinning and testing actual library dependencies, reviewing credential and audience handling, running browser and Docker integration checks and documenting any defects before submission. The assistant used the official Keycloak OIDC endpoints and MCP SDK migration documentation for implementation context, but did not exercise a live Keycloak instance or Docker container here. Do not claim a validated deployment or penetration test on the strength of static tests.


## W07 additions

An AI coding assistant helped draft the tool-selection spike, its test doubles, model/MCP transport adapters, five-case evaluation fixture and runbook. Human review priorities: dynamic calls rather than canned routing, no write execution, schema validation, bounded loops, Keycloak-scoped MCP, secret redaction and non-inflated evaluation claims. Deterministic tests were executed locally; genuine Ollama/MCP integration is **not yet executed** and requires a Docker runtime.


## W08 additions

AI-assisted code generation was used to draft the LangGraph graph, role-blueprint loader, web chat wiring, PostgreSQL-checkpointer lifecycle, tests and W08 live-smoke script. The assistant also corrected a previously incompatible `httpx2` dependency range. In this environment it ran **64 offline tests**, Python syntax compilation and the browser JavaScript syntax check. **No Docker image was built; no actual LangGraph graph or Postgres checkpoint was run, and no real model/MCP result was generated.** The developer must validate the runtime, examine the output for policy drift, review all generated code, and document any defects before supplying EY with an assessment.


## W09 additions

AI-assisted engineering drafted the read-only Escalation Summary Skill, Pydantic output contract, versioned YAML inheritance, LangGraph dispatch, nested MCP call trace events, deterministic synthetic tests and live smoke runner. The authoring environment passed **87 offline tests** and Python compilation, but did **not** run Docker, Ollama inference, actual MCP transports or PostgreSQL checkpoints. No measured live AI skill-selection result has been reported. A candidate submitting this work must review the rubric and security model, exercise all live acceptance gates, record any defects and explain the use of generated code to EY.


## W10 additions

AI-assisted code drafting was used for the verified-role Action Centre, model-visible **proposal-only** tool schemas, authenticated BFF prepare/confirm/cancel endpoints, PostgreSQL approval migration, issue-status MCP tool, transactional issue history/receipt/audit SQL, offline tests and a live smoke runner. The human candidate must review the architecture, decide whether the allowed issue transitions fit the business scenario, run real Keycloak/MCP/PostgreSQL tests, inspect permission denials and measure actual performance. Offline in-process test doubles are **not** evidence of a successful Docker deployment, real LLM tool selection or runtime RBAC.


## W11/W12 AI-assisted engineering record (9 Nov 2026)

AI coding assistance drafted a minimal run-telemetry schema, actor-scoped persistence, OpenTelemetry instrumentation, an Activity Centre and GitHub Actions workflows. Human design constraints retained: no raw access tokens or prompts in diagnostic spans, independent durable business audit, failure/recovery states, explicit read-scoped API access, and no unattended replay of writes. Validation was limited to local Python/static tests and syntax checks; Docker builds and GitHub-hosted execution still require live verification. The GitHub repository was not created automatically because repository creation is not available through the connected action set.

## W13/W14 AI-assisted engineering record (9 Nov 2026)

AI coding assistance prepared the ten-case evaluation specification, real LangGraph/MCP/Ollama evaluation runner, deterministic scoring rules, negative tests, human-review worksheet, architecture diagram and release-gate checker. It also revised GitHub Actions configuration and submission documentation. Offline tests were executed, and the actual results are recorded in `docs/W13-W14-STATUS.md`. **No real Ollama inference, Docker build, live role enforcement or GitHub workflow execution has been verified from this authoring environment.** Automated source-ID checks should not be presented as proof of hallucination-free answers; a human must inspect result quality and the AI-generated source before submission.


## NVIDIA-inspired workflow adaptation, 10 Nov 2026

AI-assisted design and code changes in draft PR #1 are based on the public NVIDIA Intelligent Warehouse, Deep Researcher/AI-Q and NeMo Agent Toolkit patterns (not copied NVIDIA implementation code). They add typed request signals, authenticated Skill and proposal prerequisites, fixture integrity checks and trajectory evaluation. The candidate must review these changes and the live runner results; no success beyond the measured main-branch W07 3/5, W09 model-Selected Skill failure, and W13 6/10 is asserted. See docs/NVIDIA_BLUEPRINT_ADAPTATION.md.
