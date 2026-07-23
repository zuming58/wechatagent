import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timezone

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from .config import Settings, get_settings
from .connectors import Connector, SyntheticConnector, WxCliConnector
from .database import build_engine, get_db, initialize_database
from .models import Contact, Conversation, Fact, FactHistoryEvent, FactHistoryMessageEvidence, FactMessageEvidence, Message, SyncRun
from .schemas import AccountSummary, ContactResponse, FactHistoryResponse, FactResponse, FactWriteRequest, MessageContextResponse, MessageSearchItem, SourceStatusResponse, SyncRequest, SyncRunResponse
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


def fact_response(fact: Fact) -> FactResponse:
    return FactResponse(
        id=fact.id,
        account_id=fact.account_id,
        contact_id=fact.contact_id,
        kind=fact.kind,
        content=fact.content,
        created_at=fact.created_at,
        updated_at=fact.updated_at,
        evidence=[message_item(link.message, link.message.conversation) for link in fact.evidence],
    )


def fact_history_response(event: FactHistoryEvent) -> FactHistoryResponse:
    return FactHistoryResponse(
        id=event.id,
        account_id=event.account_id,
        contact_id=event.contact_id,
        fact_id=event.fact_id,
        event_type=event.event_type,
        kind=event.kind,
        content=event.content,
        occurred_at=event.occurred_at,
        evidence=[message_item(link.message, link.message.conversation) for link in event.evidence],
    )


def record_fact_history(db: Session, fact: Fact, event_type: str, evidence: list[Message]) -> None:
    event = FactHistoryEvent(
        id=str(uuid.uuid4()),
        account_id=fact.account_id,
        contact_id=fact.contact_id,
        fact_id=fact.id,
        event_type=event_type,
        kind=fact.kind,
        content=fact.content,
    )
    db.add(event)
    db.flush()
    for message in evidence:
        db.add(FactHistoryMessageEvidence(id=str(uuid.uuid4()), event_id=event.id, message_id=message.id))


def account_contact_or_404(db: Session, contact_id: str, account_id: str) -> Contact:
    contact = db.scalar(select(Contact).where(Contact.id == contact_id, Contact.account_id == account_id))
    if not contact:
        raise HTTPException(status_code=404, detail="contact_not_found")
    return contact


