"""FastMCP entrypoint — thin wrappers over Rust TaskStore."""

from __future__ import annotations

import os
from pathlib import Path

from fastmcp import FastMCP

from mcp_presentation._tasks import TaskStore

STATE_DIR = Path(os.environ.get("MCP_PRESENTATION_STATE", "state"))
DB_PATH = STATE_DIR / "tasks.db"

mcp = FastMCP("mcp-presentation")
_store: TaskStore | None = None


def get_store() -> TaskStore:
    global _store
    if _store is None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _store = TaskStore(str(DB_PATH))
    return _store


@mcp.tool()
def build_presentation(session_id: str, workspace: str, target: str) -> dict:
    """Enqueue a presentation build (pdf|web). Returns task_id."""
    if target not in {"pdf", "web"}:
        return {"error": "invalid_target", "allowed": ["pdf", "web"]}
    tid = get_store().submit(session_id, workspace, target)
    return {"task_id": tid, "status": "queued"}


@mcp.tool()
def get_build_status(task_id: str) -> dict:
    """Read build task status from the Rust SQLite store."""
    row = get_store().get(task_id)
    if row is None:
        return {"error": "not_found", "task_id": task_id}
    return row


@mcp.tool()
def deploy_presentation(session_id: str, workspace: str, artifact: str = "") -> dict:
    """Enqueue deploy as a separate task (D18)."""
    tid = get_store().submit(session_id, workspace, "deploy")
    if artifact:
        get_store().update(tid, artifact=artifact)
    return {"task_id": tid, "status": "queued", "target": "deploy"}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
