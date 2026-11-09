"""Read-only and controlled-write SQL repository (parameterised, customer-scoped)."""
from datetime import datetime, timezone
from typing import Any
import json
import os
import uuid
import psycopg
from psycopg.rows import dict_row
from acme_shared.policies import Principal, effective_role
from app.actions import ALLOWED_TRANSITIONS


def db_connection():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, (uuid.UUID, datetime)):
        return str(value) if isinstance(value, uuid.UUID) else value.isoformat()
    return value


def _scope_condition(principal: Principal) -> str:
    # SQL fragment is selected from server-owned role, not from user input.
    if effective_role(principal) == "sales_user":
        return "AND EXISTS (SELECT 1 FROM user_customer_access a WHERE a.customer_id=c.id AND a.keycloak_sub=%s)"
    return ""


def _scope_params(principal: Principal) -> tuple:
    return (principal.sub,) if effective_role(principal) == "sales_user" else ()


def find_customer(principal: Principal, name: str) -> dict | None:
    with db_connection() as db, db.cursor() as cursor:
        cursor.execute(
            "SELECT c.id,c.name,c.account_owner_sub,c.status,c.created_at "
            "FROM customers c WHERE lower(c.name)=lower(%s) " + _scope_condition(principal),
            (name, *_scope_params(principal)),
        )
        row = cursor.fetchone()
    return json_safe(row) if row else None


def list_open_issues(principal: Principal, customer_id: uuid.UUID) -> list[dict]:
    with db_connection() as db, db.cursor() as cursor:
        cursor.execute(
            "SELECT i.id,i.customer_id,i.title,i.description,i.priority,i.status,i.sla_due_at,i.version,i.updated_at "
            "FROM issues i JOIN customers c ON c.id=i.customer_id "
            "WHERE c.id=%s AND i.status IN ('open','investigating') " + _scope_condition(principal) +
            " ORDER BY i.updated_at DESC, i.id",
            (customer_id, *_scope_params(principal)),
        )
        rows = cursor.fetchall()
    return json_safe(rows)


def get_issue_history(principal: Principal, issue_id: uuid.UUID) -> dict | None:
    with db_connection() as db, db.cursor() as cursor:
        cursor.execute(
            "SELECT i.id,i.customer_id,i.title,i.description,i.priority,i.status,i.version,i.updated_at "
            "FROM issues i JOIN customers c ON c.id=i.customer_id WHERE i.id=%s " + _scope_condition(principal),
            (issue_id, *_scope_params(principal)),
        )
        issue = cursor.fetchone()
        if not issue:
            return None
        cursor.execute(
            "SELECT id,issue_id,author_sub,content,created_at FROM issue_updates "
            "WHERE issue_id=%s ORDER BY created_at ASC,id ASC", (issue_id,)
        )
        updates = cursor.fetchall()
    return json_safe({"issue": issue, "updates": updates})


def create_next_action(principal: Principal, *, issue_id: uuid.UUID, description: str,
                       approval_id: uuid.UUID, operation_id: uuid.UUID) -> tuple[str, dict | None]:
    # The approval is minted by a separate authenticated user-facing endpoint,
    # never by the model or an MCP tool. Reusing the operation ID is idempotent.
    with db_connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT id,issue_id,description,operation_id,created_by_sub,created_at "
                       "FROM next_actions WHERE operation_id=%s", (operation_id,))
        existing = cursor.fetchone()
        if existing:
            if (existing["created_by_sub"] != principal.sub or existing["issue_id"] != issue_id
                    or existing["description"] != description):
                return "conflict", None
            return "ok", json_safe(existing)
        cursor.execute(
            "SELECT id,kind,actor_sub,issue_id,description,operation_id,expires_at,used_at,confirmed_at "
            "FROM approval_requests WHERE id=%s FOR UPDATE", (approval_id,)
        )
        approval = cursor.fetchone()
        if (not approval or approval["kind"] != "next_action"
                or approval["actor_sub"] != principal.sub or approval["issue_id"] != issue_id
                or approval["description"] != description or approval["operation_id"] != operation_id
                or approval["confirmed_at"] is None):
            return "approval_required", None
        # A competing retry may have committed while we waited for the approval lock.
        # Recheck under READ COMMITTED so the replay returns the original receipt.
        if approval["used_at"] is not None:
            cursor.execute(
                "SELECT id,issue_id,description,operation_id,created_by_sub,created_at "
                "FROM next_actions WHERE operation_id=%s", (operation_id,)
            )
            existing = cursor.fetchone()
            return ("ok", json_safe(existing)) if existing else ("conflict", None)
        if approval["expires_at"] <= datetime.now(timezone.utc):
            return "approval_required", None
        new_id = uuid.uuid4()
        cursor.execute(
            "INSERT INTO next_actions(id,issue_id,description,created_by_sub,operation_id) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING id,issue_id,description,operation_id,created_by_sub,created_at",
            (new_id, issue_id, description, principal.sub, operation_id),
        )
        row = cursor.fetchone()
        cursor.execute("UPDATE approval_requests SET used_at=now() WHERE id=%s", (approval_id,))
        cursor.execute("INSERT INTO audit_events(actor_sub,action,target_id,decision,details) "
                       "VALUES (%s,'create_next_action',%s,'allowed',%s::jsonb)",
                       (principal.sub, str(new_id), json.dumps({"operation_id": str(operation_id)})))
    return "ok", json_safe(row)


