# ADR-0012: Docker via ports & adapters (bollard, no CLI)

- Status: Accepted
- Date: 2026-07-11
- Code: D23
- Deciders: product / architecture
- Relates: ADR-0008, ADR-0011
- Amends: ADR-0008 (DooD остаётся, но доступ через API-библиотеку, не `docker` CLI)

## Context

Build worker запускает контейнеры для pdf/web.
Нужна **Rust-библиотека Docker Engine API**, не `docker` subprocess.
Архитектура — **hexagonal (ports & adapters)**.

Кандидат: **[`bollard`](https://github.com/fussybeaver/bollard)** — async Docker/Podman API client (Hyper/Tokio), говорит с daemon по socket/HTTP, CLI не нужен.

## Decision

### Порт

```rust
#[async_trait]
pub trait ContainerRuntime: Send + Sync {
    async fn run(&self, req: RunContainerRequest) -> Result<RunContainerResult, ContainerError>;
    // image ensure/pull — later
}
```

`RunContainerRequest`: image, binds (workspace mount), cmd, env, auto_remove, …

### Адаптер

- **`BollardDockerAdapter`**: `bollard::Docker::connect_with_local_defaults()` (DooD socket / rootless discovery).
- Запрещено: `Command::new("docker")`.

### Пакет

**`packages/mcp-docker`** — отдельный maturin/PyO3 пакет (как `mcp-state`, `mcp-git`):

| Слой | Содержание |
|------|------------|
| `port` | `ContainerRuntime` trait + DTO |
| `adapter::bollard` | реализация порта |
| PyO3 | тонкая обёртка для FastMCP worker |

### Связь с ADR-0008

- **DooD / rootless** — по-прежнему модель доверия к host daemon.
- Меняется только **клиент**: CLI → **bollard**.
- DinD по-прежнему отклонён.

```text
┌─────────────┐     port      ┌──────────────────────┐
│ Build worker│ ────────────► │ ContainerRuntime     │
└─────────────┘               └──────────┬───────────┘
                                         │ adapter
                                         ▼
                              ┌──────────────────────┐
                              │ BollardDockerAdapter │
                              │ → docker.sock / API  │
                              └──────────────────────┘
```

## Consequences

### Positive

- Тестируемость: mock `ContainerRuntime` без Docker.
- Нет зависимости от Docker CLI binary.
- Согласовано с git-слоем (тот же hexagonal стиль).

### Negative / risks

- bollard async → в PyO3 нужен tokio runtime (`block_on` / pyo3-async).
- Socket DooD = host-root risk (как в ADR-0008).

## Alternatives considered

| Option | Why not |
|--------|---------|
| `docker` CLI subprocess | Запрещено по аналогии с git |
| shiplift (legacy) | Устарел относительно bollard |
| Только Buildah/Kaniko | Другая модель; v1 = run container для сборки |
