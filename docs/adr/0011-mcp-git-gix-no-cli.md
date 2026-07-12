# ADR-0011: Separate mcp-presentation-git package (gix, no CLI, no push)

- Status: Accepted
- Date: 2026-07-11
- Code: D22
- Deciders: product / architecture
- Relates: ADR-0009, ADR-0010
- Supersedes: ADR-0009 shelling out to `git` CLI

## Context

Нужен git-слой для bare + worktree + commit **без** вызова команды `git`.
Push не нужен (некуда пушить в v1).
Как и `mcp-presentation-state` — **отдельный пакет**.

Кандидаты:

| | `gix` (gitoxide) | `git2` (libgit2) |
|--|------------------|------------------|
| CLI subprocess | нет | нет |
| Pure Rust | да | нет (C) |
| Worktree add | нет high-level; можно linked worktree через plumbing + checkout | зрелее |
| Commit | через object API | зрелее |

## Decision

1. Пакет **`packages/mcp-presentation-git`** (maturin / PyO3; ранее `mcp-git`).
2. Библиотека: **`gix`** (+ `gix-worktree-state` для checkout файлов).
3. **Ports & Adapters**: порт `GitPort`, адаптер `GixGitAdapter`.
4. v1 API (только локально):
   - `init_bare(path) → project_id/path`
   - `add_worktree(bare, worktree_path, ref) → workspace path`
   - `commit(worktree, message, paths?) → commit_id`
5. **Нет** `push` / remotes в v1.
6. Linked worktree: создаём структуру как у `git worktree` (gitdir + `.git` file + checkout tree) через filesystem + gix, **без** `std::process::Command`.

## Consequences

### Positive

- Нет зависимости от установленного `git`.
- Согласовано с ADR-0004 / ADR-0010 (отдельные Rust-пакеты).
- Port позволяет позже заменить адаптер.

### Negative / risks

- Official `git worktree add` в gix отсутствует — наш adapter эмулирует layout.
- Checkout/commit paths в gix требуют аккуратной работы с index/tree.

## Alternatives considered

| Option | Why not |
|--------|---------|
| `git2` | C/libgit2; не pure Rust |
| `git` CLI via Command | Явно запрещено |
| Push в v1 | Некуда пушить |
