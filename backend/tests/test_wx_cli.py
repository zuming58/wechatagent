import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.connectors.base import SourceAccount, SourceProbe
from app.connectors.wx_cli import WxCliConnector


def install_synthetic_environment(monkeypatch, directories, responses, executable="C:/synthetic/wx.exe"):
    calls = []
    monkeypatch.setattr("app.connectors.wx_cli.platform.system", lambda: "Windows")
    monkeypatch.setattr(WxCliConnector, "_account_directories", staticmethod(lambda: directories))
    monkeypatch.setattr(WxCliConnector, "_wechat_version", staticmethod(lambda: None))
    monkeypatch.setattr("app.connectors.wx_cli.shutil.which", lambda _command: executable)

    def fake_run(args, **_kwargs):
        calls.append(tuple(args))
        command = tuple(args[1:-1])
        payload = responses[command]
        if isinstance(payload, tuple):
            return SimpleNamespace(returncode=payload[0], stdout=payload[1], stderr=payload[2])
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr("app.connectors.wx_cli.subprocess.run", fake_run)
    return calls


def test_probe_returns_unsupported_platform_without_discovery(monkeypatch):
    monkeypatch.setattr("app.connectors.wx_cli.platform.system", lambda: "Linux")
    monkeypatch.setattr(WxCliConnector, "_account_directories", staticmethod(lambda: (_ for _ in ()).throw(AssertionError("must not inspect directories"))))

    probe = WxCliConnector().probe()

    assert probe.status == "unsupported_platform"
    assert probe.reason == "Windows only"


def test_probe_missing_connector_keeps_anonymous_stable_account_ids(monkeypatch, tmp_path):
    directory = tmp_path / "synthetic-account"
    monkeypatch.setattr("app.connectors.wx_cli.platform.system", lambda: "Windows")
    monkeypatch.setattr(WxCliConnector, "_account_directories", staticmethod(lambda: [directory]))
    monkeypatch.setattr(WxCliConnector, "_wechat_version", staticmethod(lambda: None))
    monkeypatch.setattr("app.connectors.wx_cli.shutil.which", lambda _command: None)

    connector = WxCliConnector()
    first = connector.probe()
    second = connector.probe()

    assert first.status == "connector_missing"
    assert first.accounts[0].id == second.accounts[0].id
    assert first.accounts[0].id == connector._stable_id(str(directory.resolve()).lower())
    assert str(directory) not in " ".join((first.accounts[0].id, first.accounts[0].source_key, first.accounts[0].display_name))


def test_probe_selects_only_a_single_detected_account(monkeypatch, tmp_path):
    directory = tmp_path / "synthetic-account"
    calls = install_synthetic_environment(monkeypatch, [directory], {("daemon", "status"): {"version": "synthetic-1"}})

    probe = WxCliConnector().probe()

    assert probe.status == "ready"
    assert probe.connector_version == "synthetic-1"
    assert [account.selected for account in probe.accounts] == [True]
    assert calls == [("C:/synthetic/wx.exe", "daemon", "status", "--json")]


def test_probe_requires_explicit_selection_for_multiple_accounts(monkeypatch, tmp_path):
    directories = [tmp_path / "synthetic-account-a", tmp_path / "synthetic-account-b"]
    install_synthetic_environment(monkeypatch, directories, {("daemon", "status"): {"version": "synthetic-1"}})

    probe = WxCliConnector().probe()

    assert probe.status == "account_selection_required"
    assert [account.selected for account in probe.accounts] == [False, False]


def test_collect_transforms_synthetic_json_and_passes_since(monkeypatch, tmp_path):
    directory = tmp_path / "synthetic-account"
    responses = {
        ("daemon", "status"): {"version": "synthetic-1"},
        ("contacts",): {"contacts": [{"username": "contact-1", "remark": "Synthetic Contact", "avatar_version": "v1"}]},
        ("sessions",): {"sessions": [{"username": "contact-1", "display": "Synthetic Direct", "chat_type": "private", "timestamp": "2026-07-20T09:00:00Z"}]},
        ("history", "Synthetic Direct", "--since", "2026-07-20"): {
            "meta": {"status": "ok"},
            "messages": [{"source_db": "synthetic-shard", "local_id": "message-1", "sender_username": "contact-1", "sender_contact_display": "Synthetic Contact", "timestamp": "2026-07-20T10:00:00Z", "type": "text", "content": "synthetic message"}],
        },
    }
    calls = install_synthetic_environment(monkeypatch, [directory], responses)
    connector = WxCliConnector()
    account_id = connector.probe().accounts[0].id

    batch = connector.collect(account_id, datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc))

    assert batch.contacts[0].source_id == "contact-1"
    assert batch.conversations[0].source_id == "contact-1"
    assert batch.conversations[0].conversation_type == "private"
    assert batch.messages[0].source_message_id == "message-1"
    assert batch.messages[0].sent_at == datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)
    assert batch.watermark_by_shard == {"synthetic-shard": "2026-07-20T10:00:00+00:00"}
    assert ("C:/synthetic/wx.exe", "history", "Synthetic Direct", "--since", "2026-07-20", "--json") in calls


