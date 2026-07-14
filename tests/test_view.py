"""Unit tests for public web view URL helpers (ADR-0013)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.responses import FileResponse, PlainTextResponse

from mcp_presentation.view import (
    build_view_url,
    resolve_web_root,
    safe_file_under,
    view_url_for_workspace,
)


def test_resolve_web_root_prefers_deployed_dist(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>raw</html>", encoding="utf-8")
    deployed = tmp_path / "out" / "deployed" / "dist"
    deployed.mkdir(parents=True)
    (deployed / "index.html").write_text("<html>dep</html>", encoding="utf-8")
    assert resolve_web_root(tmp_path) == deployed.resolve()


def test_resolve_web_root_falls_back_to_dist(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    assert resolve_web_root(tmp_path) == dist.resolve()


def test_resolve_web_root_missing(tmp_path: Path) -> None:
    assert resolve_web_root(tmp_path) is None


def test_build_view_url_requires_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_PRESENTATION_PUBLIC_BASE", raising=False)
    err = build_view_url("ws1")
    assert isinstance(err, dict)
    assert err["error"] == "public_base_unset"


def test_build_view_url_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_PRESENTATION_PUBLIC_BASE", "https://slides.example.com/")
    assert build_view_url("abc12") == "https://slides.example.com/view/abc12/"


def test_view_url_for_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_PRESENTATION_PUBLIC_BASE", "https://x.test")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    ok = view_url_for_workspace("wid1", tmp_path, session_id="sess1")
    assert "view_url" in ok
    assert ok["view_url"] == "https://x.test/view/wid1/"
    assert ok["resource_uri"] == "presentation://sess1/view"
    assert Path(ok["web_root"]).is_dir()


def test_view_url_no_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_PRESENTATION_PUBLIC_BASE", "https://x.test")
    err = view_url_for_workspace("wid1", tmp_path, session_id="s")
    assert err["error"] == "no_web_artifact"


def test_safe_file_under_rejects_escape(tmp_path: Path) -> None:
    root = tmp_path / "dist"
    root.mkdir()
    (root / "index.html").write_text("ok", encoding="utf-8")
    outside = tmp_path / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    assert safe_file_under(root, "") == (root / "index.html").resolve()
    assert safe_file_under(root, "../secret.txt") is None
    assert safe_file_under(root, "missing.css") is None


def test_serve_web_view_http_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise custom_route handler branches without starting uvicorn."""
    import mcp_presentation.server as server

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

    monkeypatch.setattr(paths, "PROJECTS_DIR", projects)
    monkeypatch.setattr(paths, "WORKSPACES_DIR", workspaces)

    def _req(workspace_id: str, path: str = "") -> SimpleNamespace:
        return SimpleNamespace(path_params={"workspace_id": workspace_id, "path": path})

    async def _call(workspace_id: str, path: str = "") -> object:
        return await server.serve_web_view(_req(workspace_id, path))  # type: ignore[arg-type]

    bad = asyncio.run(_call("bad id!"))
    assert isinstance(bad, PlainTextResponse)
    assert bad.status_code == 400

    missing = asyncio.run(_call("nows"))
    assert isinstance(missing, PlainTextResponse)
    assert missing.status_code == 404

    sid = server.create_session()["session_id"]
    server.create_project("vproj")
    co = server.checkout_workspace(sid, "vproj", workspace_id="viewws01")
    no_art = asyncio.run(_call("viewws01"))
    assert isinstance(no_art, PlainTextResponse)
    assert no_art.status_code == 404

    dist = Path(co["path"]) / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>hi</html>", encoding="utf-8")
    (dist / "a.css").write_text("body{}", encoding="utf-8")

    ok = asyncio.run(_call("viewws01"))
    assert isinstance(ok, FileResponse)

    css = asyncio.run(_call("viewws01", "a.css"))
    assert isinstance(css, FileResponse)

    gone = asyncio.run(_call("viewws01", "nope.js"))
    assert isinstance(gone, PlainTextResponse)
    assert gone.status_code == 404

    server.remove_workspace("viewws01")
    inactive = asyncio.run(_call("viewws01"))
    assert isinstance(inactive, PlainTextResponse)
    assert inactive.status_code == 404
