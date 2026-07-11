"""FastMCP entrypoint — TaskStore + separate mcp-state package."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

from fastmcp import FastMCP

from mcp_presentation._tasks import TaskStore
from mcp_state import StateStore

STATE_DIR = Path(os.environ.get("MCP_PRESENTATION_STATE", "state"))
TASKS_DB = STATE_DIR / "tasks.db"
SESSIONS_DB = STATE_DIR / "sessions.db"

mcp = FastMCP("mcp-presentation")
_tasks: TaskStore | None = None
_state: StateStore | None = None


def get_tasks() -> TaskStore:
    global _tasks
    if _tasks is None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _tasks = TaskStore(str(TASKS_DB))
    return _tasks


def get_state() -> StateStore:
    global _state
    if _state is None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _state = StateStore(str(SESSIONS_DB))
    return _state


def _as_dict(row: Any) -> dict[str, Any]:
    return cast(dict[str, Any], row)


@mcp.tool()
def create_session(meta: str = "") -> dict[str, Any]:
    """Create a persistent session (mcp-state package)."""
    sid = get_state().create_session(meta=meta or None)
    return {"session_id": sid}


@mcp.tool()
def get_session(session_id: str) -> dict[str, Any]:
    """Read session from mcp-state SQLite."""
    row = get_state().get_session(session_id)
    if row is None:
        return {"error": "not_found", "session_id": session_id}
    return _as_dict(row)


@mcp.tool()
def create_workspace(project_id: str, path: str, ref_name: str = "main") -> dict[str, Any]:
    """Register a workspace checkout in mcp-state (git worktree is separate)."""
    wid = get_state().create_workspace(project_id, path, ref_name=ref_name or None)
    return {"workspace_id": wid, "path": path, "project_id": project_id}


@mcp.tool()
def set_active_workspace(session_id: str, workspace_id: str) -> dict[str, Any]:
    """Attach an active workspace to a session."""
    get_state().set_active_workspace(session_id, workspace_id)
    row = get_state().get_session(session_id)
    if row is None:
        return {"error": "not_found", "session_id": session_id}
    return _as_dict(row)


@mcp.tool()
def build_presentation(session_id: str, target: str) -> dict[str, Any]:
    """Enqueue a presentation build (pdf|web) for the session's active workspace."""
    if target not in {"pdf", "web"}:
        return {"error": "invalid_target", "allowed": ["pdf", "web"]}
    session = get_state().get_session(session_id)
    if session is None:
        return {"error": "session_not_found", "session_id": session_id}
    session_d = _as_dict(session)
    wid = session_d.get("active_workspace_id")
    if not wid:
        return {"error": "no_active_workspace", "session_id": session_id}
    ws = get_state().get_workspace(str(wid))
    if ws is None:
        return {"error": "workspace_unavailable", "workspace_id": wid}
    ws_d = _as_dict(ws)
    if ws_d.get("status") != "active":
        return {"error": "workspace_unavailable", "workspace_id": wid}
    path = str(ws_d["path"])
    tid = get_tasks().submit(session_id, path, target)
    return {"task_id": tid, "status": "queued", "workspace": path}


@mcp.tool()
def get_build_status(task_id: str) -> dict[str, Any]:
    """Read build task status from the tasks SQLite store."""
    row = get_tasks().get(task_id)
    if row is None:
        return {"error": "not_found", "task_id": task_id}
    return _as_dict(row)


@mcp.tool()
def deploy_presentation(session_id: str, artifact: str = "") -> dict[str, Any]:
    """Enqueue deploy as a separate task (ADR-0007)."""
    session = get_state().get_session(session_id)
    if session is None:
        return {"error": "session_not_found", "session_id": session_id}
    session_d = _as_dict(session)
    wid = session_d.get("active_workspace_id")
    if not wid:
        return {"error": "no_active_workspace", "session_id": session_id}
    ws = get_state().get_workspace(str(wid))
    if ws is None:
        return {"error": "workspace_unavailable", "workspace_id": wid}
    path = str(_as_dict(ws)["path"])
    tid = get_tasks().submit(session_id, path, "deploy")
    if artifact:
        get_tasks().update(tid, artifact=artifact)
    return {"task_id": tid, "status": "queued", "target": "deploy"}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
