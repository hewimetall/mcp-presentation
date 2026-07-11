"""Web engine — HTML / web-PDF / slide PNGs via web-builder image.

Every web target refreshes ``out/slides/slide.NNN.png`` inside the container.
"""

from __future__ import annotations

from pathlib import Path

from mcp_presentation.engines.runtime import (
    ContainerRunner,
    RunResult,
    as_run_result,
    host_user,
    require_exit_ok,
)
from mcp_presentation.ir_compile import ensure_web_source
from mcp_presentation.settings import CONTAINER_WORK, WEB_IMAGE, workspace_bind
from mcp_presentation.slide_image import require_slide_pngs


def _ensure_marp_or_web(workspace: Path) -> Path:
    src = ensure_web_source(workspace)
    if src is None:
        msg = "no web source or presentation.ir.json in workspace"
        raise ValueError(msg)
    return src


def _run(workspace: Path, runner: ContainerRunner, cmd: str) -> RunResult:
    workspace.mkdir(parents=True, exist_ok=True)
    raw = runner.run(
        WEB_IMAGE,
        [cmd],
        binds=[workspace_bind(workspace)],
        workdir=CONTAINER_WORK,
        auto_remove=True,
        user=host_user(),
    )
    result = as_run_result(raw)
    require_exit_ok(result, label=f"web/{cmd}")
    return result


def build_web(workspace: Path, runner: ContainerRunner) -> tuple[Path, str]:
    """Build static site → ``dist/`` and refresh slide PNGs. Returns (artifact, logs)."""
    _ensure_marp_or_web(workspace)
    result = _run(workspace, runner, "web")
    artifact = workspace / "dist"
    if not artifact.exists():
        msg = f"missing artifact {artifact}"
        raise RuntimeError(msg)
    require_slide_pngs(workspace)
    return artifact, str(result.get("logs", ""))


def build_web_pdf(workspace: Path, runner: ContainerRunner) -> tuple[Path, str]:
    """Build deck PDF → ``out/web.pdf`` and refresh slide PNGs. Returns (artifact, logs)."""
    _ensure_marp_or_web(workspace)
    result = _run(workspace, runner, "web-pdf")
    artifact = workspace / "out" / "web.pdf"
    if not artifact.is_file():
        msg = f"missing artifact {artifact}"
        raise RuntimeError(msg)
    require_slide_pngs(workspace)
    return artifact, str(result.get("logs", ""))


def build_slide_images(workspace: Path, runner: ContainerRunner) -> tuple[Path, str]:
    """Images-only refresh → ``out/slides/``. Returns (slides_dir, logs)."""
    _ensure_marp_or_web(workspace)
    result = _run(workspace, runner, "slide-image")
    return require_slide_pngs(workspace), str(result.get("logs", ""))
