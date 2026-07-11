# ADR-0004: TaskStore via Rust / PyO3

- Status: Accepted
- Date: 2026-07-11
- Code: D3.3
- Deciders: product / architecture
- Relates: ADR-0002, ADR-0005
- Supersedes: SQLAlchemy / raw `sqlite3` task path drafts

## Context

Нужен единственный владелец `state/tasks.db` с:

- WAL и предсказуемым claim (`queued` → `running`);
- коротким критическим путём под GIL;
- сборкой как native extension в том же Python-пакете.

Ранее рассматривались SQLAlchemy + aiosqlite — лишний ORM-слой для узкой очереди.

## Decision

Реализовать **TaskStore на Rust**, экспортировать в Python через **PyO3** (сборка **maturin**).

- SQLite: **`rusqlite`** с feature **`bundled`**
- Модуль: `mcp_presentation._tasks.TaskStore`
- API: `submit`, `get`, `update`, `claim_next`
- Python / FastMCP — только тонкие обёртки

```python
from mcp_presentation._tasks import TaskStore
store = TaskStore("state/tasks.db")
tid = store.submit(session_id, workspace, target)
```

**SQLAlchemy в стек v1 не входит.**

## Consequences

### Positive

- Один native owner схемы и транзакций.
- Bundled SQLite — без системной libsqlite3.
- Возможность `allow_threads` вокруг долгих DB wait’ов позже.

### Negative / risks

- Нужны Rust toolchain + maturin в dev/CI.
- PyO3 ≥ 0.25 для CPython 3.14 (pin 0.29.x).

### Neutral

- Долгий `docker run` остаётся в Python worker; Rust только claim/update.

## Alternatives considered

| Option | Why not |
|--------|---------|
| SQLAlchemy + aiosqlite | ORM overhead; два владельца схемы |
| stdlib `sqlite3` в Python | Медленнее критический путь; слабее контроль WAL/claim |
| Отдельный Redis queue | ADR-0002 / ADR-0003 |
