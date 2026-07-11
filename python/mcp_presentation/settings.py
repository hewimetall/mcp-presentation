"""Build image tags and workspace paths for the container worker."""

from __future__ import annotations

import os
from pathlib import Path

LATEX_IMAGE = os.environ.get("MCP_LATEX_IMAGE", "mcp-presentation/latex-builder:latest")
WEB_IMAGE = os.environ.get("MCP_WEB_IMAGE", "mcp-presentation/web-builder:latest")

CONTAINER_WORK = "/work"

BUILD_TARGETS = frozenset({"pdf", "web", "web-pdf", "slide-image"})


def workspace_bind(host_workspace: Path) -> str:
    """Absolute host path → bollard bind `host:container`."""
    abs_host = host_workspace.resolve()
    return f"{abs_host}:{CONTAINER_WORK}"


def artifact_for_target(host_workspace: Path, target: str) -> Path:
    if target == "pdf":
        return host_workspace / "out" / "main.pdf"
    if target == "web":
        return host_workspace / "dist"
    if target == "web-pdf":
        return host_workspace / "out" / "web.pdf"
    if target == "slide-image":
        return host_workspace / "out" / "slides"
    if target == "deploy":
        return host_workspace / "out" / "deployed"
    return host_workspace / "out" / "unknown"
