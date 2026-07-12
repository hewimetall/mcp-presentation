"""Worker edge-case coverage (FakeRunner, no Docker)."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

pytest.importorskip("mcp_presentation._tasks")

import mcp_presentation.worker as worker_mod
from mcp_presentation._tasks import TaskStore
from mcp_presentation.engines import RunResult
from mcp_presentation.worker import BuildWorker, get_worker, wake_worker
from test_worker import FakeRunner


def test_start_daemon_idempotent_and_runner_prop(tmp_path: Path) -> None:
    store = TaskStore(str(tmp_path / "t.db"))
    runner = FakeRunner()
    worker = BuildWorker(store, runner, poll_seconds=0.05)
    worker.start_daemon()
    worker.start_daemon()
    assert worker.runner is runner
    worker.stop()
    time.sleep(0.05)


def test_loop_swallows_process_one_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    store = TaskStore(str(tmp_path / "t.db"))
    worker = BuildWorker(store, FakeRunner(), poll_seconds=0.05)

    def boom() -> bool:
        raise RuntimeError("iter fail")

    monkeypatch.setattr(worker, "process_one", boom)
    with caplog.at_level(logging.ERROR):
        worker.start_daemon()
        time.sleep(0.12)
        worker.stop()
    assert any("worker iteration failed" in r.message for r in caplog.records)


def test_missing_workspace_and_relative_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TaskStore(str(tmp_path / "t.db"))
    worker = BuildWorker(store, FakeRunner())
    tid = store.submit("s", "", "pdf")
    assert worker.process_one() is True
    row = store.get(tid)
    assert row is not None
    assert row["status"] == "error"
    assert "missing workspace" in (row["error"] or "")

    monkeypatch.chdir(tmp_path)
    ws = Path("rel-ws")
    ws.mkdir()
    (ws / "presentation.ir.json").write_text(
        '{"title":"T","slides":[{"title":"S"}]}',
        encoding="utf-8",
    )
    tid2 = store.submit("s", "rel-ws", "pdf")
    assert worker.process_one() is True
    assert store.get(tid2)["status"] == "done"


def test_unsupported_and_dead_else_branch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = TaskStore(str(tmp_path / "t.db"))
    worker = BuildWorker(store, FakeRunner())
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "presentation.ir.json").write_text('{"title":"T","slides":[]}', encoding="utf-8")

    tid = store.submit("s", str(ws), "weird")
    assert worker.process_one() is True
    assert "unsupported" in (store.get(tid)["error"] or "")

    monkeypatch.setattr(worker_mod, "BUILD_TARGETS", frozenset({"pdf", "web", "ghost"}))
    monkeypatch.setattr(worker_mod, "WEB_TARGETS", frozenset({"web"}))
    tid2 = store.submit("s", str(ws), "ghost")
    assert worker.process_one() is True
    assert store.get(tid2)["status"] == "error"


def test_build_pdf_missing_artifact(tmp_path: Path) -> None:
    store = TaskStore(str(tmp_path / "t.db"))
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "presentation.ir.json").write_text('{"title":"T","slides":[]}', encoding="utf-8")

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
        ) -> RunResult:
            result = super().run(image, cmd, binds, workdir, env, auto_remove, user)
            if binds:
                pdf = Path(binds[0].split(":", 1)[0]) / "out" / "main.pdf"
                if pdf.is_file():
                    pdf.unlink()
            return result

    worker = BuildWorker(store, NoPdf())
    tid = store.submit("s", str(ws), "pdf")
    assert worker.process_one() is True
    assert "missing artifact" in (store.get(tid)["error"] or "")


def test_deploy_fallback_and_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = TaskStore(str(tmp_path / "t.db"))
    worker = BuildWorker(store, FakeRunner())
    ws = tmp_path / "ws"
    ws.mkdir()

    tid = store.submit("s", str(ws), "deploy")
    assert worker.process_one() is True
    assert "no deployable" in (store.get(tid)["error"] or "")

    monkeypatch.chdir(tmp_path)
    rel = Path("reldep")
    rel.mkdir()
    pdf = rel / "out" / "main.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF")
    build_id = store.submit("s", "reldep", "pdf")
    store.update(build_id, status="done", artifact=str(pdf.resolve()))
    # Deploy with absolute path: find_latest_done(abs) misses, then
    # find_latest_done(task.workspace) also abs — seed a second done under abs path too.
    # Instead deploy with relative workspace so line 162 hits:
    tid2 = store.submit("s", "reldep", "deploy")
    # Force host resolve absolute inside _run_deploy by using absolute submit:
    # Claim via process_one — workspace "reldep" → resolved abs; first find uses abs (miss),
    # second find uses task workspace "reldep" (hit) → covers line 162.
    assert worker.process_one() is True
    row2 = store.get(tid2)
    assert row2["status"] == "done", row2.get("error")

    bad = tmp_path / "bad"
    bad.mkdir()
    tid3 = store.submit("s", str(bad), "deploy")
    store.update(tid3, artifact=str(tmp_path / "nope.pdf"))
    assert worker.process_one() is True
    assert store.get(tid3)["status"] == "error"

    art = tmp_path / "file.pdf"
    art.write_bytes(b"%PDF")
    tid4 = store.submit("s", str(bad), "deploy")
    store.update(tid4, artifact=str(art))

    def boom(_ws: Path, _art: Path) -> Any:
        raise OSError("copy failed")

    monkeypatch.setattr(worker_mod, "deploy_local", boom)
    assert worker.process_one() is True
    assert "copy failed" in (store.get(tid4)["error"] or "")


def test_get_worker_and_wake_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(worker_mod, "_worker", None)
    store = TaskStore(str(tmp_path / "t.db"))

    class FakeDocker:
        def run(self, *args: Any, **kwargs: Any) -> RunResult:
            raise AssertionError("should not run")

    fake_mod = MagicMock()
    fake_mod.DockerService = FakeDocker
    monkeypatch.setitem(__import__("sys").modules, "mcp_docker", fake_mod)

    w = get_worker(store, runner=None)
    assert isinstance(w, BuildWorker)
    w.stop()
    monkeypatch.setattr(worker_mod, "_worker", None)

    def boom(_tasks: TaskStore, runner: Any = None) -> BuildWorker:
        raise RuntimeError("no docker")

    monkeypatch.setattr(worker_mod, "get_worker", boom)
    with caplog.at_level(logging.ERROR):
        wake_worker(store)
    assert any("failed to start/wake" in r.message for r in caplog.records)
