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

## Release (GHCR)

Тег `v*` запускает [`.github/workflows/release.yml`](../.github/workflows/release.yml):
сборка обоих образов и push в GHCR + публикация docs (Pages + assets релиза).

```bash
docker pull ghcr.io/hewimetall/mcp-presentation/latex-builder:latest
docker pull ghcr.io/hewimetall/mcp-presentation/web-builder:latest

# pin to a release
docker pull ghcr.io/hewimetall/mcp-presentation/latex-builder:0.1.0
docker pull ghcr.io/hewimetall/mcp-presentation/web-builder:0.1.0
```

Для worker: `MCP_LATEX_IMAGE` / `MCP_WEB_IMAGE` → эти GHCR-теги.

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

## Worker mapping

| `build_presentation` target | Image | CMD |
|-----------------------------|-------|-----|
| `pdf` | `mcp-presentation/latex-builder:latest` | `pdf` → `out/main.pdf` + `out/slides/` (pdftoppm) |
| `web` | `mcp-presentation/web-builder:latest` | `web` → `dist/` + `out/slides/` |
| `web-pdf` | `mcp-presentation/web-builder:latest` | `web-pdf` → `out/web.pdf` + `out/slides/` |
| `slide-image` | `mcp-presentation/web-builder:latest` | images-only → `out/slides/slide.NNN.png` |

Binds: `<abs workspace>:/work` via bollard `ContainerRuntime.run` (ADR-0012).

After `build_presentation`, a daemon **BuildWorker** claims the task, validates
`presentation.ir.json` (Pydantic), optionally compiles IR → `main.tex` / `slides.md`,
then runs the image.

Deploy uses a **local adapter** (no container): copy artifact → `out/deployed/` + manifest.

## Note on IR

Canonical IR is JSON (`presentation.ir.json`, ADR-0006). Schema:
[`schemas/presentation.ir.schema.json`](../schemas/presentation.ir.schema.json).
The worker compiles IR → Beamer / Marp when no native source is present.
