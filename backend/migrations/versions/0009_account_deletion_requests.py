"""Add two-step account deletion requests.

Revision ID: 0009_account_deletion_requests
Revises: 0008_user_tags
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0009_account_deletion_requests"
down_revision: str | None = "0008_user_tags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("account_deletion_requests", sa.Column("id", sa.String(64), primary_key=True), sa.Column("account_id", sa.String(64), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False), sa.Column("confirmation_phrase", sa.String(128), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_account_deletion_requests_account_id", "account_deletion_requests", ["account_id"])
    op.create_index("ix_account_deletion_request_account_expires", "account_deletion_requests", ["account_id", "expires_at"])


def downgrade() -> None:
    op.drop_table("account_deletion_requests")
