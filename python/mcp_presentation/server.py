"""FastMCP entrypoint — TaskStore + separate mcp-state package."""

from __future__ import annotations

import os
from pathlib import Path
from typing import cast

from fastmcp import FastMCP
from mcp_state import StateStore

from mcp_presentation._tasks import TaskStore
from mcp_presentation.types import (
    BuildPresentationResult,
    BuildQueued,
    DeployPresentationResult,
    DeployQueued,
    ErrorInvalidTarget,
    ErrorNoActiveWorkspace,
    ErrorNotFound,
    ErrorSessionNotFound,
    ErrorTaskNotFound,
    ErrorWorkspaceUnavailable,
    GetBuildStatusResult,
    GetSessionResult,
    SessionCreated,
    SessionRow,
    SetActiveWorkspaceResult,
    TaskRow,
    WorkspaceCreated,
    WorkspaceRow,
)

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


def _session_row(row: object) -> SessionRow:
    return cast(SessionRow, row)


def _workspace_row(row: object) -> WorkspaceRow:
    return cast(WorkspaceRow, row)


def _task_row(row: object) -> TaskRow:
    return cast(TaskRow, row)


@mcp.tool()
def create_session(meta: str = "") -> SessionCreated:
    """Create a persistent session (mcp-state package)."""
    sid = get_state().create_session(meta=meta or None)
    return {"session_id": sid}


@mcp.tool()
def get_session(session_id: str) -> GetSessionResult:
    """Read session from mcp-state SQLite."""
    row = get_state().get_session(session_id)
    if row is None:
        err: ErrorNotFound = {"error": "not_found", "session_id": session_id}
        return err
    return _session_row(row)


@mcp.tool()
def create_workspace(
    project_id: str, path: str, ref_name: str = "main"
) -> WorkspaceCreated:
    """Register a workspace checkout in mcp-state (git worktree is separate)."""
    wid = get_state().create_workspace(project_id, path, ref_name=ref_name or None)
    return {"workspace_id": wid, "path": path, "project_id": project_id}


@mcp.tool()
def set_active_workspace(session_id: str, workspace_id: str) -> SetActiveWorkspaceResult:
    """Attach an active workspace to a session."""
    get_state().set_active_workspace(session_id, workspace_id)
    row = get_state().get_session(session_id)
    if row is None:
        err: ErrorNotFound = {"error": "not_found", "session_id": session_id}
        return err
    return _session_row(row)


@mcp.tool()
def build_presentation(session_id: str, target: str) -> BuildPresentationResult:
    """Enqueue a presentation build (pdf|web) for the session's active workspace."""
    if target not in {"pdf", "web"}:
        bad: ErrorInvalidTarget = {"error": "invalid_target", "allowed": ["pdf", "web"]}
        return bad
    session = get_state().get_session(session_id)
    if session is None:
        missing: ErrorSessionNotFound = {
            "error": "session_not_found",
            "session_id": session_id,
        }
        return missing
    session_d = _session_row(session)
    wid = session_d["active_workspace_id"]
    if not wid:
        no_ws: ErrorNoActiveWorkspace = {
            "error": "no_active_workspace",
            "session_id": session_id,
        }
        return no_ws
    ws = get_state().get_workspace(wid)
    if ws is None:
        unavailable: ErrorWorkspaceUnavailable = {
            "error": "workspace_unavailable",
            "workspace_id": wid,
        }
        return unavailable
    ws_d = _workspace_row(ws)
    if ws_d["status"] != "active":
        inactive: ErrorWorkspaceUnavailable = {
            "error": "workspace_unavailable",
            "workspace_id": wid,
        }
        return inactive
    path = ws_d["path"]
    tid = get_tasks().submit(session_id, path, target)
    queued: BuildQueued = {"task_id": tid, "status": "queued", "workspace": path}
    return queued


@mcp.tool()
def get_build_status(task_id: str) -> GetBuildStatusResult:
    """Read build task status from the tasks SQLite store."""
    row = get_tasks().get(task_id)
    if row is None:
        missing: ErrorTaskNotFound = {"error": "not_found", "task_id": task_id}
        return missing
    return _task_row(row)


@mcp.tool()
def deploy_presentation(session_id: str, artifact: str = "") -> DeployPresentationResult:
    """Enqueue deploy as a separate task (ADR-0007)."""
    session = get_state().get_session(session_id)
    if session is None:
        missing: ErrorSessionNotFound = {
            "error": "session_not_found",
            "session_id": session_id,
        }
        return missing
    session_d = _session_row(session)
    wid = session_d["active_workspace_id"]
    if not wid:
        no_ws: ErrorNoActiveWorkspace = {
            "error": "no_active_workspace",
            "session_id": session_id,
        }
        return no_ws
    ws = get_state().get_workspace(wid)
    if ws is None:
        unavailable: ErrorWorkspaceUnavailable = {
            "error": "workspace_unavailable",
            "workspace_id": wid,
        }
        return unavailable
    path = _workspace_row(ws)["path"]
    tid = get_tasks().submit(session_id, path, "deploy")
    if artifact:
        get_tasks().update(tid, artifact=artifact)
    queued: DeployQueued = {"task_id": tid, "status": "queued", "target": "deploy"}
    return queued


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
