"""Run W07 live Ollama/MCP integration from inside web container.

Usage: docker compose exec web python -m app.agent.probe
No live score is claimed without executing this command against actual services.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from app.agent.tool_probe import run_probe, score_probe, ProbeResult
from app.agent.transports import AuthenticatedMCP, OllamaChat


def load_cases(path: Path) -> list[dict]:
    root = json.loads(path.read_text(encoding="utf-8"))
    cases = root["cases"]
    if not cases or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Empty or duplicated W07 cases")
    for case in cases:
        if case["role"] not in {"sales", "support", "admin"}:
            raise ValueError("Unrecognised role")
        if not isinstance(case["expected_tools"], list):
            raise ValueError("Expected tool names missing")
    return cases


async def acquire_token(role: str) -> str:
    """Temporary Direct Grant solely for local integration tests, never browser login."""
    import httpx2
    users = {"sales": ("sales-demo", "SalesLocal2026!"),
             "support": ("support-demo", "SupportLocal2026!"),
             "admin": ("admin-demo", "AdminLocal2026!")}
    user, default_password = users[role]
    password = os.getenv("W07_" + role.upper() + "_PASSWORD", default_password)
    endpoint = os.getenv("KEYCLOAK_TOKEN_URL",
                         "http://keycloak:8080/realms/acme/protocol/openid-connect/token")
    async with httpx2.AsyncClient(timeout=15) as client:
        response = await client.post(endpoint, data={
            "grant_type": "password", "client_id": "acme-web",
            "username": user, "password": password})
        response.raise_for_status()
        return response.json()["access_token"]


async def evaluate(cases_path: Path, output: Path) -> int:
    cases = load_cases(cases_path)
    case_timeout = int(os.getenv("W07_CASE_TIMEOUT_SECONDS", "150"))
    if not 30 <= case_timeout <= 240:
        raise ValueError("W07_CASE_TIMEOUT_INVALID")
    model = OllamaChat()
    # Fail fast and keep a machine-readable report of the blocker.
    report = {"suite": "W07 authenticated MCP / Ollama tool-selection spike",
              "timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "model": model.model, "evaluated_cases": [], "passed": 0,
              "total": len(cases), "live_runtime_verified": False,
              "case_timeout_seconds": case_timeout}
    try:
        await model.check_model()
        for case in cases:
            try:
                async with asyncio.timeout(case_timeout):
                    token = await acquire_token(case["role"])
                    async with AuthenticatedMCP(token) as mcp:
                        observed = await run_probe(case["query"], model, mcp)
            except Exception as exc:
                # Persist the error type, not exception details or auth tokens.
                observed = ProbeResult(error="CASE_TIMEOUT" if isinstance(
                    exc, TimeoutError) else type(exc).__name__)
            scored = score_probe(observed, case["expected_tools"],
                                 expected_status=case.get("expected_status", "ok"),
                                 expect_no_tools=case.get("expect_no_tools", False),
                                 required_evidence_refs=case.get("required_evidence_refs", []))
            report["evaluated_cases"].append({
                "id": case["id"], "role": case["role"],
                "query": case["query"], **scored,
                "observed": observed.as_dict()})
            status = "PASS" if scored["passed"] else "FAIL"
            print(f"W07_{status} {case['id']} {scored['actual_tools']} latency_ms={observed.latency_ms}")
        report["passed"] = sum(1 for r in report["evaluated_cases"] if r["passed"])
        report["live_runtime_verified"] = True
    except Exception as exc:
        # Deliberately exclude exception message to avoid ever leaking tokens in reports.
        report["fatal_error"] = type(exc).__name__
        print("W07_BLOCKED", type(exc).__name__)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"W07_RESULT {report['passed']}/{report['total']} report={output}")
    if report["passed"] == report["total"] and report["live_runtime_verified"]:
        print("LIVE_W07_TOOL_CALL_GATE_PASS")
        return 0
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=Path("evals/w07_cases.json"))
    parser.add_argument("--output", type=Path, default=Path("evals/results/w07-live.json"))
    args = parser.parse_args()
    return asyncio.run(evaluate(args.cases, args.output))


if __name__ == "__main__":
    raise SystemExit(main())
