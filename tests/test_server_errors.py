"""Server error-path and branch coverage (FakeRunner, no Docker)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

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
    sync = BuildWorker(server.get_tasks(), FakeRunner())
    monkeypatch.setattr(worker_mod, "_worker", sync)
    monkeypatch.setattr(server, "wake_worker", lambda _t: None)
    yield
    sync.stop()


def test_session_list_and_get_errors() -> None:
    assert server.get_session("nope")["error"] == "not_found"
    sid = server.create_session("m")["session_id"]
    listed = server.list_sessions()
    assert any(s["session_id"] == sid for s in listed["sessions"])
    assert "session_id" in server.get_session(sid)


def test_create_project_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    assert server.create_project("bad id!")["error"] == "invalid_id"
    ok = server.create_project("p1")
    assert server.create_project("p1")["bare_path"] == ok["bare_path"]
    git = MagicMock()
    git.init_bare.side_effect = RuntimeError("boom")
    monkeypatch.setattr(server, "get_git", lambda: git)
    assert server.create_project("p2")["error"] == "git_error"


def test_active_workspace_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    assert server._active_workspace("missing")["error"] == "session_not_found"
    sid = server.create_session()["session_id"]
    assert server._active_workspace(sid)["error"] == "no_active_workspace"

    st = MagicMock()
    st.get_session.return_value = {
        "session_id": "s1",
        "active_workspace_id": "gone",
        "meta": None,
        "created_at": 0,
        "updated_at": 0,
    }
    st.get_workspace.return_value = None
    monkeypatch.setattr(server, "get_state", lambda: st)
    assert server._active_workspace("s1")["error"] == "workspace_unavailable"

    st.get_workspace.return_value = {
        "workspace_id": "gone",
        "project_id": "p",
        "path": "/x",
        "ref_name": "main",
        "status": "removed",
        "created_at": 0,
        "updated_at": 0,
    }
    assert server._active_workspace("s1")["error"] == "workspace_unavailable"


def test_checkout_session_and_project_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    assert server.checkout_workspace("no-sess", "p")["error"] == "session_not_found"
    sid = server.create_session()["session_id"]
    assert server.checkout_workspace(sid, "bad id!")["error"] == "invalid_id"
    git = MagicMock()
    git.init_bare.side_effect = RuntimeError("init fail")
    monkeypatch.setattr(server, "get_git", lambda: git)
    assert server.checkout_workspace(sid, "newproj")["error"] == "git_error"


def test_checkout_workspace_id_and_exists() -> None:
    sid = server.create_session()["session_id"]
    server.create_project("okp")
    assert server.checkout_workspace(sid, "okp", workspace_id="bad id!")["error"] == "invalid_id"
    co = server.checkout_workspace(sid, "okp", workspace_id="ws-one")
    assert "workspace_id" in co
    assert (
        server.checkout_workspace(sid, "okp", workspace_id="ws-one")["error"] == "workspace_exists"
    )


def test_checkout_worktree_and_state_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sid = server.create_session()["session_id"]
    server.create_project("okp")
    git2 = MagicMock()
    git2.add_worktree.side_effect = RuntimeError("wt fail")
    monkeypatch.setattr(server, "get_git", lambda: git2)
    assert server.checkout_workspace(sid, "okp", workspace_id="ws-two")["error"] == "git_error"


def test_checkout_state_register_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sid = server.create_session()["session_id"]
    server.create_project("okp")
    real = server.get_state()
    st = MagicMock()
    st.get_session.side_effect = real.get_session
    st.get_workspace.return_value = None
    st.create_workspace.side_effect = RuntimeError("db fail")
    git3 = MagicMock()
    git3.add_worktree.return_value = str(tmp_path / "fake-wt")
    monkeypatch.setattr(server, "get_git", lambda: git3)
    monkeypatch.setattr(server, "get_state", lambda: st)
    err = server.checkout_workspace(sid, "okp", workspace_id="ws-reg-fail")
    assert err["error"] == "git_error"
    assert "state register failed" in err["detail"]


def test_workspace_crud_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    created = server.create_workspace("px", "/some/path", ref_name="main")
    assert server.get_workspace("missing")["error"] == "not_found"
    assert server.get_workspace(created["workspace_id"])["path"] == "/some/path"

    sid = server.create_session()["session_id"]
    assert server.set_active_workspace("nope", created["workspace_id"])["error"] == "not_found"
    ok = server.set_active_workspace(sid, created["workspace_id"])
    assert ok["active_workspace_id"] == created["workspace_id"]

    st = MagicMock()
    st.set_active_workspace.return_value = None
    st.get_session.return_value = None
    monkeypatch.setattr(server, "get_state", lambda: st)
    assert server.set_active_workspace(sid, created["workspace_id"])["error"] == "not_found"


def test_remove_workspace_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    st = MagicMock()
    st.mark_workspace_removed.side_effect = RuntimeError("missing ws")
    monkeypatch.setattr(server, "get_state", lambda: st)
    assert server.remove_workspace("zzz")["error"] == "not_found"


def test_remove_workspace_success() -> None:
    created = server.create_workspace("py", "/other")
    assert server.remove_workspace(created["workspace_id"])["status"] == "removed"


def test_save_commit_enqueue_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    assert server.save_presentation_ir("nope", "{}")["error"] == "session_not_found"
    assert server.commit_workspace("nope")["error"] == "session_not_found"
    assert server.enqueue_build("nope", "pdf")["error"] == "session_not_found"
    assert server.enqueue_build("nope", "bad")["error"] == "invalid_target"
    assert server.get_build_status("missing")["error"] == "not_found"
    assert server.get_slide_image("nope", 1)["error"] == "session_not_found"
    assert server.enqueue_deploy("nope")["error"] == "session_not_found"
    assert server.get_view_url("nope")["error"] == "session_not_found"

    sid = server.create_session()["session_id"]
    server.create_project("c1")
    server.checkout_workspace(sid, "c1")
    monkeypatch.delenv("MCP_PRESENTATION_PUBLIC_BASE", raising=False)
    assert server.get_view_url(sid)["error"] == "public_base_unset"
    monkeypatch.setenv("MCP_PRESENTATION_PUBLIC_BASE", "https://x.test")
    assert server.get_view_url(sid)["error"] == "no_web_artifact"
    server.save_presentation_ir(
        sid, json.dumps({"title": "T", "slides": [{"title": "S", "bullets": ["a"]}]})
    )
    committed = server.commit_workspace(sid, "m", paths="")
    assert committed["paths"] == ["presentation.ir.json"]

    git = MagicMock()
    git.commit.side_effect = RuntimeError("commit fail")
    monkeypatch.setattr(server, "get_git", lambda: git)
    assert server.commit_workspace(sid, "m", "presentation.ir.json")["error"] == "git_error"

    assert server.enqueue_deploy(sid)["error"] == "no_artifact"
    assert server.enqueue_deploy(sid, artifact="/no/such.pdf")["error"] == "no_artifact"
    assert server.get_slide_image(sid, 0)["error"] == "invalid_slide"


def test_async_tools_return_enqueue_errors() -> None:
    async def _build() -> Any:
        return await server.build_presentation("nope", "pdf")

    async def _deploy() -> Any:
        return await server.deploy_presentation("nope")

    assert asyncio.run(_build())["error"] == "session_not_found"
    assert asyncio.run(_deploy())["error"] == "session_not_found"


def test_wait_timeout_path(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(*_a: Any, **_k: Any) -> Any:
        raise TimeoutError("waited too long")

    monkeypatch.setattr(server, "await_sqlite_task", boom)

    class FakeProgress:
        _impl = object()

        async def set_total(self, n: int) -> None:
            self.total = n

        async def set_message(self, message: str | None) -> None:
            self.msg = message

        async def increment(self, n: int = 1) -> None:
            self.inc = n

    out = asyncio.run(server._wait_queued_task("tid-x", FakeProgress()))
    assert out["error"] == "wait_timeout"
    assert out["task_id"] == "tid-x"


def test_main_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    runs: list[dict[str, Any]] = []

    def capture_run(*_a: Any, **kw: Any) -> None:
        runs.append(dict(kw))

    monkeypatch.delenv("MCP_PRESENTATION_TRANSPORT", raising=False)
    monkeypatch.setattr(server.mcp, "run", capture_run)
    server.main()
    assert runs == [{}]

    monkeypatch.setenv("MCP_PRESENTATION_TRANSPORT", "http")
    monkeypatch.setenv("MCP_PRESENTATION_HOST", "127.0.0.1")
    monkeypatch.setenv("MCP_PRESENTATION_PORT", "9001")
    runs.clear()
    server.main()
    assert runs == [{"transport": "http", "host": "127.0.0.1", "port": 9001}]
