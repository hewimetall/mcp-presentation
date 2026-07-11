# ADR-0006: Canonical IR is JSON Schema / Pydantic

- Status: Accepted
- Date: 2026-07-11
- Code: D17 (was Q1)
- Deciders: product / architecture

## Context

Нужен промежуточный формат презентации для двух target’ов (`pdf`, `web`).
Варианты: свободный Markdown vs жёсткий JSON Schema.

## Decision

**Канонический IR = JSON**, описанный **Pydantic / JSON Schema**.

- В git bare лежит IR (например `presentation.ir.json`) — единственный вход рендереров.
- Markdown — **опциональный authoring-frontend** (будущий tool `markdown_to_ir`), не source of truth для билда.

## Consequences

### Positive

- Один контракт → два renderer’а.
- Валидация до Docker-сборки.
- Согласуется с типизированными MCP tools.

### Negative / risks

- LLM пишет JSON хуже, чем Markdown → нужен authoring-слой или хорошие примеры схемы.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Markdown as sole IR | Неоднозначен для layout/theme/assets; слабая валидация |
| YAML | Близок к JSON, но хуже для строгих схем в экосистеме Pydantic |
