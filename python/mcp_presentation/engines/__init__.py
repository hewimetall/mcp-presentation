"""Build engines: latex (PDF) and web (HTML / web-pdf / slide PNGs)."""

from __future__ import annotations

from pathlib import Path

from mcp_presentation.engines import latex, web
from mcp_presentation.engines.runtime import ContainerRunner, RunResult

__all__ = [
    "ContainerRunner",
    "RunResult",
    "build_pdf",
    "build_slide_images",
    "build_web",
    "build_web_pdf",
    "run_target",
]

build_pdf = latex.build_pdf
build_web = web.build_web
build_web_pdf = web.build_web_pdf
build_slide_images = web.build_slide_images


def run_target(workspace: Path, target: str, runner: ContainerRunner) -> Path:
    """Dispatch a build target to the matching engine function."""
    if target == "pdf":
        return build_pdf(workspace, runner)
    if target == "web":
        return build_web(workspace, runner)
    if target == "web-pdf":
        return build_web_pdf(workspace, runner)
    if target == "slide-image":
        return build_slide_images(workspace, runner)
    msg = f"unsupported target: {target}"
    raise ValueError(msg)
