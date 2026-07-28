import hashlib
import json
import math
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import Connector, ConnectorBatch, SourceAccount, SourceProbe, StandardContact, StandardConversation, StandardMessage


class WxCliConnector(Connector):
    """Replaceable, read-only adapter around wx-cli JSON output."""

    def __init__(self, command: str = "wx") -> None:
        self.command = command

    @staticmethod
    def _stable_id(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _account_directories() -> list[Path]:
        home = Path.home()
        candidates = [home / "Documents" / "WeChat Files", home / "Documents" / "xwechat_files"]
        ignored = {"All Users", "Applet", "WMPF"}
        directories: list[Path] = []
        for root in candidates:
            if not root.exists():
                continue
            directories.extend(path for path in root.iterdir() if path.is_dir() and path.name not in ignored)
        return sorted(directories, key=lambda path: path.stat().st_mtime, reverse=True)

    @staticmethod
    def _registry_install_locations() -> list[Path]:
        if platform.system() != "Windows":
            return []
        try:
            import winreg
        except ImportError:
            return []
        locations: list[Path] = []
        roots = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
        paths = (r"Software\Microsoft\Windows\CurrentVersion\Uninstall", r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall")
        for root in roots:
            for path in paths:
                try:
                    parent = winreg.OpenKey(root, path)
                except OSError:
                    continue
                try:
                    index = 0
                    while True:
                        try:
                            name = winreg.EnumKey(parent, index)
                            index += 1
                        except OSError:
                            break
                        try:
                            entry = winreg.OpenKey(parent, name)
                            display_name, _ = winreg.QueryValueEx(entry, "DisplayName")
                            install_location, _ = winreg.QueryValueEx(entry, "InstallLocation")
                        except OSError:
                            continue
                        if isinstance(display_name, str) and ("WeChat" in display_name or "微信" in display_name) and isinstance(install_location, str) and install_location:
                            locations.append(Path(install_location))
                finally:
                    winreg.CloseKey(parent)
        return locations

    @classmethod
    def _wechat_executables(cls) -> list[Path]:
        standard = [
            Path("C:/Program Files/Tencent/Weixin/Weixin.exe"),
            Path("C:/Program Files (x86)/Tencent/Weixin/Weixin.exe"),
            Path("C:/Program Files/Tencent/WeChat/WeChat.exe"),
            Path("C:/Program Files (x86)/Tencent/WeChat/WeChat.exe"),
        ]
        candidates = list(standard)
        for location in cls._registry_install_locations():
            for executable in ("WeChat.exe", "Weixin.exe"):
                candidates.append(location / executable)
                try:
                    candidates.extend(location.glob(f"*/{executable}"))
                except OSError:
                    continue
        seen: set[Path] = set()
        return [path for path in candidates if path.exists() and not (path in seen or seen.add(path))]

    @staticmethod
    def _running_wechat_version() -> str | None:
        if platform.system() != "Windows":
            return None
        script = (
            "$process = Get-Process -Name Weixin -ErrorAction SilentlyContinue | "
            "Where-Object { $_.Path } | Select-Object -First 1; "
            "if (-not $process) { $process = Get-Process -Name WeChat -ErrorAction SilentlyContinue | "
            "Where-Object { $_.Path } | Select-Object -First 1 }; "
            "if ($process) { (Get-Item -LiteralPath $process.Path).VersionInfo.FileVersion }"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return result.stdout.strip() or None

    @staticmethod
    def _executable_version(executable: Path) -> str | None:
        if platform.system() != "Windows" or not executable.is_file():
            return None
        escaped = str(executable).replace("'", "''")
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"(Get-Item -LiteralPath '{escaped}').VersionInfo.FileVersion"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return result.stdout.strip() or None

    @classmethod
    def _wechat_version(cls) -> str | None:
        if platform.system() != "Windows":
            return None
        running_version = cls._running_wechat_version()
        if running_version:
            return running_version
        executable = next(iter(cls._wechat_executables()), None)
        if executable is None:
            return None
        return cls._executable_version(executable)

    def _run_json(self, *args: str, timeout: int = 120) -> dict[str, Any] | list[Any]:
        executable = shutil.which(self.command)
        if not executable:
            raise RuntimeError("connector_missing")
        result = subprocess.run(
            [executable, *args, "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.lower()
            if "permission" in stderr or "access" in stderr or "管理员" in result.stderr:
                raise PermissionError("permission_denied")
            raise RuntimeError(f"wx_cli_failed:{result.returncode}")
        return json.loads(result.stdout)

    def probe(self) -> SourceProbe:
        if platform.system() != "Windows":
            return SourceProbe(status="unsupported_platform", reason="Windows only")

        directories = self._account_directories()
        accounts = [
            SourceAccount(
                id=self._stable_id(str(path.resolve()).lower()),
                source_key=f"wechat-dir:{self._stable_id(str(path.resolve()).lower())}",
                display_name=f"本地微信账号 {index + 1}",
                selected=False,
            )
            for index, path in enumerate(directories)
        ]
        executable = shutil.which(self.command)
        if not executable:
            return SourceProbe(
                status="connector_missing",
                wechat_version=self._wechat_version(),
                accounts=accounts,
                reason="wx-cli is not installed or not on PATH",
                requires_elevation=False,
            )

        try:
            payload = self._run_json("daemon", "status", timeout=20)
        except PermissionError as error:
            return SourceProbe(status="permission_denied", accounts=accounts, reason=str(error), requires_elevation=False)
        except json.JSONDecodeError as error:
            return SourceProbe(status="connector_protocol_error", accounts=accounts, reason=str(error), requires_elevation=False)
        except RuntimeError as error:
            error_code = str(error)
            status = error_code if error_code == "connector_missing" else "connector_command_failed"
            return SourceProbe(status=status, accounts=accounts, reason=error_code, requires_elevation=False)
        connector_version = str(payload.get("version", "installed")) if isinstance(payload, dict) else "installed"

        status = "account_selection_required" if len(accounts) != 1 else "ready"
        if len(accounts) == 1:
            accounts[0].selected = True
        return SourceProbe(
            status=status,
            wechat_version=self._wechat_version(),
            connector_version=connector_version,
            accounts=accounts,
            requires_elevation=False,
        )

    @staticmethod
    def _results(payload: dict[str, Any] | list[Any], *keys: str) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _parse_time(value: Any) -> datetime | None:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            try:
                return datetime.fromtimestamp(value, tz=timezone.utc)
            except (OSError, OverflowError, ValueError):
                return None
        if isinstance(value, str):
            normalized = value.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(normalized)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                return None
        return None

    def collect(self, account_id: str, since: datetime | None, limit_sessions: int | None = None) -> ConnectorBatch:
        probe = self.probe()
        account = next((item for item in probe.accounts if item.id == account_id), None)
        if account is None:
            raise ValueError("account_not_found")
        # The API has already required the caller to explicitly choose an ID
        # from probe.accounts.  A multiple-account probe must therefore not
        # reject that explicit selection here.
        if probe.status not in {"ready", "account_selection_required"}:
            raise RuntimeError(probe.status)

        contacts_payload = self._run_json("contacts")
        sessions_payload = self._run_json("sessions")
        contacts_raw = self._results(contacts_payload, "contacts", "results")
        sessions_raw = self._results(sessions_payload, "sessions", "results")
        if limit_sessions:
            sessions_raw = sessions_raw[:limit_sessions]

        contacts = [
            StandardContact(
                source_id=str(item.get("username") or item.get("wxid") or item.get("id")),
                remark_name=item.get("remark") or item.get("remark_name"),
                nickname=item.get("nickname") or item.get("display"),
                avatar_ref=item.get("avatar") or item.get("avatar_url"),
                avatar_version=str(item.get("avatar_version")) if item.get("avatar_version") else None,
            )
            for item in contacts_raw
            if item.get("username") or item.get("wxid") or item.get("id")
        ]

        conversations: list[StandardConversation] = []
        messages: list[StandardMessage] = []
        meta_statuses: list[str] = []
        unknown_shards: set[str] = set()
        has_invalid_timestamps = False
        latest_by_shard: dict[str, datetime] = {}
        watermark_by_shard: dict[str, str] = {}

        for session in sessions_raw:
            source_id = str(session.get("username") or session.get("id") or session.get("name"))
            display_name = str(session.get("display") or session.get("name") or source_id)
            chat_type = str(session.get("chat_type") or "other")
            conversations.append(StandardConversation(source_id, display_name, chat_type, self._parse_time(session.get("timestamp") or session.get("time"))))

            args = ["history", display_name]
            if since:
                args.extend(["--since", since.date().isoformat()])
            history_payload = self._run_json(*args)
            history_rows = self._results(history_payload, "messages", "results", "history")
            meta = history_payload.get("meta", {}) if isinstance(history_payload, dict) else {}
            meta_statuses.append(str(meta.get("status", "ok")))
            unknown_shards.update(str(item) for item in meta.get("unknown_shards", []))

            for index, item in enumerate(history_rows):
                sent_at = self._parse_time(item.get("timestamp") or item.get("time"))
                if sent_at is None:
                    has_invalid_timestamps = True
                    continue
                shard = str(item.get("source_db") or item.get("shard") or "message_unknown")
                source_message_id = str(item.get("local_id") or item.get("id") or f"{int(sent_at.timestamp())}:{index}")
                sender_id = str(item.get("sender_username") or item.get("sender_id") or item.get("sender") or "unknown")
                sender_name = str(item.get("sender_group_nickname") or item.get("sender_contact_display") or item.get("sender") or sender_id)
                content = str(item.get("content") or item.get("text") or "")
                message_type = str(item.get("type") or item.get("message_type") or "unknown")
                direction = "outgoing" if item.get("is_self") or item.get("direction") == "outgoing" else "incoming"
                messages.append(StandardMessage(shard, source_message_id, source_id, display_name, chat_type, sender_id, sender_name, sent_at, direction, message_type, content))
                if shard not in latest_by_shard or sent_at > latest_by_shard[shard]:
                    latest_by_shard[shard] = sent_at
                    watermark_by_shard[shard] = sent_at.isoformat()

        freshness = "ok"
        if has_invalid_timestamps:
            freshness = "invalid_timestamps"
        elif any("unknown_shards" in status for status in meta_statuses):
            freshness = "unknown_shards"
        elif any("stale" in status for status in meta_statuses):
            freshness = "possibly_stale"
        return ConnectorBatch(account, contacts, conversations, messages, watermark_by_shard, latest_by_shard, freshness, sorted(unknown_shards))
