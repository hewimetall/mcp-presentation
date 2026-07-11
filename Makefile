# Lint / format helpers for Python (ruff, mypy) and Rust (fmt, clippy).
# Usage: make lint | make fmt | make check

RUST_CRATES := . packages/mcp-state packages/mcp-git packages/mcp-docker

LATEX_IMAGE := mcp-presentation/latex-builder:latest
WEB_IMAGE := mcp-presentation/web-builder:latest

.PHONY: fmt fmt-py fmt-rust lint lint-py lint-rust check test docker-build docker-build-latex docker-build-web

fmt: fmt-py fmt-rust

fmt-py:
	ruff check --fix .
	ruff format .

fmt-rust:
	@set -e; for d in $(RUST_CRATES); do \
		echo "==> rustfmt $$d"; \
		(cd $$d && cargo fmt); \
	done

lint: lint-py lint-rust

lint-py:
	ruff check .
	ruff format --check .
	mypy

lint-rust:
	@set -e; for d in $(RUST_CRATES); do \
		echo "==> rustfmt --check $$d"; \
		(cd $$d && cargo fmt -- --check); \
		echo "==> clippy $$d"; \
		(cd $$d && cargo clippy --all-targets -- -D warnings); \
	done

check: lint test

test:
	pytest -q

docker-build: docker-build-latex docker-build-web

docker-build-latex:
	docker build -t $(LATEX_IMAGE) infra/docker/latex

docker-build-web:
	docker build -t $(WEB_IMAGE) infra/docker/web
