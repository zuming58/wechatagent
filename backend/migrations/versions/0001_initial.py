"""Initial local message store.

Revision ID: 0001_initial
"""
from collections.abc import Sequence

from alembic import op

from app.database import Base
from app import models  # noqa: F401

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind)
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
