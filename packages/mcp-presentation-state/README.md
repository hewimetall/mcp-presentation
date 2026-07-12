# mcp-presentation-state

PyPI: **`mcp-presentation-state`** · import: `mcp_state`

Persistent sessions and workspaces (Rust / PyO3 + embedded SQLite).

```bash
# from repo root (uv workspace)
uv sync
# or
(cd packages/mcp-presentation-state && maturin develop)
```

```python
from mcp_state import StateStore

store = StateStore("state/sessions.db")
sid = store.create_session(meta='{"client":"demo"}')
wid = store.create_workspace(project_id="p1", path="workspaces/ws1", ref_name="main")
store.set_active_workspace(sid, wid)
```
