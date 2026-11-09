# W07 — Local Ollama tool-call spike and evidence gate

Status: **Implemented / offline tests passed / live Docker-Ollama-MCP benchmark NOT executed.**
This is not the W08 LangGraph runtime, the W09 Skill, or an end-to-end EY assessment result.

## Added files

- `app/agent/tool_probe.py`: bounded model/tool loop; MCP-originated JSON schemas; read-only allowlist; validated tool arguments; no fabricated tool fallback; recorded tool sequence, status and evidence IDs.
- `app/agent/transports.py`: actual Ollama `POST /api/chat` tool API and authenticated MCP Streamable HTTP client. Model never receives bearer tokens.
- `app/agent/probe.py`: live CLI, local test-user token acquisition, explicit gate status, machine-readable results. Credentials are never included in reports.
- `evals/w07_cases.json`: five scenarios, including customer lookup, chained lookup/open-issues, history of a contradictory issue, sales-user scope denial, and no unnecessary tool call.
- `tests/test_w07_tool_probe.py`: deterministic offline contract tests using a fake model and fake tool transport. These are not evidence that Qwen selected the correct tools.

## Run live (Docker machine)

```bash
# Bring up actual Postgres, Keycloak, Redis, MCP, Ollama and app
cp -n .env.example .env
# First run pulls multiple images and a local model
# Use without --build if images already built
docker compose up --build -d
# Check platform fundamentals before W07
docker compose exec web python -m app.smoke
docker compose exec web python -m app.smoke_w06
# Time the model's actual chosen MCP tools
# This command exits nonzero on any mandatory-case failure.
docker compose exec web python -m app.agent.probe \
  --output /code/evals/results/w07-live.json
```

The live evaluator prints `LIVE_W07_TOOL_CALL_GATE_PASS` only when all five cases pass with successful model completion, expected ordered tool invocations and required **real MCP evidence references**. It prints `W07_BLOCKED` for a dependency error; it records truthful failures to JSON. `--output` writes into the web container; because the source is copied into the image, copy out the report with:

```bash
docker compose cp web:/code/evals/results/w07-live.json ./evals/results/w07-live.json
```

The source code does **not** manufacture a passing report. The evaluator's `passed` and `live_runtime_verified` fields remain absent from disk until a real run writes the results.

## Evaluation boundary

This gate checks model-generated tool selection, ordered tool dependencies, real tool status and evidence identifiers. It does **not** establish answer correctness, relevance, recommendation quality or production readiness. Those require W09/W13 evaluations. A model that answers from its own knowledge without a required MCP call **fails**.

If the 3B model consistently fails to chain lookup -> issues, test a larger *tool-capable* local model and record results for both. Do not hardcode the expected calls to make the evaluation pass.

## Security boundary

The tool probe is **read-only**. `create_next_action` is never offered to the LLM, even if the MCP server advertises it. The backend validates tool names and arguments again before dispatch; the MCP server validates the authenticated token and customer-level scope. A future W08/W10 implementation must add admin write flows only behind authenticated human approval and idempotency validation.

## Known limits

- No Docker Engine, PyPI access or local Ollama daemon exists in the authoring environment, so no real tool-call benchmarking or image runtime verification can be asserted.
- The existing foundation's local Keycloak dual-audience tokens and password grant are development shortcuts; replace them for production with audience-scoped delegation and a dedicated integration-test client.
- Ollama requests currently use native JSON tool calling, temperature 0, six model rounds and eight tool calls maximum. These budgets are safety limits, not quality guarantees.
- The currently configured `qwen2.5:3b` advertises tool support, but that is not evidence it can reliably complete this particular multi-step enterprise case. The mandatory metric is measured behaviour, not catalogue capability.

## Exit criteria

1. Real signed Keycloak tokens accepted by MCP, with sales customer scope correctly restricted.
2. Model selects `find_customer`, `list_open_issues`, `get_issue_history` as appropriate, and passes expected evidence references.
3. No write tool is executed; no guessed hardcoded tool is invoked when the model fails to call a tool.
4. Logs and machine-readable results record tool selection, statuses and timings without raw access tokens.
5. Live evaluation report committed to the final submission only *after* actual execution.
