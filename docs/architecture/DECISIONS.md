# Architecture Decisions — mcp-presentation

Статус: **решения зафиксированы** (итерация: Rust/PyO3 task-слой).  
Стек: **Python 3.14 · FastMCP · Rust (PyO3) · rusqlite · embedded SQLite**.

---

## Сводка

| # | Тема | Решение |
|---|------|---------|
| D3 | Async-сборка | Task-based: MCP не блокируется на билде |
| **D3.1** | Task-хранилище | **Embedded SQLite** (`state/tasks.db`), persistent |
| **D3.2** | Очередь / Docket | **Не** FastMCP Docket (только memory/Redis) |
| **D3.3** | Task API | **Rust + PyO3** (`rusqlite`, WAL); Python только вызывает |
| **D16** | Runtime-стек | Python 3.14 + FastMCP + **maturin/PyO3** + Pydantic (**без SQLAlchemy**) |
| **Q1→D17** | IR-формат | **JSON Schema / Pydantic** как канон; Markdown — опциональный authoring |
| **Q3→D18** | Deploy | **Отдельный target/tool**, не post-build |
| **Q5→D19** | Docker | **DooD** (host socket) по умолчанию; rootless — preferred prod |
| **Q7→D20** | Git checkout | **`git worktree`** от bare (`projects/<id>.git`) |

Открытых вопросов по этой итерации нет.

---

## D3 / D3.1 — Task-хранилище = embedded SQLite

- Долгий билд не блокирует MCP: `build_presentation` → `task_id`, статус через `get_build_status`.
- Persistent: задачи переживают рестарт (как workspace, D14).
- Embedded: ноль внешних сервисов (в отличие от снятого Redis).
- Файл: `state/tasks.db` рядом с `projects/` и `workspaces/`.

```
state/
├── tasks.db              # SQLite: задачи (владелец — Rust TaskStore)
projects/
└── <project_id>.git/     # git bare — истина
workspaces/
└── <ws_id>/              # checkout (worktree)
```

---

## D3.2 — Почему не FastMCP Background Tasks (Docket)

| Backend Docket | Persistent | Внешняя зависимость | Совместим с D3.1 |
|----------------|------------|---------------------|------------------|
| `memory://` (default) | нет | нет | **нет** |
| `redis://` / Valkey | да | Redis/Valkey | **нет** |
| SQLite | — | — | **не существует** |

FastMCP = MCP-слой (`@mcp.tool`), без `task=True` / Docket для build pipeline.

---

## D3.3 — Task-слой через Rust / PyO3

### Решение

**Вся работа с задачами** (schema, submit, update, get, claim) живёт в **Rust-расширении** на PyO3, SQLite через **`rusqlite` (feature `bundled`)**.

| Слой | Технология | Роль |
|------|------------|------|
| MCP tools | FastMCP (Python) | тонкая обёртка: принять args → вызвать Rust → вернуть dict |
| TaskStore | **Rust + PyO3** | единственный writer/owner `state/tasks.db` |
| SQLite | **rusqlite + bundled** | WAL, busy_timeout, миграции; без системного libsqlite |
| Build worker | Python (или позже Rust) | claim через PyO3 → `docker run` → update status |
| IR / validation | Pydantic (Python) | не путать с task DB |

### Почему не SQLAlchemy

| | SQLAlchemy (снято для tasks) | Rust / PyO3 + rusqlite |
|--|------------------------------|-------------------------|
| Владение схемой | Python ORM | один native owner |
| GIL на claim/update | да | короткое удержание GIL / можно `allow_threads` |
| Зависимости | ORM + aiosqlite | один `.so` + bundled SQLite |
| Согласованность с «embedded» | ок | ок + быстрее критический путь очереди |

SQLAlchemy **не** входит в стек v1. Сырой `sqlite3` из черновика D3.1 тоже не используем — только через Rust.

### Python API (контракт)

```python
from mcp_presentation._tasks import TaskStore

store = TaskStore("state/tasks.db")          # создаёт схему, включает WAL
tid = store.submit(session_id, workspace, target)  # → str
store.update(tid, status="running", logs="...")
row = store.get(tid)                         # → dict | None
nxt = store.claim_next()                     # atomic queued→running | None
```

### Rust surface (эскиз)

```rust
#[pyclass]
struct TaskStore {
    conn: Mutex<Connection>,
}

#[pymethods]
impl TaskStore {
    #[new]
    fn new(path: &str) -> PyResult<Self> { /* open, PRAGMA WAL, migrate */ }

    fn submit(&self, session_id: &str, workspace: &str, target: &str) -> PyResult<String> { … }
    fn update(&self, task_id: &str, /** kwargs */) -> PyResult<()> { … }
    fn get(&self, task_id: &str) -> PyResult<Option<PyObject>> { … }
    fn claim_next(&self) -> PyResult<Option<PyObject>> { … }
}
```

