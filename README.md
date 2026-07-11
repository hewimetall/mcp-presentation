# mcp-presentation

MCP-сервер для сборки презентаций (**PDF** / **web**) с task-based async pipeline.

## Пакеты (ports & adapters)

| Пакет | Port / роль | Adapter | Артефакт |
|-------|-------------|---------|----------|
| **`mcp-presentation`** | FastMCP + TaskStore | rusqlite | `state/tasks.db` |
| **`mcp-state`** | sessions / workspaces | rusqlite | `state/sessions.db` |
| **`mcp-git`** | `GitPort` | **gix** | bare + worktrees |
| **`mcp-docker`** | `ContainerRuntime` | **bollard** | Docker Engine API |

Стек: **Python 3.14 · FastMCP · Rust/PyO3 · gix · bollard · rusqlite · Pydantic**.

Git v1: `init_bare` / `add_worktree` / `commit` — **без CLI, без push** (ADR-0011).  
Docker: DooD socket через bollard — **без `docker` CLI** (ADR-0012).  
Deploy v1: локальный copy в `out/deployed/` (ADR-0007).

## Happy path (MCP tools)

```text
create_session
  → create_project(project_id)
  → checkout_workspace(session_id, project_id)   # gix worktree + state
  → save_presentation_ir(session_id, ir_json)    # Pydantic validate
  → commit_workspace(session_id, …)
  → build_presentation(session_id, "pdf"|"web"|"web-pdf")
  → get_build_status(task_id)                    # queued→running→done|error
  → get_slide_image(session_id, slide=1)         # PNG, 1-based Marp page
  → deploy_presentation(session_id)              # latest artifact → out/deployed
```

Пример IR: [`examples/demo/presentation.ir.json`](examples/demo/presentation.ir.json)  
JSON Schema: [`schemas/presentation.ir.schema.json`](schemas/presentation.ir.schema.json)

## ADR

→ [`docs/adr/`](docs/adr/README.md) · overview [`docs/architecture/OVERVIEW.md`](docs/architecture/OVERVIEW.md)

## Dev

```bash
uv venv -p 3.14 .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
(cd packages/mcp-state && maturin develop)
(cd packages/mcp-git && maturin develop)
(cd packages/mcp-docker && maturin develop)
maturin develop
pytest -q
```

### Lint / format

```bash
make fmt     # ruff + rustfmt
make lint    # ruff + mypy + rustfmt --check + clippy
make check   # lint + pytest
make docker-build   # latex-builder + web-builder images
```

## Builder images + worker

→ [`infra/`](infra/README.md)

`build_presentation` ставит задачу; **BuildWorker** делает `claim_next`, валидирует IR,
компилирует в `.tex`/`.md` при необходимости, запускает образ через bollard.

Образы: `MCP_LATEX_IMAGE` / `MCP_WEB_IMAGE`.

## Диск

```text
state/tasks.db  state/sessions.db
projects/<id>.git/
workspaces/<ws_id>/
```
