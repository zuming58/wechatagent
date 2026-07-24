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
    user_remark_name: Mapped[str | None] = mapped_column(String(255))
    user_confirmed_real_name: Mapped[str | None] = mapped_column(String(255))
    user_company: Mapped[str | None] = mapped_column(String(255))
    user_role: Mapped[str | None] = mapped_column(String(255))
    avatar_ref: Mapped[str | None] = mapped_column(Text)
    avatar_version: Mapped[str | None] = mapped_column(String(128))
    avatar_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    @property
    def display_name(self) -> str:
        return self.user_remark_name or self.remark_name or self.user_confirmed_real_name or self.nickname or self.confirmed_real_name or self.source_id[-8:]

    @property
    def effective_company(self) -> str | None:
        return self.user_company or self.company

    @property
    def effective_role(self) -> str | None:
        return self.user_role or self.role


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


class Fact(Base):
    __tablename__ = "facts"
    __table_args__ = (
        Index("ix_fact_account_contact_updated", "account_id", "contact_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    evidence: Mapped[list["FactMessageEvidence"]] = relationship(back_populates="fact", cascade="all, delete-orphan")


class FactMessageEvidence(Base):
    __tablename__ = "fact_message_evidence"
    __table_args__ = (
        UniqueConstraint("fact_id", "message_id", name="uq_fact_message_evidence"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fact_id: Mapped[str] = mapped_column(ForeignKey("facts.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    fact: Mapped[Fact] = relationship(back_populates="evidence")
    message: Mapped[Message] = relationship()


class FactHistoryEvent(Base):
    __tablename__ = "fact_history_events"
    __table_args__ = (
        Index("ix_fact_history_account_contact_occurred", "account_id", "contact_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    fact_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    evidence: Mapped[list["FactHistoryMessageEvidence"]] = relationship(back_populates="event", cascade="all, delete-orphan")


class FactHistoryMessageEvidence(Base):
    __tablename__ = "fact_history_message_evidence"
    __table_args__ = (
        UniqueConstraint("event_id", "message_id", name="uq_fact_history_message_evidence"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("fact_history_events.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)

    event: Mapped[FactHistoryEvent] = relationship(back_populates="evidence")
    message: Mapped[Message] = relationship()


class ContactProfileHistoryEvent(Base):
    __tablename__ = "contact_profile_history_events"
    __table_args__ = (
        Index("ix_contact_profile_history_account_contact_occurred", "account_id", "contact_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    user_remark_name: Mapped[str | None] = mapped_column(String(255))
    user_confirmed_real_name: Mapped[str | None] = mapped_column(String(255))
    user_company: Mapped[str | None] = mapped_column(String(255))
    user_role: Mapped[str | None] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class KnowledgeCard(Base):
    __tablename__ = "knowledge_cards"
    __table_args__ = (Index("ix_knowledge_card_account_updated", "account_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    card_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    evidence: Mapped[list["KnowledgeCardEvidence"]] = relationship(back_populates="card", cascade="all, delete-orphan")


class KnowledgeCardEvidence(Base):
    __tablename__ = "knowledge_card_evidence"
    __table_args__ = (UniqueConstraint("card_id", "message_id", name="uq_knowledge_card_evidence"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    card_id: Mapped[str] = mapped_column(ForeignKey("knowledge_cards.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    card: Mapped[KnowledgeCard] = relationship(back_populates="evidence")
    message: Mapped[Message] = relationship()


class KnowledgeCardHistoryEvent(Base):
    __tablename__ = "knowledge_card_history_events"
    __table_args__ = (Index("ix_knowledge_card_history_account_occurred", "account_id", "occurred_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    card_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    card_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    evidence: Mapped[list["KnowledgeCardHistoryEvidence"]] = relationship(back_populates="event", cascade="all, delete-orphan")


class KnowledgeCardHistoryEvidence(Base):
    __tablename__ = "knowledge_card_history_evidence"
    __table_args__ = (UniqueConstraint("event_id", "message_id", name="uq_knowledge_card_history_evidence"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("knowledge_card_history_events.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    event: Mapped[KnowledgeCardHistoryEvent] = relationship(back_populates="evidence")
    message: Mapped[Message] = relationship()


class ActionItem(Base):
    __tablename__ = "action_items"
    __table_args__ = (Index("ix_action_item_account_updated", "account_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    evidence: Mapped[list["ActionItemEvidence"]] = relationship(back_populates="item", cascade="all, delete-orphan")


class ActionItemEvidence(Base):
    __tablename__ = "action_item_evidence"
    __table_args__ = (UniqueConstraint("action_item_id", "message_id", name="uq_action_item_evidence"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    action_item_id: Mapped[str] = mapped_column(ForeignKey("action_items.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    item: Mapped[ActionItem] = relationship(back_populates="evidence")
    message: Mapped[Message] = relationship()


class ActionItemHistoryEvent(Base):
    __tablename__ = "action_item_history_events"
    __table_args__ = (Index("ix_action_item_history_account_item", "account_id", "action_item_id", "occurred_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    action_item_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    evidence: Mapped[list["ActionItemHistoryEvidence"]] = relationship(back_populates="event", cascade="all, delete-orphan")


class ActionItemHistoryEvidence(Base):
    __tablename__ = "action_item_history_evidence"
    __table_args__ = (UniqueConstraint("event_id", "message_id", name="uq_action_item_history_evidence"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("action_item_history_events.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    event: Mapped[ActionItemHistoryEvent] = relationship(back_populates="evidence")
    message: Mapped[Message] = relationship()


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("account_id", "name", name="uq_tag_account_name"),
        Index("ix_tag_account_name", "account_id", "name"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class TagLink(Base):
    __tablename__ = "tag_links"
    __table_args__ = (
        UniqueConstraint("tag_id", "target_type", "target_id", name="uq_tag_link_target"),
        Index("ix_tag_link_account_target", "account_id", "target_type", "target_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    tag_id: Mapped[str] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), index=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


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
