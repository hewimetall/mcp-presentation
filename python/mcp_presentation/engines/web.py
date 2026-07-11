"""Web engine — HTML / web-PDF / slide PNGs via web-builder image."""

from __future__ import annotations

from pathlib import Path

from mcp_presentation.engines.runtime import ContainerRunner, as_run_result, require_exit_ok
from mcp_presentation.ir_compile import ensure_web_source
from mcp_presentation.settings import CONTAINER_WORK, WEB_IMAGE, workspace_bind


def _ensure_marp_or_web(workspace: Path) -> Path:
    src = ensure_web_source(workspace)
    if src is None:
        msg = "no web source or presentation.ir.json in workspace"
        raise ValueError(msg)
    return src


def _run(workspace: Path, runner: ContainerRunner, cmd: str) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    raw = runner.run(
        WEB_IMAGE,
        [cmd],
        binds=[workspace_bind(workspace)],
        workdir=CONTAINER_WORK,
        auto_remove=True,
    )
    require_exit_ok(as_run_result(raw), label=f"web/{cmd}")


def build_web(workspace: Path, runner: ContainerRunner) -> Path:
    """Build static site → ``dist/``."""
    _ensure_marp_or_web(workspace)
    _run(workspace, runner, "web")
    artifact = workspace / "dist"
    if not artifact.exists():
        msg = f"missing artifact {artifact}"
        raise RuntimeError(msg)
    return artifact


def build_web_pdf(workspace: Path, runner: ContainerRunner) -> Path:
    """Build deck PDF → ``out/web.pdf``."""
    _ensure_marp_or_web(workspace)
    _run(workspace, runner, "web-pdf")
    artifact = workspace / "out" / "web.pdf"
    if not artifact.is_file():
        msg = f"missing artifact {artifact}"
        raise RuntimeError(msg)
    return artifact


def build_slide_images(workspace: Path, runner: ContainerRunner) -> Path:
    """Export Marp pages → ``out/slides/slide.NNN.png``. Returns slides dir."""
    src = _ensure_marp_or_web(workspace)
    if src.name == "package.json" and not any(
        (workspace / n).is_file() for n in ("slides.md", "presentation.md", "index.md", "deck.md")
    ):
        msg = "slide images require Marp markdown (slides.md); npm-only projects unsupported"
        raise ValueError(msg)

    slides = workspace / "out" / "slides"
    if slides.exists():
        for old in slides.glob("slide.*.png"):
            old.unlink()
    slides.mkdir(parents=True, exist_ok=True)

    _run(workspace, runner, "slide-image")

    if not any(slides.glob("slide.*.png")):
        msg = "slide-image produced no PNG files under out/slides/"
        raise RuntimeError(msg)
    return slides
