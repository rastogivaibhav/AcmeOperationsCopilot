"""Live W09 acceptance probe. Requires running Docker Compose, Keycloak, MCP, Ollama.

    docker compose exec web python -m app.skills.smoke_w09

This writes an explicit measured report. It does NOT substitute a scripted skill
call for the second, model-selected agent invocation.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.agent.blueprint import load_blueprint
from app.agent.graph import build_graph, execute_turn
from app.agent.probe import acquire_token
from app.agent.transports import AuthenticatedMCP, OllamaChat
from app.skills.escalation import SKILL_NAME, run_customer_escalation_summary

ACME_RETAIL = "ac000000-0000-4000-8000-000000000001"


async def evaluate() -> int:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    outfile = Path("evals/results/w09-live.json")
    outfile.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "suite": "W09 live: Authenticated MCP Skill + LLM-selected Skill via LangGraph",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model": os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
        "direct_skill_passed": False, "model_selected_skill_passed": False,
        "verified": False, "steps": [], "errors": [],
    }
    try:
        token = await acquire_token("sales")
        async with AuthenticatedMCP(token) as mcp:
            # Independent deterministic Skill check through REAL MCP + PostgreSQL.
            direct = await run_customer_escalation_summary(mcp, customer_id=ACME_RETAIL)
            result = direct.get("data") or {}
            report["steps"].append({
                "step": "direct_authenticated_skill", "status": direct.get("status"),
                "risk_level": result.get("risk_level"),
                "issue_count": len(result.get("issue_assessments", [])),
                "evidence_refs": direct.get("evidence_refs", []),
                "recommended_action_count": len(result.get("recommended_actions", [])),
            })
            if (direct.get("status") != "ok" or result.get("risk_level") != "Critical"
                    or not result.get("advisory_only") or not direct.get("evidence_refs")):
                raise AssertionError("DIRECT_SKILL_RESULT_NOT_GROUNDED")
            report["direct_skill_passed"] = True

            model = OllamaChat()
            await model.check_model()
            blueprint = load_blueprint("sales_user")
            async with AsyncPostgresSaver.from_conn_string(os.environ["DATABASE_URL"]) as saver:
                await saver.setup()
                graph = build_graph(saver)
                thread = str(uuid.uuid4())
                agent = await execute_turn(
                    graph, thread,
                    "Use the customer_escalation_summary Skill for customer ID "
                    + ACME_RETAIL + ". Report the risk and cite evidence.",
                    blueprint, model, mcp,
                )
                events = agent.get("tool_events", [])
                report["steps"].append({
                    "step": "model_selected_skill", "status": agent.get("status"),
                    "tool_events": events, "evidence_refs": agent.get("evidence_refs", []),
                })
                if (agent.get("status") != "complete" or not any(
                        e.get("name") == SKILL_NAME and e.get("status") == "ok"
                        for e in events) or not agent.get("evidence_refs")):
                    raise AssertionError("MODEL_DID_NOT_EXECUTE_SKILL")
                state = await graph.aget_state({"configurable": {"thread_id": "conv:" + thread}})
                if not state or not state.values.get("messages"):
                    raise AssertionError("SKILL_GRAPH_CHECKPOINT_MISSING")
                report["model_selected_skill_passed"] = True
        report["verified"] = True
    except Exception as exc:
        # Do not log bearer tokens or remote exception bodies in eval artifacts.
        report["errors"].append(type(exc).__name__)
    outfile.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("W09_LIVE_PASS" if report["verified"] else "W09_LIVE_BLOCKED", outfile)
    return 0 if report["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(evaluate()))
