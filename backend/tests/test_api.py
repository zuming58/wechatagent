from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.config import Settings
from app.connectors.base import Connector, ConnectorBatch, SourceAccount, SourceProbe, StandardContact, StandardConversation, StandardMessage
from app.connectors.synthetic import SyntheticConnector
from app.main import create_app
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
