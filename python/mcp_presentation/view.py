"""Public HTTPS view URL helpers for built web presentations (ADR-0013)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, TypedDict


class ViewUrlOk(TypedDict):
    view_url: str
    workspace_id: str
    web_root: str
    public_base: str
    resource_uri: str
    note: str


class ErrorPublicBaseUnset(TypedDict):
    error: Literal["public_base_unset"]
    detail: str


class ErrorNoWebArtifact(TypedDict):
    error: Literal["no_web_artifact"]
    workspace_id: str
    detail: str


ViewUrlResult = ViewUrlOk | ErrorPublicBaseUnset | ErrorNoWebArtifact

VIEW_NOTE = (
    "Open view_url in a browser. Caddy should proxy /view/* to this server's HTTP "
    "custom route (not through vMCP). MCP resource presentation://{session}/view "
    "exposes the same metadata over resources/read."
)

PUBLIC_BASE_ENV = "MCP_PRESENTATION_PUBLIC_BASE"
VIEW_PREFIX = "/view"


def public_base() -> str | None:
    """HTTPS origin where Caddy fronts this process, e.g. https://slides.example.com."""
    raw = os.environ.get(PUBLIC_BASE_ENV, "").strip().rstrip("/")
    return raw or None


def resolve_web_root(host_workspace: Path) -> Path | None:
    """Prefer deployed web tree, else workspace dist/ with index.html."""
    ws = host_workspace.resolve()
    candidates = (
        ws / "out" / "deployed" / "dist",
        ws / "out" / "deployed",
        ws / "dist",
    )
    for root in candidates:
        if (root / "index.html").is_file():
            return root
    return None


def build_view_url(workspace_id: str, *, base: str | None = None) -> str | ErrorPublicBaseUnset:
    origin = base if base is not None else public_base()
    if not origin:
        err: ErrorPublicBaseUnset = {
            "error": "public_base_unset",
            "detail": (
                f"Set {PUBLIC_BASE_ENV} to the public HTTPS origin "
                "(e.g. https://slides.example.com) so tools can return an openable URL."
            ),
        }
        return err
    return f"{origin}{VIEW_PREFIX}/{workspace_id}/"


def view_url_for_workspace(
    workspace_id: str,
    host_workspace: Path,
    *,
    session_id: str | None = None,
) -> ViewUrlResult:
    """Return openable HTTPS URL + web_root, or a structured error."""
    url = build_view_url(workspace_id)
    if isinstance(url, dict):
        return url
    root = resolve_web_root(host_workspace)
    if root is None:
        missing: ErrorNoWebArtifact = {
            "error": "no_web_artifact",
            "workspace_id": workspace_id,
            "detail": (
                "No index.html under dist/ or out/deployed/. "
                "Call build_presentation(target='web') first (optional deploy)."
            ),
        }
        return missing
    resource_uri = (
        f"presentation://{session_id}/view"
        if session_id
        else f"presentation://workspace/{workspace_id}/view"
    )
    ok: ViewUrlOk = {
        "view_url": url,
        "workspace_id": workspace_id,
        "web_root": str(root),
        "public_base": public_base() or "",
        "resource_uri": resource_uri,
        "note": VIEW_NOTE,
    }
    return ok


def safe_file_under(root: Path, rel: str) -> Path | None:
    """Resolve rel under root; reject path escape. Empty → index.html."""
    cleaned = rel.strip().lstrip("/")
    if not cleaned or cleaned.endswith("/"):
        cleaned = f"{cleaned}index.html" if cleaned else "index.html"
    candidate = (root / cleaned).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate
