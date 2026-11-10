"""W09: deterministic, evidence-linked Customer Escalation Summary Skill.

This is an application-level Skill exposed to the LLM as a callable tool.
It reads only through the existing *authenticated* MCP connection, so customer
scope and Keycloak enforcement remain at the MCP boundary. It never writes.

The deterministic rubric intentionally does not infer confirmed customer impact,
remediation ETAs, or arbitrary meaning from unstructured incident narratives.
"""
from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

SKILL_NAME = "customer_escalation_summary"
SKILL_VERSION = "1.0.0"
MAX_ISSUES = 12
MAX_UPDATE_CHARS = 16000
ALLOWED_STATUSES = {"open", "investigating"}
RISK_ORDER = ("Unknown", "Low", "Medium", "High", "Critical")

# A model-visible callable workflow, *not* an MCP tool or a new security principal.
SKILL_SPEC = {
    "type": "function", "function": {
        "name": SKILL_NAME,
        "description": (
            "Reusable Customer Escalation Summary Skill. Evaluate authorised open issues "
            "for a customer, retrieve issue histories via MCP, apply deterministic risk "
            "rules, identify missing information, and return cited recommended actions. "
            "Read-only: never creates or updates records. Find the customer first "
            "to obtain a verified customer_id."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "UUID from find_customer or explicit customer ID"},
                "customer_name": {"type": "string", "maxLength": 160,
                                  "description": "Customer name; Skill resolves it using authenticated MCP"},
                "issue_ids": {"type": "array", "items": {"type": "string"},
                              "maxItems": MAX_ISSUES, "description": "Optional authorised open issue UUIDs"},
            },
            "required": [], "additionalProperties": False,
        },
    },
}


@dataclass(frozen=True)
class IssueAssessment:
    issue_id: str
    title: str
    priority: str
    status: str
    risk_level: str
    risk_reasons: tuple[str, ...]
    sla_due_at: str | None
    sla_breached: bool | None
    latest_update_at: str | None
    update_count: int
    evidence_refs: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "issue_id": self.issue_id, "title": self.title,
            "priority": self.priority, "status": self.status,
            "risk_level": self.risk_level, "risk_reasons": list(self.risk_reasons),
            "sla_due_at": self.sla_due_at, "sla_breached": self.sla_breached,
            "latest_update_at": self.latest_update_at, "update_count": self.update_count,
            "evidence_refs": list(self.evidence_refs),
        }


def _uuid(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("INVALID_UUID")
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError) as exc:
        raise ValueError("INVALID_UUID") from exc


def _timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("INVALID_TIMESTAMP")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    if parsed.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return parsed.astimezone(timezone.utc)




class ActionProposal(BaseModel):
    """Evidence-backed suggestion. Literal fields prevent pretending a write occurred."""
    model_config = ConfigDict(extra="forbid")
    issue_id: uuid.UUID
    action: str
    rationale: str
    evidence_refs: list[str]
    requires_human_decision: Literal[True]
    persisted: Literal[False]


class EscalationReport(BaseModel):
    """Versioned, typed public Skill output; no secrets or unchecked free-form keys."""
    model_config = ConfigDict(extra="forbid")
    skill: Literal["customer_escalation_summary"]
    skill_version: str
    customer_id: uuid.UUID
    as_of: datetime
    executive_summary: str
    risk_level: Literal["Unknown", "Low", "Medium", "High", "Critical"]
    risk_reasons: list[str]
    issue_assessments: list[IssueAssessment]
    recommended_actions: list[ActionProposal]
    missing_information: list[str]
    evidence_refs: list[str]
    advisory_only: Literal[True]

    @model_validator(mode="after")
    def ensure_consistency(self):
        ids = {str(x.issue_id) for x in self.issue_assessments}
        refs = set(self.evidence_refs)
        if (not ids and (self.risk_level != "Unknown" or self.recommended_actions)):
            raise ValueError("EMPTY_ASSESSMENT_MUST_ABSTAIN")
        if ids and self.risk_level == "Unknown":
            raise ValueError("UNKNOWN_RISK_WITH_ISSUES")
        for action in self.recommended_actions:
            if str(action.issue_id) not in ids or not set(action.evidence_refs).issubset(refs):
                raise ValueError("ACTION_EVIDENCE_MISMATCH")
        return self


