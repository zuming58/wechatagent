from datetime import datetime, timedelta, timezone

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select, text

from app.config import Settings
from app.connectors.base import Connector, ConnectorBatch, SourceAccount, SourceProbe, StandardContact, StandardConversation, StandardMessage
from app.connectors.synthetic import SyntheticConnector
from app.main import create_app
from app.models import AccountDeletionRequest, ActionItem, Contact, Fact, KnowledgeCard, Message, SyncShard, Tag, TagLink


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


class NeverProbeConnector(Connector):
    def __init__(self):
        self.probe_calls = 0
        self.collect_calls = 0

    def probe(self):
        self.probe_calls += 1
        raise AssertionError("The real-connector scheduler must not probe")

    def collect(self, account_id, since, limit_sessions=None):
        self.collect_calls += 1
        raise AssertionError("The real-connector scheduler must not collect")


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


def test_sync_warning_preserves_counts_and_freshness_code(client):
    sent_at = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    batch = ConnectorBatch(
        account=FixedBatchConnector.account,
        contacts=[StandardContact("warning-contact")],
        conversations=[StandardConversation("warning-contact", "Warning", "private", sent_at)],
        messages=[StandardMessage("warning-shard", "warning-message", "warning-contact", "Warning", "private", "warning-contact", "Warning", sent_at, "incoming", "text", "synthetic warning message")],
        watermark_by_shard={"warning-shard": sent_at.isoformat()},
        latest_by_shard={"warning-shard": sent_at},
        freshness_status="unknown_shards",
        unknown_shards=["synthetic-missing-shard"],
    )
    client.app.state.connector = FixedBatchConnector(batch)

    response = client.post("/api/v1/sync", json={"account_id": "fixed-account", "mode": "initial"})

    assert response.status_code == 200
    assert response.json()["status"] == "completed_with_warning"
    assert response.json()["inserted_count"] == 1
    assert response.json()["duplicate_count"] == 0
    assert response.json()["error_code"] == "unknown_shards"


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

    short_keyword = client.get("/api/v1/messages/search", params={"account_id": "dev-account", "q": "方案"})
    assert short_keyword.status_code == 200
    assert [item["text_content"] for item in short_keyword.json()] == [
        "下周二上午把方案细节再过一遍。",
        "收到，我整理方案和并发测试数据。",
    ]

    message_id = search.json()[0]["id"]
    context = client.get(f"/api/v1/messages/{message_id}/context", params={"account_id": "dev-account", "radius": 2})
    assert context.status_code == 200
    assert context.json()["anchor_id"] == message_id
    assert len(context.json()["messages"]) >= 2


def test_browser_cors_allows_local_write_methods(client):
    headers = {
        "Origin": "http://127.0.0.1:5181",
        "Access-Control-Request-Method": "PATCH",
        "Access-Control-Request-Headers": "content-type",
    }

    patch_preflight = client.options("/api/v1/settings/privacy", headers=headers)
    assert patch_preflight.status_code == 200
    assert "PATCH" in patch_preflight.headers["access-control-allow-methods"]

    delete_preflight = client.options(
        "/api/v1/facts/example",
        headers={**headers, "Access-Control-Request-Method": "DELETE"},
    )
    assert delete_preflight.status_code == 200
    assert "DELETE" in delete_preflight.headers["access-control-allow-methods"]


def test_single_resource_reads_require_the_matching_account(client):
    sync = client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"}).json()
    contact = client.get("/api/v1/contacts", params={"account_id": "dev-account"}).json()[0]
    message = client.get(
        f"/api/v1/contacts/{contact['id']}/messages",
        params={"account_id": "dev-account"},
    ).json()[0]

    assert client.get(f"/api/v1/sync/runs/{sync['id']}", params={"account_id": "dev-account"}).status_code == 200
    assert client.get(f"/api/v1/contacts/{contact['id']}", params={"account_id": "dev-account"}).status_code == 200
    assert client.get(f"/api/v1/messages/{message['id']}/context", params={"account_id": "dev-account"}).status_code == 200

    assert client.get(f"/api/v1/sync/runs/{sync['id']}", params={"account_id": "another-account"}).status_code == 404
    assert client.get(f"/api/v1/contacts/{contact['id']}", params={"account_id": "another-account"}).status_code == 404
    assert client.get(f"/api/v1/messages/{message['id']}/context", params={"account_id": "another-account"}).status_code == 404


def test_contact_search_and_account_isolation(client):
    client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
    contacts = client.get("/api/v1/contacts", params={"account_id": "dev-account", "query": "张"})
    assert contacts.status_code == 200
    assert [item["display_name"] for item in contacts.json()] == ["张工"]

    other = client.get("/api/v1/contacts", params={"account_id": "another-account"})
    assert other.status_code == 200
    assert other.json() == []


