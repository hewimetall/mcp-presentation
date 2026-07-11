"""Smoke: init bare → worktree → commit via gix (no CLI)."""

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


def test_worktree_commit_roundtrip(tmp_path: Path) -> None:
    git = GitService()
    bare = git.init_bare(str(tmp_path / "demo.git"))
    wt = Path(git.add_worktree(bare, str(tmp_path / "wt"), "main"))
    (wt / "presentation.ir.json").write_text('{"title":"T","slides":[]}', encoding="utf-8")
    cid = git.commit(str(wt), "add ir", ["presentation.ir.json"])
    assert len(cid) >= 7
    wt2 = Path(git.add_worktree(bare, str(tmp_path / "wt2"), "main"))
    assert (wt2 / "presentation.ir.json").is_file()
