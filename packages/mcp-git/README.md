# mcp-git

Отдельный пакет: **GitPort** + адаптер **gix** (без CLI, без push).

```python
from mcp_git import GitService

git = GitService()
git.init_bare("projects/demo.git")
git.add_worktree("projects/demo.git", "workspaces/ws1", ref="HEAD")
oid = git.commit("workspaces/ws1", "initial", paths=["presentation.ir.json"])
```

ADR-0011.
