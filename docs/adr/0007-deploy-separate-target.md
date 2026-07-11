# ADR-0007: Deploy is a separate target

- Status: Accepted
- Date: 2026-07-11
- Code: D18 (was Q3)
- Deciders: product / architecture
- Relates: ADR-0001

## Context

После сборки артефакта (`main.pdf` / `dist/`) может понадобиться публикация.
Секреты, сеть и ошибки CDN отличаются от ошибок компиляции.

## Decision

**Deploy — отдельный MCP-tool / task target**, не post-build hook.

```text
build_presentation(..., target="web"|"pdf")  → local artifact
deploy_presentation(...)                     → own task_id, target="deploy"
```

Build всегда завершается локальным артефактом. Deploy читает готовый артефакт (без обязательного rebuild).

## Consequences

### Positive

- Успешный build не помечается `error` из‑за auth/CDN.
- Повторный publish того же артефакта возможен.
- Агент явно контролирует шаг.

### Negative / risks

- Лишний tool-call в happy path publish.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Post-build hook always | Смешивает статусы; тянет секреты в каждый билд |
| Deploy flags on build tool | Усложняет контракт одного tool |
