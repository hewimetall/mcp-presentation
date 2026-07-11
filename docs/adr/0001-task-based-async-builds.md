# ADR-0001: Task-based async builds

- Status: Accepted
- Date: 2026-07-11
- Code: D3
- Deciders: product / architecture

## Context

Сборка презентации (PDF / web) может занимать минуты (Docker, TeX/Node).
Если MCP-tool блокируется до конца билда, клиент и агент зависают, таймауты MCP ломают UX.

## Decision

Сборка — **асинхронная задача**:

1. `build_presentation(...)` только ставит задачу в очередь и сразу возвращает `task_id`.
2. Статус читается отдельно: `get_build_status(task_id)`.
3. Исполнение — фоновый worker (claim → docker → update).

## Consequences

### Positive

- MCP не блокируется на долгом билде.
- Можно опрашивать прогресс и переживать рестарт процесса (при persistent store — ADR-0002).

### Negative / risks

- Клиент должен уметь polling (два tool-call’а вместо одного).
- Нужна модель статусов (`queued` / `running` / `done` / `error`).

## Alternatives considered

| Option | Why not |
|--------|---------|
| Синхронный `build_*` до артефакта | Блокирует MCP, таймауты |
| FastMCP `task=True` (Docket) | См. ADR-0003 |
