# ADR-0008: Docker model — DooD default

- Status: Accepted
- Date: 2026-07-11
- Code: D19 (was Q5)
- Deciders: product / architecture

## Context

Worker запускает изолированную сборку через контейнеры (`docker run` + mount workspace).
Нужна модель доступа к Docker на хосте MCP.

| | DooD (socket) | DinD | Rootless |
|--|---------------|------|----------|
| Simplicity | high | medium | lower |
| Host-root on compromise | effectively yes | via `--privileged` also | blast radius = unprivileged user |
| Nested perf | native | worse | ok |

## Decision

1. **Default: DooD** — mount `/var/run/docker.sock`, `docker run --rm -v <workspace>:<workspace> ...`.
2. **Preferred production: rootless Docker**, если доступен (тот же CLI-контракт).
3. **DinD отклоняем** для v1 (privileged, storage, лишняя поверхность).

## Consequences

### Positive

- Простой single-host deploy.
- Rootless — путь ужесточения без смены API.

### Negative / risks

- Socket mount ≈ доверие к содержимому workspace/образов на уровне host root — задокументировать в README/threat model.

## Alternatives considered

| Option | Why not |
|--------|---------|
| DinD | `--privileged`, сложный nested storage |
| Daemonless-only (Kaniko/Buildah) | Можно позже; v1 опирается на `docker run` runtime, не только image build |
