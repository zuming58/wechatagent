from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AccountSummary(BaseModel):
    id: str
    display_name: str
    selected: bool


class SourceStatusResponse(BaseModel):
    status: str
    wechat_version: str | None = None
    connector_version: str | None = None
    accounts: list[AccountSummary] = []
    reason: str | None = None
    requires_elevation: bool = False
    unknown_shards: list[str] = []


class SyncRequest(BaseModel):
    account_id: str
    mode: str = Field(default="incremental", pattern="^(initial|incremental)$")
    limit_sessions: int | None = Field(default=None, ge=1, le=20)


class SyncRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    account_id: str
    mode: str
    status: str
    inserted_count: int
    duplicate_count: int
    error_code: str | None
    started_at: datetime
    completed_at: datetime | None


class SyncScheduleResponse(BaseModel):
    enabled: bool
    interval_seconds: int
    reason: str | None = None
    last_cycle_at: datetime | None = None
    next_run_at: datetime | None = None


class StorageStatusResponse(BaseModel):
    account_id: str
    contacts: int
    conversations: int
    messages: int
    facts: int
    knowledge_cards: int
    integrity_check: str


class ActionItemWriteRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    status: str = Field(default="open", pattern="^(open|done)$")
    due_at: datetime | None = None
    message_ids: list[str] = Field(default_factory=list, max_length=50)


class ActionItemResponse(BaseModel):
    id: str
    account_id: str
    content: str
    status: str
    due_at: datetime | None
    created_at: datetime
    updated_at: datetime
    evidence: list["MessageSearchItem"]


class ActionItemHistoryResponse(BaseModel):
    id: str
    account_id: str
    action_item_id: str
    event_type: str
    content: str
    status: str
    due_at: datetime | None
    occurred_at: datetime
    evidence: list["MessageSearchItem"]


class ContactResponse(BaseModel):
    id: str
    source_id: str
    display_name: str
    remark_name: str | None
    nickname: str | None
    confirmed_real_name: str | None
    company: str | None
    role: str | None
    user_remark_name: str | None
    user_confirmed_real_name: str | None
    user_company: str | None
    user_role: str | None
    effective_company: str | None
    effective_role: str | None
    avatar_ref: str | None
    avatar_version: str | None
    avatar_updated_at: datetime | None
    last_message_at: datetime | None


class AttachmentSummary(BaseModel):
    name: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None


class MessageSearchItem(BaseModel):
    id: str
    conversation_id: str
    conversation_name: str
    conversation_type: str
    sender_display_name: str
    sent_at: datetime
    message_type: str
    text_content: str
    snippet: str
    attachments: list[AttachmentSummary] = []


class MessageContextResponse(BaseModel):
    anchor_id: str
    messages: list[MessageSearchItem]


class TimelineEventResponse(BaseModel):
    id: str
    account_id: str
    kind: str
    event_type: str
    occurred_at: datetime
    title: str
    content: str
    contact_id: str | None = None
    contact_display_name: str | None = None
    message: MessageSearchItem | None = None
    evidence: list[MessageSearchItem] = []


class FactWriteRequest(BaseModel):
    kind: str = Field(pattern="^(company|role|need|concern|commitment)$")
    content: str = Field(min_length=1, max_length=2000)
    message_ids: list[str] = Field(default_factory=list, max_length=20)


class FactResponse(BaseModel):
    id: str
    account_id: str
    contact_id: str
    kind: str
    content: str
    created_at: datetime
    updated_at: datetime
    evidence: list[MessageSearchItem]


class FactHistoryResponse(BaseModel):
    id: str
    account_id: str
    contact_id: str
    fact_id: str
    event_type: str
    kind: str
    content: str
    occurred_at: datetime
    evidence: list[MessageSearchItem]


class ContactProfileWriteRequest(BaseModel):
    remark_name: str | None = Field(default=None, max_length=255)
    confirmed_real_name: str | None = Field(default=None, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=255)


class ContactProfileHistoryResponse(BaseModel):
    id: str
    account_id: str
    contact_id: str
    user_remark_name: str | None
    user_confirmed_real_name: str | None
    user_company: str | None
    user_role: str | None
    occurred_at: datetime


class KnowledgeCardWriteRequest(BaseModel):
    card_type: str = Field(pattern="^(contact|project|decision|note)$")
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=5000)
    message_ids: list[str] = Field(default_factory=list, max_length=50)


class KnowledgeCardResponse(BaseModel):
    id: str
    account_id: str
    card_type: str
    title: str
    content: str
    created_at: datetime
    updated_at: datetime
    evidence: list[MessageSearchItem]


class KnowledgeCardHistoryResponse(BaseModel):
    id: str
    account_id: str
    card_id: str
    event_type: str
    card_type: str
    title: str
    content: str
    occurred_at: datetime
    evidence: list[MessageSearchItem]
