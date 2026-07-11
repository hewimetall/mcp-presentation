# ADR-0010: Separate mcp-state package for sessions and workspaces

- Status: Accepted
- Date: 2026-07-11
- Code: D21
- Deciders: product / architecture
- Relates: ADR-0004, ADR-0009

## Context

Сессии и workspaces должны быть persistent в embedded SQLite через Rust / PyO3
(как и задачи). Ранее рассматривалось расширение одного модуля `mcp_presentation._tasks`.

Требование: это **отдельный пакет**, не часть `mcp-presentation`.

## Decision

Выделить пакет **`mcp-state`** (`packages/mcp-state/`):

| | `mcp-presentation` | `mcp-state` |
|--|--------------------|-------------|
| Роль | MCP server + **TaskStore** | **Sessions + workspaces** |
| PyO3 module | `mcp_presentation._tasks` | `mcp_state._native` |
| SQLite file | `state/tasks.db` | `state/sessions.db` |
| Класс | `TaskStore` | `StateStore` |

`mcp-presentation` зависит от `mcp-state` (path/editable), FastMCP-tools вызывают оба.

`StateStore` API (минимум): `create_session`, `get_session`, `list_sessions`,
`create_workspace`, `get_workspace`, `list_workspaces`, `set_active_workspace`,
`mark_workspace_removed`.

Git worktree на диске — по-прежнему ADR-0009; `mcp-state` фиксирует **метаданные** в SQLite.

## Consequences

### Positive

- Чистое разделение ответственности и версионирования.
- Можно переиспользовать `mcp-state` вне MCP-сервера.
- Отдельная БД → меньше contention с очередью задач.

### Negative / risks

- Два maturin-пакета в monorepo (два `maturin develop`).
- Два файла SQLite вместо одного — осознанный trade-off изоляции.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Один PyO3-модуль на всё в `mcp-presentation` | Явно отклонено: нужен отдельный пакет |
| Одна общая SQLite на tasks+sessions | Возможна позже; v1 — раздельные DB-файлы per package |
