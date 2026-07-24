import json
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timezone

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session, selectinload, sessionmaker

from .config import Settings, get_settings
from .connectors import Connector, SyntheticConnector, WxCliConnector
from .database import build_engine, get_db, initialize_database
from .models import ActionItem, ActionItemEvidence, ActionItemHistoryEvent, ActionItemHistoryEvidence, Contact, ContactProfileHistoryEvent, Conversation, Fact, FactHistoryEvent, FactHistoryMessageEvidence, FactMessageEvidence, KnowledgeCard, KnowledgeCardEvidence, KnowledgeCardHistoryEvent, KnowledgeCardHistoryEvidence, Message, SyncRun
from .schemas import AccountSummary, ActionItemHistoryResponse, ActionItemResponse, ActionItemWriteRequest, AttachmentSummary, ContactProfileHistoryResponse, ContactProfileWriteRequest, ContactResponse, FactHistoryResponse, FactResponse, FactWriteRequest, KnowledgeCardHistoryResponse, KnowledgeCardResponse, KnowledgeCardWriteRequest, MessageContextResponse, MessageSearchItem, SourceStatusResponse, StorageStatusResponse, SyncRequest, SyncRunResponse, SyncScheduleResponse
from .services.scheduler import AutomaticSyncScheduler, SyncCoordinator
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
        confirmed_real_name=contact.confirmed_real_name,
        company=contact.company,
        role=contact.role,
        user_remark_name=contact.user_remark_name,
        user_confirmed_real_name=contact.user_confirmed_real_name,
        user_company=contact.user_company,
        user_role=contact.user_role,
        effective_company=contact.effective_company,
        effective_role=contact.effective_role,
        avatar_ref=contact.avatar_ref,
        avatar_version=contact.avatar_version,
        avatar_updated_at=contact.avatar_updated_at,
        last_message_at=contact.last_message_at,
    )


def attachment_summaries(serialized_metadata: str | None) -> list[AttachmentSummary]:
    if not serialized_metadata:
        return []
    try:
        metadata = json.loads(serialized_metadata)
    except (TypeError, json.JSONDecodeError):
        return []
    items = metadata if isinstance(metadata, list) else [metadata]
    summaries: list[AttachmentSummary] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_name = next((item.get(key) for key in ("file_name", "filename", "name", "title") if isinstance(item.get(key), str)), None)
        name = raw_name.replace("\\", "/").rsplit("/", 1)[-1] if raw_name else None
        raw_size = item.get("size_bytes", item.get("size"))
        size_bytes = raw_size if isinstance(raw_size, int) and raw_size >= 0 else None
        mime_type = item.get("mime_type", item.get("mime"))
        summaries.append(AttachmentSummary(name=name, mime_type=mime_type if isinstance(mime_type, str) else None, size_bytes=size_bytes))
    return summaries


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
        attachments=attachment_summaries(message.attachment_metadata),
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


def profile_history_response(event: ContactProfileHistoryEvent) -> ContactProfileHistoryResponse:
    return ContactProfileHistoryResponse(
        id=event.id,
        account_id=event.account_id,
        contact_id=event.contact_id,
        user_remark_name=event.user_remark_name,
        user_confirmed_real_name=event.user_confirmed_real_name,
        user_company=event.user_company,
        user_role=event.user_role,
        occurred_at=event.occurred_at,
    )


def record_contact_profile_history(db: Session, contact: Contact) -> None:
    db.add(ContactProfileHistoryEvent(
        id=str(uuid.uuid4()),
        account_id=contact.account_id,
        contact_id=contact.id,
        user_remark_name=contact.user_remark_name,
        user_confirmed_real_name=contact.user_confirmed_real_name,
        user_company=contact.user_company,
        user_role=contact.user_role,
    ))


def knowledge_card_response(card: KnowledgeCard) -> KnowledgeCardResponse:
    return KnowledgeCardResponse(id=card.id, account_id=card.account_id, card_type=card.card_type, title=card.title, content=card.content, created_at=card.created_at, updated_at=card.updated_at, evidence=[message_item(link.message, link.message.conversation) for link in card.evidence])


