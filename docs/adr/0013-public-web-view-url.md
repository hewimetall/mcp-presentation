# ADR-0013: Public web view URL (HTTP route + MCP resource)

- Status: Accepted
- Date: 2026-07-14
- Code: D24
- Deciders: product / architecture
- Relates: ADR-0007, ADR-0005

## Context

После `build_presentation(target="web")` артефакт лежит в `dist/` (локально).
Deploy v1 — только `local_copy` (ADR-0007), без CDN и без открываемой ссылки.

Нужна возможность **дать HTTPS-ссылку**, которую человек открывает в браузере,
когда сервер висит за доменом:

```text
Browser ──HTTPS──► Caddy ──/view/*──► mcp-presentation (custom HTTP route)
Agent   ──HTTPS──► Caddy ──/mcp─────► vMCP ──► mcp-presentation (MCP)
```

В MCP есть **Resources** (`resources/list` / `resources/read`) — URI-адресация
данных для клиента. Это **не** публичный `https://…` URL: схема вроде
`presentation://…` читается через MCP-протокол, браузер сам по себе её не откроет.

Для «открыть в Chrome» нужен обычный HTTP GET поверх того же процесса
(FastMCP `@custom_route` при `transport=http`) + публичный origin в конфиге.

## Decision

1. **Env `MCP_PRESENTATION_PUBLIC_BASE`** — origin вида `https://slides.example.com`
   (Caddy TLS). Без него tool/resource возвращают `public_base_unset`.
2. **HTTP custom route** `GET /view/{workspace_id}/…` отдаёт файлы из
   `out/deployed/dist` → `out/deployed` → `dist` (первый с `index.html`).
3. **Tool `get_view_url(session_id)`** возвращает `{view_url, web_root, resource_uri, …}`.
4. **Resource template** `presentation://{session_id}/view` — тот же JSON через
   `resources/read` (удобно агентам, которые предпочитают resources).
5. Caddy: `/view/*` → напрямую на HTTP-порт mcp-presentation; `/mcp` → vMCP.
   vMCP **не** проксирует static view (это MCP gateway, не file server).

```text
build_presentation(..., "web")
  → get_view_url(session_id)  → https://domain/view/<workspace_id>/
```

## Consequences

### Positive

- Открываемая ссылка без внешнего CDN.
- MCP Resource доступен клиентам, которые умеют `resources/*`.
- Deploy остаётся отдельным шагом; view может работать и с сырым `dist/`.

### Negative / risks

- Нужен HTTP transport (не только stdio) + правильный Caddy split `/view` vs `/mcp`.
- Публичный `/view/` без auth — осознанный trade-off v1 (сеть/Caddy ACL снаружи).

### Neutral

- `ui://` FastMCP Apps не используем: это iframe внутри MCP-клиента, не публичная ссылка.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Только MCP Resource `presentation://…` | Браузер не откроет; нет HTTPS |
| FastMCP `ui://` App | Просмотр в клиенте, не shareable URL |
| CDN / S3 в deploy | Вне scope v1 (ADR-0007 local_copy) |
| Отдавать static через vMCP | Gateway для MCP JSON-RPC, не для HTML |
