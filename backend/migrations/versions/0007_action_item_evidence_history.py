"""Add action-item evidence and history.

Revision ID: 0007_action_item_evidence_history
Revises: 0006_action_items
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0007_action_item_evidence_history"
down_revision: str | None = "0006_action_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("action_item_evidence", sa.Column("id", sa.String(64), primary_key=True), sa.Column("action_item_id", sa.String(64), sa.ForeignKey("action_items.id", ondelete="CASCADE"), nullable=False), sa.Column("message_id", sa.String(96), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False), sa.UniqueConstraint("action_item_id", "message_id", name="uq_action_item_evidence"))
    op.create_index("ix_action_item_evidence_action_item_id", "action_item_evidence", ["action_item_id"])
    op.create_index("ix_action_item_evidence_message_id", "action_item_evidence", ["message_id"])
    op.create_table("action_item_history_events", sa.Column("id", sa.String(64), primary_key=True), sa.Column("account_id", sa.String(64), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False), sa.Column("action_item_id", sa.String(64), nullable=False), sa.Column("event_type", sa.String(16), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("status", sa.String(16), nullable=False), sa.Column("due_at", sa.DateTime(timezone=True)), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_action_item_history_events_account_id", "action_item_history_events", ["account_id"])
    op.create_index("ix_action_item_history_events_action_item_id", "action_item_history_events", ["action_item_id"])
    op.create_index("ix_action_item_history_account_item", "action_item_history_events", ["account_id", "action_item_id", "occurred_at"])
    op.create_table("action_item_history_evidence", sa.Column("id", sa.String(64), primary_key=True), sa.Column("event_id", sa.String(64), sa.ForeignKey("action_item_history_events.id", ondelete="CASCADE"), nullable=False), sa.Column("message_id", sa.String(96), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False), sa.UniqueConstraint("event_id", "message_id", name="uq_action_item_history_evidence"))
    op.create_index("ix_action_item_history_evidence_event_id", "action_item_history_evidence", ["event_id"])
    op.create_index("ix_action_item_history_evidence_message_id", "action_item_history_evidence", ["message_id"])


def downgrade() -> None:
    op.drop_table("action_item_history_evidence")
    op.drop_table("action_item_history_events")
    op.drop_table("action_item_evidence")
