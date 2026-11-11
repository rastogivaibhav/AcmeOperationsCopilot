# EY assessment — final private-repository handover checklist

**Updated 11 November 2026.** The repository is a **private, local-only fictional prototype**. The latest completely verified reference is PR #2 at \`3437902f\`: [full-stack PASS](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42983299825), [206-test CI PASS](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42983305290). PR #2 was merged to \`main\` at \`1a2b936d3bd3\`, where [post-merge CI](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42984994299) also passed. Check [post-merge live integration](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42984994525) for its final status; the earlier reference pass is not proof that this separate run completed.

## Five submission deliverables

| Item | Location | Verified state |
|---|---|---|
| Complete source, configuration, Docker Compose | Repository root, \`compose.yaml\` | Both custom builds and full Compose startup passed |
| Setup, trade-offs and AI usage | \`README.md\`, \`AI_USAGE.md\`, \`SECURITY.md\` | Updated handover; candidate must review personal AI-use disclosure |
| Component/data-flow architecture | \`ARCHITECTURE.md\`, \`docs/architecture.mmd\` | Present; runtime tested, not production architecture certified |
| Evaluation results and commentary | \`evals/report.md\`; private GitHub Actions \`acme-live-evaluation\` artifact | **W07 5/5, W08/W09 PASS, W13 10/10 structural PASS** on verified source revision |
| Engineering decisions and limitations | \`AI_USAGE.md\`, \`SECURITY.md\`, \`docs/NVIDIA_BLUEPRINT_ADAPTATION.md\` | Recorded; candidate's independent judgement and human review are separate |

## Final check before inviting EY reviewers

- [x] Private \`main\` contains merged PR #2 (\`1a2b936d3bd3\`).
- [x] Source/static suite passed: **206 tests** on the assessed PR; post-merge CI also passed.
- [x] Real Docker, Keycloak/OIDC, MCP, PostgreSQL, browser and role-isolation checks passed.
- [x] W07 **5/5**, W08/W09 PASS and W13 **10/10** on the same assessed source revision.
- [x] Read-only fixture integrity, controlled-write/idempotency/approval tests and submission evidence gate passed.
- [ ] Check the **final** outcome of the separate post-merge live integration run and record its result.
- [ ] Download/review private \`acme-live-evaluation\` artifact and manually assess every substantive business claim and recommendation using \`evals/manual_review_template.csv\`.
- [ ] Personally review the architecture and AI-usage disclosure and prepare to explain trade-offs, security limitations, prompt/model failures and fixes in the interview.
- [ ] Confirm only authorised EY reviewers receive access, and no confidential candidate assessment pack or real customer secrets are present.
- [ ] Verify the expected submission time/date with EY if required; the original 9 November 2026 deadline referenced in earlier correspondence has passed.

## How to reproduce the full verification

\`\`\`bash
cp .env.example .env
docker compose up --build -d
docker compose exec -T web python -m app.smoke
docker compose exec -T web python -m app.smoke_w06
docker compose exec -T web python -m app.agent.probe
docker compose exec -T web python -m app.agent.smoke_w08
docker compose exec -T web python -m app.skills.smoke_w09
docker compose exec -T web python -m evals.run_w13
docker compose exec -T web python -m evals.fixture_guard --verify
# Run controlled-write smoke only after the read-only evaluation.
docker compose exec -T web python -m app.smoke_w10
\`\`\`

The fixture verification above requires a baseline captured in the same run using \`docker compose exec -T web python -m evals.fixture_guard --capture\` **before** the W07–W13 tests. For a fully repeatable run without manual sequencing, use GitHub Actions **Acme Copilot Live Compose Integration**, which captures/verifies fixtures and uploads the results in the correct order. \`docker compose down -v\` destroys all local fictional data and model volumes.

## Confidential sharing — private only

1. Open [the private repository](https://github.com/rastogivaibhav/AcmeOperationsCopilot).
2. In GitHub, go to **Settings → Collaborators / Manage access → Add people** and invite each authorised EY reviewer's GitHub account. They must accept the invitation to view the repository.
3. Send the repository URL and the [evaluation report](../evals/report.md) to the authorised panel through the existing recruitment channel. **Do not change the repo to public** while the assessment confidentiality restriction applies.
4. GitHub Actions artifacts are accessible only to people with appropriate repository permissions.

## Suggested 15-minute evaluator walkthrough

| Time | Evidence |
|---|---|
| 0–3 min | Problem, architecture, local-only constraints |
| 3–6 min | Sales sign-in, authenticated scoped customer lookup, denied write |
| 6–9 min | Support history conflicts and evidence-linked escalation Skill |
| 9–12 min | Admin proposal → deliberate human approval → audit and idempotent receipt |
| 12–15 min | Real GitHub evaluation artifact, 10/10 structural gate, limitations and lessons |

**Not claimed:** production hardening, external penetration testing, independent human semantic validation of all ten answers, or guaranteed inference latency.
