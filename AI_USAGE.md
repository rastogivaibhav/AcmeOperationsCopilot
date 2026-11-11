# AI-assisted development disclosure — EY case study

**Updated 11 November 2026. Candidate review required before submitting.** This project was substantially designed, drafted, refactored, tested and documented with AI coding assistance. The candidate remains responsible for understanding the architecture, making and defending engineering decisions, verifying the generated code, and accurately representing what was (and was not) validated. Do not claim code was independently human-authored or individually audited unless that happened.

## What AI assistance contributed

The assistant drafted the initial FastAPI BFF, Keycloak/OIDC and Redis sessions, PostgreSQL/Alembic schema/seed, authenticated MCP tools, Docker Compose deployment, browser workspace, LangGraph + local Ollama agent, role blueprints, escalation Skill, approved-write Action Centre, observability/activity records, release scripts and tests. It helped diagnose real integration failures from GitHub Actions, applied successive code fixes and prepared the evaluation and handover documentation.

This included:
- Keycloak storage and access-token claims/audience fixes, Docker readiness, and realistic role/cross-user browser checks.
- Evidence-grounded customer/issue IDs, typed request cues, scoped tool visibility and bounded invalid-argument recovery.
- NVIDIA-*inspired* workflow patterns (intent hints, authenticated prerequisites and separate execution/evaluation boundaries), **without copying NVIDIA Blueprint source code or requiring an NVIDIA runtime**.
- Customer escalation name resolution inside authenticated MCP, deterministic evidence-only responses for defined workflows, separate human approval, issue version checks and write auditability.
- Reproducible seeded fixtures, fixed W13 assessment clock, structured tool trajectories, case-level latency, and CI evidence artifacts.

## Verification record (not an assertion of production readiness)

The initial W01–W14 drafting-stage notes reported that real Docker, Ollama, Keycloak and MCP could not be run **in the original local authoring environment**. That was accurate *at the time*, but those limitations were subsequently addressed using private GitHub-hosted integration runners.

On **11 November 2026** the assessed PR #2 revision \`3437902f\` passed:
- **206** automated source tests and both Docker image builds ([CI](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42983305290)).
- Full Keycloak/HTTP/MCP/PostgreSQL/browser/W07–W13 integration ([GitHub full-stack run](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42983299825)): W07 **5/5**, W08/W09 PASS and W13 **10/10 automated structural cases**.
- Scoped read/denial checks, controlled business-write approvals, fixture integrity and \`source_ready_live_verified\` evidence gate.

That revision was merged as \`1a2b936d3bd3\`; [post-merge CI](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42984994299) passed. The separate [post-merge integration run](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42984994525) should be checked independently.

Earlier iterations objectively scored 3/5 W07 and 6/10 W13. Subsequent fixes improved these to 5/5 and 10/10, including a former 150-second EV04 timeout that completed in **8.94 seconds** in the successful reference run. These measurements show the specific evaluated cases under the tested environment, not a general reliability guarantee.

## Human review and attribution boundaries

The candidate should personally inspect source files, demo the application, review generated factual claims and advisory actions against actual source records, and fill in \`evals/manual_review_template.csv\`. Automated tool/citation/keyword checks are **not proof** that all natural-language answers are correct or business recommendations are appropriate. Manual semantic adjudication, an independent penetration test and production readiness have **not** been claimed.

The project originated from a confidential EY exercise; preserve the original restrictions when granting private GitHub access. Explain AI tools, generated code, defects discovered, corrections made, the decision to keep business writes human-approved, and the reasons for typed, evidence-aware workflows during the interview.

See [evals/report.md](evals/report.md), [architecture](ARCHITECTURE.md), [security](SECURITY.md) and [NVIDIA-inspired design adaptation](docs/NVIDIA_BLUEPRINT_ADAPTATION.md).
