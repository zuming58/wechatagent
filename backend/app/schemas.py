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


class ContactResponse(BaseModel):
    id: str
    source_id: str
    display_name: str
    remark_name: str | None
    nickname: str | None
    company: str | None
    role: str | None
    avatar_ref: str | None
    avatar_version: str | None
    avatar_updated_at: datetime | None
    last_message_at: datetime | None


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


class MessageContextResponse(BaseModel):
    anchor_id: str
    messages: list[MessageSearchItem]
