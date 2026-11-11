"""Deterministic, evidence-only response composition for simple completed workflows.

The model must still select an authorised tool. This module cannot call MCP,
propose new actions, grant roles or commit writes. It only renders results from
successful authenticated MCP calls and validated local Skill/proposal outputs.
Complex/unknown requests still use the LLM after gathering evidence.
"""
from __future__ import annotations

import re
from typing import Any

from app.agent.evidence import trusted_payloads
from app.agent.intent import analyse_request, last_question


def _plain(value: Any, limit: int = 300) -> str:
    """Bound untrusted field rendering without interpreting embedded instructions."""
    if value is None:
        return "not recorded"
    return re.sub(r"\s+", " ", str(value)).strip()[:limit] or "not recorded"


def compose_verified_answer(messages: list[dict],
                            proposed_actions: list[dict]) -> str | None:
    signal = analyse_request(messages)
    question = last_question(messages)
    source = trusted_payloads(messages)
    successful: dict[str, list[Any]] = {}
    for name, payload in source:
        successful.setdefault(name, []).append(payload.get("data"))

    if signal.purpose == "history":
        histories = successful.get("get_issue_history") or []
        if not histories or not isinstance(histories[-1], dict):
            return None
        report = histories[-1]
        issue = report.get("issue")
        updates = report.get("updates")
        if not isinstance(issue, dict) or not isinstance(updates, list):
            return None
        iid = _plain(issue.get("id"), 80)
        lines = [f"Issue {iid}: status {_plain(issue.get('status'), 60)}, "
                 f"priority {_plain(issue.get('priority'), 60)}.",
                 "Recorded updates (source evidence, not verified resolution):"]
        for update in updates[-10:]:
            if not isinstance(update, dict):
                continue
            lines.append(f"- {_plain(update.get('id'), 80)}: "
                         f"{_plain(update.get('content'), 400)}")
        if not updates:
            lines.append("- No updates are recorded in the retrieved history.")
        if re.search(r"\b(?:provisional|confirm(?:ed|ation)?|conflict(?:ing|ed)?|fix)\b", question, re.I):
            lines.append("The provisional fix is not confirmed by the supplied evidence alone; "
                         "any conflicting customer updates require owner verification.")
        lines.append("Recommended next step: obtain confirmation from the issue owner "
                     "before treating the incident as resolved.")
        return "\n".join(lines)

    if signal.purpose == "escalation":
        summaries = successful.get("customer_escalation_summary") or []
        if not summaries or not isinstance(summaries[-1], dict):
            return None
        info = summaries[-1]
        if info.get("advisory_only") is not True:
            return None
        lines = [f"Customer escalation risk: {_plain(info.get('risk_level'), 40)}.",
                 _plain(info.get("executive_summary"), 550)]
        reasons = info.get("risk_reasons") or []
        if isinstance(reasons, list) and reasons:
            lines.append("Evidence-based reasons:")
            lines += [f"- {_plain(v, 260)}" for v in reasons[:6]]
        actions = info.get("recommended_actions") or []
        if isinstance(actions, list):
            lines.append("Recommended next actions (advisory; not saved):")
            for action in actions[:6]:
                if isinstance(action, dict) and action.get("persisted") is False:
                    lines.append(f"- {_plain(action.get('action'), 250)} "
                                 f"[issue {_plain(action.get('issue_id'), 80)}]")
        missing = info.get("missing_information") or []
        lines.append("Missing information:")
        if isinstance(missing, list) and missing:
            lines += [f"- {_plain(v, 240)}" for v in missing[:8]]
        else:
            lines.append("- No additional gaps identified by the Skill.")
        return "\n".join(lines)

    if signal.purpose == "proposal" and proposed_actions:
        # A proposal must already have passed typed issue-history validation.
        # This renderer creates NO new proposals or approvals.
        histories = successful.get("get_issue_history") or []
        if not histories or not isinstance(histories[-1], dict):
            return None
        issue = histories[-1].get("issue")
        if not isinstance(issue, dict):
            return None
        lines = [f"Verified issue {_plain(issue.get('id'), 80)}: "
                 f"current status {_plain(issue.get('status'), 60)}.",
                 "PROPOSAL ONLY — not saved. No business record has been changed."]
        for proposal in proposed_actions[-4:]:
            if not isinstance(proposal, dict) or str(proposal.get("issue_id")) != str(issue.get("id")):
                return None
            if proposal.get("kind") == "issue_update":
                lines.append(f"Suggested status: {_plain(proposal.get('new_status'), 60)} "
                             f"(based on verified issue version {_plain(proposal.get('expected_version'), 15)}). "
                             f"Note: {_plain(proposal.get('note'), 450)}")
            elif proposal.get("kind") == "next_action":
                lines.append(f"Suggested next action: {_plain(proposal.get('description'), 450)}")
            else:
                return None
        lines.append("Review this proposal in the Action Centre and explicitly confirm "
                     "it before any authorised write can take place.")
        return "\n".join(lines)

    if signal.purpose == "customer_issues":
        issues = successful.get("list_open_issues") or []
        if issues and isinstance(issues[-1], list):
            lines = ["Authorised open issues from the customer record:"]
            for issue in issues[-1][:15]:
                if not isinstance(issue, dict):
                    continue
                lines.append(f"- {_plain(issue.get('id'), 80)}: "
                             f"{_plain(issue.get('title'), 180)} "
                             f"(priority {_plain(issue.get('priority'), 30)}; "
                             f"status {_plain(issue.get('status'), 30)})")
            if len(lines) == 1:
                lines.append("- No open issues were returned by the scoped MCP tool.")
            return "\n".join(lines)

    if signal.purpose == "customer_lookup":
        profiles = successful.get("find_customer") or []
        if profiles and isinstance(profiles[-1], dict):
            profile = profiles[-1]
            return (f"Customer {_plain(profile.get('name'), 160)} "
                    f"(record {_plain(profile.get('id'), 80)}): "
                    f"status {_plain(profile.get('status'), 60)}; "
                    f"account owner ID {_plain(profile.get('account_owner_sub'), 80)}. "
                    "Only fields returned by the authorised customer lookup are reported.")

    # Only explicit denial/no-result responses can be summarised as unavailable.
    if signal.purpose in {"customer_lookup", "customer_issues"}:
        for msg in reversed(messages):
            if msg.get("role") != "tool" or msg.get("tool_name") != "find_customer":
                continue
            import json
            try:
                response = json.loads(msg.get("content") or "{}")
            except (ValueError, TypeError):
                return None
            if isinstance(response, dict) and response.get("status") in {"not_found", "forbidden"}:
                return ("The requested customer could not be found in your authorised "
                        "view or access was denied. No account owner or issues can be "
                        "confirmed from the available records.")
            break
    return None
