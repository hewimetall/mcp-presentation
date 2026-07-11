"""Slide image render + get_slide_image tool."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastmcp.utilities.types import Image

pytest.importorskip("mcp_presentation._tasks")
pytest.importorskip("mcp_git._native")

import mcp_presentation.server as server
from mcp_presentation.slide_image import resolve_slide_png, slide_indices
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
    sync_worker = BuildWorker(server.get_tasks(), FakeRunner())
    monkeypatch.setattr(worker_mod, "_worker", sync_worker)
    monkeypatch.setattr(server, "wake_worker", lambda _t: None)
    yield
    sync_worker.stop()


def test_resolve_slide_png(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "presentation.ir.json").write_text(
        json.dumps(
            {
                "title": "T",
                "slides": [{"title": "A"}, {"title": "B"}],
            }
        ),
        encoding="utf-8",
    )
    runner = FakeRunner()
    path = resolve_slide_png(ws, 2, runner)
    assert path.is_file()
    assert path.name == "slide.002.png"
    assert slide_indices(ws) == [1, 2, 3]
    with pytest.raises(LookupError):
        resolve_slide_png(ws, 9, runner, force=False)


def test_get_slide_image_tool() -> None:
    sid = server.create_session()["session_id"]
    server.create_project("slides")
    server.checkout_workspace(sid, "slides")
    server.save_presentation_ir(
        sid,
        json.dumps(
            {
                "title": "Deck",
                "slides": [{"title": "One", "bullets": ["x"]}],
            }
        ),
    )
    img = server.get_slide_image(sid, 1)
    assert isinstance(img, Image)
    bad = server.get_slide_image(sid, 99)
    assert isinstance(bad, dict)
    assert bad["error"] == "invalid_slide"