def test_contact_evidence_includes_private_and_known_group_messages(client):
    client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
    contacts = client.get("/api/v1/contacts", params={"account_id": "dev-account"}).json()
    zhang = next(item for item in contacts if item["source_id"] == "wxid_zhang")
    wang = next(item for item in contacts if item["source_id"] == "wxid_wang")

    evidence = client.get(f"/api/v1/contacts/{zhang['id']}/messages", params={"account_id": "dev-account"})

    assert evidence.status_code == 200
    assert [item["text_content"] for item in evidence.json()] == [
        "下周二上午把方案细节再过一遍。",
        "先从售后群试点一个月，重点看检索效果。",
        "收到，我整理方案和并发测试数据。",
        "需要离线部署与权限审计，客户资料不能上云。",
    ]
    assert evidence.json()[1]["conversation_type"] == "group"

    empty_evidence = client.get(f"/api/v1/contacts/{wang['id']}/messages", params={"account_id": "dev-account"})
    assert empty_evidence.status_code == 200
    assert empty_evidence.json() == []

    wrong_account = client.get(f"/api/v1/contacts/{zhang['id']}/messages", params={"account_id": "another-account"})
    assert wrong_account.status_code == 404
    assert wrong_account.json()["detail"] == "contact_not_found"

    missing_contact = client.get("/api/v1/contacts/missing/messages", params={"account_id": "dev-account"})
    assert missing_contact.status_code == 404

    limited = client.get(f"/api/v1/contacts/{zhang['id']}/messages", params={"account_id": "dev-account", "limit": 2})
    assert [item["text_content"] for item in limited.json()] == ["下周二上午把方案细节再过一遍。", "先从售后群试点一个月，重点看检索效果。"]


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


def test_contact_facts_are_manual_traceable_and_survive_sync(client):
    client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
    contacts = client.get("/api/v1/contacts", params={"account_id": "dev-account"}).json()
    zhang = next(item for item in contacts if item["source_id"] == "wxid_zhang")
    chen = next(item for item in contacts if item["source_id"] == "wxid_chen")
    zhang_messages = client.get(f"/api/v1/contacts/{zhang['id']}/messages", params={"account_id": "dev-account"}).json()
    chen_messages = client.get(f"/api/v1/contacts/{chen['id']}/messages", params={"account_id": "dev-account"}).json()

    manual = client.post(
        f"/api/v1/contacts/{zhang['id']}/facts",
        params={"account_id": "dev-account"},
        json={"kind": "company", "content": "Synthetic company record", "message_ids": []},
    )
    assert manual.status_code == 201
    assert manual.json()["evidence"] == []

    evidenced = client.post(
        f"/api/v1/contacts/{zhang['id']}/facts",
        params={"account_id": "dev-account"},
        json={"kind": "need", "content": "Synthetic offline deployment need", "message_ids": [zhang_messages[0]["id"]]},
    )
    assert evidenced.status_code == 201
    assert [item["id"] for item in evidenced.json()["evidence"]] == [zhang_messages[0]["id"]]

    listed = client.get(f"/api/v1/contacts/{zhang['id']}/facts", params={"account_id": "dev-account"})
    assert listed.status_code == 200
    assert {item["id"] for item in listed.json()} == {manual.json()["id"], evidenced.json()["id"]}

    updated = client.patch(
        f"/api/v1/facts/{manual.json()['id']}",
        params={"account_id": "dev-account"},
        json={"kind": "commitment", "content": "Updated synthetic commitment", "message_ids": [zhang_messages[1]["id"]]},
    )
    assert updated.status_code == 200
    assert updated.json()["kind"] == "commitment"
    assert [item["id"] for item in updated.json()["evidence"]] == [zhang_messages[1]["id"]]
    updated_listing = client.get(f"/api/v1/contacts/{zhang['id']}/facts", params={"account_id": "dev-account"}).json()
    assert updated_listing[0]["id"] == manual.json()["id"]

    invalid_create = client.post(
        f"/api/v1/contacts/{zhang['id']}/facts",
        params={"account_id": "dev-account"},
        json={"kind": "role", "content": "Must not persist", "message_ids": [chen_messages[0]["id"]]},
    )
    assert invalid_create.status_code == 422
    assert invalid_create.json()["detail"] == "fact_evidence_message_not_allowed"
    assert len(client.get(f"/api/v1/contacts/{zhang['id']}/facts", params={"account_id": "dev-account"}).json()) == 2

    invalid_update = client.patch(
        f"/api/v1/facts/{manual.json()['id']}",
        params={"account_id": "dev-account"},
        json={"kind": "role", "content": "Must not alter", "message_ids": [chen_messages[0]["id"]]},
    )
    assert invalid_update.status_code == 422
    unchanged = client.get(f"/api/v1/contacts/{zhang['id']}/facts", params={"account_id": "dev-account"}).json()
    assert next(item for item in unchanged if item["id"] == manual.json()["id"])["content"] == "Updated synthetic commitment"

    assert client.get(f"/api/v1/contacts/{zhang['id']}/facts", params={"account_id": "another-account"}).status_code == 404
    assert client.post(
        f"/api/v1/contacts/{zhang['id']}/facts",
        params={"account_id": "another-account"},
        json={"kind": "role", "content": "Other account", "message_ids": []},
    ).status_code == 404

    deleted = client.delete(f"/api/v1/facts/{evidenced.json()['id']}", params={"account_id": "dev-account"})
    assert deleted.status_code == 204
    remaining = client.get(f"/api/v1/contacts/{zhang['id']}/facts", params={"account_id": "dev-account"}).json()
    assert [item["id"] for item in remaining] == [manual.json()["id"]]

    history = client.get(f"/api/v1/contacts/{zhang['id']}/fact-history", params={"account_id": "dev-account"})
    assert history.status_code == 200
    assert {item["event_type"] for item in history.json()} == {"created", "updated", "deleted"}
    assert len(history.json()) == 4
    assert history.json()[0]["event_type"] == "deleted"
    deleted_event = next(item for item in history.json() if item["event_type"] == "deleted")
    assert deleted_event["fact_id"] == evidenced.json()["id"]
    assert [item["id"] for item in deleted_event["evidence"]] == [zhang_messages[0]["id"]]
    updated_event = next(item for item in history.json() if item["event_type"] == "updated")
    assert updated_event["content"] == "Updated synthetic commitment"
    assert [item["id"] for item in updated_event["evidence"]] == [zhang_messages[1]["id"]]
    assert len(client.get(f"/api/v1/contacts/{zhang['id']}/fact-history", params={"account_id": "dev-account", "limit": 2}).json()) == 2
    assert client.get(f"/api/v1/contacts/{chen['id']}/fact-history", params={"account_id": "dev-account"}).json() == []
    assert client.get(f"/api/v1/contacts/{zhang['id']}/fact-history", params={"account_id": "another-account"}).status_code == 404

    repeated_sync = client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
    assert repeated_sync.status_code == 200
    assert client.get(f"/api/v1/contacts/{zhang['id']}/facts", params={"account_id": "dev-account"}).json()[0]["content"] == "Updated synthetic commitment"
    assert len(client.get(f"/api/v1/contacts/{zhang['id']}/fact-history", params={"account_id": "dev-account"}).json()) == 4


