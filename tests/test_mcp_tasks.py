"""FastMCP Client task=True waits on SQLite TaskStore + status callbacks."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp_presentation._tasks")
pytest.importorskip("mcp_state._native")
pytest.importorskip("mcp_git._native")

from fastmcp import Client

import mcp_presentation.server as server
from mcp_presentation.worker import BuildWorker
from test_worker import FakeRunner


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BuildWorker:
    state = tmp_path / "state"
    projects = tmp_path / "projects"
    workspaces = tmp_path / "workspaces"
    monkeypatch.setenv("MCP_PRESENTATION_STATE", str(state))
    monkeypatch.setenv("MCP_PRESENTATION_PROJECTS", str(projects))
    monkeypatch.setenv("MCP_PRESENTATION_WORKSPACES", str(workspaces))
    monkeypatch.setattr(server, "STATE_DIR", state)
    monkeypatch.setattr(server, "TASKS_DB", state / "tasks.db")
    monkeypatch.setattr(server, "SESSIONS_DB", state / "sessions.db")
    monkeypatch.setattr(server, "_tasks", None)
    monkeypatch.setattr(server, "_state", None)
    monkeypatch.setattr(server, "_git", None)
    import mcp_presentation.paths as paths
    import mcp_presentation.worker as worker_mod

    monkeypatch.setattr(paths, "PROJECTS_DIR", projects)
    monkeypatch.setattr(paths, "WORKSPACES_DIR", workspaces)

    tasks = server.get_tasks()
    worker = BuildWorker(tasks, FakeRunner(), poll_seconds=0.05)
    worker.start_daemon()
    monkeypatch.setattr(worker_mod, "_worker", worker)
    monkeypatch.setattr(server, "wake_worker", lambda _t: worker.wake())
    yield worker
    worker.stop()


def _parse_tool_json(result: Any) -> dict[str, Any]:
    """Normalize FastMCP CallToolResult / Task result to a dict payload."""
    if isinstance(result, dict):
        return result
    data = getattr(result, "data", None)
    if data is not None and hasattr(data, "model_dump"):
        dumped = data.model_dump()
        if isinstance(dumped, dict):
            return dumped
    if isinstance(data, dict):
        return data
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        inner = structured.get("result", structured)
        if isinstance(inner, dict):
            return inner
    content = getattr(result, "content", None)
    if content:
        text = getattr(content[0], "text", None)
        if text:
            parsed: object = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
    raise AssertionError(f"cannot parse tool result: {result!r}")


def test_build_presentation_task_true_waits_sqlite(isolated: BuildWorker) -> None:
    sid = server.create_session()["session_id"]
    server.create_project("tasked")
    server.checkout_workspace(sid, "tasked")
    server.save_presentation_ir(
        sid,
        json.dumps({"title": "T", "slides": [{"title": "One", "bullets": ["a"]}]}),
    )

    updates: list[str] = []

    def on_status(status: Any) -> None:
        msg = getattr(status, "statusMessage", None) or getattr(status, "status_message", None)
        if msg:
            updates.append(str(msg))

    async def _run() -> dict[str, Any]:
        async with Client(server.mcp) as client:
            task = await client.call_tool(
                "build_presentation",
                {"session_id": sid, "target": "web"},
                task=True,
            )
            assert not getattr(task, "returned_immediately", False)
            task.on_status_change(on_status)
            result = await asyncio.wait_for(task.result(), timeout=15.0)
        return _parse_tool_json(result)

    payload = asyncio.run(_run())
    assert payload["status"] == "done"
    assert payload.get("artifact")
    sqlite_tid = payload["task_id"]
    assert server.get_build_status(sqlite_tid)["status"] == "done"
    assert any(sqlite_tid in u or "status=" in u for u in updates), (
        f"expected status notifications, got {updates!r}"
    )
