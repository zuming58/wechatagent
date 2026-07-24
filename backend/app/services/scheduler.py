from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from threading import Event, Lock, Thread

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..connectors.base import Connector
from ..models import SyncRun
from .sync import SyncService


class SyncCoordinator:
    """Serializes sync work per account across HTTP requests and the scheduler."""

    def __init__(self) -> None:
        self._guard = Lock()
        self._account_locks: dict[str, Lock] = {}

    def try_acquire(self, account_id: str) -> Lock | None:
        with self._guard:
            lock = self._account_locks.setdefault(account_id, Lock())
        return lock if lock.acquire(blocking=False) else None


class AutomaticSyncScheduler:
    """Runs synthetic incremental syncs after a user has completed first archive."""

    def __init__(
        self,
        connector: Connector,
        session_factory: Callable[[], Session],
        coordinator: SyncCoordinator,
        overlap_seconds: int,
        interval_seconds: int,
        enabled: bool,
    ) -> None:
        self._connector = connector
        self._session_factory = session_factory
        self._coordinator = coordinator
        self._overlap_seconds = overlap_seconds
        self.interval_seconds = interval_seconds
        self.enabled = enabled
        self.last_cycle_at: datetime | None = None
        self.next_run_at: datetime | None = None
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if not self.enabled or self._thread:
            return
        self.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=self.interval_seconds)
        self._thread = Thread(target=self._loop, name="wechatagent-synthetic-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def run_cycle(self) -> list[SyncRun]:
        if not self.enabled:
            return []
        probe = self._connector.probe()
        if probe.status != "ready":
            return []
        selected_ids = {account.id for account in probe.accounts if account.selected}
        if not selected_ids:
            return []

        session = self._session_factory()
        try:
            archived_ids = set(session.scalars(
                select(SyncRun.account_id).where(
                    SyncRun.account_id.in_(selected_ids),
                    SyncRun.mode == "initial",
                    SyncRun.status.in_(("completed", "completed_with_warning")),
                )
            ))
        finally:
            session.close()

        runs: list[SyncRun] = []
        for account_id in selected_ids & archived_ids:
            lock = self._coordinator.try_acquire(account_id)
            if not lock:
                continue
            session = self._session_factory()
            try:
                runs.append(SyncService(self._connector, self._overlap_seconds).run(session, account_id, "incremental"))
            finally:
                session.close()
                lock.release()
        self.last_cycle_at = datetime.now(timezone.utc)
        self.next_run_at = self.last_cycle_at + timedelta(seconds=self.interval_seconds)
        return runs

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self.run_cycle()
