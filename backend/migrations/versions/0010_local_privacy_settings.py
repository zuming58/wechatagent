"""Add local privacy acknowledgement settings.

Revision ID: 0010_local_privacy_settings
Revises: 0009_account_deletion_requests
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0010_local_privacy_settings"
down_revision: str | None = "0009_account_deletion_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "local_privacy_settings",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("local_processing_acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("local_privacy_settings")
