# W09 — Customer Escalation Summary Skill

**Date:** 2026-11-09
**Status:** Implemented and offline-tested; NOT yet verified against a running Keycloak/MCP/PostgreSQL/Ollama/Docker stack.

## What was delivered

- `app/skills/escalation.py`: reusable, versioned, **read-only** Customer Escalation Summary Skill (`customer_escalation_summary`, `1.0.0`).
- A model-visible JSON-schema tool for invoking the Skill with a verified customer UUID and optional authorised issue UUIDs. The model chooses whether to call it; it is **not** forced on every question.
- A typed Pydantic `EscalationReport` contract containing executive summary, risk level, issue assessments, evidence references, missing information, proposed next actions and `advisory_only=true`.
- Deterministic risk classification using the existing PostgreSQL-backed MCP fields; no invented monetary impact, owner, SLA or remediation ETA.
- An `AuditedReadOnlyMCP` wrapper which restricts internal calls to `list_open_issues` and `get_issue_history` and records nested tool name, outcome, evidence refs and latency.
- Explicit fail-closed handling for missing permissions, unauthorised issue selection, changed issue state, history mismatch and excessively large issue sets; explicit `Unknown` risk when no active issues are visible.
- Blueprint inheritance: Enterprise declares the approved Skill; all three role profiles inherit it. Tool-call schemas are composed dynamically from *actual MCP* tool definitions and the local Skill spec. The Enterprise/role versions advance from `0.2.0` to `0.3.0` to avoid silently changing existing checkpoint behaviour.
- `tests/test_w09_escalation_skill.py`: deterministic tests for rubric, citations, missing data, contradictions, model-selected Skill calls, forbidden tool execution, typed contracts and scope controls.
- `app/skills/smoke_w09.py`: real-system acceptance test that runs the direct authenticated Skill and then checks whether the local model actually selects the Skill through LangGraph. Writes a machine-readable report, never fabricated results.

## Risk rubric — v1.0

| Condition (active issues only) | Risk | Example |
|---|---|---|
| Critical-priority AND SLA overdue | Critical | Payment discrepancy, unresolved past due date |
| Critical priority without verified breach; OR high priority overdue; OR 2+ explicitly escalated updates | High | Critical incident with missing SLA, or overdue high-priority issue |
| Medium/high priority without higher triggers | Medium | Active high-priority issue with SLA not yet due |
| Low priority and no higher triggers | Low | Low-severity active issue |
| No authorised active issues visible | Unknown | Abstain; does not assert that the customer has no risk |

All timestamps are UTC, and the evaluation timestamp is included in the result. In a live incident system the rubric should be calibrated with domain experts, and SLA semantics and impact should be supported by structured authoritative data.

### Information the system refuses to invent

- A confirmed remediation ETA or financial/customer impact, because neither is a structured field in the seed schema.
- The latest issue outcome when evidence contains an explicitly marked contradictory update.
- Customer-wide risk when the user cannot see any open issue, or when the read fails.
- A persisted action. Recommendations are always `persisted=false` and `requires_human_decision=true`.

### Limitations and trade-offs

- The Skill does not create a separate system identity or bypass Keycloak. Scope is enforced independently by the existing MCP service.
- The Skill accepts a customer UUID; natural-language questions by name depend on the LLM first invoking `find_customer` to obtain the authorised identifier. The W09 LIVE smoke also probes the model directly with a known ID to isolate the Skill-selection requirement.
- Explicit contradiction detection recognises tagged contradictions; it cannot semantically reconcile arbitrary prose. Multiple escalation signals are derived conservatively from explicit text markers. No LLM claims about the content of the notes are used to derive the risk score.
- A request is bounded to 12 open issues; larger workloads return an explicit unavailable response instead of silently omitting records. Long resulting tool payloads may be rejected by the existing W08 tool size limit.
- The latest issue record is checked against the list snapshot before risk scoring. A conflicting mid-run update fails closed rather than yielding a stale risk assessment.
- Each nested MCP tool call appears as a nested tool event, but complete OpenTelemetry spans and durable event storage are **W12** work.
- Support issue status mutation and model-assisted admin confirmation are **W10**, not implemented here. W09 remains read-only for *every* role.
- There is no successful live Docker/Ollama validation in this authoring environment. Do not report the 87 offline tests as if they covered real model tool selection or network authentication.

## Offline checks

```bash
python -m compileall -q app acme_shared mcp_server database tests
python -m pytest -q tests
```

**Observed:** 87 tests passed; Python source compiles. These are source/offline tests with synthetic MCP transport fixtures, not live integration.

## Required live acceptance gate

```bash
cp -n .env.example .env
docker compose up --build -d
docker compose exec web python -m app.smoke
docker compose exec web python -m app.agent.smoke_w08
docker compose exec web python -m app.skills.smoke_w09
docker compose cp web:/code/evals/results/w09-live.json ./evals/results/w09-live.json
```

The live probe records *separately* whether:
1. The direct Skill correctly retrieves real Acme Retail issue records through authenticated MCP, produces `Critical` risk from the seeded overdue incident, returns evidence references and remains advisory.
2. The Ollama model actually selects and executes `customer_escalation_summary` through LangGraph, produces evidence and stores a checkpoint.

**Live gate is not passed** unless `w09-live.json` reports `verified=true`. On failure the probe exits nonzero and records only safe error classes.

## Next project gate

**W10:** complete role-controlled support issue-status mutation and admin next-action workflow, with explicit human confirmation and idempotent DB writes. Then W11/W12 UX/observability and W13 evaluations.
