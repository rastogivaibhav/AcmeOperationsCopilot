# Acme Operations Copilot — measured agent evaluation

**Completed full-stack acceptance (11 November 2026): PASS on PR #2 source revision**
`3437902f4448b002d1e978feb0d2ce06e6451f3e`.

- [Full live Compose / Ollama / Keycloak / MCP evidence — GitHub Actions run 42983299825](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42983299825) (download the private `acme-live-evaluation` artifact for raw per-case JSON).
- [Source CI — run 42983305290](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42983305290).
- Merged into `main` as `1a2b936d3bd3ddc77807ad170de6617e6d1f163e` ([PR #2](https://github.com/rastogivaibhav/AcmeOperationsCopilot/pull/2)).
- [Post-merge CI — run 42984994299](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42984994299): passed. [Post-merge full-stack evaluation — run 42984994525](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42984994525): **PASS** on merged `main` commit `1a2b936d3bd3`, W07 **5/5**, W08/W09 PASS, W13 **10/10**, fixture integrity, writes and release gate all passed. EV04 completed in **5.831 seconds** on this post-merge run.

## Completed reference-run scorecard

| Gate | Observed result |
|---|---|
| Offline/static Python suite | **206 passed** |
| Both custom Docker image builds | Passed |
| Compose startup, health, database fixture | Passed |
| Keycloak/OIDC/JWT, authenticated MCP and customer scope | Passed |
| Browser sign-in, conversation recovery and cross-user isolation | Passed |
| W07 model-selected tool routing | **5 / 5** |
| W08 LangGraph/checkpoint execution | Passed |
| W09 direct and model-selected escalation Skill | Passed |
| W13 ten-case business evaluation | **10 / 10 structural passes** |
| Read-only evaluation fixture checksum | Passed, unchanged |
| W10 controlled writes, RBAC, approval and audit smoke | Passed |
| Submission evidence gate | `source_ready_live_verified` |

### W13 case-level results (real model, measured duration)

| Case | Outcome | Duration |
|---|---|---:|
| EV01 — Sales customer profile | PASS | 9.34 s |
| EV02 — Sales open issues | PASS | 11.70 s |
| EV03 — Support conflicting issue history | PASS | 30.16 s |
| EV04 — Sales escalation Skill | **PASS** | **8.94 s** |
| EV05 — Sales scope denial | PASS | 5.98 s |
| EV06 — Support unknown account | PASS | 10.97 s |
| EV07 — Support status proposal | PASS | 24.21 s |
| EV08 — Admin next-action proposal | PASS | 35.31 s |
| EV09 — Sales write restriction | PASS | 0.07 s |
| EV10 — General question without customer tools | PASS | 4.73 s |

Durations are one successful GitHub-hosted CPU/model run, not a latency service-level guarantee. A local laptop may behave differently.

## How this changed

An earlier 10 November baseline (`47eb98b`, [run 42858736570](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42858736570)) produced **W07 3/5, W09 model-selected Skill failure and W13 6/10**. Subsequent typed routing, authenticated evidence preconditions and bounded source synthesis improved the result to W07 5/5 and W13 9/10. PR #2 resolved EV04 by binding a narrowly extracted, explicit current-turn customer name **after the model selected the authorised Skill**, leaving all customer/issue access under MCP and Keycloak. The final reference run achieved W13 10/10.

## Limitations and required human review

**Automated PASS measures tool trajectories, required evidence references, response terms, role restrictions and proposal boundaries. It does not establish that every free-text claim, inference, recommendation or quoted update is semantically correct.** The candidate should complete `evals/manual_review_template.csv` using the actual artifact, assess contradictions and missing information, and confirm the demo covers approved/denied writes. These assessments are **not claimed as completed**.

This is a local, fictional technical-assessment implementation. Demo credentials, HTTP/Keycloak development configuration and seed data must not be exposed in a public deployment. Keep the repo private while EY's confidentiality restrictions apply.
