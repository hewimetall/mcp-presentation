# Architecture overview — ports & adapters

```text
                    ┌─────────────────────────────┐
                    │     FastMCP (Python)        │
                    │     mcp-presentation        │
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

## GitPort (v1)

- `init_bare`
- `add_worktree`
- `commit`
- **no push**

## ContainerRuntime (v1)

- `run(image, binds, cmd, …)` via bollard
- DooD / rootless socket (ADR-0008 / ADR-0012)

## Builder images (`infra/docker`)

| Target | Image |
|--------|-------|
| `pdf` | `mcp-presentation/latex-builder:latest` |
| `web` | `mcp-presentation/web-builder:latest` |

See [`infra/README.md`](../infra/README.md).

ADRs: [`docs/adr/`](../adr/README.md)
