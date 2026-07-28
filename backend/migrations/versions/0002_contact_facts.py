"""Add user-confirmed contact facts and message evidence.

Revision ID: 0002_contact_facts
Revises: 0001_initial
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0002_contact_facts"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "facts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("contact_id", sa.String(length=96), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fact_account_contact_updated", "facts", ["account_id", "contact_id", "updated_at"])
    op.create_index(op.f("ix_facts_account_id"), "facts", ["account_id"])
    op.create_index(op.f("ix_facts_contact_id"), "facts", ["contact_id"])
    op.create_table(
        "fact_message_evidence",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("fact_id", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.String(length=96), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["fact_id"], ["facts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fact_id", "message_id", name="uq_fact_message_evidence"),
    )
    op.create_index(op.f("ix_fact_message_evidence_fact_id"), "fact_message_evidence", ["fact_id"])
    op.create_index(op.f("ix_fact_message_evidence_message_id"), "fact_message_evidence", ["message_id"])


def downgrade() -> None:
    op.drop_table("fact_message_evidence")
    op.drop_table("facts")
