from datetime import datetime, timedelta, timezone

from .base import Connector, ConnectorBatch, SourceAccount, SourceProbe, StandardContact, StandardConversation, StandardMessage


class SyntheticConnector(Connector):
    """Deterministic fixture connector for development and automated tests."""

    account = SourceAccount(id="dev-account", source_key="synthetic:dev-account", display_name="本地演示账号", selected=True)

    def probe(self) -> SourceProbe:
        return SourceProbe(status="ready", wechat_version="synthetic", connector_version="0.1", accounts=[self.account])

    def collect(self, account_id: str, since: datetime | None, limit_sessions: int | None = None) -> ConnectorBatch:
        if account_id != self.account.id:
            raise ValueError("account_not_found")

        now = datetime.now(timezone.utc).replace(microsecond=0)
        contacts = [
            StandardContact(source_id="wxid_zhang", remark_name="张工", nickname="阿诚", avatar_version="v1"),
            StandardContact(source_id="wxid_chen", remark_name="陈姐", nickname="晨曦", avatar_version="v2"),
            StandardContact(source_id="wxid_wang", remark_name="王总", nickname="山海", avatar_version=None),
        ]
        conversations = [
            StandardConversation("wxid_zhang", "张工", "private", now),
            StandardConversation("room_factory", "工厂知识库试点群", "group", now - timedelta(minutes=18)),
            StandardConversation("wxid_chen", "陈姐", "private", now - timedelta(days=1)),
        ]
        raw_messages = [
            ("m001", "wxid_zhang", "张工", "private", "wxid_zhang", "张工", now - timedelta(minutes=45), "需要离线部署与权限审计，客户资料不能上云。"),
            ("m002", "wxid_zhang", "张工", "private", "self", "我", now - timedelta(minutes=40), "收到，我整理方案和并发测试数据。"),
            ("m003", "wxid_zhang", "张工", "private", "wxid_zhang", "张工", now - timedelta(minutes=5), "下周二上午把方案细节再过一遍。"),
            ("m004", "room_factory", "工厂知识库试点群", "group", "wxid_zhang", "张工", now - timedelta(minutes=18), "先从售后群试点一个月，重点看检索效果。"),
            ("m005", "wxid_chen", "陈姐", "private", "wxid_chen", "陈姐", now - timedelta(days=1), "客户访谈纪要我晚点发你。"),
        ]
        messages = [
            StandardMessage(
                source_shard_id="synthetic-message-0",
                source_message_id=message_id,
                conversation_source_id=conversation_id,
                conversation_display_name=conversation_name,
                conversation_type=conversation_type,
                sender_id=sender_id,
                sender_display_name=sender_name,
                sent_at=sent_at,
                direction="outgoing" if sender_id == "self" else "incoming",
                message_type="text",
                text_content=text,
            )
            for message_id, conversation_id, conversation_name, conversation_type, sender_id, sender_name, sent_at, text in raw_messages
            if since is None or sent_at >= since
        ]
        latest = max((message.sent_at for message in messages), default=now)
        return ConnectorBatch(
            account=self.account,
            contacts=contacts,
            conversations=conversations[:limit_sessions] if limit_sessions else conversations,
            messages=messages,
            watermark_by_shard={"synthetic-message-0": latest.isoformat()},
            latest_by_shard={"synthetic-message-0": latest},
        )
