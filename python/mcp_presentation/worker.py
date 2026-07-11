"""Background build worker: claim_next → build / deploy → status."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import cast

from mcp_presentation._tasks import TaskStore
from mcp_presentation.deploy import deploy_local
from mcp_presentation.engines import ContainerRunner, run_web_target
from mcp_presentation.engines.runtime import as_run_result, host_user, require_exit_ok
from mcp_presentation.ir_compile import ensure_latex_source, load_ir
from mcp_presentation.settings import (
    BUILD_TARGETS,
    CONTAINER_WORK,
    LATEX_IMAGE,
    workspace_bind,
)
from mcp_presentation.slide_image import require_slide_pngs
from mcp_presentation.types import TaskRow

logger = logging.getLogger(__name__)

POLL_SECONDS = float(os.environ.get("MCP_WORKER_POLL_SECONDS", "1.0"))
WEB_TARGETS = frozenset({"web", "web-pdf", "slide-image"})


def _as_task(row: object) -> TaskRow:
    return cast(TaskRow, row)


class BuildWorker:
    """Poll TaskStore, run builds or local deploy, write status back."""

    def __init__(
        self,
        tasks: TaskStore,
        runner: ContainerRunner,
        *,
        poll_seconds: float = POLL_SECONDS,
    ) -> None:
        self._tasks = tasks
        self._runner = runner
        self._poll = poll_seconds
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def wake(self) -> None:
        self._wake.set()

    def start_daemon(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="mcp-build-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def process_one(self) -> bool:
        """Claim and run at most one task. Returns True if work was claimed."""
        claimed = self._tasks.claim_next()
        if claimed is None:
            return False
        task = _as_task(claimed)
        self._run_task(task)
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                worked = self.process_one()
            except Exception:
                logger.exception("worker iteration failed")
                worked = False
            if worked:
                continue
            self._wake.wait(timeout=self._poll)
            self._wake.clear()

    def _run_task(self, task: TaskRow) -> None:
        tid = task["task_id"]
        target = task["target"]
        ws = task.get("workspace")
        if not ws:
            self._tasks.update(tid, status="error", error="missing workspace path")
            return
        host_ws = Path(ws)
        if not host_ws.is_absolute():
            host_ws = (Path.cwd() / host_ws).resolve()
        else:
            host_ws = host_ws.resolve()

        if target == "deploy":
            self._run_deploy(tid, task, host_ws)
            return

        if target not in BUILD_TARGETS:
            self._tasks.update(tid, status="error", error=f"unsupported target: {target}")
            return

        try:
            if (host_ws / "presentation.ir.json").is_file():
                load_ir(host_ws)
            self._tasks.update(tid, logs=f"build target={target}\n")
            if target in WEB_TARGETS:
                artifact = run_web_target(host_ws, target, self._runner)
            elif target == "pdf":
                artifact = self._build_pdf(host_ws)
            else:
                msg = f"unsupported target: {target}"
                raise ValueError(msg)
        except Exception as exc:
            self._tasks.update(tid, status="error", error=str(exc), logs=str(exc))
            return

        self._tasks.update(
            tid,
            status="done",
            artifact=str(artifact),
        )

    def _build_pdf(self, host_ws: Path) -> Path:
        """LaTeX PDF path stays in the worker (no separate latex engine module)."""
        host_ws.mkdir(parents=True, exist_ok=True)
        src = ensure_latex_source(host_ws)
        if src is None:
            msg = "no LaTeX source or presentation.ir.json in workspace"
            raise ValueError(msg)
        raw = self._runner.run(
            LATEX_IMAGE,
            ["pdf"],
            binds=[workspace_bind(host_ws)],
            workdir=CONTAINER_WORK,
            auto_remove=True,
            user=host_user(),
        )
        require_exit_ok(as_run_result(raw), label="pdf")
        artifact = host_ws / "out" / "main.pdf"
        if not artifact.is_file():
            msg = f"missing artifact {artifact}"
            raise RuntimeError(msg)
        require_slide_pngs(host_ws)
        return artifact

    def _run_deploy(self, tid: str, task: TaskRow, host_ws: Path) -> None:
        artifact_s = task.get("artifact")
        artifact: Path | None = Path(artifact_s) if artifact_s else None
        if artifact is None or not artifact.exists():
            latest = self._tasks.find_latest_done(str(host_ws))
            if latest is None:
                latest = self._tasks.find_latest_done(task.get("workspace") or "")
            if latest is not None:
                latest_t = _as_task(latest)
                art = latest_t.get("artifact")
                if art:
                    artifact = Path(art)
        if artifact is None or not artifact.exists():
            self._tasks.update(
                tid,
                status="error",
                error="no deployable artifact (pass artifact= or build first)",
            )
            return
        try:
            result = deploy_local(host_ws, artifact)
        except Exception as exc:
            self._tasks.update(tid, status="error", error=str(exc))
            return
        self._tasks.update(
            tid,
            status="done",
            artifact=result["deployed_path"],
            logs=f"deployed {result['source']} → {result['deployed_path']}\n",
        )

    @property
    def runner(self) -> ContainerRunner:
        return self._runner


_worker: BuildWorker | None = None
_worker_lock = threading.Lock()


def get_worker(tasks: TaskStore, runner: ContainerRunner | None = None) -> BuildWorker:
    """Process-wide daemon worker (lazy)."""
    global _worker
    with _worker_lock:
        if _worker is None:
            if runner is None:
                from mcp_docker import DockerService

                runner = DockerService()
            _worker = BuildWorker(tasks, runner)
            _worker.start_daemon()
        return _worker


def wake_worker(tasks: TaskStore) -> None:
    """Ensure worker is running and nudge it after enqueue."""
    try:
        get_worker(tasks).wake()
    except Exception:
        logger.exception("failed to start/wake build worker")
