"""Unit tests for SQLite ↔ MCP Progress bridge."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest

pytest.importorskip("mcp_presentation._tasks")

from mcp_presentation._tasks import TaskStore
from mcp_presentation.task_bridge import await_sqlite_task, status_message


class FakeProgress:
    def __init__(self) -> None:
        self.messages: list[str | None] = []

    async def set_message(self, message: str | None) -> None:
        self.messages.append(message)


def test_await_sqlite_task_mirrors_statuses(tmp_path: Path) -> None:
    store = TaskStore(str(tmp_path / "t.db"))
    tid = store.submit("sess", str(tmp_path / "ws"), "web")
    progress = FakeProgress()

    def finish() -> None:
        store.update(tid, status="running")
        store.update(tid, status="done", artifact=str(tmp_path / "out" / "dist"))

    threading.Timer(0.05, finish).start()
    row = asyncio.run(await_sqlite_task(store, tid, progress, poll_seconds=0.02))
    assert row["status"] == "done"
    assert row["task_id"] == tid
    joined = " | ".join(m for m in progress.messages if m)
    assert f"task_id={tid} status=queued" in joined
    assert f"task_id={tid} status=done" in joined
    assert "artifact=" not in joined
    assert status_message(row) == f"task_id={tid} status=done"


def test_await_sqlite_task_timeout(tmp_path: Path) -> None:
    store = TaskStore(str(tmp_path / "t.db"))
    tid = store.submit("sess", str(tmp_path / "ws"), "web")
    with pytest.raises(TimeoutError, match="timed out"):
        asyncio.run(await_sqlite_task(store, tid, poll_seconds=0.02, timeout=0.08))


def test_await_sqlite_task_missing(tmp_path: Path) -> None:
    store = TaskStore(str(tmp_path / "t.db"))
    with pytest.raises(LookupError):
        asyncio.run(await_sqlite_task(store, "nope", poll_seconds=0.01))
