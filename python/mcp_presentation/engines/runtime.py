"""Shared container runner contract for engine builds."""

from __future__ import annotations

import os
from typing import Protocol


class ContainerRunner(Protocol):
    def run(
        self,
        image: str,
        cmd: list[str],
        binds: list[str] | None = None,
        workdir: str | None = None,
        env: list[str] | None = None,
        auto_remove: bool = True,
        user: str | None = None,
    ) -> object: ...


class RunResult(dict[str, str | int]):
    """Mapping returned by adapters / fakes: status_code, logs, container_id."""


def host_user() -> str:
    """uid:gid so bind-mounted build outputs stay host-writable."""
    return f"{os.getuid()}:{os.getgid()}"


def as_run_result(raw: object) -> RunResult:
    if not isinstance(raw, dict):
        msg = "container runner must return a mapping"
        raise TypeError(msg)
    status = raw.get("status_code", -1)
    logs = raw.get("logs", "")
    cid = raw.get("container_id", "")
    return RunResult(
        status_code=int(status) if status is not None else -1,
        logs=str(logs),
        container_id=str(cid),
    )


def require_exit_ok(result: RunResult, *, label: str) -> None:
    code = int(result.get("status_code", -1))
    if code != 0:
        logs = str(result.get("logs", ""))
        msg = f"{label} container exit {code}: {logs}"
        raise RuntimeError(msg)