def test_user_contact_profile_overrides_are_traceable_and_survive_sync(client):
    client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
    contacts = client.get("/api/v1/contacts", params={"account_id": "dev-account"}).json()
    zhang = next(item for item in contacts if item["source_id"] == "wxid_zhang")
    chen = next(item for item in contacts if item["source_id"] == "wxid_chen")

    updated = client.patch(
        f"/api/v1/contacts/{zhang['id']}/profile",
        params={"account_id": "dev-account"},
        json={"remark_name": "User Remark", "confirmed_real_name": "User Name", "company": "User Company", "role": "User Role"},
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "User Remark"
    assert updated.json()["user_confirmed_real_name"] == "User Name"
    assert updated.json()["effective_company"] == "User Company"
    assert updated.json()["effective_role"] == "User Role"

    search = client.get("/api/v1/contacts", params={"account_id": "dev-account", "query": "User Company"})
    assert [item["id"] for item in search.json()] == [zhang["id"]]

    history = client.get(f"/api/v1/contacts/{zhang['id']}/profile-history", params={"account_id": "dev-account"})
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["user_role"] == "User Role"

    cleared = client.patch(
        f"/api/v1/contacts/{zhang['id']}/profile",
        params={"account_id": "dev-account"},
        json={"company": "   "},
    )
    assert cleared.status_code == 200
    assert cleared.json()["user_company"] is None
    assert cleared.json()["effective_company"] == cleared.json()["company"]
    history = client.get(f"/api/v1/contacts/{zhang['id']}/profile-history", params={"account_id": "dev-account"})
    assert len(history.json()) == 2
    assert history.json()[0]["user_company"] is None

    unchanged = client.patch(
        f"/api/v1/contacts/{zhang['id']}/profile",
        params={"account_id": "dev-account"},
        json={"remark_name": "User Remark"},
    )
    assert unchanged.status_code == 200
    assert len(client.get(f"/api/v1/contacts/{zhang['id']}/profile-history", params={"account_id": "dev-account"}).json()) == 2

    assert client.patch(
        f"/api/v1/contacts/{zhang['id']}/profile",
        params={"account_id": "another-account"},
        json={"remark_name": "Other account"},
    ).status_code == 404
    assert client.get(f"/api/v1/contacts/{zhang['id']}/profile-history", params={"account_id": "another-account"}).status_code == 404
    assert client.get(f"/api/v1/contacts/{chen['id']}/profile-history", params={"account_id": "dev-account"}).json() == []

    repeated_sync = client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
    assert repeated_sync.status_code == 200
    refreshed = client.get("/api/v1/contacts", params={"account_id": "dev-account"}).json()
    refreshed_zhang = next(item for item in refreshed if item["id"] == zhang["id"])
    assert refreshed_zhang["display_name"] == "User Remark"
    assert refreshed_zhang["user_role"] == "User Role"
    assert len(client.get(f"/api/v1/contacts/{zhang['id']}/profile-history", params={"account_id": "dev-account"}).json()) == 2


def test_synthetic_scheduler_requires_first_archive_and_records_incremental_runs(client):
    scheduler = client.app.state.sync_scheduler
    assert scheduler.enabled is True
    assert scheduler.run_cycle() == []

    first = client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
    assert first.status_code == 200
    scheduled = scheduler.run_cycle()

    assert len(scheduled) == 1
    assert scheduled[0].mode == "incremental"
    assert scheduled[0].status == "completed"
    assert scheduled[0].inserted_count == 0
    assert scheduled[0].duplicate_count == 1

    runs = client.get("/api/v1/sync/runs", params={"account_id": "dev-account"})
    assert runs.status_code == 200
    assert [item["mode"] for item in runs.json()] == ["incremental", "initial"]

    schedule = client.get("/api/v1/sync/schedule")
    assert schedule.status_code == 200
    assert schedule.json()["enabled"] is True
    assert schedule.json()["last_cycle_at"] is not None
    assert schedule.json()["next_run_at"] is not None


def test_non_synthetic_mode_never_starts_the_automatic_scheduler(tmp_path):
    connector = NeverProbeConnector()
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'scheduler-disabled.db'}", connector="wxcli", auto_sync_enabled=True)
    with TestClient(create_app(settings=settings, connector=connector)) as client:
        response = client.get("/api/v1/sync/schedule")

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert connector.probe_calls == 0
    assert connector.collect_calls == 0