Сборка: **maturin** (`pyproject.toml` build-backend = maturin), PyO3 **≥ 0.25** (поддержка CPython 3.14; актуальный 0.29.x).  
`rusqlite` с `features = ["bundled"]` — без внешней libsqlite3.

### Схема (владеет Rust)

```sql
CREATE TABLE IF NOT EXISTS tasks (
    task_id     TEXT PRIMARY KEY,
    session_id  TEXT,
    workspace   TEXT,
    target      TEXT,          -- 'pdf' | 'web' | 'deploy'
    status      TEXT,          -- 'queued'|'running'|'done'|'error'
    artifact    TEXT,
    logs        TEXT,
    error       TEXT,
    created_at  INTEGER,
    updated_at  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_tasks_status_created
  ON tasks(status, created_at);
```

`claim_next`: одна транзакция `SELECT … WHERE status='queued' ORDER BY created_at LIMIT 1` + `UPDATE … status='running'` (или `UPDATE … RETURNING` на подходящем SQLite).

### Связь с MCP

```python
@mcp.tool()
def build_presentation(session_id: str, target: str) -> dict:
    ws = sessions[session_id].active_workspace
    tid = store.submit(session_id, ws, target)
    wake_worker()
    return {"task_id": tid}

@mcp.tool()
def get_build_status(task_id: str) -> dict:
    row = store.get(task_id)
    if row is None:
        return {"error": "not_found", "task_id": task_id}
    return row
```

---

## D16 — Стек (обновлён)

| Компонент | Выбор | Зачем |
|-----------|-------|-------|
| Runtime | **Python 3.14** | продуктовый выбор |
| MCP | **FastMCP ≥ 3.4.4** | tools / schemas |
| Tasks | **Rust + PyO3 + rusqlite** | durable queue, D3.1 |
| Build | **maturin** | wheel с native extension |
| Validation | **Pydantic v2** | IR + tool I/O |
| DB file | `state/tasks.db` | только через Rust TaskStore |

**Не используем:** SQLAlchemy, aiosqlite, FastMCP Docket/Redis для задач.

Нюансы:

1. PyO3 ≥ 0.25 обязателен для 3.14; pin `pyo3 = "0.29"` (или новее).
2. Worker и MCP делят один `TaskStore` (одно соединение под `Mutex`, или connection-per-call с WAL — выбрать в реализации; v1: `Mutex<Connection>`).
3. Долгий `docker run` — **вне** Rust; Rust только claim/update статусов.

---

## Q1 → D17 — IR-формат: JSON Schema (канон)

**Канон = JSON (Pydantic / JSON Schema)** в git.  
Markdown — опциональный authoring (`markdown_to_ir`), не вход рендереров.

---

## Q3 → D18 — Deploy: отдельный target

`deploy_presentation` — отдельный tool/task `target='deploy'`, не post-build hook.

---

## Q5 → D19 — Docker: DooD (default)

1. Default: DooD (`docker.sock`).
2. Preferred prod: rootless.
3. DinD — нет в v1.

---

## Q7 → D20 — Git checkout: worktree

```text
git --git-dir=projects/<id>.git worktree add workspaces/<ws_id> <ref>
```

---

## Согласованная картина

```text
┌─────────────┐     tools      ┌──────────────────┐
│ MCP Client  │ ─────────────► │ FastMCP (Python) │
└─────────────┘                └────────┬─────────┘
                                        │ PyO3
                                        ▼
                               ┌──────────────────┐
                               │ TaskStore (Rust) │  rusqlite WAL
                               │ state/tasks.db   │
                               └────────┬─────────┘
                                        │ claim_next / update
                                        ▼
                               ┌──────────────────┐
                               │ Build worker     │
                               │  docker run      │  DooD / rootless
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
| `build_presentation` | enqueue через Rust `submit` |
| `get_build_status` | Rust `get` |
| `deploy_presentation` | enqueue `deploy` (D18) |
| (позже) `markdown_to_ir` | authoring → IR (D17) |

---

## Следующие шаги реализации

1. Maturin/PyO3 crate `TaskStore` + схема + `submit/get/update/claim_next`.
2. FastMCP server, вызывающий Rust API.
3. Worker loop: `claim_next` → docker → `update`.
4. IR schema v0 + renderer stubs.
5. Git worktree helpers.

---

## Источники

- FastMCP tasks: только `memory://` / `redis://` — https://gofastmcp.com/servers/tasks.md
- PyO3 0.25+: поддержка CPython 3.14; 0.29.x актуален
- maturin: pyo3 bindings, abi3 / version-specific wheels
- rusqlite `bundled`: встроенный SQLite, без системной lib
- SQLAlchemy снят с task-пути (D3.3)