def update_issue_status(principal: Principal, *, issue_id: uuid.UUID, new_status: str,
                        expected_version: int, note: str, approval_id: uuid.UUID,
                        operation_id: uuid.UUID) -> tuple[str, dict | None]:
    """One transactional status transition + update history + idempotency receipt.

    User/role is verified at the MCP entry point. A server-minted, human-confirmed
    approval binds the exact actor, issue, status, version, note and operation ID.
    """
    if new_status not in ALLOWED_TRANSITIONS or expected_version < 1 or not note.strip():
        return "validation_error", None
    with db_connection() as db, db.cursor() as cursor:
        def previous_receipt():
            cursor.execute(
                "SELECT operation_id,issue_id,actor_sub,previous_status,new_status,"
                "expected_version,new_version,note,update_id,created_at "
                "FROM issue_status_operations WHERE operation_id=%s", (operation_id,))
            record = cursor.fetchone()
            if record and (record["actor_sub"] != principal.sub or
                           record["issue_id"] != issue_id or
                           record["new_status"] != new_status or
                           record["expected_version"] != expected_version or
                           record["note"] != note):
                return "conflict", None
            return ("ok", json_safe(record)) if record else None

        existing = previous_receipt()
        if existing is not None:
            return existing
        cursor.execute(
            "SELECT kind,actor_sub,issue_id,new_status,expected_version,note,"
            "operation_id,expires_at,confirmed_at,used_at "
            "FROM approval_requests WHERE id=%s FOR UPDATE", (approval_id,))
        approval = cursor.fetchone()
        if (not approval or approval["kind"] != "issue_update" or
                approval["actor_sub"] != principal.sub or approval["issue_id"] != issue_id or
                approval["new_status"] != new_status or
                approval["expected_version"] != expected_version or
                approval["note"] != note or approval["operation_id"] != operation_id or
                approval["confirmed_at"] is None):
            return "approval_required", None
        # Someone may have already committed while we waited on the approval row.
        if approval["used_at"] is not None:
            return previous_receipt() or ("conflict", None)
        if approval["expires_at"] <= datetime.now(timezone.utc):
            return "approval_required", None
        cursor.execute("SELECT status,version FROM issues WHERE id=%s FOR UPDATE", (issue_id,))
        issue = cursor.fetchone()
        if issue is None:
            return "not_found", None
        if issue["version"] != expected_version:
            return "version_conflict", None
        if new_status not in ALLOWED_TRANSITIONS[issue["status"]]:
            return "invalid_transition", None
        cursor.execute("UPDATE issues SET status=%s, version=version+1, updated_at=now() "
                       "WHERE id=%s AND version=%s RETURNING version",
                       (new_status, issue_id, expected_version))
        changed = cursor.fetchone()
        if not changed:
            return "version_conflict", None
        update_id = uuid.uuid4()
        cursor.execute(
            "INSERT INTO issue_updates(id,issue_id,author_sub,content) VALUES (%s,%s,%s,%s)",
            (update_id, issue_id, principal.sub,
             f"Status {issue['status']} → {new_status}. {note}"),
        )
        cursor.execute(
            "INSERT INTO issue_status_operations(operation_id,issue_id,actor_sub,"
            "previous_status,new_status,expected_version,new_version,note,update_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "RETURNING operation_id,issue_id,actor_sub,previous_status,new_status,"
            "expected_version,new_version,note,update_id,created_at",
            (operation_id, issue_id, principal.sub, issue["status"], new_status,
             expected_version, changed["version"], note, update_id),
        )
        receipt = cursor.fetchone()
        cursor.execute("UPDATE approval_requests SET used_at=now() WHERE id=%s", (approval_id,))
        cursor.execute("INSERT INTO audit_events(actor_sub,action,target_id,decision,details) "
                       "VALUES (%s,'update_issue_status',%s,'allowed',%s::jsonb)",
                       (principal.sub, str(issue_id),
                        json.dumps({"operation_id": str(operation_id),
                                    "new_status": new_status,
                                    "new_version": changed["version"]})))
    return "ok", json_safe(receipt)
