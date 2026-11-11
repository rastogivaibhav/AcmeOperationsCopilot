"""NVIDIA NeMo-inspired trajectory diagnostics for observed agent executions.

Structure only: neither a judge LLM nor keyword scoring proves that an
individual natural-language claim is factually supported.
"""
from __future__ import annotations
from typing import Any

PROPOSALS = frozenset({"request_next_action", "request_issue_update"})


def inspect_trajectory(events: Any) -> dict:
    if not isinstance(events, list):
        events = []
    ordered = [e for e in events if isinstance(e, dict)]
    selected = [str(e.get("name")) for e in ordered
                if e.get("source") not in {"policy_precondition", "skill_dependency"}
                and not e.get("parent_skill")]
    policy = [str(e.get("name")) for e in ordered
              if e.get("source") == "policy_precondition"]
    skills = [str(e.get("name")) for e in ordered if e.get("parent_skill")]
    invalid = [e.get("name") for e in ordered
               if e.get("status") == "validation_error"]
    prerequisite_failures = []
    for index, event in enumerate(ordered):
        name = event.get("name")
        if name in PROPOSALS and event.get("status") == "approval_required":
            if not any(e.get("name") == "get_issue_history" and e.get("status") == "ok"
                       for e in ordered[:index]):
                prerequisite_failures.append("PROPOSAL_WITHOUT_VERIFIED_HISTORY")
        if name == "customer_escalation_summary" and event.get("status") == "ok":
            if not any(e.get("name") == "list_open_issues" and e.get("status") == "ok"
                       for e in ordered[:index]):
                prerequisite_failures.append("SKILL_WITHOUT_SCOPED_ISSUE_LOOKUP")
    return {
        "effective_tools": [str(e.get("name")) for e in ordered],
        "model_selected_tools": selected,
        "policy_preconditions": policy,
        "skill_dependencies": skills,
        "invalid_argument_tools": invalid,
        "invalid_argument_count": len(invalid),
        "prerequisite_failures": prerequisite_failures,
        "argument_integrity_passed": not invalid,
        "prerequisites_passed": not prerequisite_failures,
        "qualification": "Recorded execution sequence, not a model-only tool-selection score",
    }
