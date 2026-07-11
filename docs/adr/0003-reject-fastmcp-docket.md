# ADR-0003: Reject FastMCP Docket for build queue

- Status: Accepted
- Date: 2026-07-11
- Code: D3.2
- Deciders: product / architecture
- Relates: ADR-0001, ADR-0002

## Context

FastMCP ≥ 2.14 имеет protocol-native background tasks (`task=True`) на базе **Docket**.
Кажется естественным для ADR-0001, но backends Docket ограничены.

| Backend | Persistent | External dep | Fits ADR-0002 |
|---------|------------|--------------|---------------|
| `memory://` (default) | no | no | **no** |
| `redis://` / Valkey | yes | Redis/Valkey | **no** |
| SQLite | — | — | **does not exist** |

Источник: [FastMCP Background Tasks](https://gofastmcp.com/servers/tasks.md); pydocket заточен под Redis Streams.

## Decision

**Не использовать** FastMCP Docket / `task=True` для build pipeline.

Очередь и durable state — свои (ADR-0002 + ADR-0004).  
FastMCP остаётся MCP-слоем: обычные `@mcp.tool` без Docket.

Контракт для клиента тот же:

```text
build_presentation(...) → { task_id }
get_build_status(task_id) → row
```

## Consequences

### Positive

- Сохраняем embedded SQLite (ADR-0002).
- Не возвращаем Redis.

### Negative / risks

- Нет protocol-native SEP-1686 task polling «из коробки» — свой `get_build_status`.
- Не получим горизонтальных Docket workers без Redis.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Docket `memory://` | Теряет задачи при рестарте |
| Docket + Redis | Противоречит снятию Redis / ADR-0002 |
| Ждать SQLite backend в Docket | Не существует; не блокируем v1 |
