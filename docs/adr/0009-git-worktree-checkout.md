# ADR-0009: Git checkout via worktree from bare

- Status: Superseded by [ADR-0011](0011-mcp-git-gix-no-cli.md)
- Date: 2026-07-11
- Code: D20 (was Q7)
- Deciders: product / architecture

## Context

Истина проекта — **git bare** в `projects/<project_id>.git`.
Нужны изолированные working directories для сессий/сборок.

## Decision (историческое)

Checkout = worktree от bare, не полный clone. Изначально предполагался CLI:

```text
git --git-dir=projects/<id>.git worktree add workspaces/<ws_id> <ref>
```

## Update

Реализация **без CLI**: пакет `mcp-presentation-git` + **gix** (ADR-0011).
Семантика worktree сохраняется; меняется механизм.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Full `git clone` per workspace | Дублирует object store |
| Single shared checkout + stash | Ломает параллельные сессии |
