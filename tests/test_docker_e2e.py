"""Real Docker e2e: web/pdf builds emit artifacts + slide PNGs.

Requires Docker daemon and pre-built images:
  make docker-build
Skip automatically when the socket / images are missing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("mcp_presentation._tasks")
pytest.importorskip("mcp_docker._native")
pytest.importorskip("mcp_git._native")

from mcp_docker import DockerService
from mcp_presentation._tasks import TaskStore
from mcp_presentation.engines import build_web
from mcp_presentation.ir_compile import write_ir
from mcp_presentation.ir_models import IrSlide, PresentationIr
from mcp_presentation.slide_image import get_slide_png, slide_indices
from mcp_presentation.worker import BuildWorker


def _docker_ready() -> bool:
    sock = Path("/var/run/docker.sock")
    if not sock.exists():
        return False
    try:
        DockerService()
    except Exception:
        return False
    return True


def _image_present(name: str) -> bool:
    import subprocess

    r = subprocess.run(
        ["docker", "image", "inspect", name],
        capture_output=True,
        check=False,
    )
    return r.returncode == 0


pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(not _docker_ready(), reason="Docker daemon not available"),
]


@pytest.fixture
def runner() -> DockerService:
    return DockerService()


@pytest.fixture
def demo_ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    write_ir(
        ws,
        PresentationIr(
            title="E2E Demo",
            author="docker-test",
            slides=[
                IrSlide(title="One", bullets=["alpha", "beta"]),
                IrSlide(title="Two", body="hello from IR"),
            ],
        ),
    )
    return ws


def test_docker_web_emits_dist_and_slides(demo_ws: Path, runner: DockerService) -> None:
    if not _image_present("mcp-presentation/web-builder:latest"):
        pytest.skip("web-builder image missing; run make docker-build")
    artifact, _logs = build_web(demo_ws, runner)
    assert artifact.is_dir()
    assert (artifact / "index.html").is_file()
    idxs = slide_indices(demo_ws)
    assert idxs == [1, 2, 3]  # title + 2 content
    assert get_slide_png(demo_ws, 1).is_file()
    assert get_slide_png(demo_ws, 3).stat().st_size > 100


def test_docker_web_rebuild_refreshes_slides(demo_ws: Path, runner: DockerService) -> None:
    if not _image_present("mcp-presentation/web-builder:latest"):
        pytest.skip("web-builder image missing; run make docker-build")
    build_web(demo_ws, runner)
    assert slide_indices(demo_ws) == [1, 2, 3]
    # plant a stale high-index file (host-owned after user=uid:gid runs)
    stale = demo_ws / "out" / "slides" / "slide.099.png"
    stale.write_bytes(b"stale")
    write_ir(
        demo_ws,
        PresentationIr(
            title="E2E Demo",
            slides=[
                IrSlide(title="One"),
                IrSlide(title="Two"),
                IrSlide(title="Three"),
            ],
        ),
    )
    build_web(demo_ws, runner)
    assert not stale.exists()
    assert slide_indices(demo_ws) == [1, 2, 3, 4]


def test_docker_pdf_emits_pdf_and_slides(demo_ws: Path, runner: DockerService) -> None:
    if not _image_present("mcp-presentation/latex-builder:latest"):
        pytest.skip("latex-builder image missing; run make docker-build")
    store = TaskStore(str(demo_ws.parent / "tasks.db"))
    worker = BuildWorker(store, runner)
    tid = store.submit("e2e", str(demo_ws), "pdf")
    assert worker.process_one() is True
    row = store.get(tid)
    assert row is not None
    assert row["status"] == "done", row
    pdf = Path(row["artifact"])
    assert pdf.is_file()
    assert pdf.stat().st_size > 1000
    assert slide_indices(demo_ws)
    assert get_slide_png(demo_ws, 1).stat().st_size > 100