def test_collect_limits_sessions_with_synthetic_payloads(monkeypatch, tmp_path):
    directory = tmp_path / "synthetic-account"
    responses = {
        ("daemon", "status"): {"version": "synthetic-1"},
        ("contacts",): [],
        ("sessions",): {"sessions": [{"username": "first", "display": "First", "chat_type": "private"}, {"username": "second", "display": "Second", "chat_type": "private"}]},
        ("history", "First"): {"messages": []},
    }
    calls = install_synthetic_environment(monkeypatch, [directory], responses)
    connector = WxCliConnector()
    account_id = connector.probe().accounts[0].id

    batch = connector.collect(account_id, None, limit_sessions=1)

    assert [conversation.source_id for conversation in batch.conversations] == ["first"]
    assert ("C:/synthetic/wx.exe", "history", "First", "--json") in calls
    assert not any("Second" in command for command in calls)


def test_collect_rejects_invalid_or_unselected_accounts_without_commands(monkeypatch):
    connector = WxCliConnector()
    calls = []
    account = SourceAccount("synthetic-account", "synthetic:account", "Synthetic account", selected=False)
    monkeypatch.setattr(connector, "_run_json", lambda *args, **kwargs: calls.append(args))

    monkeypatch.setattr(connector, "probe", lambda: SourceProbe(status="ready", accounts=[account]))
    with pytest.raises(ValueError, match="account_not_found"):
        connector.collect("unknown-account", None)

    monkeypatch.setattr(connector, "probe", lambda: SourceProbe(status="account_selection_required", accounts=[account]))
    with pytest.raises(RuntimeError, match="account_selection_required"):
        connector.collect(account.id, None)

    assert calls == []


def test_collect_stops_after_synthetic_command_and_permission_failures(monkeypatch):
    connector = WxCliConnector()
    account = SourceAccount("synthetic-account", "synthetic:account", "Synthetic account", selected=True)
    calls = []
    monkeypatch.setattr(connector, "probe", lambda: SourceProbe(status="ready", accounts=[account]))

    def command_failure(*args, **_kwargs):
        calls.append(args)
        raise RuntimeError("wx_cli_failed:2")

    monkeypatch.setattr(connector, "_run_json", command_failure)
    with pytest.raises(RuntimeError, match="wx_cli_failed:2"):
        connector.collect(account.id, None)
    assert calls == [("contacts",)]

    monkeypatch.setattr(connector, "_run_json", lambda *args, **_kwargs: (_ for _ in ()).throw(PermissionError("permission_denied")))
    with pytest.raises(PermissionError, match="permission_denied"):
        connector.collect(account.id, None)


@pytest.mark.parametrize(
    ("daemon_result", "expected_status"),
    [
        ((0, "not-json", ""), "connector_protocol_error"),
        ((1, "", "access denied"), "permission_denied"),
        ((2, "", "command failed"), "connector_command_failed"),
    ],
)
def test_probe_exposes_synthetic_daemon_failures(monkeypatch, tmp_path, daemon_result, expected_status):
    install_synthetic_environment(monkeypatch, [tmp_path / "synthetic-account"], {("daemon", "status"): daemon_result})

    probe = WxCliConnector().probe()

    assert probe.status == expected_status


def test_collect_handles_empty_unknown_stale_and_invalid_timestamp_payloads(monkeypatch, tmp_path):
    directory = tmp_path / "synthetic-account"
    responses = {
        ("daemon", "status"): {"version": "synthetic-1"},
        ("contacts",): {"results": []},
        ("sessions",): {"results": [{"id": "group-1", "display": "Synthetic Group", "chat_type": "group", "time": "2026-07-20T09:00:00Z"}]},
        ("history", "Synthetic Group"): {
            "meta": {"status": "unknown_shards", "unknown_shards": ["missing-a"]},
            "history": [],
        },
    }
    install_synthetic_environment(monkeypatch, [directory], responses)
    connector = WxCliConnector()
    account_id = connector.probe().accounts[0].id

    unknown_batch = connector.collect(account_id, None)
    assert unknown_batch.contacts == []
    assert unknown_batch.messages == []
    assert unknown_batch.freshness_status == "unknown_shards"
    assert unknown_batch.unknown_shards == ["missing-a"]

    responses[("history", "Synthetic Group")] = {
        "meta": {"status": "possibly_stale"},
        "history": [{"id": "bad-time", "time": "not-a-timestamp", "content": "ignored"}],
    }
    invalid_batch = connector.collect(account_id, None)
    assert invalid_batch.messages == []
    assert invalid_batch.watermark_by_shard == {}
    assert invalid_batch.freshness_status == "invalid_timestamps"

    responses[("history", "Synthetic Group")] = {"meta": {"status": "possibly_stale"}, "history": []}
    stale_batch = connector.collect(account_id, None)
    assert stale_batch.freshness_status == "possibly_stale"
