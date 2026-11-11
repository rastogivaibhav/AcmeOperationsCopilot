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
Purpose = Literal["history", "proposal", "escalation", "customer_issues", "customer_lookup", "general", "other"]


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
    elif re.search(r"\b(?:propos(?:e|al)|change status|(?:update|close|resolve|change) (?:the )?issue|create (?:an? )?action)\b", lower):
        kind = "proposal"
    elif ("customer_escalation_summary" in lower or
          re.search(r"\b(?:escalat(?:e|ion|ion summary)|risk assessment|assess customer risk)\b",lower)):
        kind = "escalation"
    elif re.search(r"\b(?:history|conflict|provisional fix)\b",lower):
        kind = "history"
    elif re.search(r"\b(?:open issues|issues (?:are )?currently open|currently open issues)\b",lower):
        kind = "customer_issues"
    elif re.search(r"\b(?:customer profile|account owner|look up (?:its|the) (?:customer|profile)|find (?:the )?customer)\b",lower):
        kind = "customer_lookup"
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
        hints.append("Call customer_escalation_summary directly with customer_name "
                     "or the explicit customer UUID. It performs authenticated lookups "
                     "internally and remains advisory; do not call find_customer first.")
    if signals.purpose == "proposal":
        hints.append("Select the appropriate request_issue_update or request_next_action "
                     "proposal tool directly. Its policy layer will read authoritative "
                     "issue history, status and version first. Proposals never commit writes.")
    if signals.purpose == "general":
        hints.append("This is a general definition; use no customer tools.")
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


def tools_for_request(definitions: list[dict], messages: list[dict]) -> list[dict]:
    """Typed task-specific visibility, always a SUBSET of caller's approved tools.

    The model still selects tools. Unknown/ambiguous intents retain all tools.
    Restrict only clearly typed requests; no hard-coded case IDs or answers.
    """
    signals = analyse_request(messages)
    allowed: set[str] | None = None
    if signals.purpose == "general":
        allowed = set()
    elif signals.purpose == "customer_lookup":
        allowed = {"find_customer"}
    elif signals.purpose == "customer_issues":
        allowed = {"find_customer", "list_open_issues"}
    elif signals.purpose == "history" and signals.issue_id:
        allowed = {"get_issue_history"}
    elif signals.purpose == "proposal" and signals.issue_id:
        # The authenticated proposal handler fetches issue history as a
        # mandatory read-only prerequisite. Limit the model's job to choosing
        # the requested *proposal*, never an autonomous business write.
        question = last_question(messages).lower()
        if re.search(r"\b(?:next.action|action record|contact (?:the )?owner)\b", question):
            allowed = {"request_next_action"}
        elif re.search(r"\b(?:status|reopen|close the issue)\b", question):
            allowed = {"request_issue_update"}
        else:
            allowed = {"request_next_action", "request_issue_update"}
    elif signals.purpose == "escalation":
        # Name lookup and issue histories are dependencies of the read-only
        # Skill itself, so they need not consume additional model turns.
        allowed = {"customer_escalation_summary"}
    if allowed is None:
        return definitions
    return [spec for spec in definitions
            if spec.get("function", {}).get("name") in allowed]


# Explicit customer names are untrusted resource locators, not an identity
# or authorisation source. MCP still enforces customer visibility and role.
_CUSTOMER_NAME = r"[A-Za-z][A-Za-z0-9 &'().-]{1,158}?"
_CUSTOMER_CUES = (
    re.compile(r"^\s*(?:for|regarding)\s+(?P<name>" + _CUSTOMER_NAME +
               r")\s*,\s*(?:please\s+)?(?:use|run|assess|evaluate|summari[sz]e|show)\b", re.I),
    re.compile(r"\b(?:assess|evaluate|summari[sz]e)\s+(?:the\s+)?"
               r"(?:customer\s+)?(?:escalation\s+)?risk\s+for\s+(?P<name>" +
               _CUSTOMER_NAME + r")\s*(?:[.?!]|$)", re.I),
    re.compile(r"\b(?P<name>" + _CUSTOMER_NAME +
               r")['’]s\s+(?:customer\s+)?escalation\s+risk\b", re.I),
)


def explicit_customer_name(messages: list[dict]) -> str | None:
    """Extract a customer name only from a narrow, explicit user phrase.

    Never search the entire conversation or treat arbitrary assistant/model
    output as an entity name. Ambiguous or generic requests must abstain.
    """
    question = last_question(messages)
    if not question or len(question) > 2000:
        return None
    for pattern in _CUSTOMER_CUES:
        match = pattern.search(question)
        if match:
            name = " ".join(match.group("name").strip().split())
            if (2 <= len(name) <= 160 and
                    name.casefold() not in {"a customer", "the customer", "any customer",
                                            "this customer", "my customer", "a named customer"} and
                    not UUID_RE.search(name)):
                return name
    return None


def bind_skill_customer_name(name: str, arguments: Any,
                             messages: list[dict]) -> tuple[Any, str | None]:
    """Recover a missing Skill customer name from the *current user turn*.

    Only applies after the model selected the authorised Skill. A supplied
    conflicting customer name is rejected, not silently rewritten. Customer
    existence and visibility are checked through authenticated MCP.
    """
    if name != "customer_escalation_summary" or not isinstance(arguments, dict):
        return arguments, None
    customer = explicit_customer_name(messages)
    if customer is None:
        return arguments, None
    supplied = arguments.get("customer_name")
    if isinstance(supplied, str) and supplied.strip():
        if " ".join(supplied.split()).casefold() != customer.casefold():
            return arguments, "CUSTOMER_NAME_MISMATCH_WITH_USER_REFERENCE"
        return arguments, None
    if isinstance(arguments.get("customer_id"), str):
        try:
            uuid.UUID(arguments["customer_id"])
            return arguments, None  # Existing Skill/MCP permission enforcement.
        except ValueError:
            pass
    updated = dict(arguments)
    updated.pop("customer_id", None)  # Never forward a hallucinated placeholder.
    updated["customer_name"] = customer
    return updated, "BOUND_FROM_EXPLICIT_CUSTOMER_NAME"
