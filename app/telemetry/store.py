"""Durable run/telemetry records. No prompts, tool arguments or credentials are stored.

Traces are diagnostic; write authorisation events remain in the separate audit_events
ledger. Every read is filtered by the currently authenticated Keycloak subject.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

MAX_TOOL_EVENTS = 80
MAX_EVIDENCE_REFS = 25
_SAFE_TOKEN = re.compile(r"^[a-zA-Z0-9_.:/#-]{1,128}$")


def safe_label(value: Any, fallback: str = "unclassified", max_length: int = 64) -> str:
    """Allow only compact symbolic labels; never store raw model/tool messages."""
    if not isinstance(value, str) or len(value) > max_length:
        return fallback
    return value if _SAFE_TOKEN.fullmatch(value) else fallback


def safe_evidence_refs(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [s for s in value[:MAX_EVIDENCE_REFS]
            if isinstance(s, str) and _SAFE_TOKEN.fullmatch(s)]


def sanitize_tool_events(events: Any) -> list[dict]:
    """Scrub untrusted tool telemetry before durable storage or browser display."""
    if not isinstance(events, list):
        return []
    safe = []
    for e in events[:MAX_TOOL_EVENTS]:
        if not isinstance(e, dict):
            continue
        try:
            duration = max(0, min(3_600_000, int(e.get("duration_ms", 0))))
        except (TypeError, ValueError):
            duration = 0
        safe.append({
            "tool_name": safe_label(e.get("name"), "unknown_tool", 120),
            "status": safe_label(e.get("status"), "unknown", 48),
            "duration_ms": duration,
            "error_code": (safe_label(e["error_code"]) if e.get("error_code") else None),
            "evidence_refs": safe_evidence_refs(e.get("evidence_refs")),
        })
    return safe


def create_run(*, conversation_id: uuid.UUID, owner_sub: str, role: str,
               blueprint_version: str, model_name: str,
               run_id: uuid.UUID | None = None, trace_id: str | None = None) -> dict:
    import psycopg
    if not owner_sub or not isinstance(conversation_id, uuid.UUID):
        raise ValueError("Run must have a verified owner and conversation")
    run_id = run_id or uuid.uuid4()
    trace_id = trace_id or uuid.uuid4().hex
    if not re.fullmatch(r"[0-9a-f]{32}", trace_id):
        raise ValueError("Invalid trace ID")
    with psycopg.connect(os.environ["DATABASE_URL"]) as db:
        # The conversation owner is checked again here to avoid orphan/cross-user
        # telemetry even if a caller is accidentally refactored incorrectly.
        inserted = db.execute("""
            INSERT INTO agent_runs
              (id, conversation_id, owner_sub, role, blueprint_version, model_name, trace_id)
            SELECT %s, id, owner_sub, %s, %s, %s, %s
            FROM conversations WHERE id=%s AND owner_sub=%s
            RETURNING id
        """, (run_id, safe_label(role), safe_label(blueprint_version),
              safe_label(model_name, "unknown_model", 100), trace_id,
              conversation_id, owner_sub)).fetchone()
        if not inserted:
            raise PermissionError("Conversation is not owned by the authenticated user")
    return {"run_id": str(run_id), "trace_id": trace_id}


def finish_run(*, run_id: uuid.UUID, owner_sub: str, status: str,
               duration_ms: int, tool_events: Any = None,
               evidence_refs: Any = None, error_code: str | None = None) -> None:
    """Persist summary and tool events atomically; never save message content."""
    import psycopg
    if status not in {"complete", "failed", "interrupted"}:
        raise ValueError("Invalid terminal run state")
    events = sanitize_tool_events(tool_events)
    evidence_count = len(safe_evidence_refs(evidence_refs))
    duration_ms = max(0, int(duration_ms))
    with psycopg.connect(os.environ["DATABASE_URL"]) as db:
        row = db.execute("""
            UPDATE agent_runs SET status=%s, completed_at=now(), duration_ms=%s,
                tool_count=%s, evidence_count=%s, error_code=%s
            WHERE id=%s AND owner_sub=%s AND status='running'
            RETURNING id
        """, (status, duration_ms, len(events), evidence_count,
              safe_label(error_code) if error_code else None, run_id, owner_sub)).fetchone()
        if row is None:
            raise LookupError("Run not found or not running")
        with db.cursor() as cursor:
            for order, event in enumerate(events):
                cursor.execute("""
                    INSERT INTO agent_tool_events
                      (run_id, event_order, tool_name, status, duration_ms, error_code, evidence_refs)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                """, (run_id, order, event["tool_name"], event["status"],
                      event["duration_ms"], event["error_code"],
                      json.dumps(event["evidence_refs"])))


def list_runs(*, owner_sub: str, limit: int = 20, conversation_id: uuid.UUID | None = None) -> list[dict]:
    import psycopg
    from psycopg.rows import dict_row
    limit = max(1, min(int(limit), 50))
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as db:
        return db.execute("""
            SELECT id, conversation_id, role, blueprint_version, model_name, trace_id,
                   status, started_at, completed_at, duration_ms,
                   tool_count, evidence_count, error_code
            FROM agent_runs WHERE owner_sub=%s
              AND (%s::uuid IS NULL OR conversation_id=%s::uuid)
            ORDER BY started_at DESC, id DESC LIMIT %s
        """, (owner_sub, conversation_id, conversation_id, limit)).fetchall()


def get_run(*, owner_sub: str, run_id: uuid.UUID) -> dict | None:
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as db:
        run = db.execute("""
            SELECT id, conversation_id, role, blueprint_version, model_name, trace_id,
                   status, started_at, completed_at, duration_ms,
                   tool_count, evidence_count, error_code
            FROM agent_runs WHERE id=%s AND owner_sub=%s
        """, (run_id, owner_sub)).fetchone()
        if run is None:
            return None
        events = db.execute("""
            SELECT event_order, tool_name, status, duration_ms, error_code, evidence_refs,
                   created_at FROM agent_tool_events WHERE run_id=%s ORDER BY event_order
        """, (run_id,)).fetchall()
        return {**run, "tool_events": events}


def summary(*, owner_sub: str) -> dict:
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as db:
        return db.execute("""
            SELECT count(*)::int AS total_runs,
                count(*) FILTER (WHERE status='complete')::int AS completed,
                count(*) FILTER (WHERE status IN ('failed','interrupted'))::int AS failed,
                count(*) FILTER (WHERE status='running')::int AS running,
                coalesce(round(avg(duration_ms) FILTER (WHERE duration_ms IS NOT NULL)), 0)::int AS avg_duration_ms
            FROM agent_runs WHERE owner_sub=%s
        """, (owner_sub,)).fetchone()


def list_business_audit(*, owner_sub: str, limit: int = 20) -> list[dict]:
    """Return only the caller's auditable action headers, never unrestricted details."""
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as db:
        return db.execute("""
            SELECT id, occurred_at, action, target_id, decision
            FROM audit_events WHERE actor_sub=%s
            ORDER BY occurred_at DESC, id DESC LIMIT %s
        """, (owner_sub, max(1, min(int(limit), 50)))).fetchall()


