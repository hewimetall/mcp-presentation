"""Worker unit tests with a fake container runner (no Docker daemon)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("mcp_presentation._tasks")

from mcp_presentation._tasks import TaskStore
from mcp_presentation.engines import RunResult
from mcp_presentation.ir_compile import ensure_latex_source, ensure_web_source
from mcp_presentation.worker import BuildWorker

# 1x1 PNG
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeRunner:
    def __init__(self, status_code: int = 0) -> None:
        self.status_code = status_code
        self.calls: list[tuple[str, list[str], list[str]]] = []

    def run(
        self,
        image: str,
        cmd: list[str],
        binds: list[str] | None = None,
        workdir: str | None = None,
        env: list[str] | None = None,
        auto_remove: bool = True,
    ) -> RunResult:
        self.calls.append((image, cmd, list(binds or [])))
        if binds:
            host = binds[0].split(":", 1)[0]
            out = Path(host) / "out"
            out.mkdir(parents=True, exist_ok=True)
            if cmd == ["pdf"]:
                (out / "main.pdf").write_bytes(b"%PDF-fake")
            if cmd == ["web"]:
                dist = Path(host) / "dist"
                dist.mkdir(parents=True, exist_ok=True)
                (dist / "index.html").write_text("<html></html>", encoding="utf-8")
            if cmd == ["web-pdf"]:
                (out / "web.pdf").write_bytes(b"%PDF-web")
            if len(cmd) == 1 and cmd[0] in {"pdf", "web", "web-pdf", "slide-image"}:
                slides = out / "slides"
                if slides.exists():
                    for old in slides.glob("slide.*.png"):
                        old.unlink()
                slides.mkdir(parents=True, exist_ok=True)
                n = 2
                ir_path = Path(host) / "presentation.ir.json"
                if ir_path.is_file():
                    raw: object = json.loads(ir_path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        slides_raw = raw.get("slides")
                        if isinstance(slides_raw, list):
                            n = 1 + len(slides_raw)
                for i in range(1, n + 1):
                    (slides / f"slide.{i:03d}.png").write_bytes(TINY_PNG)
        return RunResult(
            status_code=self.status_code,
            logs="ok\n",
            container_id="fake",
        )


def test_ir_to_latex_and_marp(tmp_path: Path) -> None:
    ir = tmp_path / "presentation.ir.json"
    ir.write_text(
        '{"title":"Demo","author":"A","slides":[{"title":"One","bullets":["a","b"]}]}',
        encoding="utf-8",
    )
    tex = ensure_latex_source(tmp_path)
    assert tex is not None and tex.is_file()
    assert "beamer" in tex.read_text(encoding="utf-8")
    md = ensure_web_source(tmp_path)
    assert md is not None and md.name == "slides.md"


def test_worker_pdf_success(tmp_path: Path) -> None:
    db = tmp_path / "tasks.db"
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "presentation.ir.json").write_text(
        '{"title":"T","slides":[{"title":"S","bullets":["x"]}]}',
        encoding="utf-8",
    )
    store = TaskStore(str(db))
    runner = FakeRunner()
    worker = BuildWorker(store, runner, poll_seconds=0.1)
    tid = store.submit("s1", str(ws), "pdf")
    assert worker.process_one() is True
    row = store.get(tid)
    assert row is not None
    assert row["status"] == "done"
    assert row["artifact"] is not None
    assert Path(row["artifact"]).is_file()
    assert runner.calls[0][1] == ["pdf"]
    assert worker.process_one() is False


def test_worker_web_success(tmp_path: Path) -> None:
    db = tmp_path / "tasks.db"
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "presentation.ir.json").write_text(
        '{"title":"W","slides":[{"title":"S","body":"hi"}]}',
        encoding="utf-8",
    )
    store = TaskStore(str(db))
    runner = FakeRunner()
    worker = BuildWorker(store, runner)
    tid = store.submit("s1", str(ws), "web")
    assert worker.process_one() is True
    row = store.get(tid)
    assert row is not None
    assert row["status"] == "done"
    assert Path(row["artifact"]).is_dir()
    assert runner.calls[0][1] == ["web"]


def test_worker_missing_source(tmp_path: Path) -> None:
    db = tmp_path / "tasks.db"
    ws = tmp_path / "empty"
    ws.mkdir()
    store = TaskStore(str(db))
    runner = FakeRunner()
    worker = BuildWorker(store, runner)
    tid = store.submit("s1", str(ws), "pdf")
    assert worker.process_one() is True
    row = store.get(tid)
    assert row is not None
    assert row["status"] == "error"
    assert "no LaTeX" in (row["error"] or "")
    assert runner.calls == []


def test_worker_invalid_ir(tmp_path: Path) -> None:
    db = tmp_path / "tasks.db"
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "presentation.ir.json").write_text('{"title":""}', encoding="utf-8")
    store = TaskStore(str(db))
    runner = FakeRunner()
    worker = BuildWorker(store, runner)
    tid = store.submit("s1", str(ws), "pdf")
    assert worker.process_one() is True
    row = store.get(tid)
    assert row is not None
    assert row["status"] == "error"
    assert "invalid presentation IR" in (row["error"] or "")


def test_worker_deploy_local(tmp_path: Path) -> None:
    db = tmp_path / "tasks.db"
    ws = tmp_path / "ws"
    ws.mkdir()
    pdf = ws / "out" / "main.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF")
    store = TaskStore(str(db))
    # seed a done build so find_latest_done works without explicit artifact
    build_id = store.submit("s1", str(ws), "pdf")
    store.update(build_id, status="done", artifact=str(pdf))
    runner = FakeRunner()
    worker = BuildWorker(store, runner)
    tid = store.submit("s1", str(ws), "deploy")
    assert worker.process_one() is True
    row = store.get(tid)
    assert row is not None
    assert row["status"] == "done"
    assert row["artifact"] is not None
    assert Path(row["artifact"]).is_file()
    assert (ws / "out" / "deployed" / "manifest.json").is_file()
    assert runner.calls == []
