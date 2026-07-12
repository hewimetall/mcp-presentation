# Architecture overview — ports & adapters

```text
                    ┌─────────────────────────────┐
                    │     FastMCP (Python)        │
                    │  mcp-presentation-core      │
                    │  + BuildWorker + IR/Pydantic│
                    └──────────────┬──────────────┘
           ┌───────────────────────┼───────────────────────┐
           ▼                       ▼                       ▼
   ┌───────────────┐      ┌───────────────┐      ┌────────────────┐
   │  mcp-presentation-state │  mcp-presentation-git │  mcp-presentation-docker │
   │  StateStore             │  GitPort              │  ContainerRuntime        │
   │  (rusqlite)             │  ↑ GixAdapter         │  ↑ BollardAdapter        │
   └─────────────────────────┘  └────────────────────┘  └────────────────────────┘
           │                       │                       │
           ▼                       ▼                       ▼
   state/sessions.db      projects/*.git          docker.sock (DooD)
                          workspaces/*/           Engine API
```

## Packages

| Package (PyPI) | Port | Adapter | Persistence / side-effect |
|----------------|------|---------|---------------------------|
| `mcp-presentation-core` | FastMCP + TaskStore | rusqlite | `state/tasks.db` |
| `mcp-presentation-state` | (store API) | rusqlite | `state/sessions.db` |
| `mcp-presentation-git` | `GitPort` | `GixGitAdapter` | bare + worktrees on disk |
| `mcp-presentation-docker` | `ContainerRuntime` | `BollardDockerAdapter` | container runs via API |

## MCP tools (v1)

| Tool | Role |
|------|------|
| `create_session` / `get_session` / `list_sessions` | sessions |
| `create_project` | `git.init_bare` → `projects/<id>.git` |
| `checkout_workspace` | worktree + state + set active |
| `create_workspace` / `get_workspace` / `list_workspaces` / `remove_workspace` | state metadata |
| `set_active_workspace` | bind session → workspace |
| `save_presentation_ir` | validate + write `presentation.ir.json` |
| `commit_workspace` | gix commit of listed paths |
| `build_presentation` | wait on SQLite task (optional MCP `task=True` notifications) |
| `get_build_status` | inspect SQLite row (optional) |
| `get_slide_image` | PNG + structured `{path, available, index_note}` (1=title) |
| `deploy_presentation` | wait; local_copy under `out/deployed/` (not a URL) |

## Task statuses

`queued` → `running` → `done` | `error`

## GitPort (v1)

- `init_bare` (seeds empty `main`)
- `add_worktree`
- `commit`
- **no push**

## ContainerRuntime (v1)

- `run(image, binds, cmd, …)` via bollard
- DooD / rootless socket (ADR-0008 / ADR-0012)

## Builder images (`infra/docker`)

| Target | Image | CMD |
|--------|-------|-----|
| `pdf` | `mcp-presentation/latex-builder:latest` | `pdf` |
| `web` | `mcp-presentation/web-builder:latest` | `web` |
| `web-pdf` | `mcp-presentation/web-builder:latest` | `web-pdf` |
| `slide-image` | `mcp-presentation/web-builder:latest` | `slide-image` |

See [`infra/README.md`](../infra/README.md).

## Build engines (library)

Web only:

| Function | Target | Artifact + slides |
|----------|--------|-------------------|
| `build_web` | `web` | `dist/` + `out/slides/` |
| `build_web_pdf` | `web-pdf` | `out/web.pdf` + `out/slides/` |
| `build_slide_images` | `slide-image` | `out/slides/` only |

**PDF** (worker): `out/main.pdf` + `out/slides/` via `pdftoppm` inside latex-builder.

Every `pdf` / `web` / `web-pdf` rebuild **clears and rewrites** `out/slides/slide.NNN.png`.
MCP `get_slide_image` only reads those files.

## Build worker

After enqueue, `wake_worker` starts a daemon that:

1. `claim_next`
2. validates IR (if present)
3. web → `run_web_target` / pdf → latex path / deploy → local copy
4. writes `done` / `error`

MCP clients should prefer `call_tool("build_presentation", …, task=True)` then
`await task.result()` / `on_status_change`. The tool waits on the **same** SQLite
`task_id` and pushes `notifications/tasks/status` (Progress bridge). Docket is only
the protocol wait layer — not the durable queue (ADR-0003).

Deploy v1 copies the artifact into `out/deployed/` + `manifest.json` (no CDN).

ADRs: [`docs/adr/`](../adr/README.md)