def _validated_summary(data: dict) -> dict:
    return EscalationReport.model_validate(data).model_dump(mode="json")


class AuditedReadOnlyMCP:
    """Restrict a Skill's internal MCP calls and record nested tool timings.

    The wrapper cannot mint identity or gain authority; the underlying transport
    continues to enforce the current Keycloak principal and customer scope.
    """
    READ_TOOLS = frozenset({"find_customer", "list_open_issues", "get_issue_history"})

    def __init__(self, transport: Any):
        self._transport = transport
        self.events: list[dict] = []

    async def call_tool(self, name: str, arguments: dict) -> dict:
        if name not in self.READ_TOOLS:
            raise ValueError("SKILL_TOOL_NOT_ALLOWED")
        started = time.perf_counter()
        try:
            response = await self._transport.call_tool(name, arguments)
        except Exception:
            self.events.append({"name": name, "parent_skill": SKILL_NAME,
                                "status": "exception", "duration_ms": round(
                                    (time.perf_counter() - started) * 1000),
                                "evidence_refs": []})
            raise
        self.events.append({
            "name": name, "parent_skill": SKILL_NAME,
            "status": response.get("status", "invalid") if isinstance(response, dict) else "invalid",
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "evidence_refs": response.get("evidence_refs", []) if isinstance(response, dict) else [],
        })
        return response


def _envelope(status: str, data: dict | None = None, refs: list[str] | None = None,
              error: str | None = None) -> dict:
    return {"status": status, "data": data, "evidence_refs": refs or [],
            "error_code": error, "trace_id": None}


def _validate_result(result: Any, tool_name: str) -> Any:
    if not isinstance(result, dict):
        raise ValueError(f"{tool_name}: INVALID_RESULT")
    if result.get("status") != "ok":
        # Refuse to turn a denied, missing, or unavailable lookup into a
        # misleading 'no open issues' report. Do not leak partially read data.
        return None
    return result.get("data")


