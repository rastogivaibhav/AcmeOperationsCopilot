"""Resolve model references only from authenticated MCP evidence in the current turn.

No role escalation, guessed identifiers, or new tool selection is performed here.
The LLM decides *which* tool to call; this module binds an ambiguous argument
only when an earlier successful, authorised lookup supplies exactly one UUID.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

from app.agent.intent import explicit_customer_id

UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
IDENTIFIER_KEYS = frozenset({
    "id", "customer_id", "issue_id", "update_id", "account_owner_sub",
    "author_sub", "keycloak_sub", "created_by_sub", "actor_sub", "owner_sub",
})


def _uuid(value: Any) -> str | None:
    try:
        return str(uuid.UUID(value)) if isinstance(value, str) else None
    except ValueError:
        return None


def _current_turn_messages(messages: list[dict]) -> list[dict]:
    last_user = max((i for i, m in enumerate(messages) if m.get("role") == "user"), default=-1)
    return messages[last_user + 1:]


def trusted_payloads(messages: list[dict]) -> list[tuple[str, dict]]:
    """Only successful MCP tool responses in the current turn are usable."""
    payloads = []
    for msg in _current_turn_messages(messages):
        if msg.get("role") != "tool":
            continue
        try:
            value = json.loads(msg.get("content") or "")
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict) and value.get("status") == "ok":
            payloads.append((str(msg.get("tool_name") or ""), value))
    return payloads


def verified_customer_ids(messages: list[dict]) -> set[str]:
    ids = set()
    for name, payload in trusted_payloads(messages):
        if name == "find_customer" and isinstance(payload.get("data"), dict):
            v = _uuid(payload["data"].get("id"))
            if v:
                ids.add(v)
    return ids


def bind_customer_argument(name: str, arguments: dict, messages: list[dict]) -> tuple[dict, str | None]:
    """Never replace a valid but different UUID; reject mismatched lookups."""
    if name not in {"list_open_issues", "customer_escalation_summary"}:
        return arguments, None
    # The Skill may resolve a customer name internally via scoped MCP.
    if name == "customer_escalation_summary":
        # The Skill performs its own authenticated, customer-scoped MCP
        # lookup. A user-provided valid ID is a locator, never authorisation.
        # No evidence is invented or used to bypass MCP permissions.
        if arguments.get("customer_name"):
            return arguments, None
        if _uuid(arguments.get("customer_id")):
            return arguments, None
    ids = verified_customer_ids(messages)
    value = arguments.get("customer_id")
    provided = _uuid(value)
    if provided:
        if ids and provided not in ids:
            return arguments, "CUSTOMER_ID_MISMATCH_WITH_VERIFIED_LOOKUP"
        # A generic user request does not authorise the model to invent a
        # customer UUID, even one the caller could otherwise read. Require a
        # prior current-turn lookup or an explicitly supplied customer ID.
        # The MCP layer independently verifies actual customer permissions.
        if name == "list_open_issues" and not ids and explicit_customer_id(messages) != provided:
            return arguments, "VERIFIED_CUSTOMER_ID_REQUIRED"
        return arguments, None
    if len(ids) == 1:
        copied = dict(arguments)
        copied["customer_id"] = next(iter(ids))
        return copied, "BOUND_FROM_VERIFIED_CUSTOMER_LOOKUP"
    return arguments, "VERIFIED_CUSTOMER_ID_REQUIRED"


def bind_issue_argument(name: str, arguments: dict, messages: list[dict]) -> tuple[dict, str | None]:
    """Resolve a proposal's issue ID only after a successful issue history lookup."""
    if name not in {"request_issue_update", "request_next_action"}:
        return arguments, None
    ids: set[str] = set()
    for tool_name, payload in trusted_payloads(messages):
        data = payload.get("data")
        if tool_name == "get_issue_history" and isinstance(data, dict):
            issue = data.get("issue")
            if isinstance(issue, dict):
                found = _uuid(issue.get("id"))
                if found:
                    ids.add(found)
    value = _uuid(arguments.get("issue_id"))
    if value:
        if not ids:
            return arguments, "VERIFIED_ISSUE_HISTORY_REQUIRED"
        return (arguments, "ISSUE_ID_MISMATCH_WITH_VERIFIED_HISTORY") if value not in ids else (arguments, None)
    if len(ids) == 1:
        updated = dict(arguments)
        updated["issue_id"] = next(iter(ids))
        return updated, "BOUND_FROM_VERIFIED_ISSUE_HISTORY"
    return arguments, "VERIFIED_ISSUE_ID_REQUIRED"


def trusted_identifiers(messages: list[dict]) -> set[str]:
    """Identifiers from real MCP data, for groundedness checks (not permissions)."""
    discovered: set[str] = set()
    def visit(obj: Any) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in IDENTIFIER_KEYS:
                    normalized = _uuid(value)
                    if normalized:
                        discovered.add(normalized)
                if isinstance(value, (dict, list)):
                    visit(value)
        elif isinstance(obj, list):
            for value in obj:
                visit(value)
    for _, payload in trusted_payloads(messages):
        visit(payload.get("data"))
    return discovered


def redact_unverified_identifiers(answer: str, messages: list[dict]) -> tuple[str, bool]:
    """Suppress model-invented UUIDs while retaining quoted user identifiers."""
    user_ids = set()
    for m in messages:
        if m.get("role") == "user":
            user_ids.update(_uuid(s) for s in UUID_RE.findall(str(m.get("content") or "")))
    allowed = trusted_identifiers(messages) | user_ids
    replaced = False
    def sub(match: re.Match) -> str:
        nonlocal replaced
        if _uuid(match.group(0)) in allowed:
            return match.group(0)
        replaced = True
        return "[unverified identifier omitted]"
    clean = UUID_RE.sub(sub, answer)
    if replaced:
        clean += "\n\nNote: An identifier not supported by retrieved records was omitted."
    return clean, replaced