def test_structured_search_filters_and_attachment_summaries_stay_local_and_sanitized(client):
    sent_at = datetime(2026, 7, 24, 9, 0, tzinfo=timezone.utc)
    account = SourceAccount(id="search-account", source_key="synthetic:search-account", display_name="Search synthetic account", selected=True)
    batch = ConnectorBatch(
        account=account,
        contacts=[StandardContact("contact-a", remark_name="Contact A"), StandardContact("contact-b", remark_name="Contact B")],
        conversations=[
            StandardConversation("contact-a", "Contact A", "private", sent_at),
            StandardConversation("group-a", "Synthetic group", "group", sent_at),
            StandardConversation("contact-b", "Contact B", "private", sent_at),
        ],
        messages=[
            StandardMessage("search-shard", "file-message", "contact-a", "Contact A", "private", "contact-a", "Contact A", sent_at, "incoming", "file", "文件已发送", attachment_metadata={"file_name": r"C:\synthetic\报价方案.pdf", "mime_type": "application/pdf", "size_bytes": 1024}),
            StandardMessage("search-shard", "group-message", "group-a", "Synthetic group", "group", "contact-a", "Contact A", sent_at - timedelta(minutes=1), "incoming", "text", "报价方案请在群内确认"),
            StandardMessage("search-shard", "other-message", "contact-b", "Contact B", "private", "contact-b", "Contact B", sent_at - timedelta(minutes=2), "incoming", "text", "报价方案由其他联系人发送"),
        ],
        watermark_by_shard={"search-shard": sent_at.isoformat()},
        latest_by_shard={"search-shard": sent_at},
    )
    search_connector = FixedBatchConnector(batch)
    search_connector.account = account
    client.app.state.connector = search_connector
    archived = client.post("/api/v1/sync", json={"account_id": account.id, "mode": "initial"})
    assert archived.status_code == 200

    contacts = client.get("/api/v1/contacts", params={"account_id": account.id}).json()
    contact_a = next(item for item in contacts if item["source_id"] == "contact-a")
    filtered = client.get("/api/v1/messages/search", params={"account_id": account.id, "q": "报价方案", "contact_id": contact_a["id"]})
    assert filtered.status_code == 200
    assert {item["id"] for item in filtered.json()} == {
        next(item["id"] for item in client.get(f"/api/v1/contacts/{contact_a['id']}/messages", params={"account_id": account.id}).json() if item["text_content"] == "文件已发送"),
        next(item["id"] for item in client.get(f"/api/v1/contacts/{contact_a['id']}/messages", params={"account_id": account.id}).json() if item["text_content"] == "报价方案请在群内确认"),
    }

    attachments_only = client.get("/api/v1/messages/search", params={"account_id": account.id, "q": "报价方案", "has_attachment": "true", "message_type": "file"})
    assert attachments_only.status_code == 200
    assert len(attachments_only.json()) == 1
    attachment = attachments_only.json()[0]["attachments"][0]
    assert attachment == {"name": "报价方案.pdf", "mime_type": "application/pdf", "size_bytes": 1024}
    assert "C:" not in str(attachments_only.json())
    assert "synthetic" not in str(attachments_only.json())

    assert client.get("/api/v1/messages/search", params={"account_id": account.id, "q": "报价方案", "contact_id": "not-a-contact"}).status_code == 404