def _assess_issue(issue: dict, history: dict, now: datetime) -> tuple[IssueAssessment, list[str], dict]:
    issue_id = _uuid(issue.get("id"))
    priority = issue.get("priority")
    status = issue.get("status")
    if priority not in {"critical", "high", "medium", "low"} or status not in ALLOWED_STATUSES:
        raise ValueError("INVALID_ACTIVE_ISSUE")
    if not isinstance(issue.get("title"), str) or len(issue["title"]) > 400:
        raise ValueError("INVALID_ISSUE_TITLE")
    history_issue = history.get("issue")
    updates = history.get("updates")
    if (not isinstance(history_issue, dict) or
            _uuid(history_issue.get("id")) != issue_id or
            not isinstance(updates, list) or len(updates) > 150):
        raise ValueError("ISSUE_HISTORY_MISMATCH")
    if _uuid(history_issue.get("customer_id")) != _uuid(issue.get("customer_id")):
        raise ValueError("ISSUE_HISTORY_CUSTOMER_MISMATCH")
    if history_issue.get("status") != status or history_issue.get("priority") != priority:
        # A mid-run update invalidates the earlier list snapshot.
        raise ValueError("ISSUE_CHANGED_DURING_ASSESSMENT")

    due = _timestamp(issue.get("sla_due_at"))
    breached = due < now if due is not None else None
    reasons = []
    missing = []
    if due is None:
        missing.append(f"{issue_id}: SLA due time not recorded")

    history_refs = []
    latest = None
    escalation_count = 0
    explicit_conflict = False
    for update in updates:
        if not isinstance(update, dict) or _uuid(update.get("issue_id")) != issue_id:
            raise ValueError("ISSUE_UPDATE_MISMATCH")
        updated = _timestamp(update.get("created_at"))
        if updated is None:
            raise ValueError("ISSUE_UPDATE_NO_TIMESTAMP")
        latest = max(latest, updated) if latest else updated
        content = update.get("content")
        if not isinstance(content, str) or len(content) > MAX_UPDATE_CHARS:
            raise ValueError("INVALID_ISSUE_UPDATE")
        if re.search(r"\bescalat(?:e|ed|ion|ions)\b", content, re.IGNORECASE):
            escalation_count += 1
        # Only explicitly marked contradictions are flagged, not inferred from
        # arbitrary conflicting prose; this is a conservative signal.
        if re.search(r"\bconflicting update\b|\bcontradiction\b", content, re.IGNORECASE):
            explicit_conflict = True
        history_refs.append(f"issue_updates:{_uuid(update.get('id'))}")

    if status not in ALLOWED_STATUSES:
        raise ValueError("NOT_ACTIVE")
    if priority == "critical" and breached is True:
        level = "Critical"
        reasons.append("Critical-priority active issue has passed its SLA due time")
    elif (priority == "critical" or (priority == "high" and breached is True)
          or escalation_count >= 2):
        level = "High"
        if priority == "critical":
            reasons.append("Active issue marked critical; critical SLA breach not established")
        elif breached is True:
            reasons.append("High-priority active issue has passed its SLA due time")
        else:
            reasons.append("Multiple issue updates explicitly mention escalation")
    elif priority in {"medium", "high"}:
        level = "Medium"
        reasons.append("Active issue with medium or high priority; higher-risk triggers not established")
    else:
        level = "Low"
        reasons.append("Only low-priority active issue triggers were observed")

    if explicit_conflict:
        missing.append(f"{issue_id}: Confirm which conflicting update reflects current status")
    if not updates:
        missing.append(f"{issue_id}: No recorded issue updates to establish latest progress")
    # There is no structured ETA or impact measure in the EY seed schema.
    missing.append(f"{issue_id}: No structured confirmed remediation ETA or business-impact assessment")
    refs = [f"issues:{issue_id}", *history_refs]
    recommendation = {
        "issue_id": issue_id,
        "action": ("Escalate to the accountable support owner and obtain a confirmed recovery plan"
                   if level in {"Critical", "High"} else
                   "Request the next verified progress update and confirm resolution timing"),
        "rationale": reasons[0],
        "evidence_refs": refs,
        "requires_human_decision": True,
        "persisted": False,
    }
    return IssueAssessment(
        issue_id=issue_id, title=issue["title"], priority=priority, status=status,
        risk_level=level, risk_reasons=tuple(reasons),
        sla_due_at=due.isoformat() if due is not None else None,
        sla_breached=breached,
        latest_update_at=latest.isoformat() if latest else None,
        update_count=len(updates), evidence_refs=tuple(refs),
    ), missing, recommendation


