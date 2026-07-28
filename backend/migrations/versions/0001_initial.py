"""Initial local message store.

Revision ID: 0001_initial
"""
from collections.abc import Sequence

from alembic import op

import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("accounts", sa.Column("id", sa.String(64), primary_key=True), sa.Column("source_key", sa.String(255), nullable=False, unique=True), sa.Column("display_name", sa.String(255), nullable=False), sa.Column("source_version", sa.String(64)), sa.Column("selected", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("conversations", sa.Column("id", sa.String(96), primary_key=True), sa.Column("account_id", sa.String(64), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False), sa.Column("source_id", sa.String(255), nullable=False), sa.Column("conversation_type", sa.String(32), nullable=False), sa.Column("display_name", sa.String(255), nullable=False), sa.Column("latest_message_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("account_id", "source_id", name="uq_conversation_source"))
    op.create_table("contacts", sa.Column("id", sa.String(96), primary_key=True), sa.Column("account_id", sa.String(64), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False), sa.Column("source_id", sa.String(255), nullable=False), sa.Column("remark_name", sa.String(255)), sa.Column("nickname", sa.String(255)), sa.Column("confirmed_real_name", sa.String(255)), sa.Column("company", sa.String(255)), sa.Column("role", sa.String(255)), sa.Column("avatar_ref", sa.Text()), sa.Column("avatar_version", sa.String(128)), sa.Column("avatar_updated_at", sa.DateTime(timezone=True)), sa.Column("last_message_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("account_id", "source_id", name="uq_contact_source"))
    op.create_table("messages", sa.Column("id", sa.String(96), primary_key=True), sa.Column("account_id", sa.String(64), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False), sa.Column("source_shard_id", sa.String(255), nullable=False), sa.Column("source_message_id", sa.String(255), nullable=False), sa.Column("conversation_id", sa.String(96), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False), sa.Column("sender_id", sa.String(255), nullable=False), sa.Column("sender_display_name", sa.String(255), nullable=False), sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False), sa.Column("direction", sa.String(16), nullable=False), sa.Column("message_type", sa.String(32), nullable=False), sa.Column("text_content", sa.Text(), nullable=False), sa.Column("structured_content", sa.Text()), sa.Column("attachment_metadata", sa.Text()), sa.Column("source_freshness", sa.String(64), nullable=False), sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("account_id", "source_shard_id", "source_message_id", name="uq_message_source"))
    op.create_table("sync_shards", sa.Column("id", sa.String(96), primary_key=True), sa.Column("account_id", sa.String(64), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False), sa.Column("source_shard_id", sa.String(255), nullable=False), sa.Column("watermark", sa.String(255)), sa.Column("latest_source_at", sa.DateTime(timezone=True)), sa.Column("freshness_status", sa.String(64), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("account_id", "source_shard_id", name="uq_sync_shard_source"))
    op.create_table("sync_runs", sa.Column("id", sa.String(64), primary_key=True), sa.Column("account_id", sa.String(64), nullable=False), sa.Column("mode", sa.String(32), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("inserted_count", sa.Integer(), nullable=False), sa.Column("duplicate_count", sa.Integer(), nullable=False), sa.Column("error_code", sa.String(128)), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            message_id UNINDEXED,
            account_id UNINDEXED,
            conversation_id UNINDEXED,
            text_content,
            tokenize = 'trigram'
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS messages_fts")
    Base.metadata.drop_all(op.get_bind())
