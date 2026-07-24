"""Add user-managed action items.

Revision ID: 0006_action_items
Revises: 0005_knowledge_cards
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0006_action_items"
down_revision: str | None = "0005_knowledge_cards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("action_items", sa.Column("id", sa.String(64), primary_key=True), sa.Column("account_id", sa.String(64), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("status", sa.String(16), nullable=False), sa.Column("due_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_action_item_account_updated", "action_items", ["account_id", "updated_at"])


def downgrade() -> None:
    op.drop_table("action_items")
