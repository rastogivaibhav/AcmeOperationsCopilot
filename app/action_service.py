"""W10: trusted BFF two-step approval store; no model can mint authorisation."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import os
import uuid

import psycopg
from psycopg.rows import dict_row

from acme_shared.policies import Principal
from app.actions import ALLOWED_TRANSITIONS, WriteIntent


def prepare(actor: Principal, intent: WriteIntent) -> dict:
    intent.require_role(actor)
    approval_id, operation_id = uuid.uuid4(), uuid.uuid4()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as db:
        with db.cursor() as cursor:
            cursor.execute("SELECT status,version FROM issues WHERE id=%s", (intent.issue_id,))
            issue = cursor.fetchone()
            if issue is None:
                raise LookupError("ISSUE_NOT_FOUND")
            if intent.kind == "issue_update":
                if issue["version"] != intent.expected_version:
                    raise ValueError("VERSION_CONFLICT")
                if intent.new_status not in ALLOWED_TRANSITIONS[issue["status"]]:
                    raise ValueError("INVALID_TRANSITION")
            cursor.execute(
                "INSERT INTO approval_requests(id,actor_sub,issue_id,description,operation_id,"
                "expires_at,kind,new_status,expected_version,note) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (approval_id, actor.sub, intent.issue_id, intent.description.strip()
                 if intent.description else "", operation_id, expires_at, intent.kind,
                 intent.new_status, intent.expected_version,
                 intent.note.strip() if intent.note else None),
            )
    return {"approval_id": str(approval_id), "operation_id": str(operation_id),
            "expires_at": expires_at.isoformat(), "intent": intent.model_dump(mode="json",
                                                                               exclude_none=True),
            "status": "awaiting_confirmation"}


def confirm(actor: Principal, approval_id: uuid.UUID) -> tuple[WriteIntent, str, str]:
    """Loads bound payload from DB and records human confirmation; MCP performs the write."""
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as db:
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT id,kind,actor_sub,issue_id,description,new_status,expected_version,note,"
                "operation_id,expires_at,used_at,confirmed_at "
                "FROM approval_requests WHERE id=%s AND actor_sub=%s FOR UPDATE",
                (approval_id, actor.sub),
            )
            row = cursor.fetchone()
            if row is None:
                raise LookupError("APPROVAL_NOT_FOUND")
            fields = {"kind": row["kind"], "issue_id": row["issue_id"]}
            if row["kind"] == "next_action":
                fields["description"] = row["description"]
            else:
                fields.update(new_status=row["new_status"], expected_version=row["expected_version"],
                              note=row["note"])
            intent = WriteIntent(**fields)
            intent.require_role(actor)  # Permissions may have been revoked since prepare.
            if row["used_at"] is None and row["expires_at"] <= datetime.now(timezone.utc):
                raise ValueError("APPROVAL_EXPIRED")
            if row["confirmed_at"] is None:
                cursor.execute("UPDATE approval_requests SET confirmed_at=now() WHERE id=%s",
                               (approval_id,))
            return intent, str(row["id"]), str(row["operation_id"])


def cancel(actor: Principal, approval_id: uuid.UUID) -> bool:
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as db:
        with db.cursor() as cursor:
            cursor.execute("DELETE FROM approval_requests WHERE id=%s AND actor_sub=%s "
                           "AND confirmed_at IS NULL AND used_at IS NULL RETURNING id",
                           (approval_id, actor.sub))
            return cursor.fetchone() is not None
