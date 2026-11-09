"""Run ten actual LangGraph + Ollama + authenticated MCP questions in Docker.

    docker compose exec -T web python -m evals.run_w13

This command NEVER fabricates results. A complete report is always written,
including failure and runtime blocker cases. No human-grounding claim is inferred
from simple keyword or source-ID checks.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import uuid

from evals.w13_scoring import score_agent_case, validate_cases, summarise

INPUT = Path(__file__).with_name("w13_cases.json")
OUTPUT = Path("evals/results/w13-live.json")
MARKDOWN = Path("evals/results/w13-live-report.md")


def _report_markdown(report: dict) -> str:
    rows = [
        "# W13 Live Evaluation — Acme Operations Copilot",
        "", f"**Executed:** {report['timestamp_utc']}",
        f"**Model:** {report.get('model') or 'not available'}",
        f"**Live runtime verified:** {report.get('live_runtime_verified', False)}",
        "", "## Results", "",
        "| Case | Role | Result | Time (ms) | Failed checks |",
        "|---|---|---|---:|---|",
    ]
    for case in report["cases"]:
        failed = [k for k, ok in case.get("checks", {}).items() if not ok]
        rows.append(f"| {case['id']} | {case['role']} | "
                    f"{'PASS' if case.get('passed') else 'FAIL'} | "
                    f"{case.get('elapsed_ms', 0)} | {', '.join(failed) or '—'} |")
    summ = report.get("summary", {})
    rows.extend(["", f"**Automated structural passes:** {summ.get('passed',0)} / {summ.get('case_count',10)}",
                 "", "## Limitations and commentary", "",
                 "- A PASS validates the reported structure, expected tool sequence, some factual terms and observed evidence IDs. It does not prove semantic groundedness.",
                 "- Review every generated recommendation and claimed business fact against the supplied tool data, checking omitted context and potential hallucination.",
                 "- This suite does not perform approved writes. Separate W10 live tests verify RBAC, explicit human confirmation, database receipts and idempotency.",
                 "- Model output and machine timing are meaningful only if `live_runtime_verified` is true. Do not use simulated/unit results as live measurements.",
                 "- A case failure is retained; never relabel it successful without rerunning and preserving evidence.",
                 "", "## Runtime errors", ""])
    rows.extend(f"- {e}" for e in report.get("blockers", []))
    if not report.get("blockers"):
        rows.append("- None recorded by the harness.")
    return "\n".join(rows) + "\n"


async def evaluate(input_path: Path = INPUT, output_path: Path = OUTPUT) -> int:
    spec = json.loads(input_path.read_text(encoding="utf-8"))
    cases = spec["cases"]
    validate_cases(cases)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = {"suite": spec["suite"],
              "timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "model": os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
              "live_runtime_verified": False, "cases": [], "blockers": []}
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from app.agent.probe import acquire_token
        from app.agent.blueprint import load_blueprint
        from app.agent.graph import build_graph, execute_turn
        from app.agent.transports import AuthenticatedMCP, OllamaChat

        model = OllamaChat()
        await model.check_model()
        async with AsyncPostgresSaver.from_conn_string(os.environ["DATABASE_URL"]) as saver:
            await saver.setup()
            graph = build_graph(saver)
            for case in cases:
                started = time.perf_counter()
                record = {"id": case["id"], "role": case["role"],
                          "category": case.get("category", ""), "passed": False}
                try:
                    token = await acquire_token({"sales_user": "sales", "support_user": "support", "admin": "admin"}[case["role"]])
                    async with AuthenticatedMCP(token) as mcp:
                        # New thread per case to avoid contaminating independent results.
                        observed = await execute_turn(graph, str(uuid.uuid4()), case["question"],
                                                      load_blueprint(case["role"]), model, mcp)
                        outcome = score_agent_case(case, observed)
                        record.update(outcome)
                        record["answer_excerpt"] = str(observed.get("answer") or "")[:2500]
                except Exception as exc:
                    # Only the class is persisted; external exception text may include secrets.
                    record["error_class"] = type(exc).__name__
                record["elapsed_ms"] = round((time.perf_counter() - started)*1000)
                report["cases"].append(record)
                print(f"W13_{'PASS' if record['passed'] else 'FAIL'} {case['id']} ({record['elapsed_ms']}ms)", flush=True)
        report["live_runtime_verified"] = len(report["cases"]) == len(cases)
    except Exception as exc:
        report["blockers"].append(type(exc).__name__)
        print("W13_LIVE_BLOCKED", type(exc).__name__)
    report["summary"] = summarise(report["cases"])
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    companion = output_path.with_name("w13-live-report.md")
    companion.write_text(_report_markdown(report), encoding="utf-8")
    if report["live_runtime_verified"] and report["summary"]["passed"] == len(cases):
        print("W13_10_CASE_STRUCTURAL_GATE_PASS")
        return 0
    print(f"W13_RESULT {report['summary']['passed']}/{len(cases)} verified={report['live_runtime_verified']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(evaluate()))