def test_user_managed_knowledge_cards_keep_account_isolated_evidence_history(client):
    client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
    messages = client.get("/api/v1/messages/search", params={"account_id": "dev-account", "q": "离线部署"}).json()
    created = client.post("/api/v1/knowledge-cards", params={"account_id": "dev-account"}, json={"card_type": "project", "title": "Local deployment", "content": "User-written note", "message_ids": [messages[0]["id"]]})
    assert created.status_code == 201
    card = created.json()
    assert [item["id"] for item in card["evidence"]] == [messages[0]["id"]]
    updated = client.patch(f"/api/v1/knowledge-cards/{card['id']}", params={"account_id": "dev-account"}, json={"card_type": "decision", "title": "Updated local card", "content": "Still user-written", "message_ids": []})
    assert updated.status_code == 200
    assert client.patch(f"/api/v1/knowledge-cards/{card['id']}", params={"account_id": "other-account"}, json={"card_type": "note", "title": "No", "content": "No", "message_ids": []}).status_code == 404
    deleted = client.delete(f"/api/v1/knowledge-cards/{card['id']}", params={"account_id": "dev-account"})
    assert deleted.status_code == 204
    assert client.get("/api/v1/knowledge-cards", params={"account_id": "dev-account"}).json() == []
    history = client.get(f"/api/v1/knowledge-cards/{card['id']}/history", params={"account_id": "dev-account"})
    assert [item["event_type"] for item in history.json()] == ["deleted", "updated", "created"]


def test_storage_status_reports_only_requested_account_and_integrity(client):
    client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
    status = client.get("/api/v1/storage/status", params={"account_id": "dev-account"})
    assert status.status_code == 200
    assert status.json() == {"account_id": "dev-account", "contacts": 3, "conversations": 3, "messages": 5, "facts": 0, "knowledge_cards": 0, "integrity_check": "ok"}
    other = client.get("/api/v1/storage/status", params={"account_id": "other-account"})
    assert other.json()["messages"] == 0


def test_archive_coverage_reports_only_the_selected_account(client):
    client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})

    coverage = client.get("/api/v1/storage/archive-coverage", params={"account_id": "dev-account"})

    assert coverage.status_code == 200
    payload = coverage.json()
    assert payload["account_id"] == "dev-account"
    assert payload["contacts"] == 3
    assert payload["conversations"] == 3
    assert payload["messages"] == 5
    assert payload["earliest_message_at"] is not None
    assert payload["latest_message_at"] is not None
    assert payload["index_status"] == "ready"
    assert payload["indexed_message_count"] == 5
    assert payload["integrity_check"] == "ok"
    assert payload["last_sync_status"] == "completed"
    assert payload["last_sync_error_code"] is None

    assert client.get("/api/v1/storage/archive-coverage", params={"account_id": "another-account"}).status_code == 404


