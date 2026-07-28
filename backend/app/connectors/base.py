from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class SourceAccount:
    id: str
    source_key: str
    display_name: str
    selected: bool = False


@dataclass(slots=True)
class SourceProbe:
    status: str
    wechat_version: str | None = None
    connector_version: str | None = None
    accounts: list[SourceAccount] = field(default_factory=list)
    reason: str | None = None
    requires_elevation: bool = False
    unknown_shards: list[str] = field(default_factory=list)


@dataclass(slots=True)
class StandardContact:
    source_id: str
    remark_name: str | None = None
    nickname: str | None = None
    avatar_ref: str | None = None
    avatar_version: str | None = None


@dataclass(slots=True)
class StandardConversation:
    source_id: str
    display_name: str
    conversation_type: str
    latest_message_at: datetime | None = None


@dataclass(slots=True)
class StandardMessage:
    source_shard_id: str
    source_message_id: str
    conversation_source_id: str
    conversation_display_name: str
    conversation_type: str
    sender_id: str
    sender_display_name: str
    sent_at: datetime
    direction: str
    message_type: str
    text_content: str
    structured_content: dict | None = None
    attachment_metadata: dict | None = None


@dataclass(slots=True)
class ConnectorBatch:
    account: SourceAccount
    contacts: list[StandardContact]
    conversations: list[StandardConversation]
    messages: list[StandardMessage]
    watermark_by_shard: dict[str, str]
    latest_by_shard: dict[str, datetime]
    freshness_status: str = "ok"
    unknown_shards: list[str] = field(default_factory=list)


class Connector(ABC):
    @abstractmethod
    def probe(self) -> SourceProbe:
        raise NotImplementedError

    @abstractmethod
    def collect(self, account_id: str, since: datetime | None, limit_sessions: int | None = None) -> ConnectorBatch:
        raise NotImplementedError
