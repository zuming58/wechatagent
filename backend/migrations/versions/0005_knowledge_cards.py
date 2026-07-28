"""Add local user-managed knowledge cards and history.

Revision ID: 0005_knowledge_cards
Revises: 0004_contact_profile_overrides
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0005_knowledge_cards"
down_revision: str | None = "0004_contact_profile_overrides"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("knowledge_cards", sa.Column("id", sa.String(64), primary_key=True), sa.Column("account_id", sa.String(64), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False), sa.Column("card_type", sa.String(32), nullable=False), sa.Column("title", sa.String(255), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_knowledge_card_account_updated", "knowledge_cards", ["account_id", "updated_at"])
    op.create_table("knowledge_card_evidence", sa.Column("id", sa.String(64), primary_key=True), sa.Column("card_id", sa.String(64), sa.ForeignKey("knowledge_cards.id", ondelete="CASCADE"), nullable=False), sa.Column("message_id", sa.String(96), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False), sa.UniqueConstraint("card_id", "message_id", name="uq_knowledge_card_evidence"))
    op.create_table("knowledge_card_history_events", sa.Column("id", sa.String(64), primary_key=True), sa.Column("account_id", sa.String(64), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False), sa.Column("card_id", sa.String(64), nullable=False), sa.Column("event_type", sa.String(16), nullable=False), sa.Column("card_type", sa.String(32), nullable=False), sa.Column("title", sa.String(255), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_knowledge_card_history_account_occurred", "knowledge_card_history_events", ["account_id", "occurred_at"])
    op.create_table("knowledge_card_history_evidence", sa.Column("id", sa.String(64), primary_key=True), sa.Column("event_id", sa.String(64), sa.ForeignKey("knowledge_card_history_events.id", ondelete="CASCADE"), nullable=False), sa.Column("message_id", sa.String(96), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False), sa.UniqueConstraint("event_id", "message_id", name="uq_knowledge_card_history_evidence"))


def downgrade() -> None:
    op.drop_table("knowledge_card_history_evidence")
    op.drop_table("knowledge_card_history_events")
    op.drop_table("knowledge_card_evidence")
    op.drop_table("knowledge_cards")
