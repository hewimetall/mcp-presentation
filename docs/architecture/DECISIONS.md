# Architecture Decisions — mcp-presentation

Статус: **решения зафиксированы** (итерация после D3.1 + выбор стека).  
Стек: **Python 3.14 · FastMCP · SQLAlchemy · embedded SQLite**.

---

## Сводка

| # | Тема | Решение |
|---|------|---------|
| D3 | Async-сборка | Task-based: MCP не блокируется на билде |
| **D3.1** | Task-хранилище | **Embedded SQLite** (`state/tasks.db`), persistent |
| **D3.2** | Очередь исполнения | **Свой worker** (asyncio + SQLAlchemy), **не** FastMCP Docket |
| **D16** | Runtime-стек | Python 3.14 + FastMCP + SQLAlchemy 2.x + Pydantic |
| **Q1→D17** | IR-формат | **JSON Schema / Pydantic** как канон; Markdown — опциональный authoring |
| **Q3→D18** | Deploy | **Отдельный target/tool**, не post-build |
| **Q5→D19** | Docker | **DooD** (host socket) по умолчанию; rootless — preferred prod |
| **Q7→D20** | Git checkout | **`git worktree`** от bare (`projects/<id>.git`) |

Открытых вопросов по этой итерации нет.

---

## Уже зафиксировано ранее

### D3 / D3.1 — Task-хранилище = embedded SQLite

- Долгий билд не блокирует MCP: `build_presentation` → `task_id`, статус через `get_build_status`.
- Persistent: задачи переживают рестарт (как workspace, D14).
- Embedded: ноль внешних сервисов (в отличие от снятого Redis).
- Файл: `state/tasks.db` рядом с `projects/` и `workspaces/`.

```
state/
├── tasks.db              # SQLite: задачи сборки (persistent)
projects/
└── <project_id>.git/     # git bare — истина
workspaces/
└── <ws_id>/              # checkout (worktree)
```

---

## D3.2 — Почему не FastMCP Background Tasks (Docket)

