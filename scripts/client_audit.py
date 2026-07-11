#!/usr/bin/env python3
"""Act as a real FastMCP client against mcp-presentation (Docker builds)."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(tempfile.mkdtemp(prefix="mcp-client-audit-"))
STATE = ROOT / "state"
PROJECTS = ROOT / "projects"
WORKSPACES = ROOT / "workspaces"
for d in (STATE, PROJECTS, WORKSPACES):
    d.mkdir(parents=True)

os.environ["MCP_PRESENTATION_STATE"] = str(STATE)
os.environ["MCP_PRESENTATION_PROJECTS"] = str(PROJECTS)
os.environ["MCP_PRESENTATION_WORKSPACES"] = str(WORKSPACES)
# Keep waits short enough for a client session, long enough for Docker.
os.environ.setdefault("MCP_TASK_WAIT_TIMEOUT", "300")
os.environ.setdefault("MCP_TASK_BRIDGE_POLL_SECONDS", "0.5")

import mcp_presentation.paths as paths
import mcp_presentation.server as server

server.STATE_DIR = STATE
server.TASKS_DB = STATE / "tasks.db"
server.SESSIONS_DB = STATE / "sessions.db"
server._tasks = None
server._state = None
server._git = None
paths.PROJECTS_DIR = PROJECTS
paths.WORKSPACES_DIR = WORKSPACES

from fastmcp import Client

IR = {
    "schema_version": 1,
    "title": "Client audit deck",
    "author": "tester-client",
    "slides": [
        {"title": "Agenda", "bullets": ["Wait", "Slides", "Deploy"]},
        {"title": "Body", "body": "Content slide should be image index 2."},
    ],
}

IR_EDITED = {
    **IR,
    "slides": [
        {"title": "Agenda", "bullets": ["Wait", "Slides", "Deploy", "Rebuild"]},
        {"title": "Body", "body": "Edited — needs rebuild."},
        {"title": "Extra", "bullets": ["third content → image 4"]},
    ],
}


def _payload(result: Any) -> dict[str, Any]:
    data = getattr(result, "data", None)
    if data is not None and hasattr(data, "model_dump"):
        return dict(data.model_dump())
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        inner = structured.get("result", structured)
        if isinstance(inner, dict):
            return dict(inner)
    content = getattr(result, "content", None)
    if content:
        text = getattr(content[0], "text", None)
        if text:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
    raise AssertionError(f"cannot parse tool result: {result!r}")


def _ok(label: str, detail: str = "") -> None:
    print(f"PASS  {label}" + (f" — {detail}" if detail else ""))


def _fail(label: str, detail: str) -> None:
    print(f"FAIL  {label} — {detail}")
    raise SystemExit(1)


async def main() -> None:
    print(f"CLIENT ROOT={ROOT}")
    statuses: list[str] = []

    def on_status(status: Any) -> None:
        msg = getattr(status, "statusMessage", None)
        st = getattr(status, "status", None)
        line = f"{st}: {msg}"
        statuses.append(line)
        print(f"  NOTIFY  {line}")

    async with Client(server.mcp) as client:
        # --- session / project / checkout ---
        sess = _payload(await client.call_tool("create_session", {"meta": "client-audit"}))
        sid = sess["session_id"]
        _ok("create_session", sid)

        await client.call_tool("create_project", {"project_id": "audit"})
        co = _payload(
            await client.call_tool(
                "checkout_workspace",
                {"session_id": sid, "project_id": "audit"},
            )
        )
        if Path(co["path"]).name != co["workspace_id"]:
            _fail(
                "workspace_id == folder",
                f"id={co['workspace_id']!r} name={Path(co['path']).name!r}",
            )
        _ok("checkout_workspace", f"id={co['workspace_id']} path={co['path']}")

        # --- save IR: must warn rebuild ---
        saved = _payload(
            await client.call_tool(
                "save_presentation_ir",
                {"session_id": sid, "ir_json": json.dumps(IR)},
            )
        )
        if not saved.get("rebuild_required"):
            _fail("save IR rebuild_required", str(saved))
        if "stale" not in saved.get("note", "").lower() and "rebuild" not in saved.get(
            "note", ""
        ).lower():
            _fail("save IR note", str(saved))
        _ok("save_presentation_ir", saved["note"][:80])

        await client.call_tool(
            "commit_workspace",
            {
                "session_id": sid,
                "message": "add ir",
                "paths": "presentation.ir.json",
            },
        )
        _ok("commit_workspace")

        # --- build WITHOUT task=True: must WAIT (not return queued) ---
        print("CALL   build_presentation(web)  [no task=True — expect blocking wait]")
        built = await client.call_tool(
            "build_presentation",
            {"session_id": sid, "target": "web"},
        )
        build_row = _payload(built)
        if build_row.get("status") == "queued":
            _fail("build waits by default", "still returned queued — client would need poll")
        if build_row.get("status") != "done":
            _fail("build done", str(build_row))
        logs = build_row.get("logs") or ""
        if "container" not in logs and "fake-container" not in logs:
            # real docker should have --- container --- section
            if "--- container ---" not in logs:
                _fail("build logs include container output", repr(logs[:200]))
        _ok("build_presentation wait", f"task_id={build_row['task_id']} artifact={build_row.get('artifact')}")
        print(f"  LOGS  {logs[:300]!r}...")

        # --- get_slide_image: structured meta + image ---
        slide1 = await client.call_tool(
            "get_slide_image",
            {"session_id": sid, "slide": 1},
        )
        meta = _payload(slide1)
        for key in ("path", "available", "index_note", "slide"):
            if key not in meta:
                _fail(f"slide meta has {key}", str(meta))
        if meta["slide"] != 1:
            _fail("slide 1", str(meta))
        if "title" not in meta["index_note"].lower():
            _fail("index_note mentions title", meta["index_note"])
        has_image = any(getattr(c, "type", None) == "image" for c in (slide1.content or []))
        if not has_image:
            _fail("slide image content", str(slide1.content))
        _ok(
            "get_slide_image",
            f"slide=1 path={meta['path']} available={meta['available']} note={meta['index_note'][:60]}…",
        )

        slide2 = _payload(
            await client.call_tool(
                "get_slide_image",
                {"session_id": sid, "slide": 2},
            )
        )
        _ok("get_slide_image content index", f"slide=2 path={slide2['path']}")

        # --- edit IR → rebuild warning → rebuild grows slides ---
        saved2 = _payload(
            await client.call_tool(
                "save_presentation_ir",
                {"session_id": sid, "ir_json": json.dumps(IR_EDITED)},
            )
        )
        if not saved2.get("rebuild_required"):
            _fail("edit IR rebuild_required", str(saved2))
        _ok("edit IR warns rebuild", "rebuild_required=true")

        print("CALL   build_presentation(web, task=True)  [expect notifications + wait]")
        task = await client.call_tool(
            "build_presentation",
            {"session_id": sid, "target": "web"},
            task=True,
        )
        if getattr(task, "returned_immediately", False):
            _fail("task=True background", "returned immediately")
        task.on_status_change(on_status)
        rebuild = _payload(await asyncio.wait_for(task.result(), timeout=300))
        if rebuild.get("status") != "done":
            _fail("rebuild task result", str(rebuild))
        if not any("status=" in s for s in statuses):
            _fail("task status notifications", f"got {statuses!r}")
        _ok("build task=True + notifications", f"updates={len(statuses)}")

        slide4 = await client.call_tool(
            "get_slide_image",
            {"session_id": sid, "slide": 4},
        )
        meta4 = _payload(slide4)
        if 4 not in meta4.get("available", []):
            _fail("rebuild refreshed slides", str(meta4))
        _ok("slides after rebuild", f"available={meta4['available']}")

        # --- deploy: local_copy not URL ---
        print("CALL   deploy_presentation(task=True)")
        dep_task = await client.call_tool(
            "deploy_presentation",
            {"session_id": sid},
            task=True,
        )
        dep = _payload(await asyncio.wait_for(dep_task.result(), timeout=120))
        if dep.get("status") != "done":
            _fail("deploy done", str(dep))
        art = dep.get("artifact") or ""
        if not art or not Path(art).exists():
            _fail("deploy artifact on disk", str(dep))
        if art.startswith("http://") or art.startswith("https://"):
            _fail("deploy is not URL", art)
        dlogs = dep.get("logs") or ""
        if "local_copy" not in dlogs:
            _fail("deploy logs say local_copy", repr(dlogs))
        _ok("deploy_presentation local_copy", f"artifact={art}")

        # get_build_status still works for inspection (optional)
        status = _payload(
            await client.call_tool(
                "get_build_status",
                {"task_id": rebuild["task_id"]},
            )
        )
        _ok("get_build_status inspect-only", f"status={status['status']}")

    print()
    print("CLIENT AUDIT: ALL CHECKS PASSED")
    print(f"artifacts under {WORKSPACES}")


if __name__ == "__main__":
    asyncio.run(main())