def test_fts_index_health_and_rebuild_preserve_raw_messages(client):
    client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
    ready = client.get("/api/v1/storage/index-status", params={"account_id": "dev-account"})
    assert ready.json() == {"account_id": "dev-account", "message_count": 5, "indexed_message_count": 5, "status": "ready"}

    with database_session(client) as session:
        message_id = session.scalar(select(Message.id).where(Message.account_id == "dev-account").order_by(Message.id))
        session.execute(text("DELETE FROM messages_fts WHERE message_id = :message_id"), {"message_id": message_id})
        session.commit()
        assert session.scalar(select(func.count(Message.id)).where(Message.account_id == "dev-account")) == 5

    needs_rebuild = client.get("/api/v1/storage/index-status", params={"account_id": "dev-account"})
    assert needs_rebuild.json()["status"] == "needs_rebuild"
    assert needs_rebuild.json()["indexed_message_count"] == 4
    rebuilt = client.post("/api/v1/storage/rebuild-index", params={"account_id": "dev-account"})
    assert rebuilt.status_code == 200
    assert rebuilt.json() == {"account_id": "dev-account", "message_count": 5, "indexed_message_count": 5, "status": "ready"}
    assert client.get("/api/v1/messages/search", params={"account_id": "dev-account", "q": "离线部署"}).status_code == 200
    with database_session(client) as session:
        assert session.scalar(select(func.count(Message.id)).where(Message.account_id == "dev-account")) == 5


def test_local_privacy_acknowledgement_is_persisted_without_authorizing_real_collection(client):
    initial = client.get("/api/v1/settings/privacy")
    assert initial.status_code == 200
    assert initial.json() == {
        "local_processing_acknowledged": False,
        "real_collection_authorized": False,
        "ai_processing_enabled": False,
        "updated_at": None,
    }

    saved = client.patch("/api/v1/settings/privacy", json={"local_processing_acknowledged": True})
    assert saved.status_code == 200
    assert saved.json()["local_processing_acknowledged"] is True
    assert saved.json()["real_collection_authorized"] is False
    assert saved.json()["ai_processing_enabled"] is False
    assert saved.json()["updated_at"]
    assert client.get("/api/v1/settings/privacy").json()["local_processing_acknowledged"] is True


def test_backup_manifest_and_two_step_account_deletion_are_local_and_explicit(client):
    client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
    contact = client.get("/api/v1/contacts", params={"account_id": "dev-account"}).json()[0]
    message = client.get("/api/v1/messages/search", params={"account_id": "dev-account", "q": "离线部署"}).json()[0]
    client.post(f"/api/v1/contacts/{contact['id']}/facts", params={"account_id": "dev-account"}, json={"kind": "need", "content": "Local fact", "message_ids": [message["id"]]})
    client.post("/api/v1/knowledge-cards", params={"account_id": "dev-account"}, json={"card_type": "note", "title": "Local card", "content": "User-written", "message_ids": []})
    client.post("/api/v1/action-items", params={"account_id": "dev-account"}, json={"content": "Local action", "status": "open", "message_ids": []})
    client.post("/api/v1/tags", params={"account_id": "dev-account"}, json={"name": "Local tag", "color": "#1677ff"})
    manifest = client.get("/api/v1/storage/backup-manifest", params={"account_id": "dev-account"})
    assert manifest.status_code == 200
    assert manifest.json()["integrity_check"] == "ok"
    assert manifest.json()["counts"]["messages"] == 5
    assert {key: manifest.json()["counts"][key] for key in ("facts", "knowledge_cards", "action_items", "tags")} == {"facts": 1, "knowledge_cards": 1, "action_items": 1, "tags": 1}
    assert "text_content" not in str(manifest.json())

    request = client.post("/api/v1/accounts/dev-account/deletion-requests")
    assert request.status_code == 201
    deletion = request.json()
    assert deletion["confirmation_phrase"] == "DELETE dev-account"
    mismatch = client.delete("/api/v1/accounts/dev-account/data", params={"request_id": deletion["id"], "confirmation": "DELETE anything-else"})
    assert mismatch.status_code == 422
    assert mismatch.json()["detail"] == "deletion_confirmation_mismatch"
    wrong_account = client.delete("/api/v1/accounts/another-account/data", params={"request_id": deletion["id"], "confirmation": deletion["confirmation_phrase"]})
    assert wrong_account.status_code == 404
    with database_session(client) as session:
        session.get(AccountDeletionRequest, deletion["id"]).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    expired = client.delete("/api/v1/accounts/dev-account/data", params={"request_id": deletion["id"], "confirmation": deletion["confirmation_phrase"]})
    assert expired.status_code == 409
    assert expired.json()["detail"] == "deletion_request_expired"

    fresh = client.post("/api/v1/accounts/dev-account/deletion-requests").json()
    deleted = client.delete("/api/v1/accounts/dev-account/data", params={"request_id": fresh["id"], "confirmation": fresh["confirmation_phrase"]})
    assert deleted.status_code == 204
    assert client.get("/api/v1/storage/status", params={"account_id": "dev-account"}).json()["messages"] == 0
    assert client.get("/api/v1/sync/runs", params={"account_id": "dev-account"}).json() == []
    with database_session(client) as session:
        for model in (Fact, KnowledgeCard, ActionItem, Tag):
            assert session.scalar(select(func.count(model.id)).where(model.account_id == "dev-account")) == 0


