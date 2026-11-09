"""Durable conversation metadata, owned by Keycloak subject.

Revision ID: 0002_conversations
Revises: 0001_initial
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0002_conversations"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_sub", sa.Text(), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("blueprint_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_conversations_owner_updated", "conversations", ["owner_sub", "updated_at"])
    op.create_table(
        "conversation_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", UUID(as_uuid=True),
                  sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('user','assistant','system_notice')", name="message_role_valid"),
    )
    op.create_index("ix_messages_conversation_time", "conversation_messages",
                    ["conversation_id", "created_at"])


def downgrade() -> None:
    op.drop_table("conversation_messages")
    op.drop_table("conversations")
