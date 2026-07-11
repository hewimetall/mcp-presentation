# ADR-0002: Embedded SQLite task store

- Status: Accepted
- Date: 2026-07-11
- Code: D3.1
- Deciders: product / architecture
- Relates: ADR-0001, ADR-0004

## Context

Нужно persistent хранилище задач, которое:

- переживает рестарт MCP-сервера;
- не требует внешних сервисов (Redis уже снят осознанно);
- согласуется с локальным layout (`projects/`, `workspaces/`).

## Decision

Задачи хранятся в **embedded SQLite**: файл `state/tasks.db`.

```text
state/
├── tasks.db              # задачи сборки (persistent)
projects/
└── <project_id>.git/     # git bare — истина
workspaces/
└── <ws_id>/              # checkout
```

Схема (минимум): `task_id`, `session_id`, `workspace`, `target`, `status`,
`artifact`, `logs`, `error`, `created_at`, `updated_at`.

Владелец файла БД и API доступа — Rust TaskStore (ADR-0004), не Python `sqlite3` напрямую.

## Consequences

### Positive

- Ноль внешних зависимостей для queue/state.
- Persistent как workspace (D14).
- Простой бэкап: один файл (+ WAL sidecar).

### Negative / risks

- Один writer (SQLite); нужна сериализация обновлений.
- Горизонтальное масштабирование worker’ов на несколько машин — вне scope v1.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Redis / Valkey | Внешний сервис; противоречит «embedded» |
| In-memory dict | Теряется при рестарте |
| PostgreSQL | Лишняя ops-нагрузка для v1 |
