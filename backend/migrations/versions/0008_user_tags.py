"""Add user-managed tags.

Revision ID: 0008_user_tags
Revises: 0007_action_item_evidence_history
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0008_user_tags"
down_revision: str | None = "0007_action_item_evidence_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("tags", sa.Column("id", sa.String(64), primary_key=True), sa.Column("account_id", sa.String(64), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(64), nullable=False), sa.Column("color", sa.String(7), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("account_id", "name", name="uq_tag_account_name"))
    op.create_index("ix_tags_account_id", "tags", ["account_id"])
    op.create_index("ix_tag_account_name", "tags", ["account_id", "name"])
    op.create_table("tag_links", sa.Column("id", sa.String(64), primary_key=True), sa.Column("account_id", sa.String(64), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False), sa.Column("tag_id", sa.String(64), sa.ForeignKey("tags.id", ondelete="CASCADE"), nullable=False), sa.Column("target_type", sa.String(32), nullable=False), sa.Column("target_id", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("tag_id", "target_type", "target_id", name="uq_tag_link_target"))
    op.create_index("ix_tag_links_account_id", "tag_links", ["account_id"])
    op.create_index("ix_tag_links_tag_id", "tag_links", ["tag_id"])
    op.create_index("ix_tag_link_account_target", "tag_links", ["account_id", "target_type", "target_id"])


def downgrade() -> None:
    op.drop_table("tag_links")
    op.drop_table("tags")