def log_policy_denial(*, actor_sub: str, operation: str) -> None:
    """Record a policy denial without storing request bodies or target identifiers."""
    import psycopg
    operation = safe_label(operation)
    with psycopg.connect(os.environ["DATABASE_URL"]) as db:
        db.execute("""
            INSERT INTO audit_events (actor_sub, action, decision, details)
            VALUES (%s, %s, 'denied', '{}'::jsonb)
        """, (actor_sub, operation))


def mark_interrupted_runs(*, older_than_minutes: int = 20) -> int:
    """Mark executions stranded by unclean application shutdowns.

    W08's maximum execution time is 840s and its Redis lock TTL is 900s.
    20m gives in-flight runs sufficient time to finish; only called on startup.
    """
    import psycopg
    if not 20 <= older_than_minutes <= 24 * 60:
        raise ValueError("Invalid interruption threshold")
    with psycopg.connect(os.environ["DATABASE_URL"]) as db:
        row = db.execute("""
            WITH updated AS (
              UPDATE agent_runs
              SET status='interrupted', completed_at=now(),
                  error_code='PROCESS_RESTART'
              WHERE status='running'
                AND started_at < now() - make_interval(mins => %s)
              RETURNING id
            ) SELECT count(*)::int FROM updated
        """, (older_than_minutes,)).fetchone()
        return int(row[0])
