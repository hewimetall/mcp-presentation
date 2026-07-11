# ADR-0005: Runtime stack

- Status: Accepted
- Date: 2026-07-11
- Code: D16
- Deciders: product / architecture
- Relates: ADR-0004

## Context

Нужен согласованный runtime для MCP-сервера презентаций: tools, validation, native task store, без внешних брокеров.

## Decision

| Layer | Choice |
|-------|--------|
| Runtime | **Python 3.14** |
| MCP | **FastMCP ≥ 3.4.4** |
| Tasks | **Rust + PyO3 + rusqlite** (ADR-0004) |
| Packaging | **maturin** (mixed Python/Rust) |
| Validation / IR | **Pydantic v2** |
| Task DB file | `state/tasks.db` |

**Не используем:** SQLAlchemy, aiosqlite, FastMCP Docket/Redis для задач.

## Consequences

### Positive

- Один понятный стек под продуктовый запрос.
- IR и tool I/O валидируются одной библиотекой (Pydantic).

### Negative / risks

- FastMCP classifiers на PyPI формально до 3.13 — CI обязан гонять 3.14; pin ≥ 3.4.4 (фиксы DeprecationWarning).
- Dev-машина должна иметь Rust stable (см. `rust-toolchain.toml`).

## Alternatives considered

| Option | Why not |
|--------|---------|
| Python 3.12/3.13 only | Продуктовый выбор — 3.14 |
| Pure Python task store | ADR-0004 |
| Low-level MCP SDK without FastMCP | Больше boilerplate |
