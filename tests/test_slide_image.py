"""Slide PNGs are part of pdf/web builds; get_slide_image only reads them."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastmcp.utilities.types import Image

pytest.importorskip("mcp_presentation._tasks")
pytest.importorskip("mcp_git._native")

import mcp_presentation.server as server
from mcp_presentation.engines import build_web
from mcp_presentation.slide_image import get_slide_png, slide_indices
from mcp_presentation.worker import BuildWorker
from test_worker import TINY_PNG, FakeRunner


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


def test_get_slide_png_reads_only(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    slides = ws / "out" / "slides"
    slides.mkdir(parents=True)
    (slides / "slide.001.png").write_bytes(TINY_PNG)
    (slides / "slide.002.png").write_bytes(TINY_PNG)
    path = get_slide_png(ws, 2)
    assert path.name == "slide.002.png"
    assert slide_indices(ws) == [1, 2]
    with pytest.raises(LookupError):
        get_slide_png(ws, 9)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        get_slide_png(empty, 1)


def test_web_build_refreshes_slide_pngs(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "presentation.ir.json").write_text(
        json.dumps({"title": "T", "slides": [{"title": "A"}, {"title": "B"}]}),
        encoding="utf-8",
    )
    # stale image from previous deck
    stale = ws / "out" / "slides"
    stale.mkdir(parents=True)
    (stale / "slide.001.png").write_bytes(TINY_PNG)
    (stale / "slide.009.png").write_bytes(TINY_PNG)

    build_web(ws, FakeRunner())
    assert slide_indices(ws) == [1, 2, 3]
    assert not (stale / "slide.009.png").exists()


def test_pdf_build_emits_slide_pngs(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "presentation.ir.json").write_text(
        json.dumps({"title": "T", "slides": [{"title": "A"}]}),
        encoding="utf-8",
    )
    store = __import__("mcp_presentation._tasks", fromlist=["TaskStore"]).TaskStore(
        str(tmp_path / "t.db")
    )
    worker = BuildWorker(store, FakeRunner())
    tid = store.submit("s", str(ws), "pdf")
    assert worker.process_one() is True
    row = store.get(tid)
    assert row is not None
    assert row["status"] == "done"
    assert slide_indices(ws) == [1, 2]


def test_get_slide_image_after_web_build() -> None:
    sid = server.create_session()["session_id"]
    server.create_project("slides")
    server.checkout_workspace(sid, "slides")
    server.save_presentation_ir(
        sid,
        json.dumps({"title": "Deck", "slides": [{"title": "One", "bullets": ["x"]}]}),
    )
    missing = server.get_slide_image(sid, 1)
    assert isinstance(missing, dict)
    assert missing["error"] == "no_artifact"

    queued = server.enqueue_build(sid, "web")
    import mcp_presentation.worker as worker_mod

    assert worker_mod._worker is not None
    assert worker_mod._worker.process_one() is True
    assert server.get_build_status(queued["task_id"])["status"] == "done"

    img = server.get_slide_image(sid, 1)
    assert isinstance(img, Image)
    bad = server.get_slide_image(sid, 99)
    assert isinstance(bad, dict)
    assert bad["error"] == "invalid_slide"
