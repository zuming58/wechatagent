"""Add user contact profile overrides and history.

Revision ID: 0004_contact_profile_overrides
Revises: 0003_fact_history_events
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0004_contact_profile_overrides"
down_revision: str | None = "0003_fact_history_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("user_remark_name", sa.String(length=255), nullable=True))
    op.add_column("contacts", sa.Column("user_confirmed_real_name", sa.String(length=255), nullable=True))
    op.add_column("contacts", sa.Column("user_company", sa.String(length=255), nullable=True))
    op.add_column("contacts", sa.Column("user_role", sa.String(length=255), nullable=True))
    op.create_table(
        "contact_profile_history_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("contact_id", sa.String(length=96), nullable=False),
        sa.Column("user_remark_name", sa.String(length=255), nullable=True),
        sa.Column("user_confirmed_real_name", sa.String(length=255), nullable=True),
        sa.Column("user_company", sa.String(length=255), nullable=True),
        sa.Column("user_role", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contact_profile_history_account_contact_occurred", "contact_profile_history_events", ["account_id", "contact_id", "occurred_at"])
    op.create_index(op.f("ix_contact_profile_history_events_account_id"), "contact_profile_history_events", ["account_id"])
    op.create_index(op.f("ix_contact_profile_history_events_contact_id"), "contact_profile_history_events", ["contact_id"])


def downgrade() -> None:
    op.drop_table("contact_profile_history_events")
    op.drop_column("contacts", "user_role")
    op.drop_column("contacts", "user_company")
    op.drop_column("contacts", "user_confirmed_real_name")
    op.drop_column("contacts", "user_remark_name")
