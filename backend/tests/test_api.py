from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text

from app.connectors.base import Connector, ConnectorBatch, SourceAccount, SourceProbe, StandardContact, StandardConversation, StandardMessage
from app.connectors.synthetic import SyntheticConnector
from app.models import Contact, Message, SyncShard


class RecordingSyntheticConnector(SyntheticConnector):
    def __init__(self):
        self.since_values = []

    def collect(self, account_id, since, limit_sessions=None):
        self.since_values.append(since)
        return super().collect(account_id, since, limit_sessions)


class NotReadyConnector(Connector):
    def __init__(self, status="connector_missing"):
        self.status = status
        self.collect_calls = 0

    def probe(self):
        return SourceProbe(status=self.status, reason="Synthetic test connector is unavailable")

    def collect(self, account_id, since, limit_sessions=None):
        self.collect_calls += 1
        raise AssertionError("collect must not run when the connector is not ready")


class FixedBatchConnector(Connector):
    account = SourceAccount(id="fixed-account", source_key="synthetic:fixed-account", display_name="Fixed synthetic account", selected=True)

    def __init__(self, batch):
        self.batch = batch
        self.collect_calls = 0

    def probe(self):
        return SourceProbe(status="ready", accounts=[self.account])

    def collect(self, account_id, since, limit_sessions=None):
        self.collect_calls += 1
        assert account_id == self.account.id
        return self.batch


class AccountSelectionConnector(Connector):
    accounts = [
        SourceAccount(id="account-a", source_key="synthetic:account-a", display_name="Account A"),
        SourceAccount(id="account-b", source_key="synthetic:account-b", display_name="Account B"),
    ]

    def __init__(self):
        self.collect_calls = []

    def probe(self):
        return SourceProbe(
            status="account_selection_required",
            accounts=self.accounts,
            reason="Choose the local account to archive.",
        )

    def collect(self, account_id, since, limit_sessions=None):
        self.collect_calls.append(account_id)
        account = next(account for account in self.accounts if account.id == account_id)
        return ConnectorBatch(
            account=account,
            contacts=[],
            conversations=[],
            messages=[],
            watermark_by_shard={},
            latest_by_shard={},
        )


def database_session(client):
    return client.app.state.testing_session_factory()


def test_source_status_and_initial_sync(client):
    status = client.get("/api/v1/source/status")
    assert status.status_code == 200
    assert status.json()["status"] == "ready"

    response = client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["inserted_count"] == 5

    contacts = client.get("/api/v1/contacts", params={"account_id": "dev-account"})
    assert [item["source_id"] for item in contacts.json()] == ["wxid_zhang", "wxid_chen", "wxid_wang"]
    assert contacts.json()[0]["last_message_at"] is not None
    assert contacts.json()[1]["last_message_at"] is not None
    assert contacts.json()[2]["last_message_at"] is None


def test_idempotent_import_and_search_context(client):
    counts = []
    for _ in range(3):
        response = client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
        counts.append((response.json()["inserted_count"], response.json()["duplicate_count"]))
    assert counts[0] == (5, 0)
    assert counts[1] == (0, 5)
    assert counts[2] == (0, 5)

    with database_session(client) as session:
        assert session.scalar(select(func.count(Message.id))) == 5

    search = client.get("/api/v1/messages/search", params={"account_id": "dev-account", "q": "离线部署"})
    assert search.status_code == 200
    assert len(search.json()) == 1
    assert "离线部署" in search.json()[0]["text_content"]

    message_id = search.json()[0]["id"]
    context = client.get(f"/api/v1/messages/{message_id}/context", params={"radius": 2})
    assert context.status_code == 200
    assert context.json()["anchor_id"] == message_id
    assert len(context.json()["messages"]) >= 2


def test_contact_search_and_account_isolation(client):
    client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
    contacts = client.get("/api/v1/contacts", params={"account_id": "dev-account", "query": "张"})
    assert contacts.status_code == 200
    assert [item["display_name"] for item in contacts.json()] == ["张工"]

    other = client.get("/api/v1/contacts", params={"account_id": "another-account"})
    assert other.status_code == 200
    assert other.json() == []


