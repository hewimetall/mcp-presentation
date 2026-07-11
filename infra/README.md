# Builder images for mcp-presentation (used by bollard ContainerRuntime).

## Images

| Image | Tag | Role |
|-------|-----|------|
| LaTeX / PDF | `mcp-presentation/latex-builder:latest` | XeLaTeX + latexmk + fonts/Cyrillic/Beamer stack |
| Web (+ optional PDF) | `mcp-presentation/web-builder:latest` | Node 22, Marp CLI, Vite, system Chromium |

Workspace is always mounted at **`/work`**. Artifacts:

- LaTeX → `out/main.pdf`
- Web → `dist/` (HTML)
- Web PDF → `out/web.pdf`

## Build

```bash
# from repo root
make docker-build

# or
docker build -t mcp-presentation/latex-builder:latest infra/docker/latex
docker build -t mcp-presentation/web-builder:latest infra/docker/web
```

## Run (manual)

```bash
# PDF (needs main.tex|presentation.tex|slides.tex in workspace)
docker run --rm -v "$PWD/workspaces/demo:/work" mcp-presentation/latex-builder:latest pdf

# Web (package.json build or slides.md via Marp)
docker run --rm -v "$PWD/workspaces/demo:/work" mcp-presentation/web-builder:latest web

# HTML → PDF (Marp or Chromium print)
docker run --rm -v "$PWD/workspaces/demo:/work" mcp-presentation/web-builder:latest web-pdf
```

Compose:

```bash
WORKSPACE=$PWD/workspaces/demo docker compose -f infra/docker/compose.yaml run --rm latex pdf
WORKSPACE=$PWD/workspaces/demo docker compose -f infra/docker/compose.yaml run --rm web web
```

## Worker mapping (planned)

| `build_presentation` target | Image | CMD |
|-----------------------------|-------|-----|
| `pdf` | `mcp-presentation/latex-builder:latest` | `pdf` |
| `web` | `mcp-presentation/web-builder:latest` | `web` |

Binds: `<abs workspace>:/work` via bollard `ContainerRuntime.run` (ADR-0012).

## Note on IR

Canonical IR is JSON (`presentation.ir.json`, ADR-0006). Compilers IR→`.tex` / IR→web will land in the worker; images already provide the heavy toolchain.