def knowledge_card_history_response(event: KnowledgeCardHistoryEvent) -> KnowledgeCardHistoryResponse:
    return KnowledgeCardHistoryResponse(id=event.id, account_id=event.account_id, card_id=event.card_id, event_type=event.event_type, card_type=event.card_type, title=event.title, content=event.content, occurred_at=event.occurred_at, evidence=[message_item(link.message, link.message.conversation) for link in event.evidence])


def action_item_response(item: ActionItem) -> ActionItemResponse:
    return ActionItemResponse(id=item.id, account_id=item.account_id, content=item.content, status=item.status, due_at=item.due_at, created_at=item.created_at, updated_at=item.updated_at, evidence=[message_item(link.message, link.message.conversation) for link in item.evidence])


def action_item_history_response(event: ActionItemHistoryEvent) -> ActionItemHistoryResponse:
    return ActionItemHistoryResponse(id=event.id, account_id=event.account_id, action_item_id=event.action_item_id, event_type=event.event_type, content=event.content, status=event.status, due_at=event.due_at, occurred_at=event.occurred_at, evidence=[message_item(link.message, link.message.conversation) for link in event.evidence])


def knowledge_card_messages_or_422(db: Session, account_id: str, message_ids: list[str]) -> list[Message]:
    unique_ids = list(dict.fromkeys(message_ids))
    messages = list(db.scalars(select(Message).where(Message.id.in_(unique_ids), Message.account_id == account_id)))
    if len(messages) != len(unique_ids):
        raise HTTPException(status_code=422, detail="knowledge_card_evidence_message_not_found")
    return messages


def action_item_messages_or_422(db: Session, account_id: str, message_ids: list[str]) -> list[Message]:
    unique_ids = list(dict.fromkeys(message_ids))
    messages = list(db.scalars(select(Message).where(Message.id.in_(unique_ids), Message.account_id == account_id)))
    if len(messages) != len(unique_ids):
        raise HTTPException(status_code=422, detail="action_item_evidence_message_not_found")
    return messages


def record_action_item_history(db: Session, item: ActionItem, event_type: str, evidence: list[Message]) -> None:
    event = ActionItemHistoryEvent(id=str(uuid.uuid4()), account_id=item.account_id, action_item_id=item.id, event_type=event_type, content=item.content, status=item.status, due_at=item.due_at)
    db.add(event)
    db.flush()
    for message in evidence:
        db.add(ActionItemHistoryEvidence(id=str(uuid.uuid4()), event_id=event.id, message_id=message.id))


def record_knowledge_card_history(db: Session, card: KnowledgeCard, event_type: str, evidence: list[Message]) -> None:
    event = KnowledgeCardHistoryEvent(id=str(uuid.uuid4()), account_id=card.account_id, card_id=card.id, event_type=event_type, card_type=card.card_type, title=card.title, content=card.content)
    db.add(event)
    db.flush()
    for message in evidence:
        db.add(KnowledgeCardHistoryEvidence(id=str(uuid.uuid4()), event_id=event.id, message_id=message.id))


