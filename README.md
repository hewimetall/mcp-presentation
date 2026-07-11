# mcp-presentation

MCP-сервер для сборки презентаций (**PDF** / **web**) с task-based async pipeline.

## Пакеты (ports & adapters)

| Пакет | Port / роль | Adapter | Артефакт |
|-------|-------------|---------|----------|
| **`mcp-presentation`** | FastMCP + TaskStore | rusqlite | `state/tasks.db` |
| **`mcp-state`** | sessions / workspaces | rusqlite | `state/sessions.db` |
| **`mcp-git`** | `GitPort` | **gix** | bare + worktrees |
| **`mcp-docker`** | `ContainerRuntime` | **bollard** | Docker Engine API |

Стек: **Python 3.14 · FastMCP · Rust/PyO3 · gix · bollard · rusqlite**.

Git v1: `init_bare` / `add_worktree` / `commit` — **без CLI, без push** (ADR-0011).  
Docker: DooD socket через bollard — **без `docker` CLI** (ADR-0012).

## ADR

→ [`docs/adr/`](docs/adr/README.md) · overview [`docs/architecture/OVERVIEW.md`](docs/architecture/OVERVIEW.md)

## Dev

```bash
uv venv -p 3.14 .venv && source .venv/bin/activate
(cd packages/mcp-state && maturin develop)
(cd packages/mcp-git && maturin develop)
(cd packages/mcp-docker && maturin develop)
maturin develop
pytest -q
```

## Диск

```text
state/tasks.db  state/sessions.db
projects/<id>.git/
workspaces/<ws_id>/
```
