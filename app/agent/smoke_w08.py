"""W08 live integration gate; run INSIDE the web container after Docker startup.

   docker compose exec web python -m app.agent.smoke_w08

Uses a local-only Keycloak demo user and live MCP/Ollama/PostgreSQL, not mocked data.
Persists a machine-readable report and exits nonzero on missing evidence/checkpoints.
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


async def evaluate() -> int:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    output = Path("evals/results/w08-live.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    thread = str(uuid.uuid4())
    report = {"suite": "W08 live LangGraph + authenticated MCP + Postgres checkpoint",
              "timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "model": os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
              "verified": False, "steps": [], "errors": []}
    try:
        token = await acquire_token("sales")
        model = OllamaChat()
        await model.check_model()
        blueprint = load_blueprint("sales_user")
        async with AsyncPostgresSaver.from_conn_string(os.environ["DATABASE_URL"]) as saver:
            await saver.setup()
            graph = build_graph(saver)
            async with AuthenticatedMCP(token) as mcp:
                first = await execute_turn(graph, thread, "Find the customer Acme Retail and cite the customer record ID.",
                                           blueprint, model, mcp)
                report["steps"].append({"step": "initial", "status": first["status"],
                                         "tools": [e["name"] for e in first["tool_events"]],
                                         "evidence_refs": first["evidence_refs"]})
                if first["status"] != "complete" or not any(
                        e["name"] == "find_customer" and e["status"] == "ok"
                        for e in first["tool_events"]):
                    raise AssertionError("LIVE_TOOL_SELECTION_FAILED")
            snapshot = await graph.aget_state({"configurable": {"thread_id": "conv:" + thread}})
            if not snapshot or len(snapshot.values.get("messages", [])) < 2:
                raise AssertionError("CHECKPOINT_NOT_WRITTEN")
            old_count = len(snapshot.values["messages"])
        # Fresh Postgres connection and recompiled graph: no in-memory continuity.
        async with AsyncPostgresSaver.from_conn_string(os.environ["DATABASE_URL"]) as reopened:
            restored_graph = build_graph(reopened)
            restored = await restored_graph.aget_state({"configurable": {"thread_id": "conv:" + thread}})
            if len(restored.values.get("messages", [])) != old_count:
                raise AssertionError("CHECKPOINT_NOT_RECOVERED")
            report["steps"].append({"step": "new_process_equivalent_restore",
                                     "status": "passed", "persisted_message_count": old_count})
        report["verified"] = True
    except Exception as exc:
        # Never persist raw Keycloak/MCP/HTTP exceptions, which may contain secrets.
        report["errors"].append(type(exc).__name__)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("W08_LIVE_PASS" if report["verified"] else "W08_LIVE_BLOCKED", output)
    return 0 if report["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(evaluate()))