def test_user_action_items_are_account_isolated_and_manually_completed(client):
    client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
    message = client.get("/api/v1/messages/search", params={"account_id": "dev-account", "q": "离线部署"}).json()[0]
    created = client.post("/api/v1/action-items", params={"account_id": "dev-account"}, json={"content": "Follow up manually", "status": "open", "message_ids": [message["id"]]})
    assert created.status_code == 201
    item = created.json()
    assert [evidence["id"] for evidence in item["evidence"]] == [message["id"]]
    assert client.get("/api/v1/action-items", params={"account_id": "dev-account", "status": "open"}).json()[0]["id"] == item["id"]
    completed = client.patch(f"/api/v1/action-items/{item['id']}", params={"account_id": "dev-account"}, json={"content": "Follow up manually", "status": "done", "message_ids": [message["id"]]})
    assert completed.status_code == 200
    assert completed.json()["status"] == "done"
    assert client.patch(f"/api/v1/action-items/{item['id']}", params={"account_id": "other-account"}, json={"content": "No", "status": "done", "message_ids": []}).status_code == 404
    invalid = client.post("/api/v1/action-items", params={"account_id": "dev-account"}, json={"content": "Must not persist", "status": "open", "message_ids": ["other-account-message"]})
    assert invalid.status_code == 422
    assert invalid.json()["detail"] == "action_item_evidence_message_not_found"
    assert client.delete(f"/api/v1/action-items/{item['id']}", params={"account_id": "dev-account"}).status_code == 204
    assert client.get("/api/v1/action-items", params={"account_id": "dev-account"}).json() == []
    history = client.get(f"/api/v1/action-items/{item['id']}/history", params={"account_id": "dev-account"})
    assert [event["event_type"] for event in history.json()] == ["deleted", "updated", "created"]
    assert all([event["evidence"][0]["id"] for event in history.json()])
    assert client.get(f"/api/v1/action-items/{item['id']}/history", params={"account_id": "other-account"}).status_code == 404


def test_user_tags_are_account_isolated_and_link_only_existing_local_targets(client):
    client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
    contact = client.get("/api/v1/contacts", params={"account_id": "dev-account"}).json()[0]
    message = client.get("/api/v1/messages/search", params={"account_id": "dev-account", "q": "离线部署"}).json()[0]
    fact = client.post(f"/api/v1/contacts/{contact['id']}/facts", params={"account_id": "dev-account"}, json={"kind": "need", "content": "Local requirement", "message_ids": [message["id"]]}).json()
    card = client.post("/api/v1/knowledge-cards", params={"account_id": "dev-account"}, json={"card_type": "note", "title": "Local note", "content": "User-written", "message_ids": []}).json()
    action = client.post("/api/v1/action-items", params={"account_id": "dev-account"}, json={"content": "Follow up", "status": "open", "message_ids": []}).json()

    created = client.post("/api/v1/tags", params={"account_id": "dev-account"}, json={"name": "Priority", "color": "#1677FF"})
    assert created.status_code == 201
    tag = created.json()
    assert tag["color"] == "#1677ff"
    assert client.post("/api/v1/tags", params={"account_id": "dev-account"}, json={"name": "Priority", "color": "#1677ff"}).status_code == 409
    updated = client.patch(f"/api/v1/tags/{tag['id']}", params={"account_id": "dev-account"}, json={"name": "Customer", "color": "#12A150"})
    assert updated.status_code == 200
    assert client.get("/api/v1/tags", params={"account_id": "dev-account"}).json()[0]["name"] == "Customer"

    targets = [("contact", contact["id"]), ("fact", fact["id"]), ("knowledge_card", card["id"]), ("action_item", action["id"])]
    for target_type, target_id in targets:
        response = client.post("/api/v1/tags/links", params={"account_id": "dev-account"}, json={"tag_id": tag["id"], "target_type": target_type, "target_id": target_id})
        assert response.status_code == 201
        assert response.json()["tag"]["id"] == tag["id"]

    links = client.get("/api/v1/tags/links", params={"account_id": "dev-account", "target_type": "fact", "target_id": fact["id"]})
    assert links.status_code == 200
    assert [item["tag"]["name"] for item in links.json()] == ["Customer"]
    assert client.post("/api/v1/tags/links", params={"account_id": "dev-account"}, json={"tag_id": tag["id"], "target_type": "fact", "target_id": fact["id"]}).status_code == 409
    assert client.post("/api/v1/tags/links", params={"account_id": "dev-account"}, json={"tag_id": tag["id"], "target_type": "fact", "target_id": "other-account-fact"}).status_code == 422
    assert client.post("/api/v1/tags/links", params={"account_id": "another-account"}, json={"tag_id": tag["id"], "target_type": "contact", "target_id": contact["id"]}).status_code == 404

    assert client.delete(f"/api/v1/tags/{tag['id']}/links", params={"account_id": "dev-account", "target_type": "contact", "target_id": contact["id"]}).status_code == 204
    assert client.delete(f"/api/v1/action-items/{action['id']}", params={"account_id": "dev-account"}).status_code == 204
    with database_session(client) as session:
        assert session.scalar(select(func.count(TagLink.id)).where(TagLink.target_type == "action_item", TagLink.target_id == action["id"])) == 0
    assert client.delete(f"/api/v1/tags/{tag['id']}", params={"account_id": "dev-account"}).status_code == 204
    assert client.get("/api/v1/tags", params={"account_id": "dev-account"}).json() == []


