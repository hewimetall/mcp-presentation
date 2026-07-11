#!/usr/bin/env python3
"""Multiple Cursor-like FastMCP client runs — evaluate mcp-presentation UX."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastmcp import Client


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    ms: float = 0.0


@dataclass
class RunReport:
    name: str
    checks: list[Check] = field(default_factory=list)
    error: str | None = None

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.ok)

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if not c.ok)


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
    raise AssertionError(f"cannot parse: {type(result)} {result!r}")


def _isolate() -> Path:
    root = Path(tempfile.mkdtemp(prefix="mcp-cursor-client-"))
    state, projects, workspaces = root / "state", root / "projects", root / "workspaces"
    for d in (state, projects, workspaces):
        d.mkdir()
    os.environ["MCP_PRESENTATION_STATE"] = str(state)
    os.environ["MCP_PRESENTATION_PROJECTS"] = str(projects)
    os.environ["MCP_PRESENTATION_WORKSPACES"] = str(workspaces)
    os.environ["MCP_TASK_WAIT_TIMEOUT"] = "300"
    os.environ["MCP_TASK_BRIDGE_POLL_SECONDS"] = "0.4"

    import mcp_presentation.paths as paths
    import mcp_presentation.server as server
    import mcp_presentation.worker as worker_mod

    # Fresh process-wide singletons per run (same interpreter).
    server.STATE_DIR = state
    server.TASKS_DB = state / "tasks.db"
    server.SESSIONS_DB = state / "sessions.db"
    server._tasks = None
    server._state = None
    server._git = None
    paths.PROJECTS_DIR = projects
    paths.WORKSPACES_DIR = workspaces
    if worker_mod._worker is not None:
        try:
            worker_mod._worker.stop()
        except Exception:
            pass
        worker_mod._worker = None
    return root


async def _check(report: RunReport, name: str, coro: Any) -> Any:
    t0 = time.perf_counter()
    try:
        value = await coro
        report.checks.append(Check(name, True, ms=(time.perf_counter() - t0) * 1000))
        return value
    except Exception as exc:
        report.checks.append(
            Check(name, False, detail=str(exc), ms=(time.perf_counter() - t0) * 1000)
        )
        raise


def _expect(report: RunReport, name: str, cond: bool, detail: str = "") -> None:
    report.checks.append(Check(name, cond, detail=detail))
    if not cond:
        raise AssertionError(f"{name}: {detail}")


async def _bootstrap(client: Client, project: str, ir: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    sess = _payload(await client.call_tool("create_session", {"meta": "cursor-client"}))
    sid = sess["session_id"]
    await client.call_tool("create_project", {"project_id": project})
    co = _payload(
        await client.call_tool(
            "checkout_workspace",
            {"session_id": sid, "project_id": project},
        )
    )
    await client.call_tool(
        "save_presentation_ir",
        {"session_id": sid, "ir_json": json.dumps(ir)},
    )
    return sid, co


# --- Scenario runners (Cursor-agent style tool sequences) -------------------


async def run_web_happy(report: RunReport) -> None:
    """Cursor agent: make a web deck, peek slide 1, deploy."""
    import mcp_presentation.server as server

    root = _isolate()
    ir = {
        "title": "Web happy",
        "author": "cursor",
        "slides": [
            {"title": "One", "bullets": ["a", "b"]},
            {"title": "Two", "body": "hello"},
        ],
    }
    async with Client(server.mcp) as client:
        sid, co = await _check(report, "bootstrap", _bootstrap(client, "web-happy", ir))
        _expect(
            report,
            "workspace_id==folder",
            Path(co["path"]).name == co["workspace_id"],
            f"{co['workspace_id']} vs {Path(co['path']).name}",
        )
        saved = _payload(
            await client.call_tool(
                "save_presentation_ir",
                {"session_id": sid, "ir_json": json.dumps(ir)},
            )
        )
        _expect(report, "rebuild_required on save", bool(saved.get("rebuild_required")))

        t0 = time.perf_counter()
        built = _payload(
            await client.call_tool(
                "build_presentation",
                {"session_id": sid, "target": "web"},
            )
        )
        wait_ms = (time.perf_counter() - t0) * 1000
        _expect(
            report,
            "build waits (not queued)",
            built.get("status") == "done",
            str(built.get("status")),
        )
        _expect(
            report,
            "container logs present",
            "--- container ---" in (built.get("logs") or ""),
            repr((built.get("logs") or "")[:120]),
        )
        report.checks.append(Check("build latency", True, detail=f"{wait_ms:.0f}ms", ms=wait_ms))

        slide = await client.call_tool("get_slide_image", {"session_id": sid, "slide": 1})
        meta = _payload(slide)
        _expect(report, "slide JSON has path", "path" in meta and bool(meta["path"]))
        _expect(report, "slide JSON has available", isinstance(meta.get("available"), list))
        _expect(
            report,
            "index_note explains title",
            "title" in str(meta.get("index_note", "")).lower(),
            str(meta.get("index_note")),
        )
        _expect(
            report,
            "image content block",
            any(getattr(c, "type", None) == "image" for c in (slide.content or [])),
        )
        _expect(report, "slide1 is title (idx 1)", meta.get("slide") == 1 and 1 in meta["available"])

        dep = _payload(await client.call_tool("deploy_presentation", {"session_id": sid}))
        _expect(report, "deploy done", dep.get("status") == "done", str(dep))
        art = dep.get("artifact") or ""
        _expect(report, "deploy path exists", Path(art).exists(), art)
        _expect(report, "deploy not URL", not art.startswith("http"), art)
        _expect(
            report,
            "deploy local_copy in logs",
            "local_copy" in (dep.get("logs") or ""),
            repr(dep.get("logs")),
        )
    report.checks.append(Check("isolate root", True, detail=str(root)))


async def run_pdf_happy(report: RunReport) -> None:
    """Cursor agent: PDF target + slide images."""
    import mcp_presentation.server as server

    _isolate()
    ir = {
        "title": "PDF happy",
        "slides": [{"title": "S1", "bullets": ["x"]}],
    }
    async with Client(server.mcp) as client:
        sid, _ = await _check(report, "bootstrap", _bootstrap(client, "pdf-happy", ir))
        built = _payload(
            await client.call_tool(
                "build_presentation",
                {"session_id": sid, "target": "pdf"},
            )
        )
        _expect(report, "pdf done", built.get("status") == "done", str(built))
        _expect(
            report,
            "pdf artifact",
            bool(built.get("artifact")) and Path(str(built["artifact"])).is_file(),
            str(built.get("artifact")),
        )
        meta = _payload(
            await client.call_tool("get_slide_image", {"session_id": sid, "slide": 1})
        )
        _expect(report, "pdf slides available", len(meta.get("available") or []) >= 2, str(meta))


async def run_task_true_notifications(report: RunReport) -> None:
    """Cursor client with task=True — expect status push, then result."""
    import mcp_presentation.server as server

    _isolate()
    ir = {"title": "Tasks", "slides": [{"title": "A"}, {"title": "B"}]}
    notes: list[str] = []

    async with Client(server.mcp) as client:
        sid, _ = await _check(report, "bootstrap", _bootstrap(client, "tasks", ir))
        task = await client.call_tool(
            "build_presentation",
            {"session_id": sid, "target": "web"},
            task=True,
        )
        _expect(
            report,
            "not immediate",
            not getattr(task, "returned_immediately", True),
            f"immediate={getattr(task, 'returned_immediately', None)}",
        )

        def on_status(st: Any) -> None:
            msg = getattr(st, "statusMessage", None)
            if msg:
                notes.append(str(msg))

        task.on_status_change(on_status)
        row = _payload(await asyncio.wait_for(task.result(), timeout=300))
        _expect(report, "task result done", row.get("status") == "done", str(row))
        _expect(
            report,
            "got statusMessage with our task_id",
            any(row["task_id"] in n and "status=" in n for n in notes),
            f"notes={notes!r}",
        )
        _expect(
            report,
            "notification has no fat error dump",
            all("error=" not in n or len(n) < 300 for n in notes),
            f"notes={notes!r}",
        )


async def run_edit_rebuild_stale(report: RunReport) -> None:
    """Edit IR → must warn; rebuild must refresh available slides."""
    import mcp_presentation.server as server

    _isolate()
    ir1 = {"title": "Deck", "slides": [{"title": "A"}]}
    ir2 = {"title": "Deck", "slides": [{"title": "A"}, {"title": "B"}, {"title": "C"}]}
    async with Client(server.mcp) as client:
        sid, _ = await _check(report, "bootstrap", _bootstrap(client, "rebuild", ir1))
        await client.call_tool(
            "build_presentation",
            {"session_id": sid, "target": "web"},
        )
        before = _payload(
            await client.call_tool("get_slide_image", {"session_id": sid, "slide": 1})
        )
        saved = _payload(
            await client.call_tool(
                "save_presentation_ir",
                {"session_id": sid, "ir_json": json.dumps(ir2)},
            )
        )
        _expect(report, "warn after edit", bool(saved.get("rebuild_required")))
        # stale: available still old until rebuild
        stale = _payload(
            await client.call_tool("get_slide_image", {"session_id": sid, "slide": 1})
        )
        _expect(
            report,
            "slides stale until rebuild",
            stale.get("available") == before.get("available"),
            f"before={before.get('available')} stale={stale.get('available')}",
        )
        await client.call_tool(
            "build_presentation",
            {"session_id": sid, "target": "web"},
        )
        after = _payload(
            await client.call_tool("get_slide_image", {"session_id": sid, "slide": 1})
        )
        _expect(
            report,
            "slides grew after rebuild",
            len(after.get("available") or []) > len(before.get("available") or []),
            f"before={before.get('available')} after={after.get('available')}",
        )
        # title=1, 3 content → available 1..4
        _expect(report, "index 4 exists", 4 in (after.get("available") or []), str(after))


async def run_error_paths(report: RunReport) -> None:
    """Bad IR, missing slide, invalid target — client must get clear errors."""
    import mcp_presentation.server as server

    _isolate()
    ir = {"title": "Err", "slides": [{"title": "Only"}]}
    async with Client(server.mcp) as client:
        sid, _ = await _check(report, "bootstrap", _bootstrap(client, "errors", ir))

        bad = _payload(
            await client.call_tool(
                "save_presentation_ir",
                {"session_id": sid, "ir_json": '{"title":""}'},
            )
        )
        _expect(report, "invalid_ir error", bad.get("error") == "invalid_ir", str(bad))

        bad_tgt = _payload(
            await client.call_tool(
                "build_presentation",
                {"session_id": sid, "target": "nope"},
            )
        )
        _expect(
            report,
            "invalid_target error",
            bad_tgt.get("error") == "invalid_target",
            str(bad_tgt),
        )

        await client.call_tool(
            "build_presentation",
            {"session_id": sid, "target": "web"},
        )
        missing = _payload(
            await client.call_tool(
                "get_slide_image",
                {"session_id": sid, "slide": 99},
            )
        )
        _expect(
            report,
            "invalid_slide has available",
            missing.get("error") == "invalid_slide" and "available" in missing,
            str(missing),
        )

        # duplicate workspace_id
        co = _payload(
            await client.call_tool(
                "checkout_workspace",
                {
                    "session_id": sid,
                    "project_id": "errors",
                    "workspace_id": "dupedupid01",
                },
            )
        )
        dup = _payload(
            await client.call_tool(
                "checkout_workspace",
                {
                    "session_id": sid,
                    "project_id": "errors",
                    "workspace_id": "dupedupid01",
                },
            )
        )
        _expect(
            report,
            "workspace_exists on collision",
            dup.get("error") == "workspace_exists",
            f"first={co.get('workspace_id')} second={dup}",
        )


async def run_list_tools_contract(report: RunReport) -> None:
    """Like Cursor discovering tools — taskSupport and descriptions."""
    import mcp_presentation.server as server

    _isolate()
    async with Client(server.mcp) as client:
        tools = await client.list_tools()
        by_name = {t.name: t for t in tools}
        for needed in (
            "create_session",
            "checkout_workspace",
            "save_presentation_ir",
            "build_presentation",
            "get_slide_image",
            "deploy_presentation",
            "get_build_status",
        ):
            _expect(report, f"tool listed: {needed}", needed in by_name)

        build = by_name["build_presentation"]
        exec_meta = getattr(build, "execution", None)
        support = getattr(exec_meta, "taskSupport", None) if exec_meta else None
        _expect(
            report,
            "build taskSupport=optional",
            support == "optional" or str(support) == "optional",
            f"execution={exec_meta}",
        )
        desc = (build.description or "").lower()
        _expect(report, "build desc mentions wait", "wait" in desc, build.description or "")

        slide = by_name["get_slide_image"]
        sdesc = (slide.description or "").lower()
        _expect(
            report,
            "slide desc mentions title index",
            "title" in sdesc and ("1" in sdesc or "index" in sdesc),
            slide.description or "",
        )


SCENARIOS = [
    ("1. list_tools contract (Cursor discover)", run_list_tools_contract),
    ("2. web happy path", run_web_happy),
    ("3. pdf happy path", run_pdf_happy),
    ("4. task=True notifications", run_task_true_notifications),
    ("5. edit IR → stale → rebuild", run_edit_rebuild_stale),
    ("6. error paths", run_error_paths),
]


async def main() -> None:
    print("=" * 64)
    print("CURSOR-CLIENT EVALUATION — multiple runs")
    print("=" * 64)
    reports: list[RunReport] = []
    for name, fn in SCENARIOS:
        report = RunReport(name=name)
        print(f"\n>>> RUN: {name}")
        t0 = time.perf_counter()
        try:
            await fn(report)
        except Exception as exc:
            report.error = f"{exc}"
            if not report.checks or report.checks[-1].ok:
                report.checks.append(Check("scenario", False, detail=str(exc)))
            print(f"    ABORT: {exc}")
            traceback.print_exc(limit=2)
        elapsed = (time.perf_counter() - t0) * 1000
        for c in report.checks:
            mark = "PASS" if c.ok else "FAIL"
            extra = f" — {c.detail}" if c.detail else ""
            timing = f" ({c.ms:.0f}ms)" if c.ms else ""
            print(f"    {mark}  {c.name}{timing}{extra}")
        print(
            f"    —— {report.passed} passed / {report.failed} failed  ({elapsed:.0f}ms total)"
        )
        reports.append(report)

    print("\n" + "=" * 64)
    print("SCORECARD")
    print("=" * 64)
    total_p = sum(r.passed for r in reports)
    total_f = sum(r.failed for r in reports)
    for r in reports:
        status = "OK" if r.failed == 0 and r.error is None else "ISSUES"
        print(f"  [{status}] {r.name}: {r.passed}✓ {r.failed}✗")
    print(f"\nTOTAL: {total_p} passed, {total_f} failed across {len(reports)} runs")

    # Client UX verdict
    print("\n" + "=" * 64)
    print("CLIENT VERDICT (as Cursor MCP user)")
    print("=" * 64)
    if total_f == 0:
        print(
            "Usable: wait works without polling, slides return JSON+image,\n"
            "IR warns on rebuild, deploy is clearly local_copy, task=True notifies.\n"
            "Ready for Cursor-agent workflows."
        )
        raise SystemExit(0)
    print("Not fully ready — fix FAIL lines above before relying on Cursor client.")
    raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
