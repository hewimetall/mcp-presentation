# ADR-0008: Docker model — DooD default

- Status: Accepted (amended by ADR-0012)
- Date: 2026-07-11
- Code: D19 (was Q5)
- Deciders: product / architecture

## Context

Worker запускает изолированную сборку через контейнеры с mount workspace.
Нужна модель доступа к Docker на хосте MCP.

| | DooD (socket) | DinD | Rootless |
|--|---------------|------|----------|
| Simplicity | high | medium | lower |
| Host-root on compromise | effectively yes | via `--privileged` also | blast radius = unprivileged user |
| Nested perf | native | worse | ok |

## Decision

1. **Default: DooD** — доступ к host Docker daemon через socket.
2. **Клиент: bollard** через порт `ContainerRuntime` — [ADR-0012](0012-docker-ports-adapters-bollard.md). **Не** `docker` CLI.
3. **Preferred production: rootless Docker**, если доступен.
4. **DinD отклоняем** для v1.

## Consequences

### Positive

- Простой single-host deploy.
- Rootless — путь ужесточения без смены API.
- Тестируемый port/adapter.

### Negative / risks

- Socket mount ≈ доверие к содержимому workspace/образов на уровне host root.

## Alternatives considered

| Option | Why not |
|--------|---------|
| DinD | `--privileged`, сложный nested storage |
| `docker` CLI subprocess | Заменено на bollard (ADR-0012) |
| Daemonless-only (Kaniko/Buildah) | Можно позже; v1 = run container |
