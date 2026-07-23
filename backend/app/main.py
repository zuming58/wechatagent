from contextlib import asynccontextmanager
from datetime import date, datetime, time, timezone

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .connectors import Connector, SyntheticConnector, WxCliConnector
from .database import build_engine, get_db, initialize_database
from .models import Contact, Conversation, Message, SyncRun
from .schemas import AccountSummary, ContactResponse, MessageContextResponse, MessageSearchItem, SourceStatusResponse, SyncRequest, SyncRunResponse
from .services.sync import SyncService


def build_connector(settings: Settings) -> Connector:
    if settings.connector == "wxcli":
        return WxCliConnector(settings.wx_command)
    return SyntheticConnector()


def contact_response(contact: Contact) -> ContactResponse:
    return ContactResponse(
        id=contact.id,
        source_id=contact.source_id,
        display_name=contact.display_name,
        remark_name=contact.remark_name,
        nickname=contact.nickname,
        company=contact.company,
        role=contact.role,
        avatar_ref=contact.avatar_ref,
        avatar_version=contact.avatar_version,
        avatar_updated_at=contact.avatar_updated_at,
        last_message_at=contact.last_message_at,
    )


def message_item(message: Message, conversation: Conversation, snippet: str | None = None) -> MessageSearchItem:
    return MessageSearchItem(
        id=message.id,
        conversation_id=message.conversation_id,
        conversation_name=conversation.display_name,
        conversation_type=conversation.conversation_type,
        sender_display_name=message.sender_display_name,
        sent_at=message.sent_at,
        message_type=message.message_type,
        text_content=message.text_content,
        snippet=snippet or message.text_content,
    )


def create_app(settings: Settings | None = None, connector: Connector | None = None) -> FastAPI:
    current_settings = settings or get_settings()
    current_connector = connector or build_connector(current_settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # The app owns the configured local database.  Tests can still replace
        # the request-scoped session dependency without creating the default DB.
        app_engine = build_engine(current_settings.database_url)
        initialize_database(app_engine)
        _app.state.database_engine = app_engine
        yield
        app_engine.dispose()

    app = FastAPI(title=current_settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.connector = current_connector
    app.state.settings = current_settings
    app.add_middleware(CORSMiddleware, allow_origins=[current_settings.allowed_origin], allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["*"])

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/source/status", response_model=SourceStatusResponse)
    def source_status() -> SourceStatusResponse:
        probe = app.state.connector.probe()
        return SourceStatusResponse(
            status=probe.status,
            wechat_version=probe.wechat_version,
            connector_version=probe.connector_version,
            accounts=[AccountSummary(id=item.id, display_name=item.display_name, selected=item.selected) for item in probe.accounts],
            reason=probe.reason,
            requires_elevation=probe.requires_elevation,
            unknown_shards=probe.unknown_shards,
        )

    @app.post("/api/v1/sync", response_model=SyncRunResponse)
    def start_sync(request: SyncRequest, db: Session = Depends(get_db)) -> SyncRun:
        probe = app.state.connector.probe()
        if probe.status != "ready":
            raise HTTPException(
                status_code=409,
                detail={
                    "status": "failed",
                    "error_code": probe.status,
                    "reason": probe.reason,
                },
            )
        service = SyncService(app.state.connector, app.state.settings.sync_overlap_seconds)
        return service.run(db, request.account_id, request.mode, request.limit_sessions)

    @app.get("/api/v1/sync/runs/{run_id}", response_model=SyncRunResponse)
    def get_sync_run(run_id: str, db: Session = Depends(get_db)) -> SyncRun:
        run = db.get(SyncRun, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="sync_run_not_found")
        return run

    @app.get("/api/v1/contacts", response_model=list[ContactResponse])
    def list_contacts(account_id: str, query: str | None = None, limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)) -> list[ContactResponse]:
        statement = select(Contact).where(Contact.account_id == account_id)
        if query:
            like = f"%{query}%"
            statement = statement.where(or_(Contact.remark_name.like(like), Contact.nickname.like(like), Contact.confirmed_real_name.like(like), Contact.company.like(like), Contact.role.like(like)))
        statement = statement.order_by(Contact.last_message_at.desc().nullslast(), Contact.remark_name, Contact.nickname).limit(limit)
        return [contact_response(contact) for contact in db.scalars(statement)]

    @app.get("/api/v1/contacts/{contact_id}", response_model=ContactResponse)
    def get_contact(contact_id: str, db: Session = Depends(get_db)) -> ContactResponse:
        contact = db.get(Contact, contact_id)
        if not contact:
            raise HTTPException(status_code=404, detail="contact_not_found")
        return contact_response(contact)

    @app.get("/api/v1/messages/search", response_model=list[MessageSearchItem])
    def search_messages(
        account_id: str,
        q: str,
        conversation_id: str | None = None,
        message_type: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = Query(100, ge=1, le=500),
        db: Session = Depends(get_db),
    ) -> list[MessageSearchItem]:
        filters = ["messages_fts.account_id = :account_id", "messages_fts MATCH :query"]
        params: dict[str, object] = {"account_id": account_id, "query": q, "limit": limit}
        if conversation_id:
            filters.append("m.conversation_id = :conversation_id")
            params["conversation_id"] = conversation_id
        if message_type:
            filters.append("m.message_type = :message_type")
            params["message_type"] = message_type
        if date_from:
            filters.append("m.sent_at >= :date_from")
            params["date_from"] = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        if date_to:
            filters.append("m.sent_at <= :date_to")
            params["date_to"] = datetime.combine(date_to, time.max, tzinfo=timezone.utc)
        rows = db.execute(text(f"""
            SELECT m.id, m.conversation_id, c.display_name, c.conversation_type,
                   m.sender_display_name, m.sent_at, m.message_type, m.text_content,
                   snippet(messages_fts, 3, '<mark>', '</mark>', '…', 12) AS hit_snippet
            FROM messages_fts
            JOIN messages m ON m.id = messages_fts.message_id
            JOIN conversations c ON c.id = m.conversation_id
            WHERE {' AND '.join(filters)}
            ORDER BY bm25(messages_fts), m.sent_at DESC
            LIMIT :limit
        """), params).mappings().all()
        return [MessageSearchItem(id=row["id"], conversation_id=row["conversation_id"], conversation_name=row["display_name"], conversation_type=row["conversation_type"], sender_display_name=row["sender_display_name"], sent_at=row["sent_at"], message_type=row["message_type"], text_content=row["text_content"], snippet=row["hit_snippet"]) for row in rows]

    @app.get("/api/v1/messages/{message_id}/context", response_model=MessageContextResponse)
    def message_context(message_id: str, radius: int = Query(3, ge=1, le=20), db: Session = Depends(get_db)) -> MessageContextResponse:
        anchor = db.get(Message, message_id)
        if not anchor:
            raise HTTPException(status_code=404, detail="message_not_found")
        before = list(db.scalars(select(Message).where(Message.conversation_id == anchor.conversation_id, Message.sent_at <= anchor.sent_at).order_by(Message.sent_at.desc()).limit(radius + 1)))
        after = list(db.scalars(select(Message).where(Message.conversation_id == anchor.conversation_id, Message.sent_at > anchor.sent_at).order_by(Message.sent_at).limit(radius)))
        messages = list(reversed(before)) + after
        conversation = db.get(Conversation, anchor.conversation_id)
        return MessageContextResponse(anchor_id=message_id, messages=[message_item(item, conversation) for item in messages])

    return app


app = create_app()
