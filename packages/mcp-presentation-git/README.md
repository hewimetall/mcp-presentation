# mcp-presentation-git

PyPI: **`mcp-presentation-git`** · import: `mcp_git`

GitPort + **gix** adapter — bare repo, worktree, commit. No `git` CLI, no push.

```bash
(cd packages/mcp-presentation-git && maturin develop)
```

```python
from mcp_git import GitService

git = GitService()
bare = git.init_bare("projects/demo.git")
wt = git.add_worktree(bare, "workspaces/ws1", "main")
```
