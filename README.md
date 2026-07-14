# mcp-presentation

MCP-сервер для сборки презентаций (**PDF** / **web**) с task-based async pipeline.

## Пакеты (PyPI names)

| Пакет | Import | Роль |
|-------|--------|------|
| **`mcp-presentation-core`** | `mcp_presentation` | FastMCP server + TaskStore + CLI |
| **`mcp-presentation-state`** | `mcp_state` | sessions / workspaces (rusqlite) |
| **`mcp-presentation-git`** | `mcp_git` | GitPort / **gix** |
| **`mcp-presentation-docker`** | `mcp_docker` | ContainerRuntime / **bollard** |

Стек: **Python 3.14 · FastMCP · Rust/PyO3 · gix · bollard · rusqlite · Pydantic**.

Git v1: `init_bare` / `add_worktree` / `commit` — **без CLI, без push** (ADR-0011).  
Docker: DooD socket через bollard — **без `docker` CLI** (ADR-0012).  
Deploy v1: локальный copy в `out/deployed/` (ADR-0007).

## Run with uv tool

From a checkout (builds native extensions via maturin as needed):

```bash
uv sync
uv tool run --from . mcp-presentation
```

After packages are on an index:

```bash
uv tool run --from mcp-presentation-core mcp-presentation
# or install once:
uv tool install mcp-presentation-core
mcp-presentation
```

Cursor / stdio `mcp.json` (local editable):

```json
{
  "mcpServers": {
    "mcp-presentation": {
      "command": "uv",
      "args": ["tool", "run", "--from", "/absolute/path/to/mcp-presentation", "mcp-presentation"],
      "env": {
        "MCP_PRESENTATION_STATE": "/absolute/path/to/data/state",
        "MCP_PRESENTATION_PROJECTS": "/absolute/path/to/data/projects",
        "MCP_PRESENTATION_WORKSPACES": "/absolute/path/to/data/workspaces"
      }
    }
  }
}
```

## Happy path (MCP tools)

```text
create_session
  → create_project(project_id)
  → checkout_workspace(session_id, project_id)   # gix worktree + state
  → save_presentation_ir(session_id, ir_json)    # Pydantic validate
  → commit_workspace(session_id, …)
  → build_presentation(session_id, "pdf"|"web"|"web-pdf")  # waits; refreshes out/slides/
  → get_slide_image(session_id, slide=1)  # 1=title; JSON: path/available/index_note + Image
  → get_view_url(session_id)             # HTTPS link when PUBLIC_BASE is set (ADR-0013)
  → deploy_presentation(session_id)      # local_copy under out/deployed/ (not a URL)
```

`save_presentation_ir` returns `rebuild_required: true` — slide PNGs stay stale until rebuild.
`workspace_id` equals the folder name under `workspaces/`.
Preferred wait UX: tool itself waits (and with MCP `task=True` also pushes status notifications).
`get_build_status` remains for inspection only.

### Public web view URL

MCP **Resources** (`presentation://{session_id}/view`) give agents metadata via `resources/read` —
they are **not** openable in a browser. For a real link:

```bash
export MCP_PRESENTATION_TRANSPORT=http
export MCP_PRESENTATION_HOST=0.0.0.0
export MCP_PRESENTATION_PORT=8000
export MCP_PRESENTATION_PUBLIC_BASE=https://slides.example.com
mcp-presentation
```

Then `get_view_url` → `https://slides.example.com/view/<workspace_id>/`.

Caddy sketch:

```text
slides.example.com {
  handle /view/* {
    reverse_proxy 127.0.0.1:8000
  }
  handle /mcp* {
    reverse_proxy vmcp:8080   # vMCP → mcp-presentation
  }
}
```

`GET /view/{workspace_id}/…` is a FastMCP custom route on the same HTTP process (ADR-0013).

Пример IR: [`examples/demo/presentation.ir.json`](examples/demo/presentation.ir.json)  
JSON Schema: [`schemas/presentation.ir.schema.json`](schemas/presentation.ir.schema.json)

## ADR

→ [`docs/adr/`](docs/adr/README.md) · overview [`docs/architecture/OVERVIEW.md`](docs/architecture/OVERVIEW.md)

## Release

Тег `v*` → [`.github/workflows/release.yml`](.github/workflows/release.yml):
Docker-образы в GHCR + docs (GitHub Pages и assets релиза).

```bash
git tag v0.1.0 && git push origin v0.1.0
```

## Dev

```bash
uv venv -p 3.14 .venv && source .venv/bin/activate
uv sync --extra dev
(cd packages/mcp-presentation-state && maturin develop)
(cd packages/mcp-presentation-git && maturin develop)
(cd packages/mcp-presentation-docker && maturin develop)
maturin develop
pytest -q
make cov-rust   # per-crate cargo-llvm-cov, fail-under 98%
```

### Lint / format

```bash
make fmt     # ruff + rustfmt
make lint    # ruff + mypy + rustfmt --check + clippy
make check   # lint + pytest + cov-rust
make cov-py  # Python coverage (fail-under 98)
make cov-rust
make docker-build   # latex-builder + web-builder images
```

## Builder images + worker

→ [`infra/`](infra/README.md)

`build_presentation` / `deploy_presentation` ставят задачу в SQLite; при MCP
`task=True` tool ждёт ту же строку и шлёт `notifications/tasks/status`.
**BuildWorker** делает `claim_next`, валидирует IR, компилирует в `.tex`/`.md`
при необходимости, запускает образ через bollard.

Образы: `MCP_LATEX_IMAGE` / `MCP_WEB_IMAGE`.

## Диск

```text
state/tasks.db  state/sessions.db
projects/<id>.git/
workspaces/<ws_id>/
```
