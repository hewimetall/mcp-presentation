"""Bridge MCP/FastMCP background tasks ↔ durable SQLite TaskStore.

ADR-0003 still rejects Docket as the *build queue*. Docket/memory is only the
SEP-1686 wait + ``notifications/tasks/status`` layer. Durable state and the
BuildWorker stay on ``mcp_presentation._tasks.TaskStore``.
"""

from __future__ import annotations

import asyncio
import os
from typing import Protocol, cast

from mcp_presentation._tasks import TaskStore
from mcp_presentation.types import TaskRow

POLL_SECONDS = float(os.environ.get("MCP_TASK_BRIDGE_POLL_SECONDS", "0.25"))
TERMINAL = frozenset({"done", "error"})


class ProgressReporter(Protocol):
    async def set_message(self, message: str | None) -> None: ...


def _as_row(row: object) -> TaskRow:
    return cast(TaskRow, row)


def status_message(row: TaskRow) -> str:
    """Human status line that always carries our SQLite task_id."""
    tid = row["task_id"]
    status = row["status"]
    err = row.get("error")
    if status == "error" and err:
        return f"task_id={tid} status=error error={err}"
    artifact = row.get("artifact")
    if status == "done" and artifact:
        return f"task_id={tid} status=done artifact={artifact}"
    return f"task_id={tid} status={status}"


async def await_sqlite_task(
    tasks: TaskStore,
    task_id: str,
    progress: ProgressReporter | None = None,
    *,
    poll_seconds: float = POLL_SECONDS,
) -> TaskRow:
    """Poll SQLite until terminal status; mirror each change via Progress.

    Progress messages become ``notifications/tasks/status`` when the tool runs
    as an MCP background task (client ``task=True``).
    """
    last: str | None = None
    while True:
        raw = await asyncio.to_thread(tasks.get, task_id)
        if raw is None:
            msg = f"task_id={task_id} status=missing"
            if progress is not None:
                await progress.set_message(msg)
            raise LookupError(f"task not found: {task_id}")
        row = _as_row(raw)
        msg = status_message(row)
        if msg != last and progress is not None:
            await progress.set_message(msg)
            last = msg
        if row["status"] in TERMINAL:
            return row
        await asyncio.sleep(poll_seconds)
