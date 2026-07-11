# Architecture overview — ports & adapters

```text
                    ┌─────────────────────────────┐
                    │     FastMCP (Python)        │
                    │     mcp-presentation        │
                    │  + BuildWorker + IR/Pydantic│
                    └──────────────┬──────────────┘
           ┌───────────────────────┼───────────────────────┐
           ▼                       ▼                       ▼
   ┌───────────────┐      ┌───────────────┐      ┌────────────────┐
   │  mcp-state    │      │  mcp-git      │      │  mcp-docker    │
   │  StateStore   │      │  GitPort      │      │  ContainerRuntime│
   │  (rusqlite)   │      │  ↑            │      │  ↑               │
   └───────────────┘      │  GixAdapter   │      │  BollardAdapter  │
                          └───────────────┘      └────────────────┘
           │                       │                       │
           ▼                       ▼                       ▼
   state/sessions.db      projects/*.git          docker.sock (DooD)
                          workspaces/*/           Engine API
```

## Packages

| Package | Port | Adapter | Persistence / side-effect |
|---------|------|---------|---------------------------|
| `mcp-state` | (store API) | rusqlite | `state/sessions.db` |
| `mcp-presentation` tasks | (store API) | rusqlite | `state/tasks.db` |
| `mcp-git` | `GitPort` | `GixGitAdapter` | bare + worktrees on disk |
| `mcp-docker` | `ContainerRuntime` | `BollardDockerAdapter` | container runs via API |

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
| `build_presentation` | enqueue `pdf` / `web` / `web-pdf` / `slide-image` |
| `get_build_status` | poll task |
| `get_slide_image` | PNG одного **готового** слайда (1-based); без сборки |
| `deploy_presentation` | enqueue local deploy |

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

| Engine | Functions | Image |
|--------|-----------|-------|
| latex | `build_pdf` | `latex-builder` |
| web | `build_web`, `build_web_pdf`, `build_slide_images` | `web-builder` |

Worker calls `engines.run_target(...)`. MCP `get_slide_image` only reads
`out/slides/slide.NNN.png` after `build_presentation(..., "slide-image")`.

## Build worker

After enqueue, `wake_worker` starts a daemon that:

1. `claim_next`
2. validates IR (if present)
3. calls engine `run_target` (latex/web) **or** local deploy
4. writes `done` / `error`

Deploy v1 copies the artifact into `out/deployed/` + `manifest.json` (no CDN).

ADRs: [`docs/adr/`](../adr/README.md)
