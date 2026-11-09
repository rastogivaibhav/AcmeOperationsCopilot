# W13 evaluation report — evidence status

**Status: NOT EXECUTED against a live Ollama/Keycloak/MCP/PostgreSQL stack.**

This file is a truthful submission placeholder and test plan, **not a claim of 10 passing evaluations**. Run `python -m evals.run_w13` **inside the running web container** to obtain measured, timestamped results in `evals/results/w13-live.json` and `evals/results/w13-live-report.md`. Include those outputs only after an actual run and manual review.

## Test design

- Ten independent natural-language questions in `evals/w13_cases.json` across Sales, Support and Admin.
- Dynamically constructed LangGraph agent instances, real Keycloak bearer tokens, actual MCP read tools, an actual local Ollama model and PostgreSQL checkpoints.
- Automated checks for tool choice/order, tool denials, source-record presence, obvious unsupported identifiers, safe proposals and no autonomous writes.
- The W09 direct Skill verification supplies a separate deterministic check of risk classification and recommended actions.
- The W10 live smoke checks actual permission denial, confirmation, idempotent retry and database effects.

## Interpretation

Automated tool routing and evidence-ID checks are necessary but insufficient for semantic grounding. A human assessor must inspect each generated answer against its actual returned records, including the proposed next action's operational reasonableness, omitted contradictory updates, stale data, false assertions and acknowledgement of missing information.

| Metric | Result |
|---|---|
| Live 10-question pass rate | **NOT MEASURED** |
| Tool-routing accuracy | **NOT MEASURED** |
| Evidence-linked response rate | **NOT MEASURED** |
| RBAC integration pass rate | **NOT MEASURED** |
| Recommended-action quality | **NEEDS LIVE EXECUTION + HUMAN REVIEW** |
| Live latency | **NOT MEASURED** |

**Never replace `NOT MEASURED` with a unit-test pass count.**
