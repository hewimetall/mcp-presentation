# Architecture Decision Records (ADR)

Каноническое место фиксации архитектурных решений проекта **mcp-presentation**.

Формат: [Nygard ADR](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) — Context / Decision / Consequences.

| ADR | Код | Статус | Тема |
|-----|-----|--------|------|
| [0001](0001-task-based-async-builds.md) | D3 | Accepted | Task-based async-сборка |
| [0002](0002-embedded-sqlite-task-store.md) | D3.1 | Accepted | Embedded SQLite для задач |
| [0003](0003-reject-fastmcp-docket.md) | D3.2 | Accepted | Отказ от FastMCP Docket |
| [0004](0004-rust-pyo3-taskstore.md) | D3.3 | Accepted | TaskStore через Rust / PyO3 |
| [0005](0005-runtime-stack.md) | D16 | Accepted | Runtime-стек |
| [0006](0006-ir-json-schema.md) | D17 | Accepted | IR = JSON Schema / Pydantic |
| [0007](0007-deploy-separate-target.md) | D18 | Accepted | Deploy — отдельный target |
| [0008](0008-docker-dood.md) | D19 | Accepted | Docker DooD (default) |
| [0009](0009-git-worktree-checkout.md) | D20 | Superseded | Git worktree (→ ADR-0011) |
| [0010](0010-separate-mcp-state-package.md) | D21 | Accepted | Отдельный пакет `mcp-state` (sessions/workspaces) |
| [0011](0011-mcp-git-gix-no-cli.md) | D22 | Accepted | `mcp-git`: gix, bare/worktree/commit, без CLI/push |
| [0012](0012-docker-ports-adapters-bollard.md) | D23 | Accepted | Docker: bollard + ports & adapters |

## Как добавить ADR

1. Скопировать [`0000-template.md`](0000-template.md).
2. Следующий номер `NNNN-short-title.md`.
3. Статус: `Proposed` → `Accepted` / `Deprecated` / `Superseded by ADR-XXXX`.
4. Обновить таблицу в этом файле.
