# mcp-presentation

MCP-сервер для сборки презентаций (**PDF** / **web**) с task-based async pipeline.

## Стек

- **Python 3.14** + **FastMCP** — MCP tools
- **Rust / PyO3** (`rusqlite`) — TaskStore, embedded SQLite (`state/tasks.db`)
- **maturin** — сборка native extension

## Решения

→ [`docs/architecture/DECISIONS.md`](docs/architecture/DECISIONS.md)

## Состояние на диске

```text
state/tasks.db           # SQLite: только через Rust TaskStore
projects/<id>.git/       # git bare — истина
workspaces/<ws_id>/      # git worktree checkout
```
