# mcp-state

Отдельный пакет: **сессии и workspaces** в embedded SQLite через **Rust / PyO3**.

Не часть `mcp-presentation` — ставится и собирается отдельно (`maturin`), подключается как dependency.

```python
from mcp_state import StateStore

store = StateStore("state/sessions.db")
sid = store.create_session()
wid = store.create_workspace(project_id="p1", path="workspaces/ws1", ref_name="main")
store.set_active_workspace(sid, wid)
```

См. ADR-0010.