Исследование FastMCP 3.4.x ([Background Tasks](https://gofastmcp.com/servers/tasks.md)):

| Backend Docket | Persistent | Внешняя зависимость | Совместим с D3.1 |
|----------------|------------|---------------------|------------------|
| `memory://` (default) | нет | нет | **нет** — теряется при рестарте |
| `redis://` / Valkey | да | Redis/Valkey | **нет** — Redis снят осознанно |
| SQLite | — | — | **не существует** |

Docket (pydocket) заточен под Redis Streams; in-memory — только для тестов/dev.

**Решение:** durable state и очередь билдов — **наша** модель на SQLAlchemy/SQLite.  
FastMCP используем как MCP-слой (`@mcp.tool`), без `task=True` / Docket для build pipeline.

MCP-контракт остаётся тем же:

```text
build_presentation(session_id, target) → { task_id }
get_build_status(task_id)              → row из SQLite
```

---

## D16 — Стек: Python 3.14 + FastMCP + SQLAlchemy

| Компонент | Выбор | Зачем |
|-----------|-------|-------|
| Runtime | **Python 3.14** | Запрос продукта; asyncio introspection (`python -m asyncio ps`) полезен для worker’ов |
| MCP | **FastMCP ≥ 3.4.4** | Стандарт для Python MCP; sync tools в threadpool; чистые tool-схемы |
| ORM / SQL | **SQLAlchemy 2.0** (+ **aiosqlite** для async) | Типизированные модели Task; WAL; миграции позже через Alembic |
| Validation | **Pydantic v2** | IR + tool I/O; уже в зависимостях FastMCP |
| DB file | `sqlite+aiosqlite:///state/tasks.db` | Embedded, WAL |

### Важные нюансы стека

1. **FastMCP classifiers** на PyPI сейчас до 3.13; 3.14 уже используется в экосистеме. Фиксируем `fastmcp>=3.4.4` (есть фикс `asyncio.iscoroutinefunction` DeprecationWarning на 3.14). CI обязан гонять 3.14.
2. **SQLAlchemy + SQLite file**: по умолчанию `QueuePool` и `check_same_thread=False` — ок для MCP + background worker в одном процессе.
3. **WAL** обязателен при старте:

```python
from sqlalchemy import event, create_engine

engine = create_engine(
    "sqlite+aiosqlite:///state/tasks.db",
    connect_args={"timeout": 30},
)

@event.listens_for(engine.sync_engine, "connect")
def _sqlite_pragma(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()
```

4. **Писатели**: один in-process worker сериализует обновления статусов (SQLite = один writer). MCP только читает / вставляет `queued`.
5. Сырой `sqlite3` из черновика D3.1 **заменяем** на SQLAlchemy-модели — тот же файл БД, другой API.

### Модель Task (SQLAlchemy)

```python
class Task(Base):
    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str | None]
    workspace: Mapped[str | None]
    target: Mapped[str]          # 'pdf' | 'web' | 'deploy'
    status: Mapped[str]          # queued|running|done|error
    artifact: Mapped[str | None]
    logs: Mapped[str | None]
    error: Mapped[str | None]
    created_at: Mapped[int]
    updated_at: Mapped[int]
```

---

## Q1 → D17 — IR-формат: JSON Schema (канон)

### Варианты

| | Markdown | JSON Schema / Pydantic |
|--|----------|-------------------------|
| LLM-friendly authoring | отлично | хуже (больше «перевода») |
| Валидация до рендера | слабая | строгая |
| Два таргета (pdf + web) | неоднозначно | один контракт → два renderer’а |
| Git diff | читаемый | читаемый при аккуратном dump |
| Детерминизм сборки | низкий | высокий |

### Решение: **канонический IR = JSON (Pydantic / JSON Schema)**

- В git bare лежит **IR** (`presentation.ir.json` или эквивалент) — единственный вход в `pdf`/`web` pipeline.
- Renderers (Typst/LaTeX/HTML — уточняется отдельно) потребляют **только** валидированный IR.
- Markdown — **опциональный authoring-frontend** (MCP-tool `markdown_to_ir`), не source of truth для билда.

Обоснование: два артефакта из одного источника требуют жёсткого контракта; агент уже говорит с tools через схемы — IR того же класса. Markdown оставляем как UX-слой, не как compile-input.

---

## Q3 → D18 — Deploy: отдельный target

### Варианты

| | Post-build hook | Отдельный target `deploy` |
|--|-----------------|---------------------------|
| Успех build ≠ успех publish | смешивает статусы | раздельные `task_id` |
| Секреты / сеть | тянет в каждый билд | только когда нужно |
| Повторный publish того же артефакта | нет | да |
| Агент контролирует шаг | неявно | явно |

### Решение: **`deploy` — отдельный MCP-tool / target**

```text
build_presentation(..., target="web"|"pdf")  → artifact
deploy_presentation(task_id | artifact, dest) → свой task_id
```

- Build всегда заканчивается локальным артефактом (`artifact` path в SQLite).
- Deploy читает готовый артефакт, не пересобирает (если не передан `rebuild=true`).
- Ошибки auth/CDN не помечают успешный build как `error`.

---

## Q5 → D19 — Docker-модель: DooD (default)

Контекст: MCP-хост запускает `docker run` для изолированной сборки (TeX/Node/и т.п.) с mount workspace.

| | DooD (socket) | DinD | Rootless |
|--|---------------|------|----------|
| Простота | высокая | средняя | ниже |
| Host-root при компромиссе | фактически да | через `--privileged` тоже | blast radius = unprivileged user |
| Вложенность / perf | нативная | хуже | ок |
| Совместимость с «ноль внешних сервисов» | да | да | да |

### Решение

1. **Default: DooD** — `/var/run/docker.sock` + `docker run --rm -v <workspace>:<workspace> ...`.
2. **Preferred production: rootless Docker**, если доступен на хосте (тот же CLI-контракт).
3. **DinD отклоняем** для v1: privileged, сложный storage, лишняя поверхность.

Документировать в README: socket mount = доверие к содержимому workspace/образов на уровне host root.

---

## Q7 → D20 — Git checkout: worktree

Уже есть bare в `projects/<project_id>.git`.

| | `git clone` (полный) | `git worktree` |
|--|----------------------|----------------|
| Диск | полный object store × N | объекты в bare, файлы × N |
| Fetch | по каждому clone | один bare |
| Параллельные workspace | ок | ок + защита «ветка уже checked out» |
| Согласованность с bare-истиной | дублирование | нативная |

### Решение: **`git worktree add`** от bare

```text
git --git-dir=projects/<id>.git worktree add workspaces/<ws_id> <ref>
```

- `workspaces/<ws_id>` = active checkout для сессии.
- Удаление workspace = `git worktree remove` (+ prune).
- Не клонировать bare целиком в каждый workspace.

---

## Согласованная картина

```text
┌─────────────┐     tools      ┌──────────────────┐
│ MCP Client  │ ─────────────► │ FastMCP server   │
└─────────────┘                │  (Python 3.14)   │
                               └────────┬─────────┘
                                        │
                    submit/get status   │  SQLAlchemy
                                        ▼
                               ┌──────────────────┐
                               │ state/tasks.db   │  WAL SQLite
                               └────────┬─────────┘
                                        │ claim queued
                                        ▼
                               ┌──────────────────┐
                               │ Build worker     │
                               │  docker run      │  DooD / rootless
                               │  (pdf|web)       │
                               └────────┬─────────┘
                                        │
              projects/*.git (bare) ──► worktree ──► workspaces/<ws>
                                        │
                                        ▼
                               artifact → optional deploy tool
```

### MCP-tools (минимум)

| Tool | Роль |
|------|------|
| `build_presentation` | enqueue `pdf` \| `web` |
| `get_build_status` | read SQLite |
| `deploy_presentation` | enqueue `deploy` (D18) |
| (позже) `markdown_to_ir` | authoring → IR (D17) |

---

## Следующие шаги реализации (не решения)

1. Каркас пакета: `pyproject.toml` (requires-python `>=3.14`), FastMCP entrypoint, SQLAlchemy Task store.
2. Worker loop: claim `queued` → `running` → docker → `done`/`error`.
3. Черновик JSON Schema IR v0 + один pdf/web renderer-stub.
4. Git worktree helpers вокруг bare.
5. Документация threat model для DooD.

---

## Источники исследования

- FastMCP Background Tasks: https://gofastmcp.com/servers/tasks.md (backends: `memory://` \| `redis://`)
- Docket / pydocket: Redis Streams required; memory via burner-redis for tests
- SQLAlchemy 2.0 SQLite dialect: QueuePool + `check_same_thread=False` for file DB; WAL recommended
- Python 3.14: stable since 2025-10-07; FastMCP 3.14 warning fix in PR #3767
- Docker: DooD socket = host root; DinD typically `--privileged`; rootless reduces blast radius
- Git: bare + worktree — стандарт для multi-checkout / agent isolation
- IR: structured IR for multi-renderer pipelines; Markdown better as authoring mediation layer
