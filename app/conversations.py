"""Owner-scoped durable conversation metadata; agent execution is W08."""
from __future__ import annotations

import os
import uuid
from datetime import datetime

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, Field


class NewConversation(BaseModel):
    title: str = Field(default="New investigation", min_length=1, max_length=120)


def _serialize(row: dict) -> dict:
    return {k: str(v) if isinstance(v, (uuid.UUID, datetime)) else v for k, v in row.items()}


def list_owned(owner_sub: str) -> list[dict]:
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as db:
        rows = db.execute("""SELECT id,title,created_at,updated_at FROM conversations
                             WHERE owner_sub=%s ORDER BY updated_at DESC LIMIT 100""",
                          (owner_sub,)).fetchall()
        return [_serialize(row) for row in rows]


def create_owned(owner_sub: str, title: str, blueprint_version: str = "0.2.0") -> dict:
    conversation_id = uuid.uuid4()
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as db:
        row = db.execute("""INSERT INTO conversations(id,owner_sub,title,blueprint_version)
                            VALUES (%s,%s,%s,%s)
                            RETURNING id,title,created_at,updated_at""",
                         (conversation_id, owner_sub, title.strip(), blueprint_version)).fetchone()
        return _serialize(row)


def get_owned(owner_sub: str, conversation_id: uuid.UUID) -> dict | None:
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as db:
        item = db.execute("""SELECT id,title,created_at,updated_at,blueprint_version
                             FROM conversations WHERE id=%s AND owner_sub=%s""",
                          (conversation_id, owner_sub)).fetchone()
        if not item:
            return None
        messages = db.execute("""SELECT id,role,body,created_at FROM conversation_messages
                                 WHERE conversation_id=%s ORDER BY created_at,id""",
                              (conversation_id,)).fetchall()
    return {**_serialize(item), "messages": [_serialize(row) for row in messages],
            "agent_status": "chat_available"}


def store_turn(owner_sub: str, conversation_id: uuid.UUID, user_body: str,
               assistant_body: str, *, successful: bool, blueprint_version: str) -> None:
    """Commit one UI transcript turn atomically, with database ownership recheck.

    The LangGraph checkpoint remains the execution source of truth. The UI transcript
    is a projection; if a crash occurs between checkpoint and projection, a future
    reconciliation is required (not falsely claimed to be implemented by W08).
    """
    with psycopg.connect(os.environ["DATABASE_URL"]) as db:
        with db.cursor() as cursor:
            cursor.execute("SELECT id FROM conversations WHERE id=%s AND owner_sub=%s FOR UPDATE",
                           (conversation_id, owner_sub))
            if not cursor.fetchone():
                raise PermissionError("CONVERSATION_NOT_OWNED")
            cursor.execute(
                "INSERT INTO conversation_messages(id,conversation_id,role,body) "
                "VALUES (%s,%s,'user',%s)",
                (uuid.uuid4(), conversation_id, user_body),
            )
            cursor.execute(
                "INSERT INTO conversation_messages(id,conversation_id,role,body) "
                "VALUES (%s,%s,%s,%s)",
                (uuid.uuid4(), conversation_id,
                 "assistant" if successful else "system_notice", assistant_body),
            )
            cursor.execute("UPDATE conversations SET updated_at=now(), blueprint_version=%s "
                           "WHERE id=%s", (blueprint_version, conversation_id))
