"""Smoke: init bare via gix (no CLI)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("mcp_git._native")

from mcp_git import GitService


def test_init_bare(tmp_path: Path) -> None:
    git = GitService()
    bare = tmp_path / "demo.git"
    path = git.init_bare(str(bare))
    assert Path(path).exists()
    assert (bare / "HEAD").exists() or (Path(path) / "HEAD").exists()
