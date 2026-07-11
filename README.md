# mcp-presentation

MCP-сервер для сборки презентаций (**PDF** / **web**) с task-based async pipeline.

## Пакеты

| Пакет | Что хранит | PyO3 |
|-------|------------|------|
| **`mcp-presentation`** (этот репо root) | задачи сборки → `state/tasks.db` | `mcp_presentation._tasks` |
| **`mcp-state`** ([`packages/mcp-state`](packages/mcp-state)) | сессии + workspaces → `state/sessions.db` | `mcp_state._native` |

Стек: **Python 3.14 · FastMCP · Rust/PyO3 · rusqlite · maturin**.

## ADR

→ [`docs/adr/`](docs/adr/README.md)

## Dev

```bash
uv venv -p 3.14 .venv && source .venv/bin/activate
# отдельный пакет state
(cd packages/mcp-state && maturin develop)
# tasks + MCP server
maturin develop
uv pip install -e packages/mcp-state
pytest -q packages/mcp-state/tests tests
```

## Состояние на диске

```text
state/tasks.db           # mcp-presentation TaskStore
state/sessions.db        # mcp-state StateStore
projects/<id>.git/       # git bare
workspaces/<ws_id>/      # git worktree checkout
```
