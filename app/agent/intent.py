"""Typed request cues and verified reference binding (not an authorisation layer).

The model still decides the tools. This module only extracts *explicit*
user references and supplies narrow guidance; MCP enforces resource scope.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal
import re
import uuid

UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
Purpose = Literal["history", "proposal", "escalation", "customer_issues", "general", "other"]


@dataclass(frozen=True)
class RequestSignals:
    purpose: Purpose
    issue_id: str | None


def last_question(messages: list[dict]) -> str:
    return next((str(m.get("content") or "") for m in reversed(messages)
                 if m.get("role") == "user"), "")


def analyse_request(messages: list[dict]) -> RequestSignals:
    text = last_question(messages)
    lower = text.lower()
    matches = tuple(dict.fromkeys(str(uuid.UUID(v)) for v in UUID_RE.findall(text)))
    # An issue reference is typed only if the user explicitly calls it an issue.
    issue = matches[0] if len(matches) == 1 and re.search(r"\bissue\b", lower) else None
    # Explicitly general/definition questions take priority over domain terms
    # such as "escalation"; they should not invoke customer data tools.
    if re.search(r"\b(?:in general|define|explain what|do not access customer records)\b", lower):
        kind: Purpose = "general"
    elif re.search(r"\b(?:propos(?:e|al)|update|change status|create (?:an? )?action)\b", lower):
        kind = "proposal"
    elif re.search(r"\b(?:escalat(?:e|ion|ion summary)|risk assessment|assess customer risk)\b",lower):
        kind = "escalation"
    elif re.search(r"\b(?:history|conflict|provisional fix)\b",lower):
        kind = "history"
    elif re.search(r"\b(?:open issues|issues currently open|currently open issues)\b",lower):
        kind = "customer_issues"
    elif re.search(r"\b(?:in one sentence|in general|define|explain what)\b",lower):
        kind = "general"
    else:
        kind = "other"
    return RequestSignals(kind, issue)


def task_guidance(messages: list[dict]) -> str:
    signals = analyse_request(messages)
    hints = []
    if signals.issue_id:
        hints.append("The user explicitly referenced issue UUID " + signals.issue_id +
                     ". Inspect get_issue_history with this exact UUID for history or proposals; "
                     "do not invent a customer name or substitute a different issue.")
    if signals.purpose == "escalation":
        hints.append("For customer escalation use the customer_escalation_summary Skill. "
                     "It accepts customer_name or a verified customer_id, and remains advisory.")
    if signals.purpose == "proposal":
        hints.append("Read issue history, its current status and version before a proposal. "
                     "Proposal tools cannot commit changes.")
    if signals.purpose == "general":
        hints.append("This is a general definition; avoid customer tools.")
    return " ".join(hints)


def explicit_customer_id(messages: list[dict]) -> str | None:
    text = last_question(messages)
    matches = tuple(dict.fromkeys(str(uuid.UUID(v)) for v in UUID_RE.findall(text)))
    return matches[0] if len(matches) == 1 and re.search(
        r"\bcustomer\s+id\b", text, re.I) else None


def bind_explicit_issue(name: str, arguments: Any,
                        messages: list[dict]) -> tuple[Any, str | None]:
    """Correct absent/invalid history IDs from one explicitly supplied user UUID."""
    if name != "get_issue_history" or not isinstance(arguments, dict):
        return arguments, None
    ref = analyse_request(messages).issue_id
    if not ref:
        return arguments, None
    value = arguments.get("issue_id")
    try:
        supplied = str(uuid.UUID(value)) if isinstance(value, str) else None
    except ValueError:
        supplied = None
    if supplied and supplied != ref:
        return arguments, "ISSUE_ID_MISMATCH_WITH_USER_REFERENCE"
    if supplied == ref:
        return arguments, None
    args = dict(arguments)
    args["issue_id"] = ref
    return args, "BOUND_FROM_EXPLICIT_USER_ISSUE"


def reject_unrelated_lookup(name: str, messages: list[dict]) -> str | None:
    signals = analyse_request(messages)
    text = last_question(messages).lower()
    if (name == "find_customer" and signals.issue_id
            and signals.purpose in {"history", "proposal"}
            and not re.search(r"\b(?:customer named|customer called|customer profile for)\b",text)):
        return "ISSUE_REQUEST_REQUIRES_ISSUE_HISTORY"
    return None