def fact_evidence_or_422(db: Session, contact: Contact, account_id: str, message_ids: list[str]) -> list[Message]:
    if not message_ids:
        return []
    unique_ids = list(dict.fromkeys(message_ids))
    messages = list(db.scalars(
        select(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Message.id.in_(unique_ids), Message.account_id == account_id)
    ))
    if len(messages) != len(unique_ids):
        raise HTTPException(status_code=422, detail="fact_evidence_message_not_found")
    for message in messages:
        conversation = message.conversation
        is_private_evidence = conversation.conversation_type == "private" and conversation.source_id == contact.source_id
        is_group_evidence = conversation.conversation_type == "group" and message.sender_id == contact.source_id
        if not is_private_evidence and not is_group_evidence:
            raise HTTPException(status_code=422, detail="fact_evidence_message_not_allowed")
    return messages


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
        if probe.status not in {"ready", "account_selection_required"}:
            raise HTTPException(
                status_code=409,
                detail={
                    "status": "failed",
                    "error_code": probe.status,
                    "reason": probe.reason,
                },
            )
        if request.account_id not in {account.id for account in probe.accounts}:
            raise HTTPException(
                status_code=409,
                detail={
                    "status": "failed",
                    "error_code": "account_not_available",
                    "reason": "Select one of the accounts currently detected on this device.",
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

    @app.get("/api/v1/contacts/{contact_id}/messages", response_model=list[MessageSearchItem])
    def contact_messages(
        contact_id: str,
        account_id: str,
        limit: int = Query(100, ge=1, le=500),
        db: Session = Depends(get_db),
    ) -> list[MessageSearchItem]:
        contact = account_contact_or_404(db, contact_id, account_id)

        statement = (
            select(Message, Conversation)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Message.account_id == account_id,
                or_(
                    and_(Conversation.conversation_type == "private", Conversation.source_id == contact.source_id),
                    and_(Conversation.conversation_type == "group", Message.sender_id == contact.source_id),
                ),
            )
            .order_by(Message.sent_at.desc())
            .limit(limit)
        )
        return [message_item(message, conversation) for message, conversation in db.execute(statement).all()]

    @app.get("/api/v1/contacts/{contact_id}/facts", response_model=list[FactResponse])
    def list_contact_facts(contact_id: str, account_id: str, db: Session = Depends(get_db)) -> list[FactResponse]:
        account_contact_or_404(db, contact_id, account_id)
        facts = db.scalars(
            select(Fact)
            .where(Fact.account_id == account_id, Fact.contact_id == contact_id)
            .options(selectinload(Fact.evidence).selectinload(FactMessageEvidence.message).selectinload(Message.conversation))
            .order_by(Fact.updated_at.desc(), Fact.id.desc())
        ).all()
        return [fact_response(fact) for fact in facts]

    @app.get("/api/v1/contacts/{contact_id}/fact-history", response_model=list[FactHistoryResponse])
    def list_contact_fact_history(
        contact_id: str,
        account_id: str,
        limit: int = Query(100, ge=1, le=500),
        db: Session = Depends(get_db),
    ) -> list[FactHistoryResponse]:
        account_contact_or_404(db, contact_id, account_id)
        events = db.scalars(
            select(FactHistoryEvent)
            .where(FactHistoryEvent.account_id == account_id, FactHistoryEvent.contact_id == contact_id)
            .options(selectinload(FactHistoryEvent.evidence).selectinload(FactHistoryMessageEvidence.message).selectinload(Message.conversation))
            .order_by(FactHistoryEvent.occurred_at.desc(), FactHistoryEvent.id.desc())
            .limit(limit)
        ).all()
        return [fact_history_response(event) for event in events]

    @app.post("/api/v1/contacts/{contact_id}/facts", response_model=FactResponse, status_code=201)
    def create_contact_fact(contact_id: str, request: FactWriteRequest, account_id: str, db: Session = Depends(get_db)) -> FactResponse:
        contact = account_contact_or_404(db, contact_id, account_id)
        evidence = fact_evidence_or_422(db, contact, account_id, request.message_ids)
        content = request.content.strip()
        if not content:
            raise HTTPException(status_code=422, detail="fact_content_required")
        fact = Fact(id=str(uuid.uuid4()), account_id=account_id, contact_id=contact.id, kind=request.kind, content=content)
        db.add(fact)
        db.flush()
        for message in evidence:
            db.add(FactMessageEvidence(id=str(uuid.uuid4()), fact_id=fact.id, message_id=message.id))
        record_fact_history(db, fact, "created", evidence)
        db.commit()
        fact = db.scalar(
            select(Fact).where(Fact.id == fact.id)
            .options(selectinload(Fact.evidence).selectinload(FactMessageEvidence.message).selectinload(Message.conversation))
        )
        return fact_response(fact)

    @app.patch("/api/v1/facts/{fact_id}", response_model=FactResponse)
    def update_fact(fact_id: str, request: FactWriteRequest, account_id: str, db: Session = Depends(get_db)) -> FactResponse:
        fact = db.scalar(select(Fact).where(Fact.id == fact_id, Fact.account_id == account_id))
        if not fact:
            raise HTTPException(status_code=404, detail="fact_not_found")
        contact = account_contact_or_404(db, fact.contact_id, account_id)
        evidence = fact_evidence_or_422(db, contact, account_id, request.message_ids)
        content = request.content.strip()
        if not content:
            raise HTTPException(status_code=422, detail="fact_content_required")
        fact.kind = request.kind
        fact.content = content
        db.query(FactMessageEvidence).filter(FactMessageEvidence.fact_id == fact.id).delete()
        for message in evidence:
            db.add(FactMessageEvidence(id=str(uuid.uuid4()), fact_id=fact.id, message_id=message.id))
        record_fact_history(db, fact, "updated", evidence)
        db.commit()
        fact = db.scalar(
            select(Fact).where(Fact.id == fact.id)
            .options(selectinload(Fact.evidence).selectinload(FactMessageEvidence.message).selectinload(Message.conversation))
        )
        return fact_response(fact)

    @app.delete("/api/v1/facts/{fact_id}", status_code=204)
    def delete_fact(fact_id: str, account_id: str, db: Session = Depends(get_db)) -> None:
        fact = db.scalar(
            select(Fact)
            .where(Fact.id == fact_id, Fact.account_id == account_id)
            .options(selectinload(Fact.evidence).selectinload(FactMessageEvidence.message))
        )
        if not fact:
            raise HTTPException(status_code=404, detail="fact_not_found")
        record_fact_history(db, fact, "deleted", [link.message for link in fact.evidence])
        db.delete(fact)
        db.commit()

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
