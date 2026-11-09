"""W10: explicitly confirmed two-phase writes and idempotent issue updates.

Revision ID: 0003_controlled_writes
Revises: 0002_conversations
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0003_controlled_writes"
down_revision = "0002_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("approval_requests", sa.Column("kind", sa.Text(), nullable=False,
                                                  server_default="next_action"))
    op.add_column("approval_requests", sa.Column("new_status", sa.Text()))
    op.add_column("approval_requests", sa.Column("expected_version", sa.Integer()))
    op.add_column("approval_requests", sa.Column("note", sa.Text()))
    op.add_column("approval_requests", sa.Column("confirmed_at", sa.DateTime(timezone=True)))
    op.create_check_constraint("approval_kind_valid", "approval_requests",
                               "kind IN ('next_action','issue_update')")
    op.create_table(
        "issue_status_operations",
        sa.Column("operation_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("issue_id", UUID(as_uuid=True), sa.ForeignKey("issues.id"), nullable=False),
        sa.Column("actor_sub", sa.Text(), nullable=False),
        sa.Column("previous_status", sa.Text(), nullable=False),
        sa.Column("new_status", sa.Text(), nullable=False),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("new_version", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("update_id", UUID(as_uuid=True), sa.ForeignKey("issue_updates.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_issue_operations_issue", "issue_status_operations", ["issue_id"])


def downgrade() -> None:
    op.drop_table("issue_status_operations")
    op.drop_constraint("approval_kind_valid", "approval_requests", type_="check")
    for name in ("confirmed_at", "note", "expected_version", "new_status", "kind"):
        op.drop_column("approval_requests", name)
