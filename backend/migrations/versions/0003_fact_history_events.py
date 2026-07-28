"""Add append-only fact history events.

Revision ID: 0003_fact_history_events
Revises: 0002_contact_facts
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0003_fact_history_events"
down_revision: str | None = "0002_contact_facts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fact_history_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("contact_id", sa.String(length=96), nullable=False),
        sa.Column("fact_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fact_history_account_contact_occurred", "fact_history_events", ["account_id", "contact_id", "occurred_at"])
    op.create_index(op.f("ix_fact_history_events_account_id"), "fact_history_events", ["account_id"])
    op.create_index(op.f("ix_fact_history_events_contact_id"), "fact_history_events", ["contact_id"])
    op.create_index(op.f("ix_fact_history_events_fact_id"), "fact_history_events", ["fact_id"])
    op.create_table(
        "fact_history_message_evidence",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.String(length=96), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["fact_history_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "message_id", name="uq_fact_history_message_evidence"),
    )
    op.create_index(op.f("ix_fact_history_message_evidence_event_id"), "fact_history_message_evidence", ["event_id"])
    op.create_index(op.f("ix_fact_history_message_evidence_message_id"), "fact_history_message_evidence", ["message_id"])


def downgrade() -> None:
    op.drop_table("fact_history_message_evidence")
    op.drop_table("fact_history_events")
