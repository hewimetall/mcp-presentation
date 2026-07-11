"""Render Marp slides to PNG and resolve a slide by 1-based index."""

from __future__ import annotations

import re
from pathlib import Path

from mcp_presentation.ir_compile import ensure_web_source
from mcp_presentation.settings import CONTAINER_WORK, WEB_IMAGE, workspace_bind
from mcp_presentation.worker import ContainerRunner, WorkerRunResult, _as_run_result

_SLIDE_RE = re.compile(r"^slide\.(\d+)\.png$", re.IGNORECASE)


def slides_dir(workspace: Path) -> Path:
    return workspace / "out" / "slides"


def slide_png_path(workspace: Path, slide: int) -> Path:
    """Marp naming: slide.001.png (1-based)."""
    return slides_dir(workspace) / f"slide.{slide:03d}.png"


def list_slide_pngs(workspace: Path) -> list[Path]:
    root = slides_dir(workspace)
    if not root.is_dir():
        return []
    found: list[tuple[int, Path]] = []
    for p in root.iterdir():
        m = _SLIDE_RE.match(p.name)
        if m and p.is_file():
            found.append((int(m.group(1)), p))
    found.sort(key=lambda t: t[0])
    return [p for _, p in found]


def slide_indices(workspace: Path) -> list[int]:
    out: list[int] = []
    for p in list_slide_pngs(workspace):
        m = _SLIDE_RE.match(p.name)
        if m:
            out.append(int(m.group(1)))
    return out


def render_slide_images(workspace: Path, runner: ContainerRunner) -> list[Path]:
    """Ensure Marp source exists, run web-builder slide-image, return PNG paths."""
    src = ensure_web_source(workspace)
    if src is None:
        msg = "no web source or presentation.ir.json in workspace"
        raise ValueError(msg)
    # package.json-only projects need slides.md for Marp image export
    if src.name == "package.json" and not any(
        (workspace / n).is_file() for n in ("slides.md", "presentation.md", "index.md", "deck.md")
    ):
        msg = "slide images require Marp markdown (slides.md); npm-only projects unsupported"
        raise ValueError(msg)

    out = slides_dir(workspace)
    if out.exists():
        for old in out.glob("slide.*.png"):
            old.unlink()
    out.mkdir(parents=True, exist_ok=True)

    raw = runner.run(
        WEB_IMAGE,
        ["slide-image"],
        binds=[workspace_bind(workspace)],
        workdir=CONTAINER_WORK,
        auto_remove=True,
    )
    result: WorkerRunResult = _as_run_result(raw)
    code = int(result.get("status_code", -1))
    if code != 0:
        logs = str(result.get("logs", ""))
        msg = f"slide-image container exit {code}: {logs}"
        raise RuntimeError(msg)

    pngs = list_slide_pngs(workspace)
    if not pngs:
        msg = "slide-image produced no PNG files under out/slides/"
        raise RuntimeError(msg)
    return pngs


def resolve_slide_png(
    workspace: Path,
    slide: int,
    runner: ContainerRunner,
    *,
    force: bool = False,
) -> Path:
    """Return path to slide PNG (1-based). Renders if missing or force=True."""
    if slide < 1:
        msg = f"slide must be >= 1, got {slide}"
        raise ValueError(msg)

    existing = list_slide_pngs(workspace)
    if force or not existing:
        existing = render_slide_images(workspace, runner)

    path = slide_png_path(workspace, slide)
    if not path.is_file():
        available = slide_indices(workspace)
        msg = f"slide {slide} not found; available={available}"
        raise LookupError(msg)
    return path
