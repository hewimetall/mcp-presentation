"""FastMCP entrypoint — TaskStore + mcp-state + mcp-git + build worker."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import cast

from fastmcp import FastMCP
from fastmcp.utilities.types import Image

from mcp_git import GitService
from mcp_presentation._tasks import TaskStore
from mcp_presentation.ir_compile import IR_FILENAME, write_ir
from mcp_presentation.ir_models import validate_ir_obj
from mcp_presentation.paths import PROJECTS_DIR, WORKSPACES_DIR, project_bare_path
from mcp_presentation.settings import BUILD_TARGETS
from mcp_presentation.slide_image import get_slide_png, slide_indices
from mcp_presentation.types import (
    BuildPresentationResult,
    BuildQueued,
    CheckoutResult,
    CheckoutWorkspaceResult,
    CommitResult,
    CommitWorkspaceResult,
    CreateProjectResult,
    DeployPresentationResult,
    DeployQueued,
    ErrorGit,
    ErrorInvalidId,
    ErrorInvalidIr,
    ErrorInvalidSlide,
    ErrorInvalidTarget,
    ErrorNoActiveWorkspace,
    ErrorNoArtifact,
    ErrorNotFound,
    ErrorSessionNotFound,
    ErrorTaskNotFound,
    ErrorWorkspaceNotFound,
    ErrorWorkspaceUnavailable,
    GetBuildStatusResult,
    GetSessionResult,
    GetSlideImageResult,
    GetWorkspaceResult,
    IrSaved,
    ProjectCreated,
    RemoveWorkspaceResult,
    SaveIrResult,
    SessionCreated,
    SessionRow,
    SessionsList,
    SetActiveWorkspaceResult,
    TaskRow,
    WorkspaceCreated,
    WorkspaceRemoved,
    WorkspaceRow,
    WorkspacesList,
)
from mcp_presentation.worker import wake_worker
from mcp_state import StateStore

STATE_DIR = Path(os.environ.get("MCP_PRESENTATION_STATE", "state"))
TASKS_DB = STATE_DIR / "tasks.db"
SESSIONS_DB = STATE_DIR / "sessions.db"

mcp = FastMCP("mcp-presentation")
_tasks: TaskStore | None = None
_state: StateStore | None = None
_git: GitService | None = None


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


def get_git() -> GitService:
    global _git
    if _git is None:
        _git = GitService()
    return _git


def _session_row(row: object) -> SessionRow:
    return cast(SessionRow, row)


def _workspace_row(row: object) -> WorkspaceRow:
    return cast(WorkspaceRow, row)


def _task_row(row: object) -> TaskRow:
    return cast(TaskRow, row)


def _active_workspace(
    session_id: str,
) -> (
    tuple[SessionRow, WorkspaceRow]
    | ErrorSessionNotFound
    | ErrorNoActiveWorkspace
    | ErrorWorkspaceUnavailable
):
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
    return session_d, ws_d


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
def list_sessions() -> SessionsList:
    """List all sessions."""
    rows = get_state().list_sessions()
    return {"sessions": [_session_row(r) for r in rows]}


@mcp.tool()
def create_project(project_id: str) -> CreateProjectResult:
    """Init bare git repo under projects/<id>.git (seeded empty main)."""
    try:
        bare = project_bare_path(project_id)
    except ValueError as exc:
        bad: ErrorInvalidId = {"error": "invalid_id", "detail": str(exc)}
        return bad
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    if bare.exists():
        created: ProjectCreated = {
            "project_id": project_id,
            "bare_path": str(bare.resolve()),
        }
        return created
    try:
        path = get_git().init_bare(str(bare))
    except Exception as exc:
        git_err: ErrorGit = {"error": "git_error", "detail": str(exc)}
        return git_err
    ok: ProjectCreated = {"project_id": project_id, "bare_path": path}
    return ok


@mcp.tool()
def checkout_workspace(
    session_id: str,
    project_id: str,
    ref_name: str = "main",
    workspace_id: str = "",
) -> CheckoutWorkspaceResult:
    """Create git worktree + register workspace + set session active."""
    session = get_state().get_session(session_id)
    if session is None:
        missing: ErrorSessionNotFound = {
            "error": "session_not_found",
            "session_id": session_id,
        }
        return missing
    try:
        bare = project_bare_path(project_id)
    except ValueError as exc:
        bad: ErrorInvalidId = {"error": "invalid_id", "detail": str(exc)}
        return bad
    if not bare.exists():
        try:
            get_git().init_bare(str(bare))
        except Exception as exc:
            git_err: ErrorGit = {"error": "git_error", "detail": str(exc)}
            return git_err

    wid = workspace_id.strip() or uuid.uuid4().hex[:12]
    try:
        from mcp_presentation.paths import require_safe_id, workspace_path

        require_safe_id(wid, kind="workspace_id")
        wt = workspace_path(wid)
    except ValueError as exc:
        bad_id: ErrorInvalidId = {"error": "invalid_id", "detail": str(exc)}
        return bad_id

    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    try:
        abs_wt = get_git().add_worktree(str(bare), str(wt), ref_name)
    except Exception as exc:
        git_fail: ErrorGit = {"error": "git_error", "detail": str(exc)}
        return git_fail

    state_wid = get_state().create_workspace(project_id, abs_wt, ref_name=ref_name or None)
    get_state().set_active_workspace(session_id, state_wid)
    result: CheckoutResult = {
        "workspace_id": state_wid,
        "path": abs_wt,
        "project_id": project_id,
        "ref_name": ref_name or "main",
        "bare_path": str(bare.resolve()),
        "session_id": session_id,
    }
    return result


@mcp.tool()
def create_workspace(project_id: str, path: str, ref_name: str = "main") -> WorkspaceCreated:
    """Register an existing checkout path in mcp-state (no git). Prefer checkout_workspace."""
    wid = get_state().create_workspace(project_id, path, ref_name=ref_name or None)
    return {"workspace_id": wid, "path": path, "project_id": project_id}


@mcp.tool()
def get_workspace(workspace_id: str) -> GetWorkspaceResult:
    """Read one workspace row."""
    row = get_state().get_workspace(workspace_id)
    if row is None:
        err: ErrorWorkspaceNotFound = {
            "error": "not_found",
            "workspace_id": workspace_id,
        }
        return err
    return _workspace_row(row)


@mcp.tool()
def list_workspaces(project_id: str = "", status: str = "active") -> WorkspacesList:
    """List workspaces, optionally filtered by project and status."""
    rows = get_state().list_workspaces(
        project_id=project_id or None,
        status=status or None,
    )
    return {"workspaces": [_workspace_row(r) for r in rows]}


@mcp.tool()
def set_active_workspace(session_id: str, workspace_id: str) -> SetActiveWorkspaceResult:
    """Attach an active workspace to a session."""
    try:
        get_state().set_active_workspace(session_id, workspace_id)
    except Exception:
        err: ErrorNotFound = {"error": "not_found", "session_id": session_id}
        return err
    row = get_state().get_session(session_id)
    if row is None:
        missing: ErrorNotFound = {"error": "not_found", "session_id": session_id}
        return missing
    return _session_row(row)


@mcp.tool()
def remove_workspace(workspace_id: str) -> RemoveWorkspaceResult:
    """Mark workspace removed (does not delete files on disk)."""
    try:
        get_state().mark_workspace_removed(workspace_id)
    except Exception:
        err: ErrorWorkspaceNotFound = {
            "error": "not_found",
            "workspace_id": workspace_id,
        }
        return err
    removed: WorkspaceRemoved = {"workspace_id": workspace_id, "status": "removed"}
    return removed


@mcp.tool()
def save_presentation_ir(session_id: str, ir_json: str) -> SaveIrResult:
    """Validate and write presentation.ir.json into the active workspace."""
    resolved = _active_workspace(session_id)
    if isinstance(resolved, dict):
        return resolved
    _, ws = resolved
    try:
        raw: object = json.loads(ir_json)
        ir = validate_ir_obj(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        bad: ErrorInvalidIr = {"error": "invalid_ir", "detail": str(exc)}
        return bad
    path = write_ir(Path(ws["path"]), ir)
    saved: IrSaved = {"path": str(path), "workspace_id": ws["workspace_id"]}
    return saved


@mcp.tool()
def commit_workspace(
    session_id: str, message: str = "update presentation", paths: str = ""
) -> CommitWorkspaceResult:
    """Commit listed paths (comma-separated) in the active worktree via gix."""
    resolved = _active_workspace(session_id)
    if isinstance(resolved, dict):
        return resolved
    _, ws = resolved
    path_list = [p.strip() for p in paths.split(",") if p.strip()]
    if not path_list:
        path_list = [IR_FILENAME]
    try:
        cid = get_git().commit(ws["path"], message, path_list)
    except Exception as exc:
        git_err: ErrorGit = {"error": "git_error", "detail": str(exc)}
        return git_err
    ok: CommitResult = {
        "commit_id": cid,
        "workspace_id": ws["workspace_id"],
        "paths": path_list,
    }
    return ok


@mcp.tool()
def build_presentation(session_id: str, target: str) -> BuildPresentationResult:
    """Enqueue a presentation build (pdf|web|web-pdf) for the active workspace."""
    if target not in BUILD_TARGETS:
        bad: ErrorInvalidTarget = {
            "error": "invalid_target",
            "allowed": sorted(BUILD_TARGETS),
        }
        return bad
    resolved = _active_workspace(session_id)
    if isinstance(resolved, dict):
        return resolved
    session_d, ws_d = resolved
    path = ws_d["path"]
    tid = get_tasks().submit(session_d["session_id"], path, target)
    wake_worker(get_tasks())
    queued: BuildQueued = {"task_id": tid, "status": "queued", "workspace": path}
    return queued


@mcp.tool()
def get_build_status(task_id: str) -> GetBuildStatusResult:
    """Read build/deploy task status from the tasks SQLite store."""
    row = get_tasks().get(task_id)
    if row is None:
        missing: ErrorTaskNotFound = {"error": "not_found", "task_id": task_id}
        return missing
    return _task_row(row)


@mcp.tool()
def get_slide_image(session_id: str, slide: int) -> Image | GetSlideImageResult:
    """Return PNG for one already-built slide (1-based). Does not build.

    Requires a prior ``build_presentation(..., target="slide-image")``.
    Slide 1 is the first Marp page (usually the title page from IR).
    """
    resolved = _active_workspace(session_id)
    if isinstance(resolved, dict):
        return resolved
    _, ws_d = resolved
    host_ws = Path(ws_d["path"]).resolve()
    try:
        path = get_slide_png(host_ws, slide)
    except ValueError as exc:
        bad: ErrorInvalidSlide = {
            "error": "invalid_slide",
            "slide": slide,
            "detail": str(exc),
            "available": slide_indices(host_ws),
        }
        return bad
    except FileNotFoundError as exc:
        missing_build: ErrorNoArtifact = {
            "error": "no_artifact",
            "detail": str(exc),
        }
        return missing_build
    except LookupError as exc:
        missing_slide: ErrorInvalidSlide = {
            "error": "invalid_slide",
            "slide": slide,
            "detail": str(exc),
            "available": slide_indices(host_ws),
        }
        return missing_slide
    return Image(path=str(path), format="png")


@mcp.tool()
def deploy_presentation(session_id: str, artifact: str = "") -> DeployPresentationResult:
    """Enqueue local deploy of an artifact (or latest successful build)."""
    resolved = _active_workspace(session_id)
    if isinstance(resolved, dict):
        return resolved
    session_d, ws_d = resolved
    path = ws_d["path"]
    art: str | None = artifact.strip() or None
    if art is None:
        latest = get_tasks().find_latest_done(path)
        if latest is not None:
            art = _task_row(latest).get("artifact")
    if art is None:
        no_art: ErrorNoArtifact = {
            "error": "no_artifact",
            "detail": "pass artifact= or complete a pdf/web build first",
        }
        return no_art
    if not Path(art).exists():
        missing_art: ErrorNoArtifact = {
            "error": "no_artifact",
            "detail": f"artifact not found: {art}",
        }
        return missing_art
    tid = get_tasks().submit(session_d["session_id"], path, "deploy")
    get_tasks().update(tid, artifact=art)
    wake_worker(get_tasks())
    queued: DeployQueued = {
        "task_id": tid,
        "status": "queued",
        "target": "deploy",
        "artifact": art,
    }
    return queued


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
