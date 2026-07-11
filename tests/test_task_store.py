"""Smoke tests for Rust TaskStore (requires maturin develop)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("mcp_presentation._tasks")

from mcp_presentation._tasks import TaskStore


def test_submit_get_claim(tmp_path: Path) -> None:
    db = tmp_path / "tasks.db"
    store = TaskStore(str(db))

    tid = store.submit("s1", "ws/a", "pdf")
    row = store.get(tid)
    assert row is not None
    assert row["status"] == "queued"
    assert row["target"] == "pdf"

    claimed = store.claim_next()
    assert claimed is not None
    assert claimed["task_id"] == tid
    assert claimed["status"] == "running"

    assert store.claim_next() is None

    store.update(tid, status="done", artifact="out/main.pdf")
    done = store.get(tid)
    assert done["status"] == "done"
    assert done["artifact"] == "out/main.pdf"

    latest = store.find_latest_done("ws/a")
    assert latest is not None
    assert latest["task_id"] == tid
    assert store.find_latest_done("ws/a", "web") is None
    assert store.find_latest_done("ws/missing") is None
