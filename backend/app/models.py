from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(64))
    selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("account_id", "source_id", name="uq_conversation_source"),)

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    conversation_type: Mapped[str] = mapped_column(String(32), default="other", nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    latest_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("account_id", "source_id", name="uq_contact_source"),)

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    remark_name: Mapped[str | None] = mapped_column(String(255))
    nickname: Mapped[str | None] = mapped_column(String(255))
    confirmed_real_name: Mapped[str | None] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str | None] = mapped_column(String(255))
    avatar_ref: Mapped[str | None] = mapped_column(Text)
    avatar_version: Mapped[str | None] = mapped_column(String(128))
    avatar_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    @property
    def display_name(self) -> str:
        return self.remark_name or self.nickname or self.confirmed_real_name or self.source_id[-8:]


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("account_id", "source_shard_id", "source_message_id", name="uq_message_source"),
        Index("ix_message_account_conversation_time", "account_id", "conversation_id", "sent_at"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    source_shard_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    sender_id: Mapped[str] = mapped_column(String(255), index=True)
    sender_display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), nullable=False)
    text_content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    structured_content: Mapped[str | None] = mapped_column(Text)
    attachment_metadata: Mapped[str | None] = mapped_column(Text)
    source_freshness: Mapped[str] = mapped_column(String(64), default="ok", nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    conversation: Mapped[Conversation] = relationship()


class SyncShard(Base):
    __tablename__ = "sync_shards"
    __table_args__ = (UniqueConstraint("account_id", "source_shard_id", name="uq_sync_shard_source"),)

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    source_shard_id: Mapped[str] = mapped_column(String(255), nullable=False)
    watermark: Mapped[str | None] = mapped_column(String(255))
    latest_source_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    freshness_status: Mapped[str] = mapped_column(String(64), default="ok", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), index=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
