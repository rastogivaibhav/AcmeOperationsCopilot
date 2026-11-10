"""Guarded prerequisite execution for model-suggested business proposals.

A proposal is NEVER an approved write. The mandatory issue-history lookup uses
the authenticated MCP transport and is recorded distinctly from LLM calls.
"""
from __future__ import annotations
import json
import time
import uuid
from typing import Any

from app.agent.intent import analyse_request
from app.agent.evidence import trusted_payloads
from app.actions import ALLOWED_TRANSITIONS

PROPOSALS = frozenset({"request_issue_update", "request_next_action"})


def _uuid(value: Any) -> str | None:
    try:
        return str(uuid.UUID(value)) if isinstance(value, str) else None
    except ValueError:
        return None


def _histories(messages: list[dict]) -> dict[str, dict]:
    found = {}
    for name, envelope in trusted_payloads(messages):
        if name != "get_issue_history" or not isinstance(envelope.get("data"), dict):
            continue
        issue = envelope["data"].get("issue")
        if isinstance(issue, dict):
            key = _uuid(issue.get("id"))
            if key:
                found[key] = issue
    return found


async def resolve_proposal(name: str, raw_args: Any, messages: list[dict],
                           mcp: Any) -> tuple[Any, list[dict], list[dict], str | None]:
    """Return args, extra tool messages, trace events, and optional denial code."""
    if name not in PROPOSALS or not isinstance(raw_args, dict):
        return raw_args, [], [], None
    args = dict(raw_args)
    known = analyse_request(messages).issue_id
    given = _uuid(args.get("issue_id"))
    if known and given and known != given:
        return args, [], [], "ISSUE_ID_MISMATCH_WITH_USER_REFERENCE"

    history = _histories(messages)
    extra_messages: list[dict] = []
    extra_events: list[dict] = []
    target = given or known or (next(iter(history)) if len(history) == 1 else None)
    if target is None:
        return args, [], [], "VERIFIED_ISSUE_HISTORY_REQUIRED"
    if target not in history:
        # Only a uniquely and explicitly specified issue can trigger automatic
        # prerequisite retrieval, otherwise the model must call history itself.
        if known != target:
            return args, [], [], "VERIFIED_ISSUE_HISTORY_REQUIRED"
        started = time.perf_counter()
        response = await mcp.call_tool("get_issue_history", {"issue_id": target})
        if not isinstance(response, dict) or not isinstance(response.get("status"), str):
            raise ValueError("INVALID_MCP_RESULT")
        references = response.get("evidence_refs") or []
        if not isinstance(references, list) or not all(isinstance(v,str) for v in references):
            raise ValueError("INVALID_EVIDENCE_REFS")
        extra_events.append({"name":"get_issue_history", "status":response["status"],
                            "evidence_refs":references, "duration_ms":round(
                                (time.perf_counter()-started)*1000),
                            "source":"policy_precondition","error_code":response.get("error_code")})
        content = json.dumps(response, default=str, ensure_ascii=False)
        if len(content) > 14000:
            return args, [], extra_events, "ISSUE_PRECONDITION_TOO_LARGE"
        extra_messages.append({"role":"tool", "tool_name":"get_issue_history",
                               "content":content})
        history = _histories([*messages, *extra_messages])
        if response["status"] != "ok" or target not in history:
            return args, extra_messages, extra_events, "VERIFIED_ISSUE_HISTORY_REQUIRED"
    issue = history[target]
    args["issue_id"] = target
    if name == "request_issue_update":
        version = issue.get("version")
        current = issue.get("status")
        if not isinstance(version, int) or isinstance(version,bool) or version < 1:
            return args, extra_messages, extra_events, "ISSUE_VERSION_UNAVAILABLE"
        if args.get("expected_version") is None:
            args["expected_version"] = version
        elif args["expected_version"] != version:
            return args, extra_messages, extra_events, "STALE_PROPOSAL_ISSUE_VERSION"
        if args.get("new_status") not in ALLOWED_TRANSITIONS.get(current, frozenset()):
            return args, extra_messages, extra_events, "INVALID_ISSUE_STATUS_TRANSITION"
    return args, extra_messages, extra_events, None
