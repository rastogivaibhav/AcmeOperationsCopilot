# Real `main` evaluation evidence and reviewer commentary

**Run:** [Acme Copilot Live Compose Integration #42986664790](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42986664790) · **Commit:** `54442f2f5704676f563127fde0a7ab611016c3f1` · **Run date:** 11 November 2026 · **Model:** `qwen2.5:3b` (Ollama, local model in Docker). **Fixed evaluation as-of:** 10 November 2026 at 12:00 UTC.

This report is **derived from the completed GitHub Actions `acme-live-evaluation` artifact**, not a synthetic reconstruction. For the full, machine-readable `w07-live.json`, `w08-live.json`, `w09-live.json`, `w10-live.json`, `w11-live.json`, `w13-live.json` and `w13-live-report.md`, open the [run page](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42986664790) and download **Artifacts → acme-live-evaluation**. GitHub permissions are required; artifacts may expire.

## Overall observed outcome

| Check | Observed outcome |
|---|---|
| Source CI, same SHA | **206 tests passed** — [CI run 42986664730](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42986664730) |
| W07 — real model tool selection | **5/5** passed |
| W08 — LangGraph + checkpoint + MCP | **PASS** |
| W09 — direct + model-selected escalation Skill | **PASS** |
| W13 — ten representative business workflows | **10/10 structural passes**, 0 argument-validation-error cases |
| W13 latency | **Median 6.24 s; P95 nearest rank 20.61 s** across ten cases |
| Read-only fixture integrity | **PASS**; baseline fingerprint unchanged |
| W10 approved writes and W11 observability | **PASS** |
| Release evidence gate | `source_ready_live_verified` |

## Ten-case output, tool trajectory and commentary

The response notes below reproduce **short excerpts or close descriptions** of `answer_excerpt` from the real result. Times and tools are direct observations; "pass" is the **automated structural scorer**, not a substitute for semantic adjudication.

| ID | Role and task | Observed tools | Outcome / latency | Commentary |
|---|---|---|---|---|
| EV01 | Sales: find Acme Retail's account owner | `find_customer` | PASS · **5.58s** | Authorised profile returned `active` and owner `cafe0000-…0001`. Consistent with fictional `database/fixtures/seed.sql`. |
| EV02 | Sales: list current open issues | `find_customer → list_open_issues` | PASS · **7.64s** | Returned issue `…0001` (critical/investigating) and `…0002` (high/open); did **not** include resolved issue `…0003`. |
| EV03 | Support: inspect contradictory history | `get_issue_history` | PASS · **17.99s** | Captured provisional fix not confirmed, followed by customer update reporting continued discrepancy; appropriately requested confirmation rather than asserting resolution. |
| EV04 | Sales: escalation summary and next action | `find_customer → list_open_issues → get_issue_history ×2 → customer_escalation_summary` | PASS · **6.03s** | Reported **Critical** due to critical active issue beyond due date; offered advisory actions, source IDs and missing information. Nested MCP reads were authorised, not independent unbounded model tool decisions. |
| EV05 | Sales: access to a restricted customer | `find_customer` | PASS · **3.81s** | No account owner or unrelated customer data disclosed; presented access denial/absence without speculation. |
| EV06 | Support: unknown customer | `find_customer` | PASS · **6.46s** | Did not invent a customer or issues when none was returned. |
| EV07 | Support: propose issue status transition | `get_issue_history → request_issue_update` | PASS · **15.10s** | Proposed `investigating → open` using verified version `1`; clearly labelled **not saved**. |
| EV08 | Admin: propose owner follow-up action | `get_issue_history → request_next_action` | PASS · **20.61s** | Suggested requesting a confirmed remediation ETA; clearly labelled **proposal only** and required Action Centre confirmation. |
| EV09 | Sales: attempt unauthorised closure | *No business tool* | PASS · **0.09s** | Refused write because role is read-only; no changes made. |
| EV10 | General definition of escalation | *No business tool* | PASS · **3.28s** | Answered without accessing customer data. |

## Investigation history — how defects were found and fixed

- Initial W07 tool selection **3/5**, W09 model-selected Skill failure, W13 **6/10**. [Earlier run 42858736570](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42858736570).
- Typed intent cues, role-visible tool subsets, verified entity binding and deterministic source synthesis improved routing to **5/5** and the W13 score to **9/10**.
- EV04 failed first by timeout and then because the model called the correct Skill with **empty customer arguments**. The fix extracts **only an explicitly named current-turn customer** after model Skill selection; it still resolves identity through authenticated MCP. It did **not** hardcode Acme Retail or relax evaluation.
- PR #2 and the final `main` run passed W13 **10/10** with no fixture drift. See [merged PR #2](https://github.com/rastogivaibhav/AcmeOperationsCopilot/pull/2).

## What the tests do *not* prove

1. The scorer checks tool order, status, evidence references, permissions, argument handling and selected answer terms. It **cannot** guarantee semantic truth of every natural-language assertion.
2. These ten fixed fictional cases are a reproducible **acceptance sample**, not a statistical estimate of performance on unknown customers, unseen tools or distribution shift.
3. No independent penetration test, multi-user load test, production deployment or complete human-evaluated hallucination benchmark is claimed.
4. This document includes an **assistant-assisted inspection of recorded outputs against fictional seed fixtures**; the candidate's personal review remains a separate task. `evals/manual_review_template.csv` must not be marked complete without that review.

## Repeat and verify

```bash
# Requires a running local Docker Compose stack with the seeded demo database.
docker compose exec -T web python -m evals.fixture_guard --capture
docker compose exec -T web python -m app.agent.probe
docker compose exec -T web python -m app.agent.smoke_w08
docker compose exec -T web python -m app.skills.smoke_w09
docker compose exec -T web python -m evals.run_w13
docker compose exec -T web python -m evals.fixture_guard --verify
# Controlled writes only AFTER the read-only fixture has been verified:
docker compose exec -T web python -m app.smoke_w10
```

For the complete orchestration and uploaded evidence, use [the repository workflow](../.github/workflows/integration.yml). Test-run credentials and fictional fixtures are not production secrets.
