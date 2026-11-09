# Final EY submission and live verification checklist

## Important: status

Source through W14 is implemented and offline-tested. **The project has not been verified by a real Docker Compose boot or a GitHub Actions run in this environment.** The W13 automated case set is ready, but the actual ten-model-question metric is **not measured**. Do not treat this document as a signed acceptance report.

## The five EY deliverables

| Deliverable | Location | Evidence level |
|---|---|---|
| Complete source, all configuration and Docker Compose | Repository root | Exists; Docker build not run |
| README with setup, trade-offs and use of AI tools | `README.md` and `AI_USAGE.md` | Exists; setup unverified |
| Architecture diagram showing component relationships and data flows | `docs/architecture.mmd` | Exists; not runtime-certified |
| Evaluation results and commentary | `evals/report.md`; actual outputs under `evals/results/` | Suite specified; no live metrics |
| AI-assisted development account | `AI_USAGE.md` | Exists; author must review for accuracy |

## Run before submission (from a checked-out repository)

1. Run `python -m pip install -e '.[test]' && sh scripts/verify_static.sh`.
2. Run `python scripts/verify_release.py` and inspect the output.
3. Run `docker compose up --build -d` and verify `docker compose ps` reports healthy services.
4. Run `docker compose exec -T web python -m app.smoke` and `python -m app.smoke_w06`.
5. Run `docker compose exec -T web python -m app.smoke_w10`; this writes **fictional test data** to the demo DB.
6. Run `docker compose exec -T web python -m app.telemetry.smoke_w11`.
7. Run `docker compose exec -T web python -m app.agent.probe`, `python -m app.agent.smoke_w08`, and `python -m app.skills.smoke_w09`.
8. Run `docker compose exec -T web python -m evals.run_w13`; retain the generated report and record failures exactly as returned.
9. Copy evaluated outputs: `docker compose cp web:/code/evals/results ./evals/results` and review the files for sensitive content.
10. Fill in `evals/manual_review_template.csv` with an actual human judgement of factual grounding, missing information, action reasonableness and permissions. Do not infer semantic correctness from string matches.
11. Run `python scripts/verify_release.py --submission` and record outcome. This checks the presence and reported success of W11 and W13 evidence; inspect W01–W10 outputs separately.
12. Verify all five EY deliverables are present and the actual repository contains no confidential EY documents, `.env` file, real enterprise data or tokens.

## GitHub actions

- The private repository `https://github.com/rastogivaibhav/AcmeOperationsCopilot` exists. Keep it private during assessment.
- `bash scripts/publish_github.sh --private` from the extracted repository root if GitHub CLI is installed and authenticated.
- `Acme Copilot CI` runs unit/static/Compose verification and builds both images.
- `Acme Copilot Live Compose Integration` (manual dispatch) starts the full service graph and runs W07–W13 probes. Download its `acme-live-evaluation` artifact; review both failures and passing results.
- A public repository is **not required** for Actions and would disclose the solution. Only change visibility after publication restrictions permit it.

## 15-minute demo script

| Time | Proof | What to show |
|---|---|---|
| 0–3 min | Client problem and architecture | Real diagrams and local Docker stack |
| 3–6 min | Sales identity and constrained customer lookup | Keycloak account, real MCP calls and source records |
| 6–9 min | Support Skill and issue proposal | Model-selected read tools, explicit approval boundary |
| 9–12 min | Admin action | User-confirmed next action, audit receipt, idempotent retry |
| 12–15 min | Quality | Agent trace, ten-case evaluation outcomes, known defects/limitations |

## Known readiness blockers

- The private GitHub repository is created. Source upload and workflow execution remain outstanding until a push succeeds.
- Container images, Keycloak/OIDC live handshake, MCP transport and Ollama tool selection have not been verified on a Docker daemon.
- W13 automated checks are **structural**. Human adjudication of every actual response is still necessary.
- Model pull and CPU-only inference on a hosted GitHub runner can be slow and may exceed workflow budgets.
- The submitted source uses fictional credentials for development; its HTTP/Keycloak start-dev configuration is **not production-ready**.
- EY's stated deadline was 9 November 2026. Verify delivery with the recruiter if not already submitted.
