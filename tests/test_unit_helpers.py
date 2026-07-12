"""Unit coverage for helpers: settings, deploy, engines, IR, paths, slides, bridge."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from mcp_presentation.deploy import deploy_local
from mcp_presentation.engines import run_web_target
from mcp_presentation.engines.runtime import as_run_result, host_user, require_exit_ok
from mcp_presentation.engines.web import build_slide_images, build_web, build_web_pdf
from mcp_presentation.ir_compile import (
    ensure_latex_source,
    ensure_web_source,
    load_ir,
    write_ir,
)
from mcp_presentation.ir_models import IrSlide, PresentationIr, ir_json_schema, validate_ir_obj
from mcp_presentation.paths import require_safe_id
from mcp_presentation.settings import artifact_for_target, workspace_bind
from mcp_presentation.slide_image import get_slide_png, require_slide_pngs
from mcp_presentation.task_bridge import await_sqlite_task, status_message
from test_worker import TINY_PNG, FakeRunner


def test_artifact_for_target_all_branches(tmp_path: Path) -> None:
    assert artifact_for_target(tmp_path, "pdf") == tmp_path / "out" / "main.pdf"
    assert artifact_for_target(tmp_path, "web") == tmp_path / "dist"
    assert artifact_for_target(tmp_path, "web-pdf") == tmp_path / "out" / "web.pdf"
    assert artifact_for_target(tmp_path, "slide-image") == tmp_path / "out" / "slides"
    assert artifact_for_target(tmp_path, "deploy") == tmp_path / "out" / "deployed"
    assert artifact_for_target(tmp_path, "other") == tmp_path / "out" / "unknown"
    assert ":" in workspace_bind(tmp_path)
    assert ":" in host_user()


def test_deploy_local_missing_and_dir_and_replace(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    with pytest.raises(FileNotFoundError):
        deploy_local(ws, tmp_path / "missing.bin")

    dest = ws / "out" / "deployed"
    dest.mkdir(parents=True)
    (dest / "old.txt").write_text("old", encoding="utf-8")

    src_dir = tmp_path / "dist"
    src_dir.mkdir()
    (src_dir / "index.html").write_text("ok", encoding="utf-8")
    result = deploy_local(ws, src_dir)
    assert result["deploy_kind"] == "local_copy"
    assert Path(result["deployed_path"]).is_dir()
    assert not (dest / "old.txt").exists()


def test_runtime_as_run_result_and_require_exit() -> None:
    with pytest.raises(TypeError):
        as_run_result("not-a-dict")
    ok = as_run_result({"status_code": None, "logs": None, "container_id": None})
    assert ok["status_code"] == -1
    with pytest.raises(RuntimeError, match="exit 7"):
        require_exit_ok({"status_code": 7, "logs": "boom"}, label="x")


def test_run_web_target_dispatch(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "presentation.ir.json").write_text(
        '{"title":"T","slides":[{"title":"S"}]}',
        encoding="utf-8",
    )
    runner = FakeRunner()
    art, _logs = run_web_target(ws, "web-pdf", runner)
    assert art.name == "web.pdf"
    art2, _ = run_web_target(ws, "slide-image", runner)
    assert art2.name == "slides"
    with pytest.raises(ValueError, match="unsupported"):
        run_web_target(ws, "nope", runner)


def test_web_engine_error_paths(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="no web source"):
        build_web(empty, FakeRunner())

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "presentation.ir.json").write_text('{"title":"T","slides":[]}', encoding="utf-8")

    class NoDist(FakeRunner):
        def run(
            self,
            image: str,
            cmd: list[str],
            binds: list[str] | None = None,
            workdir: str | None = None,
            env: list[str] | None = None,
            auto_remove: bool = True,
            user: str | None = None,
        ) -> Any:
            result = super().run(image, cmd, binds, workdir, env, auto_remove, user)
            if binds:
                dist = Path(binds[0].split(":", 1)[0]) / "dist"
                if dist.is_dir():
                    for p in dist.iterdir():
                        p.unlink()
                    dist.rmdir()
            return result

    with pytest.raises(RuntimeError, match="missing artifact"):
        build_web(ws, NoDist())

    class NoPdf(FakeRunner):
        def run(
            self,
            image: str,
            cmd: list[str],
            binds: list[str] | None = None,
            workdir: str | None = None,
            env: list[str] | None = None,
            auto_remove: bool = True,
            user: str | None = None,
        ) -> Any:
            result = super().run(image, cmd, binds, workdir, env, auto_remove, user)
            if binds:
                pdf = Path(binds[0].split(":", 1)[0]) / "out" / "web.pdf"
                if pdf.is_file():
                    pdf.unlink()
            return result

    with pytest.raises(RuntimeError, match="missing artifact"):
        build_web_pdf(ws, NoPdf())

    build_slide_images(ws, FakeRunner())


def test_ir_compile_fallbacks_and_rich_ir(tmp_path: Path) -> None:
    assert ensure_latex_source(tmp_path) is None
    assert ensure_web_source(tmp_path) is None

    tex = tmp_path / "presentation.tex"
    tex.write_text("% tex", encoding="utf-8")
    assert ensure_latex_source(tmp_path) == tex

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "package.json").write_text("{}", encoding="utf-8")
    assert ensure_web_source(pkg) == pkg / "package.json"

    md_ws = tmp_path / "md"
    md_ws.mkdir()
    deck = md_ws / "deck.md"
    deck.write_text("# hi", encoding="utf-8")
    assert ensure_web_source(md_ws) == deck

    ir = PresentationIr(
        title="T&A",
        author="A",
        theme="dark",
        language="ru",
        slides=[],
    )
    write_ir(tmp_path / "empty-ir", ir)
    loaded = load_ir(tmp_path / "empty-ir")
    assert loaded is not None
    tex_out = ensure_latex_source(tmp_path / "empty-ir")
    assert tex_out is not None
    body = tex_out.read_text(encoding="utf-8")
    assert "theme hint" in body
    assert "Empty" in body
    assert "russian" in body

    rich = PresentationIr(
        title="Rich",
        author="Auth",
        theme="gaia",
        slides=[
            IrSlide(title="S1", bullets=["b"], body="Body text", notes="Note me"),
        ],
    )
    ws = tmp_path / "rich"
    write_ir(ws, rich)
    tex2 = ensure_latex_source(ws)
    assert tex2 is not None
    t = tex2.read_text(encoding="utf-8")
    assert "Body text" in t
    assert r"\note{" in t
    md = ensure_web_source(ws)
    assert md is not None
    m = md.read_text(encoding="utf-8")
    assert "theme: gaia" in m
    assert "notes: Note me" in m

    schema = ir_json_schema()
    assert "properties" in schema
    with pytest.raises(ValueError):
        validate_ir_obj({"title": ""})


def test_paths_and_slide_helpers(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid"):
        require_safe_id("../evil", kind="project_id")
    with pytest.raises(RuntimeError, match="missing slide"):
        require_slide_pngs(tmp_path)
    with pytest.raises(ValueError, match="slide must be"):
        get_slide_png(tmp_path, 0)
    slides = tmp_path / "out" / "slides"
    slides.mkdir(parents=True)
    (slides / "slide.001.png").write_bytes(TINY_PNG)
    assert require_slide_pngs(tmp_path) == slides


def test_task_bridge_error_truncation_and_progress(tmp_path: Path) -> None:
    pytest.importorskip("mcp_presentation._tasks")
    from mcp_presentation import task_bridge as tb
    from mcp_presentation._tasks import TaskStore

    assert tb._short_error("short") == "short"
    long_err = ("word " * 80).strip()
    truncated = tb._short_error(long_err)
    assert truncated.endswith("...")
    assert len(truncated) == tb._STATUS_ERROR_MAX

    row = {
        "task_id": "t1",
        "status": "error",
        "error": long_err,
        "session_id": "s",
        "workspace": "/w",
        "target": "web",
        "artifact": None,
        "logs": None,
        "created_at": 0,
        "updated_at": 0,
    }
    msg = status_message(row)  # type: ignore[arg-type]
    assert "status=error" in msg
    assert "..." in msg

    store = TaskStore(str(tmp_path / "t.db"))

    class Prog:
        def __init__(self) -> None:
            self.msgs: list[str | None] = []

        async def set_message(self, message: str | None) -> None:
            self.msgs.append(message)

    prog = Prog()
    with pytest.raises(LookupError):
        asyncio.run(await_sqlite_task(store, "missing-id", prog, poll_seconds=0.01))
    assert prog.msgs and "missing" in (prog.msgs[0] or "")
