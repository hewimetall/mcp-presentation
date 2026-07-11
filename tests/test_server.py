"""MCP server orchestration with FakeRunner (no Docker)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("mcp_presentation._tasks")
pytest.importorskip("mcp_state._native")
pytest.importorskip("mcp_git._native")

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
    # Sync FakeRunner worker — no daemon thread (avoids races with Docker).
    runner = FakeRunner()
    tasks = server.get_tasks()
    sync_worker = BuildWorker(tasks, runner)
    monkeypatch.setattr(worker_mod, "_worker", sync_worker)
    monkeypatch.setattr(server, "wake_worker", lambda _t: None)
    yield
    sync_worker.stop()


def test_full_flow_pdf_and_deploy() -> None:
    sess = server.create_session("demo")
    sid = sess["session_id"]
    proj = server.create_project("demo")
    assert "bare_path" in proj
    co = server.checkout_workspace(sid, "demo")
    assert "workspace_id" in co
    assert Path(co["path"]).is_dir()

    ir = {
        "title": "Hello",
        "author": "Test",
        "slides": [{"title": "One", "bullets": ["a", "b"]}],
    }
    saved = server.save_presentation_ir(sid, json.dumps(ir))
    assert "path" in saved
    assert Path(saved["path"]).is_file()

    committed = server.commit_workspace(sid, "add ir", "presentation.ir.json")
    assert "commit_id" in committed

    queued = server.enqueue_build(sid, "pdf")
    assert queued["status"] == "queued"

    import mcp_presentation.worker as worker_mod

    assert worker_mod._worker is not None
    assert worker_mod._worker.process_one() is True
    status = server.get_build_status(queued["task_id"])
    assert status["status"] == "done"
    assert status.get("artifact")

    dep = server.enqueue_deploy(sid)
    assert dep["status"] == "queued"
    assert worker_mod._worker.process_one() is True
    dstatus = server.get_build_status(dep["task_id"])
    assert dstatus["status"] == "done"
    assert Path(dstatus["artifact"]).exists()

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