def test_private_and_group_messages_update_only_known_contacts(client):
    base = datetime(2026, 7, 23, 10, 0, tzinfo=timezone.utc)
    account = FixedBatchConnector.account
    batch = ConnectorBatch(
        account=account,
        contacts=[StandardContact("private-contact"), StandardContact("group-contact")],
        conversations=[
            StandardConversation("private-contact", "Private", "private", base),
            StandardConversation("group", "Group", "group", base),
        ],
        messages=[
            StandardMessage("fixed-shard", "private-1", "private-contact", "Private", "private", "self", "Self", base, "outgoing", "text", "private message"),
            StandardMessage("fixed-shard", "group-1", "group", "Group", "group", "group-contact", "Known", base + timedelta(minutes=1), "incoming", "text", "known group message"),
            StandardMessage("fixed-shard", "group-2", "group", "Group", "group", "unknown-sender", "Unknown", base + timedelta(minutes=2), "incoming", "text", "unknown group message"),
        ],
        watermark_by_shard={"fixed-shard": (base + timedelta(minutes=2)).isoformat()},
        latest_by_shard={"fixed-shard": base + timedelta(minutes=2)},
    )
    client.app.state.connector = FixedBatchConnector(batch)

    response = client.post("/api/v1/sync", json={"account_id": account.id, "mode": "initial"})
    assert response.status_code == 200

    with database_session(client) as session:
        contacts = {contact.source_id: contact for contact in session.scalars(select(Contact))}
        assert set(contacts) == {"private-contact", "group-contact"}
        assert contacts["private-contact"].last_message_at.replace(tzinfo=timezone.utc) == base
        assert contacts["group-contact"].last_message_at.replace(tzinfo=timezone.utc) == base + timedelta(minutes=1)


def test_incremental_overlap_is_idempotent_and_watermark_requires_message_commit(client):
    connector = RecordingSyntheticConnector()
    client.app.state.connector = connector
    initial = client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
    assert initial.status_code == 200

    with database_session(client) as session:
        watermark = session.scalar(select(SyncShard.latest_source_at).where(SyncShard.account_id == "dev-account"))

    incremental = client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "incremental"})
    assert incremental.status_code == 200
    assert incremental.json()["inserted_count"] == 0
    assert incremental.json()["duplicate_count"] == 1
    assert connector.since_values[-1] == watermark.replace(tzinfo=timezone.utc) - timedelta(minutes=5)

    with database_session(client) as session:
        session.execute(text("DROP TABLE messages_fts"))
        session.commit()

    failed_at = datetime(2026, 7, 23, 11, 0, tzinfo=timezone.utc)
    failed_batch = ConnectorBatch(
        account=FixedBatchConnector.account,
        contacts=[StandardContact("failed-contact")],
        conversations=[StandardConversation("failed-contact", "Failed", "private", failed_at)],
        messages=[StandardMessage("failed-shard", "failed-message", "failed-contact", "Failed", "private", "failed-contact", "Failed", failed_at, "incoming", "text", "message that cannot commit")],
        watermark_by_shard={"failed-shard": failed_at.isoformat()},
        latest_by_shard={"failed-shard": failed_at},
    )
    client.app.state.connector = FixedBatchConnector(failed_batch)
    failed = client.post("/api/v1/sync", json={"account_id": "fixed-account", "mode": "initial"})
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    with database_session(client) as session:
        assert session.scalar(select(func.count(Message.id))) == 5
        assert session.scalar(select(func.count(SyncShard.id))) == 1


@pytest.mark.parametrize(
    "status",
    ["connector_missing", "permission_denied", "unsupported_version", "wechat_offline", "unexpected_status"],
)
def test_sync_rejects_unavailable_connector_without_collecting(client, status):
    connector = NotReadyConnector(status)
    client.app.state.connector = connector

    response = client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
    assert response.status_code == 409
    assert response.json()["detail"] == {
        "status": "failed",
        "error_code": status,
        "reason": "Synthetic test connector is unavailable",
    }
    assert connector.collect_calls == 0


def test_sync_requires_an_explicit_detected_account_for_account_selection(client):
    connector = AccountSelectionConnector()
    client.app.state.connector = connector

    unselected = client.post("/api/v1/sync", json={"account_id": "", "mode": "initial"})
    assert unselected.status_code == 409
    assert unselected.json()["detail"]["error_code"] == "account_not_available"
    assert connector.collect_calls == []

    unknown = client.post("/api/v1/sync", json={"account_id": "unknown-account", "mode": "initial"})
    assert unknown.status_code == 409
    assert unknown.json()["detail"]["error_code"] == "account_not_available"
    assert connector.collect_calls == []

    selected = client.post("/api/v1/sync", json={"account_id": "account-b", "mode": "initial"})
    assert selected.status_code == 200
    assert selected.json()["status"] == "completed"
    assert connector.collect_calls == ["account-b"]


def test_sync_rejects_unknown_account_even_when_source_is_ready(client):
    connector = FixedBatchConnector(
        ConnectorBatch(
            account=FixedBatchConnector.account,
            contacts=[],
            conversations=[],
            messages=[],
            watermark_by_shard={},
            latest_by_shard={},
        )
    )
    client.app.state.connector = connector

    response = client.post("/api/v1/sync", json={"account_id": "unknown-account", "mode": "initial"})
    assert response.status_code == 409
    assert response.json()["detail"]["error_code"] == "account_not_available"
    assert connector.collect_calls == 0
