"""LaTeX engine — PDF via latex-builder image."""

from __future__ import annotations

from pathlib import Path

from mcp_presentation.engines.runtime import ContainerRunner, as_run_result, require_exit_ok
from mcp_presentation.ir_compile import ensure_latex_source
from mcp_presentation.settings import CONTAINER_WORK, LATEX_IMAGE, workspace_bind


def build_pdf(workspace: Path, runner: ContainerRunner) -> Path:
    """Compile Beamer/LaTeX → ``out/main.pdf``. Returns artifact path."""
    workspace.mkdir(parents=True, exist_ok=True)
    src = ensure_latex_source(workspace)
    if src is None:
        msg = "no LaTeX source or presentation.ir.json in workspace"
        raise ValueError(msg)

    raw = runner.run(
        LATEX_IMAGE,
        ["pdf"],
        binds=[workspace_bind(workspace)],
        workdir=CONTAINER_WORK,
        auto_remove=True,
    )
    require_exit_ok(as_run_result(raw), label="latex/pdf")

    artifact = workspace / "out" / "main.pdf"
    if not artifact.is_file():
        msg = f"missing artifact {artifact}"
        raise RuntimeError(msg)
    return artifact
