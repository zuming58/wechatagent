import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from ..connectors.base import Connector, ConnectorBatch, StandardMessage
from ..models import Account, Contact, Conversation, Message, SyncRun, SyncShard


def stable_id(prefix: str, *parts: str) -> str:
    payload = "|".join(parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]}"


class SyncService:
    def __init__(self, connector: Connector, overlap_seconds: int = 300) -> None:
        self.connector = connector
        self.overlap_seconds = overlap_seconds

    def _since(self, session: Session, account_id: str, mode: str) -> datetime | None:
        if mode == "initial":
            return None
        latest = session.scalar(select(SyncShard.latest_source_at).where(SyncShard.account_id == account_id).order_by(SyncShard.latest_source_at.desc()))
        return latest - timedelta(seconds=self.overlap_seconds) if latest else None

    def run(self, session: Session, account_id: str, mode: str = "incremental", limit_sessions: int | None = None) -> SyncRun:
        run = SyncRun(id=str(uuid.uuid4()), account_id=account_id, mode=mode, status="running")
        session.add(run)
        session.commit()

        try:
            batch = self.connector.collect(account_id, self._since(session, account_id, mode), limit_sessions)
            inserted, duplicates = self._apply_batch(session, batch)
            run.status = "completed" if batch.freshness_status == "ok" else "completed_with_warning"
            run.inserted_count = inserted
            run.duplicate_count = duplicates
            run.error_code = None if batch.freshness_status == "ok" else batch.freshness_status
        except Exception as error:
            session.rollback()
            run = session.get(SyncRun, run.id) or run
            run.status = "failed"
            run.error_code = str(error).split(":", 1)[0][:128]
        run.completed_at = datetime.now(timezone.utc)
        session.add(run)
        session.commit()
        session.refresh(run)
        return run

    def _apply_batch(self, session: Session, batch: ConnectorBatch) -> tuple[int, int]:
        account = session.get(Account, batch.account.id)
        if not account:
            account = Account(id=batch.account.id, source_key=batch.account.source_key, display_name=batch.account.display_name, selected=batch.account.selected)
            session.add(account)
        else:
            account.display_name = batch.account.display_name
            account.selected = batch.account.selected

        for source in batch.contacts:
            contact_id = stable_id("contact", batch.account.id, source.source_id)
            contact = session.get(Contact, contact_id)
            if not contact:
                contact = Contact(id=contact_id, account_id=batch.account.id, source_id=source.source_id)
                session.add(contact)
            contact.remark_name = source.remark_name
            contact.nickname = source.nickname
            if source.avatar_version != contact.avatar_version:
                contact.avatar_ref = source.avatar_ref
                contact.avatar_version = source.avatar_version
                contact.avatar_updated_at = datetime.now(timezone.utc)

        conversation_map: dict[str, Conversation] = {}
        for source in batch.conversations:
            conversation_id = stable_id("conversation", batch.account.id, source.source_id)
            conversation = session.get(Conversation, conversation_id)
            if not conversation:
                conversation = Conversation(id=conversation_id, account_id=batch.account.id, source_id=source.source_id, display_name=source.display_name)
                session.add(conversation)
            conversation.display_name = source.display_name
            conversation.conversation_type = source.conversation_type
            conversation.latest_message_at = source.latest_message_at
            conversation_map[source.source_id] = conversation

        session.flush()
        inserted = 0
        duplicates = 0
        for source in batch.messages:
            message_id = stable_id("message", batch.account.id, source.source_shard_id, source.source_message_id)
            if session.get(Message, message_id):
                duplicates += 1
                continue
            conversation = conversation_map.get(source.conversation_source_id)
            if not conversation:
                conversation_id = stable_id("conversation", batch.account.id, source.conversation_source_id)
                conversation = Conversation(id=conversation_id, account_id=batch.account.id, source_id=source.conversation_source_id, display_name=source.conversation_display_name, conversation_type=source.conversation_type, latest_message_at=source.sent_at)
                session.add(conversation)
                conversation_map[source.conversation_source_id] = conversation
                session.flush()
            message = Message(
                id=message_id,
                account_id=batch.account.id,
                source_shard_id=source.source_shard_id,
                source_message_id=source.source_message_id,
                conversation_id=conversation.id,
                sender_id=source.sender_id,
                sender_display_name=source.sender_display_name,
                sent_at=source.sent_at,
                direction=source.direction,
                message_type=source.message_type,
                text_content=source.text_content,
                structured_content=json.dumps(source.structured_content, ensure_ascii=False) if source.structured_content else None,
                attachment_metadata=json.dumps(source.attachment_metadata, ensure_ascii=False) if source.attachment_metadata else None,
                source_freshness=batch.freshness_status,
            )
            session.add(message)
            session.flush()
            session.execute(text("INSERT INTO messages_fts(message_id, account_id, conversation_id, text_content) VALUES (:id, :account, :conversation, :content)"), {"id": message.id, "account": message.account_id, "conversation": message.conversation_id, "content": message.text_content})
            inserted += 1

        for shard_id, watermark in batch.watermark_by_shard.items():
            shard_key = stable_id("shard", batch.account.id, shard_id)
            shard = session.get(SyncShard, shard_key)
            if not shard:
                shard = SyncShard(id=shard_key, account_id=batch.account.id, source_shard_id=shard_id)
                session.add(shard)
            shard.watermark = watermark
            shard.latest_source_at = batch.latest_by_shard.get(shard_id)
            shard.freshness_status = batch.freshness_status
        session.commit()
        return inserted, duplicates
