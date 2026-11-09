"""W10: pure, testable write-intent contracts; model output never carries authority."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
import uuid
from pydantic import BaseModel, Field, ConfigDict, model_validator

from acme_shared.policies import Principal, has_permission

ALLOWED_TRANSITIONS = {
    "open": frozenset({"investigating", "resolved"}),
    "investigating": frozenset({"open", "resolved"}),
    "resolved": frozenset({"closed", "investigating"}),
    "closed": frozenset(),
}

class WriteIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["issue_update", "next_action"]
    issue_id: uuid.UUID
    new_status: Literal["open", "investigating", "resolved", "closed"] | None = None
    expected_version: int | None = Field(default=None, ge=1)
    note: str | None = Field(default=None, max_length=600)
    description: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_kind(self):
        if self.kind == "issue_update":
            if (self.new_status is None or self.expected_version is None or
                    not self.note or not self.note.strip() or self.description is not None):
                raise ValueError("ISSUE_UPDATE_FIELDS_INVALID")
        elif (not self.description or not self.description.strip() or
              self.new_status is not None or self.expected_version is not None or self.note is not None):
            raise ValueError("NEXT_ACTION_FIELDS_INVALID")
        return self

    @property
    def permission(self) -> str:
        return "update_issue_status" if self.kind == "issue_update" else "create_next_action"

    def require_role(self, actor: Principal):
        if not has_permission(actor, self.permission):
            raise PermissionError("ROLE_DENIED")

    def args_for_mcp(self, approval_id: str, operation_id: str) -> tuple[str, dict]:
        if self.kind == "issue_update":
            return "update_issue_status", {"issue_id": str(self.issue_id),
                "new_status": self.new_status, "expected_version": self.expected_version,
                "note": self.note.strip(), "approval_id": approval_id,
                "operation_id": operation_id}
        return "create_next_action", {"issue_id": str(self.issue_id),
            "description": self.description.strip(), "approval_id": approval_id,
            "operation_id": operation_id}


def proposal_from_model(name: str, args: dict, actor_role: str) -> dict:
    """Validate untrusted LLM proposals. This cannot grant approval or write data."""
    if name == "request_issue_update":
        if actor_role not in {"support_user", "admin"}:
            raise PermissionError("ROLE_DENIED")
        request = WriteIntent(kind="issue_update", **args)
    elif name == "request_next_action":
        if actor_role != "admin":
            raise PermissionError("ROLE_DENIED")
        request = WriteIntent(kind="next_action", **args)
    else:
        raise ValueError("UNKNOWN_PROPOSAL_TOOL")
    return request.model_dump(mode="json", exclude_none=True)


PROPOSAL_TOOL_SPECS = {
    "request_issue_update": {"type": "function", "function": {
        "name": "request_issue_update",
        "description": "PROPOSAL ONLY: draft an issue status change for the logged-in user to review and confirm. Never writes to the database. Use a verified issue ID and version from issue history.",
        "parameters": {"type": "object", "properties": {
            "issue_id": {"type": "string"},
            "new_status": {"type": "string", "enum": list(ALLOWED_TRANSITIONS)},
            "expected_version": {"type": "integer", "minimum": 1},
            "note": {"type": "string", "maxLength": 600},
        }, "required": ["issue_id", "new_status", "expected_version", "note"],
        "additionalProperties": False}}},
    "request_next_action": {"type": "function", "function": {
        "name": "request_next_action",
        "description": "PROPOSAL ONLY: draft a recommended next-action record for admin review and explicit confirmation. Never commits a write.",
        "parameters": {"type": "object", "properties": {
            "issue_id": {"type": "string"},
            "description": {"type": "string", "maxLength": 1000},
        }, "required": ["issue_id", "description"], "additionalProperties": False}}},
}
