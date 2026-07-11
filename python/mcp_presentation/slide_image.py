"""Read slide PNGs produced by web/pdf builds (no render)."""

from __future__ import annotations

import re
from pathlib import Path

_SLIDE_RE = re.compile(r"^slide\.(\d+)\.png$", re.IGNORECASE)


def slides_dir(workspace: Path) -> Path:
    return workspace / "out" / "slides"


def slide_png_path(workspace: Path, slide: int) -> Path:
    """Naming: slide.001.png (1-based)."""
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


def require_slide_pngs(workspace: Path) -> Path:
    """Assert out/slides/slide.*.png exist after a build. Returns slides dir."""
    root = slides_dir(workspace)
    pngs = list_slide_pngs(workspace)
    if not pngs:
        msg = f"missing slide PNGs under {root} (expected slide.001.png …)"
        raise RuntimeError(msg)
    return root


def get_slide_png(workspace: Path, slide: int) -> Path:
    """Return existing slide PNG (1-based). Does not build — artifacts must exist."""
    if slide < 1:
        msg = f"slide must be >= 1, got {slide}"
        raise ValueError(msg)

    available = slide_indices(workspace)
    if not available:
        msg = (
            "no slide images in out/slides/; "
            "run build_presentation(target='pdf'|'web'|'web-pdf') first"
        )
        raise FileNotFoundError(msg)

    path = slide_png_path(workspace, slide)
    if not path.is_file():
        msg = f"slide {slide} not found; available={available}"
        raise LookupError(msg)
    return path