async def run_customer_escalation_summary(
    mcp: Any, *, customer_id: str | None = None, customer_name: str | None = None,
    issue_ids: list[str] | None = None,
    now: datetime | None = None,
) -> dict:
    """Read exclusively through authenticated MCP; return auditable structured output.

    No identity/roles/tokens are accepted from the caller, prompt or tool args.
    """
    # Resolve a name only through the caller's authenticated MCP transport.
    # A user-supplied identifier is NEVER proof of customer access.
    if customer_name is not None:
        if (not isinstance(customer_name, str) or not customer_name.strip()
                or len(customer_name) > 160):
            return _envelope("validation_error", error="INVALID_CUSTOMER_NAME")
        match = await mcp.call_tool("find_customer", {"customer_name": customer_name.strip()})
        record = _validate_result(match, "find_customer")
        if not isinstance(record, dict) or not record.get("id"):
            return _envelope("unavailable", error="CUSTOMER_NOT_ACCESSIBLE")
        resolved_id = _uuid(record["id"])
        if customer_id is not None:
            try:
                explicit_id = _uuid(customer_id)
            except ValueError:
                return _envelope("validation_error", error="INVALID_CUSTOMER_ID")
            if explicit_id != resolved_id:
                return _envelope("validation_error", error="CUSTOMER_ID_NAME_MISMATCH")
        cid = resolved_id
    elif customer_id is not None:
        cid = _uuid(customer_id)
    else:
        return _envelope("validation_error", error="CUSTOMER_REFERENCE_REQUIRED")
    requested: list[str] | None = None
    if issue_ids is not None:
        if not isinstance(issue_ids, list) or not 1 <= len(issue_ids) <= MAX_ISSUES:
            raise ValueError("INVALID_ISSUE_SELECTION")
        requested = [_uuid(v) for v in issue_ids]
        if len(set(requested)) != len(requested):
            raise ValueError("DUPLICATE_ISSUE_SELECTION")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_EVALUATION_TIME")
    now = now.astimezone(timezone.utc)

    listed = await mcp.call_tool("list_open_issues", {"customer_id": cid})
    issues = _validate_result(listed, "list_open_issues")
    if issues is None:
        return _envelope("unavailable", error="CUSTOMER_ISSUES_NOT_ACCESSIBLE")
    if not isinstance(issues, list) or len(issues) > MAX_ISSUES:
        return _envelope("unavailable", error="ISSUE_COUNT_EXCEEDS_SKILL_LIMIT")
    available: dict[str, dict] = {}
    for issue in issues:
        if not isinstance(issue, dict) or _uuid(issue.get("customer_id")) != cid:
            return _envelope("unavailable", error="INCONSISTENT_CUSTOMER_SCOPE")
        iid = _uuid(issue.get("id"))
        if iid in available or issue.get("status") not in ALLOWED_STATUSES:
            return _envelope("unavailable", error="INVALID_ISSUE_SET")
        available[iid] = issue
    if requested is not None and not set(requested).issubset(available):
        return _envelope("not_found", error="ISSUE_NOT_IN_AUTHORISED_OPEN_SET")
    chosen = [available[i] for i in (requested if requested is not None else available)]

    if not chosen:
        return _envelope("ok", data=_validated_summary({
            "skill": SKILL_NAME, "skill_version": SKILL_VERSION, "customer_id": cid,
            "as_of": now.isoformat(), "executive_summary": (
                "No open issues were returned in the authorised customer view; "
                "customer-wide risk cannot be established from this result."),
            "risk_level": "Unknown", "risk_reasons": [], "issue_assessments": [],
            "recommended_actions": [], "missing_information": [
                "Customer visibility and closed issue history were not independently verified"],
            "evidence_refs": [], "advisory_only": True,
        }), refs=[])

    assessments, missing, recommendations, all_refs = [], [], [], []
    for issue in chosen:
        history_result = await mcp.call_tool("get_issue_history", {"issue_id": _uuid(issue["id"])})
        history = _validate_result(history_result, "get_issue_history")
        if not isinstance(history, dict):
            return _envelope("unavailable", error="ISSUE_HISTORY_NOT_ACCESSIBLE")
        try:
            assessment, gaps, action = _assess_issue(issue, history, now)
        except ValueError:
            return _envelope("unavailable", error="ISSUE_EVIDENCE_INCONSISTENT")
        assessments.append(assessment)
        missing.extend(gaps)
        recommendations.append(action)
        all_refs.extend(assessment.evidence_refs)

    level = max((x.risk_level for x in assessments), key=RISK_ORDER.index)
    reasons = list(dict.fromkeys(r for item in assessments for r in item.risk_reasons))
    refs = list(dict.fromkeys(all_refs))
    ordered = sorted(assessments, key=lambda x: (-RISK_ORDER.index(x.risk_level), x.issue_id))
    recommendations.sort(key=lambda r: (-RISK_ORDER.index(next(
        i.risk_level for i in assessments if i.issue_id == r["issue_id"])), r["issue_id"]))
    return _envelope("ok", data=_validated_summary({
        "skill": SKILL_NAME, "skill_version": SKILL_VERSION,
        "customer_id": cid, "as_of": now.isoformat(),
        "executive_summary": (
            f"{len(chosen)} active issue(s) evaluated from authorised customer records. "
            f"Highest rubric risk is {level}. Recommendations are advisory and require human review."),
        "risk_level": level, "risk_reasons": reasons,
        "issue_assessments": [a.as_dict() for a in ordered],
        "recommended_actions": recommendations,
        "missing_information": list(dict.fromkeys(missing)),
        "evidence_refs": refs, "advisory_only": True,
    }), refs=refs)