def normalized_profile_value(value: str | None) -> str | None:
    return value.strip() or None if value is not None else None


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
        session_factory = sessionmaker(bind=app_engine, autoflush=False, expire_on_commit=False)
        coordinator = SyncCoordinator()
        # The real connector remains an explicit Go/No-Go operation.  Automatic
        # work is available only for the deterministic synthetic connector.
        scheduler = AutomaticSyncScheduler(
            current_connector,
            session_factory,
            coordinator,
            current_settings.sync_overlap_seconds,
            current_settings.auto_sync_interval_seconds,
            current_settings.auto_sync_enabled and current_settings.connector == "synthetic",
        )
        _app.state.sync_coordinator = coordinator
        _app.state.sync_scheduler = scheduler
        scheduler.start()
        yield
        scheduler.stop()
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
        lock = app.state.sync_coordinator.try_acquire(request.account_id)
        if not lock:
            raise HTTPException(
                status_code=409,
                detail={"status": "failed", "error_code": "sync_in_progress", "reason": "A sync is already running for this account."},
            )
        try:
            service = SyncService(app.state.connector, app.state.settings.sync_overlap_seconds)
            return service.run(db, request.account_id, request.mode, request.limit_sessions)
        finally:
            lock.release()

    @app.get("/api/v1/sync/runs/{run_id}", response_model=SyncRunResponse)
    def get_sync_run(run_id: str, db: Session = Depends(get_db)) -> SyncRun:
        run = db.get(SyncRun, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="sync_run_not_found")
        return run

    @app.get("/api/v1/sync/runs", response_model=list[SyncRunResponse])
    def list_sync_runs(
        account_id: str,
        limit: int = Query(20, ge=1, le=100),
        db: Session = Depends(get_db),
    ) -> list[SyncRun]:
        return db.scalars(
            select(SyncRun)
            .where(SyncRun.account_id == account_id)
            .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
            .limit(limit)
        ).all()

    @app.get("/api/v1/sync/schedule", response_model=SyncScheduleResponse)
    def sync_schedule() -> SyncScheduleResponse:
        scheduler = app.state.sync_scheduler
        reason = None
        if not scheduler.enabled:
            reason = "Automatic sync is restricted to the synthetic connector until real collection receives Go/No-Go authorization."
        return SyncScheduleResponse(
            enabled=scheduler.enabled,
            interval_seconds=scheduler.interval_seconds,
            reason=reason,
            last_cycle_at=scheduler.last_cycle_at,
            next_run_at=scheduler.next_run_at,
        )

    @app.get("/api/v1/storage/status", response_model=StorageStatusResponse)
    def storage_status(account_id: str, db: Session = Depends(get_db)) -> StorageStatusResponse:
        integrity = db.execute(text("PRAGMA integrity_check")).scalar() or "unknown"
        return StorageStatusResponse(
            account_id=account_id,
            contacts=db.scalar(select(func.count(Contact.id)).where(Contact.account_id == account_id)) or 0,
            conversations=db.scalar(select(func.count(Conversation.id)).where(Conversation.account_id == account_id)) or 0,
            messages=db.scalar(select(func.count(Message.id)).where(Message.account_id == account_id)) or 0,
            facts=db.scalar(select(func.count(Fact.id)).where(Fact.account_id == account_id)) or 0,
            knowledge_cards=db.scalar(select(func.count(KnowledgeCard.id)).where(KnowledgeCard.account_id == account_id)) or 0,
            integrity_check=str(integrity),
        )

    @app.get("/api/v1/contacts", response_model=list[ContactResponse])
    def list_contacts(account_id: str, query: str | None = None, limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)) -> list[ContactResponse]:
        statement = select(Contact).where(Contact.account_id == account_id)
        if query:
            like = f"%{query}%"
            statement = statement.where(or_(Contact.user_remark_name.like(like), Contact.remark_name.like(like), Contact.user_confirmed_real_name.like(like), Contact.nickname.like(like), Contact.confirmed_real_name.like(like), Contact.user_company.like(like), Contact.company.like(like), Contact.user_role.like(like), Contact.role.like(like)))
        statement = statement.order_by(Contact.last_message_at.desc().nullslast(), func.coalesce(Contact.user_remark_name, Contact.remark_name, Contact.user_confirmed_real_name, Contact.nickname, Contact.confirmed_real_name, Contact.source_id)).limit(limit)
        return [contact_response(contact) for contact in db.scalars(statement)]

    @app.get("/api/v1/contacts/{contact_id}", response_model=ContactResponse)
    def get_contact(contact_id: str, db: Session = Depends(get_db)) -> ContactResponse:
        contact = db.get(Contact, contact_id)
        if not contact:
            raise HTTPException(status_code=404, detail="contact_not_found")
        return contact_response(contact)

    @app.patch("/api/v1/contacts/{contact_id}/profile", response_model=ContactResponse)
    def update_contact_profile(contact_id: str, request: ContactProfileWriteRequest, account_id: str, db: Session = Depends(get_db)) -> ContactResponse:
        contact = account_contact_or_404(db, contact_id, account_id)
        fields = {
            "remark_name": "user_remark_name",
            "confirmed_real_name": "user_confirmed_real_name",
            "company": "user_company",
            "role": "user_role",
        }
        changed = False
        for request_field, model_field in fields.items():
            if request_field not in request.model_fields_set:
                continue
            value = normalized_profile_value(getattr(request, request_field))
            if getattr(contact, model_field) != value:
                setattr(contact, model_field, value)
                changed = True
        if changed:
            record_contact_profile_history(db, contact)
            db.commit()
            db.refresh(contact)
        return contact_response(contact)

    @app.get("/api/v1/contacts/{contact_id}/profile-history", response_model=list[ContactProfileHistoryResponse])
    def list_contact_profile_history(
        contact_id: str,
        account_id: str,
        limit: int = Query(100, ge=1, le=500),
        db: Session = Depends(get_db),
    ) -> list[ContactProfileHistoryResponse]:
        account_contact_or_404(db, contact_id, account_id)
        events = db.scalars(
            select(ContactProfileHistoryEvent)
            .where(ContactProfileHistoryEvent.account_id == account_id, ContactProfileHistoryEvent.contact_id == contact_id)
            .order_by(ContactProfileHistoryEvent.occurred_at.desc(), ContactProfileHistoryEvent.id.desc())
            .limit(limit)
        ).all()
        return [profile_history_response(event) for event in events]

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

    @app.get("/api/v1/knowledge-cards", response_model=list[KnowledgeCardResponse])
    def list_knowledge_cards(account_id: str, limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)) -> list[KnowledgeCardResponse]:
        cards = db.scalars(select(KnowledgeCard).where(KnowledgeCard.account_id == account_id).options(selectinload(KnowledgeCard.evidence).selectinload(KnowledgeCardEvidence.message).selectinload(Message.conversation)).order_by(KnowledgeCard.updated_at.desc(), KnowledgeCard.id.desc()).limit(limit)).all()
        return [knowledge_card_response(card) for card in cards]

    @app.post("/api/v1/knowledge-cards", response_model=KnowledgeCardResponse, status_code=201)
    def create_knowledge_card(request: KnowledgeCardWriteRequest, account_id: str, db: Session = Depends(get_db)) -> KnowledgeCardResponse:
        title, content = request.title.strip(), request.content.strip()
        if not title or not content:
            raise HTTPException(status_code=422, detail="knowledge_card_content_required")
        evidence = knowledge_card_messages_or_422(db, account_id, request.message_ids)
        card = KnowledgeCard(id=str(uuid.uuid4()), account_id=account_id, card_type=request.card_type, title=title, content=content)
        db.add(card)
        db.flush()
        for message in evidence:
            db.add(KnowledgeCardEvidence(id=str(uuid.uuid4()), card_id=card.id, message_id=message.id))
        record_knowledge_card_history(db, card, "created", evidence)
        db.commit()
        card = db.scalar(select(KnowledgeCard).where(KnowledgeCard.id == card.id).options(selectinload(KnowledgeCard.evidence).selectinload(KnowledgeCardEvidence.message).selectinload(Message.conversation)))
        return knowledge_card_response(card)

    @app.patch("/api/v1/knowledge-cards/{card_id}", response_model=KnowledgeCardResponse)
    def update_knowledge_card(card_id: str, request: KnowledgeCardWriteRequest, account_id: str, db: Session = Depends(get_db)) -> KnowledgeCardResponse:
        card = db.scalar(select(KnowledgeCard).where(KnowledgeCard.id == card_id, KnowledgeCard.account_id == account_id))
        if not card:
            raise HTTPException(status_code=404, detail="knowledge_card_not_found")
        title, content = request.title.strip(), request.content.strip()
        if not title or not content:
            raise HTTPException(status_code=422, detail="knowledge_card_content_required")
        evidence = knowledge_card_messages_or_422(db, account_id, request.message_ids)
        card.card_type, card.title, card.content = request.card_type, title, content
        db.query(KnowledgeCardEvidence).filter(KnowledgeCardEvidence.card_id == card.id).delete()
        for message in evidence:
            db.add(KnowledgeCardEvidence(id=str(uuid.uuid4()), card_id=card.id, message_id=message.id))
        record_knowledge_card_history(db, card, "updated", evidence)
        db.commit()
        card = db.scalar(select(KnowledgeCard).where(KnowledgeCard.id == card.id).options(selectinload(KnowledgeCard.evidence).selectinload(KnowledgeCardEvidence.message).selectinload(Message.conversation)))
        return knowledge_card_response(card)

    @app.delete("/api/v1/knowledge-cards/{card_id}", status_code=204)
    def delete_knowledge_card(card_id: str, account_id: str, db: Session = Depends(get_db)) -> None:
        card = db.scalar(select(KnowledgeCard).where(KnowledgeCard.id == card_id, KnowledgeCard.account_id == account_id).options(selectinload(KnowledgeCard.evidence).selectinload(KnowledgeCardEvidence.message)))
        if not card:
            raise HTTPException(status_code=404, detail="knowledge_card_not_found")
        record_knowledge_card_history(db, card, "deleted", [link.message for link in card.evidence])
        db.delete(card)
        db.commit()

    @app.get("/api/v1/action-items", response_model=list[ActionItemResponse])
    def list_action_items(account_id: str, status: str | None = Query(default=None, pattern="^(open|done)$"), db: Session = Depends(get_db)) -> list[ActionItemResponse]:
        statement = select(ActionItem).where(ActionItem.account_id == account_id).options(selectinload(ActionItem.evidence).selectinload(ActionItemEvidence.message).selectinload(Message.conversation))
        if status:
            statement = statement.where(ActionItem.status == status)
        return [action_item_response(item) for item in db.scalars(statement.order_by(ActionItem.due_at.is_(None), ActionItem.due_at, ActionItem.updated_at.desc()))]

    @app.post("/api/v1/action-items", response_model=ActionItemResponse, status_code=201)
    def create_action_item(request: ActionItemWriteRequest, account_id: str, db: Session = Depends(get_db)) -> ActionItemResponse:
        content = request.content.strip()
        if not content:
            raise HTTPException(status_code=422, detail="action_item_content_required")
        evidence = action_item_messages_or_422(db, account_id, request.message_ids)
        item = ActionItem(id=str(uuid.uuid4()), account_id=account_id, content=content, status=request.status, due_at=request.due_at)
        db.add(item)
        db.flush()
        for message in evidence:
            db.add(ActionItemEvidence(id=str(uuid.uuid4()), action_item_id=item.id, message_id=message.id))
        record_action_item_history(db, item, "created", evidence)
        db.commit()
        item = db.scalar(select(ActionItem).where(ActionItem.id == item.id).options(selectinload(ActionItem.evidence).selectinload(ActionItemEvidence.message).selectinload(Message.conversation)))
        return action_item_response(item)

    @app.patch("/api/v1/action-items/{item_id}", response_model=ActionItemResponse)
    def update_action_item(item_id: str, request: ActionItemWriteRequest, account_id: str, db: Session = Depends(get_db)) -> ActionItemResponse:
        item = db.scalar(select(ActionItem).where(ActionItem.id == item_id, ActionItem.account_id == account_id).options(selectinload(ActionItem.evidence).selectinload(ActionItemEvidence.message)))
        if not item:
            raise HTTPException(status_code=404, detail="action_item_not_found")
        content = request.content.strip()
        if not content:
            raise HTTPException(status_code=422, detail="action_item_content_required")
        evidence = action_item_messages_or_422(db, account_id, request.message_ids)
        item.content, item.status, item.due_at = content, request.status, request.due_at
        item.evidence.clear()
        db.flush()
        for message in evidence:
            db.add(ActionItemEvidence(id=str(uuid.uuid4()), action_item_id=item.id, message_id=message.id))
        record_action_item_history(db, item, "updated", evidence)
        db.commit()
        item = db.scalar(select(ActionItem).where(ActionItem.id == item.id).options(selectinload(ActionItem.evidence).selectinload(ActionItemEvidence.message).selectinload(Message.conversation)))
        return action_item_response(item)

    @app.delete("/api/v1/action-items/{item_id}", status_code=204)
    def delete_action_item(item_id: str, account_id: str, db: Session = Depends(get_db)) -> None:
        item = db.scalar(select(ActionItem).where(ActionItem.id == item_id, ActionItem.account_id == account_id).options(selectinload(ActionItem.evidence).selectinload(ActionItemEvidence.message)))
        if not item:
            raise HTTPException(status_code=404, detail="action_item_not_found")
        record_action_item_history(db, item, "deleted", [link.message for link in item.evidence])
        db.delete(item)
        db.commit()

    @app.get("/api/v1/action-items/{item_id}/history", response_model=list[ActionItemHistoryResponse])
    def action_item_history(item_id: str, account_id: str, limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)) -> list[ActionItemHistoryResponse]:
        item = db.scalar(select(ActionItem).where(ActionItem.id == item_id, ActionItem.account_id == account_id))
        has_history = db.scalar(select(ActionItemHistoryEvent.id).where(ActionItemHistoryEvent.action_item_id == item_id, ActionItemHistoryEvent.account_id == account_id).limit(1))
        if not item and not has_history:
            raise HTTPException(status_code=404, detail="action_item_not_found")
        events = db.scalars(select(ActionItemHistoryEvent).where(ActionItemHistoryEvent.action_item_id == item_id, ActionItemHistoryEvent.account_id == account_id).options(selectinload(ActionItemHistoryEvent.evidence).selectinload(ActionItemHistoryEvidence.message).selectinload(Message.conversation)).order_by(ActionItemHistoryEvent.occurred_at.desc(), ActionItemHistoryEvent.id.desc()).limit(limit)).all()
        return [action_item_history_response(event) for event in events]

    @app.get("/api/v1/knowledge-cards/{card_id}/history", response_model=list[KnowledgeCardHistoryResponse])
    def knowledge_card_history(card_id: str, account_id: str, limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)) -> list[KnowledgeCardHistoryResponse]:
        card = db.scalar(select(KnowledgeCard).where(KnowledgeCard.id == card_id, KnowledgeCard.account_id == account_id))
        has_history = db.scalar(select(KnowledgeCardHistoryEvent.id).where(KnowledgeCardHistoryEvent.card_id == card_id, KnowledgeCardHistoryEvent.account_id == account_id).limit(1))
        if not card and not has_history:
            raise HTTPException(status_code=404, detail="knowledge_card_not_found")
        events = db.scalars(select(KnowledgeCardHistoryEvent).where(KnowledgeCardHistoryEvent.card_id == card_id, KnowledgeCardHistoryEvent.account_id == account_id).options(selectinload(KnowledgeCardHistoryEvent.evidence).selectinload(KnowledgeCardHistoryEvidence.message).selectinload(Message.conversation)).order_by(KnowledgeCardHistoryEvent.occurred_at.desc(), KnowledgeCardHistoryEvent.id.desc()).limit(limit)).all()
        return [knowledge_card_history_response(event) for event in events]

    @app.get("/api/v1/messages/search", response_model=list[MessageSearchItem])
    def search_messages(
        account_id: str,
        q: str,
        conversation_id: str | None = None,
        contact_id: str | None = None,
        message_type: str | None = None,
        has_attachment: bool | None = None,
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
        if contact_id:
            contact = account_contact_or_404(db, contact_id, account_id)
            filters.append("((c.conversation_type = 'private' AND c.source_id = :contact_source_id) OR (c.conversation_type = 'group' AND m.sender_id = :contact_source_id))")
            params["contact_source_id"] = contact.source_id
        if message_type:
            filters.append("m.message_type = :message_type")
            params["message_type"] = message_type
        if has_attachment is True:
            filters.append("m.attachment_metadata IS NOT NULL")
        if date_from:
            filters.append("m.sent_at >= :date_from")
            params["date_from"] = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        if date_to:
            filters.append("m.sent_at <= :date_to")
            params["date_to"] = datetime.combine(date_to, time.max, tzinfo=timezone.utc)
        rows = db.execute(text(f"""
            SELECT m.id, m.conversation_id, c.display_name, c.conversation_type,
                   m.sender_display_name, m.sent_at, m.message_type, m.text_content, m.attachment_metadata,
                   snippet(messages_fts, 3, '<mark>', '</mark>', '…', 12) AS hit_snippet
            FROM messages_fts
            JOIN messages m ON m.id = messages_fts.message_id
            JOIN conversations c ON c.id = m.conversation_id
            WHERE {' AND '.join(filters)}
            ORDER BY bm25(messages_fts), m.sent_at DESC
            LIMIT :limit
        """), params).mappings().all()
        return [MessageSearchItem(id=row["id"], conversation_id=row["conversation_id"], conversation_name=row["display_name"], conversation_type=row["conversation_type"], sender_display_name=row["sender_display_name"], sent_at=row["sent_at"], message_type=row["message_type"], text_content=row["text_content"], snippet=row["hit_snippet"], attachments=attachment_summaries(row["attachment_metadata"])) for row in rows]

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
