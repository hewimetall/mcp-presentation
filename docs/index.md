# mcp-presentation

MCP-сервер для сборки презентаций (**PDF** / **web**) с task-based async pipeline.

## Документация

- [Architecture overview](architecture/OVERVIEW.md) — ports & adapters, tools, builder images
- [Decisions](architecture/DECISIONS.md) — указатель на ADR
- [ADR index](adr/README.md) — Architecture Decision Records

## Builder images (release tags)

На тег `v*` GitHub Actions публикует образы в GHCR:

| Image | Pull |
|-------|------|
| LaTeX / PDF | `ghcr.io/hewimetall/mcp-presentation/latex-builder:<version>` |
| Web | `ghcr.io/hewimetall/mcp-presentation/web-builder:<version>` |

Локальная сборка: `make docker-build` (см. `infra/README.md` в репозитории).

## Репозиторий

Исходники и README: [hewimetall/mcp-presentation](https://github.com/hewimetall/mcp-presentation).
