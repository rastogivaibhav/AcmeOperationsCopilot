# Final EY submission and private-repository sharing checklist

## Current status (11 November 2026)

The implementation is merged into private `main` at `1a2b936d3bd3`. [Source CI on the merged commit](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42984994299) **passed**. The [verified full-stack evaluation](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42983299825) on source-equivalent PR commit `3437902f4448` passed W07 **5/5**, W08, W09, W13 **10/10**, browser OIDC, Keycloak/MCP, controlled writes and fixture integrity, with **206 offline tests** and successful Docker image builds. Its release gate returned `source_ready_live_verified`.

**Post-merge full-stack evidence:** [run 42984994525](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42984994525); check the run's latest conclusion rather than assuming that the PR and merge runs are identical outcomes. See [measured report](../evals/report.md).

This is an assessment prototype, **not production-ready**. Automated checks do not replace the candidate's own review of AI-generated code, factual answers or security trade-offs.

## Five deliverables

| Deliverable | Repository location | What is verified |
|---|---|---|
| Complete source, configuration and Docker Compose | Repository root, `compose.yaml`, `app/`, `mcp_server/` | Docker image builds and full Compose startup passed |
| Setup, design trade-offs and AI-tool disclosure | `README.md`, `AI_USAGE.md`, `SECURITY.md` | Documents present and updated; candidate should read and endorse |
| Architecture and data-flow diagrams | `ARCHITECTURE.md`, `docs/architecture.mmd` | Source diagrams supplied; architecture is still a prototype |
| Measured evaluation and commentary | `evals/report.md`, GitHub Actions `acme-live-evaluation` artifact | W07 5/5, W13 10/10 structural score, W08/W09 passed |
| Evidence of human approval, security, tests and limitations | `app/`, `tests/`, `evals/manual_review_template.csv` | Automated role/write checks passed; manual quality review remains separate |

## Before inviting EY reviewers

- [x] Source merged into private `main`; no need to upload or publish again
- [x] Post-merge source CI passed
- [x] Full-stack evaluation passed on the source-equivalent PR commit, including EV04
- [x] Browser sign-in, conversation ownership, role denials and controlled writes exercised in GitHub Actions
- [x] README, evaluation summary, security/publication notice and AI-usage handover reconciled to real evidence
- [ ] Confirm the *post-merge* full-stack workflow concluded successfully: [check here](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42984994525)
- [ ] Personally inspect the generated case records and fill `evals/manual_review_template.csv`; structural scoring alone cannot prove semantic grounding
- [ ] Review AI-tool disclosure, design decisions and known limitations in preparation for evaluator Q&A
- [ ] Invite the specific authorised EY GitHub usernames to the private repository (requires their usernames); do not make it public

### Private access steps

Open [the private repository](https://github.com/rastogivaibhav/AcmeOperationsCopilot), go to **Settings → Collaborators → Add people**, and invite only EY reviewers approved to receive the assessment solution. They must accept the invitation. An uninvited reviewer cannot access a private repository by URL alone. Do not upload the confidential candidate pack or real organisational data.

The local demo's seeded Keycloak passwords are **fictional and disposable** and must never be exposed as a public service. This project requires Docker/Compose and downloads an Ollama model on first boot. Reviewers can also view GitHub Actions artifacts if their repository access permits it.

## Reproduction and evaluation sequence

```bash
cp .env.example .env
docker compose up --build -d
curl --fail http://127.0.0.1:8000/readyz

docker compose exec -T web python -m app.smoke
docker compose exec -T web python -m app.smoke_w06
docker compose exec -T web python -m app.telemetry.smoke_w11
docker compose exec -T web python -m evals.fixture_guard --capture

docker compose exec -T web python -m app.agent.probe
docker compose exec -T web python -m app.agent.smoke_w08
docker compose exec -T web python -m app.skills.smoke_w09
docker compose exec -T web python -m evals.run_w13
docker compose exec -T web python -m evals.fixture_guard --verify

# Changes fictional data: run AFTER the read-only evaluation.
docker compose exec -T web python -m app.smoke_w10
docker compose cp web:/code/evals/results/. ./evals/results/
python scripts/verify_release.py --submission
```

Alternatively, inspect the completed private GitHub Actions runs and download their `acme-live-evaluation` artifact. Never post raw bearer tokens, credentials, or confidential material into public logs or files.

## Fifteen-minute evaluator walkthrough

| Time | Evidence | What to demonstrate |
|---|---|---|
| 0–3 min | User problem, system diagram and running stack | BFF, LangGraph, Ollama, Keycloak, MCP, PostgreSQL |
| 3–6 min | Sales login | Role-scoped customer lookup and forbidden write |
| 6–9 min | Support investigation and escalation | History, verified sources, missing information and advisory Skill |
| 9–12 min | Admin approval | Proposed action, explicit confirmation, receipt and idempotent replay |
| 12–15 min | Test transparency | Live 10/10 run, failure-to-fix history, audit events, prototype limitations |

## Remaining boundaries

- Human semantic review and an independent security assessment have **not** been certified.
- CPU-only Ollama latency may vary, and model outputs should not be described as guaranteed.
- Local-only HTTP, Keycloak `start-dev`, embedded demo identities and simplified token audiences are **not** production settings.
- EY's confidentiality restriction means private access for expressly authorised assessment reviewers only; obtain permission before any public release.
