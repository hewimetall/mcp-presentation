# mcp-presentation

MCP-сервер для сборки презентаций (**PDF** / **web**) с task-based async pipeline.

## Стек

- **Python 3.14**
- **FastMCP** — MCP tools
- **SQLAlchemy** + embedded **SQLite** — persistent task store (`state/tasks.db`)

## Решения

Архитектурные решения (IR, deploy, Docker, git worktree, отказ от Docket/Redis):  
→ [`docs/architecture/DECISIONS.md`](docs/architecture/DECISIONS.md)

## Состояние на диске

```text
state/tasks.db           # SQLite: задачи сборки
projects/<id>.git/       # git bare — истина
workspaces/<ws_id>/      # git worktree checkout
```