def test_timeline_merges_archived_messages_and_user_history_with_account_isolation(client):
    client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
    contacts = client.get("/api/v1/contacts", params={"account_id": "dev-account"}).json()
    zhang = next(item for item in contacts if item["source_id"] == "wxid_zhang")
    message = client.get("/api/v1/messages/search", params={"account_id": "dev-account", "q": "离线部署"}).json()[0]

    fact = client.post(f"/api/v1/contacts/{zhang['id']}/facts", params={"account_id": "dev-account"}, json={"kind": "need", "content": "User-confirmed local requirement", "message_ids": [message["id"]]})
    assert fact.status_code == 201
    profile = client.patch(f"/api/v1/contacts/{zhang['id']}/profile", params={"account_id": "dev-account"}, json={"remark_name": "User Remark", "confirmed_real_name": None, "company": None, "role": None})
    assert profile.status_code == 200
    action = client.post("/api/v1/action-items", params={"account_id": "dev-account"}, json={"content": "Follow up manually", "status": "open", "message_ids": [message["id"]]})
    assert action.status_code == 201

    timeline = client.get("/api/v1/timeline", params=[("account_id", "dev-account"), ("kind", "message"), ("kind", "fact"), ("kind", "profile"), ("kind", "action_item")])
    assert timeline.status_code == 200
    events = timeline.json()
    assert {"message", "fact", "profile", "action_item"}.issubset({event["kind"] for event in events})
    assert [event["occurred_at"] for event in events] == sorted((event["occurred_at"] for event in events), reverse=True)
    fact_event = next(event for event in events if event["kind"] == "fact")
    assert fact_event["contact_id"] == zhang["id"]
    assert fact_event["evidence"][0]["id"] == message["id"]

    contact_timeline = client.get("/api/v1/timeline", params={"account_id": "dev-account", "contact_id": zhang["id"], "limit": 2})
    assert contact_timeline.status_code == 200
    assert len(contact_timeline.json()) == 2
    assert {event["kind"] for event in contact_timeline.json()}.issubset({"message", "fact", "profile"})
    assert all(event["contact_id"] == zhang["id"] for event in contact_timeline.json())

    assert client.get("/api/v1/timeline", params={"account_id": "another-account"}).json() == []
    assert client.get("/api/v1/timeline", params={"account_id": "dev-account", "kind": "not-supported"}).status_code == 422


def test_alembic_upgrades_a_temporary_database_to_current_head(tmp_path):
    database_path = tmp_path / "migrations.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        assert {"accounts", "facts", "knowledge_cards", "action_items", "tags", "account_deletion_requests", "local_privacy_settings"}.issubset(set(inspect(engine).get_table_names()))
    finally:
        engine.dispose()


def test_database_initialization_repairs_legacy_contact_profile_columns(tmp_path):
    database_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE contacts (
                    id VARCHAR(96) PRIMARY KEY,
                    account_id VARCHAR(64) NOT NULL,
                    source_id VARCHAR(255) NOT NULL,
                    remark_name VARCHAR(255),
                    nickname VARCHAR(255),
                    confirmed_real_name VARCHAR(255),
                    company VARCHAR(255),
                    role VARCHAR(255),
                    avatar_ref TEXT,
                    avatar_version VARCHAR(128),
                    avatar_updated_at DATETIME,
                    last_message_at DATETIME
                )
            """))
        from app.database import initialize_database

        initialize_database(engine)

        columns = {column["name"] for column in inspect(engine).get_columns("contacts")}
        assert {"user_remark_name", "user_confirmed_real_name", "user_company", "user_role"}.issubset(columns)
        assert engine.connect().execute(text("SELECT version_num FROM alembic_version")).scalar() == "0010_local_privacy_settings"
    finally:
        engine.dispose()
