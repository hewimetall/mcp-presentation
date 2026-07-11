# ADR-0009: Git checkout via worktree from bare

- Status: Accepted
- Date: 2026-07-11
- Code: D20 (was Q7)
- Deciders: product / architecture

## Context

Истина проекта — **git bare** в `projects/<project_id>.git`.
Нужны изолированные working directories для сессий/сборок.

## Decision

Checkout = **`git worktree`** от bare, не полный clone:

```text
git --git-dir=projects/<id>.git worktree add workspaces/<ws_id> <ref>
```

- `workspaces/<ws_id>` — active checkout сессии.
- Удаление: `git worktree remove` (+ prune).

## Consequences

### Positive

- Общий object store (экономия диска).
- Fetch один раз в bare.
- Git не даст checkout той же ветки в двух worktree — защита от конфликтов.

### Negative / risks

- Worktree lifecycle нужно аккуратно чистить.
- Shared hooks/config — учитывать при multi-session.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Full `git clone` per workspace | Дублирует object store |
| Single shared checkout + stash | Ломает параллельные сессии |
