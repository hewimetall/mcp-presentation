"""TypedDict models for MCP tool I/O and Rust store rows."""

from __future__ import annotations

from typing import Literal, TypedDict


class SessionRow(TypedDict):
    session_id: str
    active_workspace_id: str | None
    meta: str | None
    created_at: int
    updated_at: int


class WorkspaceRow(TypedDict):
    workspace_id: str
    project_id: str
    path: str
    ref_name: str | None
    status: str
    created_at: int
    updated_at: int


class TaskRow(TypedDict):
    task_id: str
    session_id: str | None
    workspace: str | None
    target: str
    status: str
    artifact: str | None
    logs: str | None
    error: str | None
    created_at: int
    updated_at: int


class SessionCreated(TypedDict):
    session_id: str


class WorkspaceCreated(TypedDict):
    workspace_id: str
    path: str
    project_id: str


class ProjectCreated(TypedDict):
    project_id: str
    bare_path: str


class CheckoutResult(TypedDict):
    workspace_id: str
    path: str
    project_id: str
    ref_name: str
    bare_path: str
    session_id: str


class IrSaved(TypedDict):
    path: str
    workspace_id: str


class CommitResult(TypedDict):
    commit_id: str
    workspace_id: str
    paths: list[str]


class BuildQueued(TypedDict):
    task_id: str
    status: Literal["queued"]
    workspace: str


class DeployQueued(TypedDict):
    task_id: str
    status: Literal["queued"]
    target: Literal["deploy"]
    artifact: str | None


class WorkspaceRemoved(TypedDict):
    workspace_id: str
    status: Literal["removed"]


class SessionsList(TypedDict):
    sessions: list[SessionRow]


class WorkspacesList(TypedDict):
    workspaces: list[WorkspaceRow]


class ErrorNotFound(TypedDict):
    error: Literal["not_found"]
    session_id: str


class ErrorTaskNotFound(TypedDict):
    error: Literal["not_found"]
    task_id: str


class ErrorWorkspaceNotFound(TypedDict):
    error: Literal["not_found"]
    workspace_id: str


class ErrorSessionNotFound(TypedDict):
    error: Literal["session_not_found"]
    session_id: str


class ErrorNoActiveWorkspace(TypedDict):
    error: Literal["no_active_workspace"]
    session_id: str


class ErrorWorkspaceUnavailable(TypedDict):
    error: Literal["workspace_unavailable"]
    workspace_id: str | None


class ErrorInvalidTarget(TypedDict):
    error: Literal["invalid_target"]
    allowed: list[str]


class ErrorInvalidIr(TypedDict):
    error: Literal["invalid_ir"]
    detail: str


class ErrorInvalidId(TypedDict):
    error: Literal["invalid_id"]
    detail: str


class ErrorGit(TypedDict):
    error: Literal["git_error"]
    detail: str


class ErrorNoArtifact(TypedDict):
    error: Literal["no_artifact"]
    detail: str


GetSessionResult = SessionRow | ErrorNotFound
SetActiveWorkspaceResult = SessionRow | ErrorNotFound
GetBuildStatusResult = TaskRow | ErrorTaskNotFound
GetWorkspaceResult = WorkspaceRow | ErrorWorkspaceNotFound
BuildPresentationResult = (
    BuildQueued
    | ErrorInvalidTarget
    | ErrorSessionNotFound
    | ErrorNoActiveWorkspace
    | ErrorWorkspaceUnavailable
)
DeployPresentationResult = (
    DeployQueued
    | ErrorSessionNotFound
    | ErrorNoActiveWorkspace
    | ErrorWorkspaceUnavailable
    | ErrorNoArtifact
)
CreateProjectResult = ProjectCreated | ErrorInvalidId | ErrorGit
CheckoutWorkspaceResult = CheckoutResult | ErrorSessionNotFound | ErrorInvalidId | ErrorGit
SaveIrResult = (
    IrSaved
    | ErrorSessionNotFound
    | ErrorNoActiveWorkspace
    | ErrorWorkspaceUnavailable
    | ErrorInvalidIr
)
CommitWorkspaceResult = (
    CommitResult
    | ErrorSessionNotFound
    | ErrorNoActiveWorkspace
    | ErrorWorkspaceUnavailable
    | ErrorGit
)
RemoveWorkspaceResult = WorkspaceRemoved | ErrorWorkspaceNotFound
