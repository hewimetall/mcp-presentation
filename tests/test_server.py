"""MCP server orchestration with FakeRunner (no Docker)."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any, cast

import pytest

pytest.importorskip("mcp_presentation._tasks")
pytest.importorskip("mcp_state._native")
pytest.importorskip("mcp_git._native")

from fastmcp import Client

import mcp_presentation.server as server
from mcp_presentation.worker import BuildWorker
from test_worker import FakeRunner


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    runner = FakeRunner()
    tasks = server.get_tasks()
    sync_worker = BuildWorker(tasks, runner)

    def _wake(_t: object) -> None:
        threading.Thread(target=sync_worker.process_one, daemon=True).start()

    monkeypatch.setattr(worker_mod, "_worker", sync_worker)
    monkeypatch.setattr(server, "wake_worker", _wake)
    yield
    sync_worker.stop()


def _payload(result: Any) -> dict[str, Any]:
    data = getattr(result, "data", None)
    if data is not None and hasattr(data, "model_dump"):
        return cast(dict[str, Any], data.model_dump())
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        inner = structured.get("result", structured)
        if isinstance(inner, dict):
            return cast(dict[str, Any], inner)
    raise AssertionError(f"cannot parse: {result!r}")


def test_full_flow_pdf_and_deploy() -> None:
    sess = server.create_session("demo")
    sid = sess["session_id"]
    proj = server.create_project("demo")
    assert "bare_path" in proj
    co = server.checkout_workspace(sid, "demo")
    assert "workspace_id" in co
    assert Path(co["path"]).is_dir()
    assert Path(co["path"]).name == co["workspace_id"]

    ir = {
        "title": "Hello",
        "author": "Test",
        "slides": [{"title": "One", "bullets": ["a", "b"]}],
    }
    saved = server.save_presentation_ir(sid, json.dumps(ir))
    assert "path" in saved
    assert saved.get("rebuild_required") is True
    assert "stale" in saved["note"].lower() or "rebuild" in saved["note"].lower()
    assert Path(saved["path"]).is_file()

    committed = server.commit_workspace(sid, "add ir", "presentation.ir.json")
    assert "commit_id" in committed

    async def _build_and_deploy() -> None:
        async with Client(server.mcp) as client:
            built = await client.call_tool(
                "build_presentation",
                {"session_id": sid, "target": "pdf"},
            )
            payload = _payload(built)
            assert payload["status"] == "done"
            assert "container" in (payload.get("logs") or "")
            dep = await client.call_tool("deploy_presentation", {"session_id": sid})
            dpay = _payload(dep)
            assert dpay["status"] == "done"
            assert Path(dpay["artifact"]).exists()
            assert "local_copy" in (dpay.get("logs") or "")

    asyncio.run(_build_and_deploy())

    listed = server.list_workspaces(project_id="demo")
    assert len(listed["workspaces"]) == 1
    ws = server.get_workspace(co["workspace_id"])
    assert ws["status"] == "active"


def test_invalid_ir_rejected() -> None:
    sess = server.create_session()
    sid = sess["session_id"]
    server.create_project("p1")
    server.checkout_workspace(sid, "p1")
    bad = server.save_presentation_ir(sid, '{"title":""}')
    assert bad.get("error") == "invalid_ir"


def test_get_slide_image_structured_meta() -> None:
    sid = server.create_session()["session_id"]
    server.create_project("slides")
    co = server.checkout_workspace(sid, "slides")
    server.save_presentation_ir(
        sid,
        json.dumps({"title": "Deck", "slides": [{"title": "One", "bullets": ["x"]}]}),
    )

    async def _run() -> Any:
        async with Client(server.mcp) as client:
            await client.call_tool(
                "build_presentation",
                {"session_id": sid, "target": "web"},
            )
            return await client.call_tool(
                "get_slide_image",
                {"session_id": sid, "slide": 1},
            )

    result = asyncio.run(_run())
    meta = _payload(result)
    assert meta["slide"] == 1
    assert meta["path"]
    assert 1 in meta["available"]
    assert "title" in meta["index_note"].lower()
    assert Path(co["path"]).name == co["workspace_id"]
