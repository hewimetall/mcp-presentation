# ADR-0003: Reject FastMCP Docket for build queue

- Status: Accepted (amended)
- Date: 2026-07-11
- Amended: 2026-07-11
- Code: D3.2
- Deciders: product / architecture
- Relates: ADR-0001, ADR-0002, ADR-0004

## Context

FastMCP ≥ 2.14 имеет protocol-native background tasks (`task=True`) на базе **Docket**.
Кажется естественным для ADR-0001, но backends Docket ограничены.

| Backend | Persistent | External dep | Fits ADR-0002 |
|---------|------------|--------------|---------------|
| `memory://` (default) | no | no | **no** (as build queue) |
| `redis://` / Valkey | yes | Redis/Valkey | **no** |
| SQLite | — | — | **does not exist** |

Источник: [FastMCP Background Tasks](https://gofastmcp.com/servers/tasks.md); pydocket заточен под Redis Streams.

Клиенту при этом нужны SEP-1686 wait + `notifications/tasks/status` в рамках MCP-сессии
([Clients → Tasks](https://gofastmcp.com/clients/tasks.md)), а не только ручной poll `get_build_status`.

## Decision

**Не использовать** FastMCP Docket как durable **build queue**.

Очередь и durable state сборок — свои (ADR-0002 + ADR-0004) + `BuildWorker`.

**Разрешено** включить FastMCP `task=True` / Docket `memory://` как тонкий **MCP protocol
wait-слой** поверх SQLite TaskStore:

1. Tool ставит задачу в **наш** `TaskStore` (тот же `task_id`).
2. `BuildWorker` исполняет, как раньше.
3. Если клиент вызвал `call_tool(..., task=True)`, tool ждёт SQLite-строку и зеркалит
   статусы через `Progress` → `notifications/tasks/status`.
4. `await task.result()` возвращает финальный row (`done` / `error`).
5. Без `task=True` поведение прежнее: сразу `{ task_id, status: "queued" }`.

`get_build_status(task_id)` остаётся для инспекции SQLite-строки.

Код моста: `python/mcp_presentation/task_bridge.py`.

## Consequences

### Positive

- Сохраняем embedded SQLite (ADR-0002).
- Не возвращаем Redis для очереди сборок.
- Клиент получает protocol-native wait + session notifications, привязанные к нашему `task_id`.

### Negative / risks

- Два ID в полёте: MCP protocol task id (Docket) и наш SQLite `task_id`. Связь —
  в progress/`statusMessage` (`task_id=… status=…`) и в payload результата.
- Docket `memory://` эфемерен: обрыв MCP-wait при рестарте сервера; сама сборка в SQLite
  переживает рестарт и дожимается worker'ом.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Docket `memory://` as build queue | Теряет задачи при рестарте |
| Docket + Redis as build queue | Противоречит снятию Redis / ADR-0002 |
| Ждать SQLite backend в Docket | Не существует; не блокируем v1 |
| Только `get_build_status` | Плохой UX; нет session notifications |
