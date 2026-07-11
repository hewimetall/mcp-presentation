#!/usr/bin/env bash
# Build PDF from workspace mounted at /work.
# Prefers main.tex / presentation.tex; falls back to IR stub note.
set -euo pipefail

WORK="${WORK_DIR:-/work}"
OUT="${OUT_DIR:-${WORK}/out}"
mkdir -p "${OUT}"
cd "${WORK}"

TARGET="${1:-pdf}"
case "${TARGET}" in
  pdf|latex) ;;
  *)
    echo "usage: entrypoint.sh [pdf]" >&2
    exit 2
    ;;
esac

TEX=""
for candidate in main.tex presentation.tex slides.tex; do
  if [[ -f "${candidate}" ]]; then
    TEX="${candidate}"
    break
  fi
done

if [[ -z "${TEX}" ]]; then
  echo "error: no .tex source in ${WORK} (expected main.tex|presentation.tex|slides.tex)" >&2
  echo "hint: IR→LaTeX compiler will emit main.tex here in a later step" >&2
  exit 1
fi

# XeLaTeX for Unicode / Cyrillic fonts; latexmk drives rebuilds.
latexmk -xelatex -interaction=nonstopmode -halt-on-error \
  -outdir="${OUT}" \
  "${TEX}"

# Normalize artifact name for TaskStore
if [[ -f "${OUT}/${TEX%.tex}.pdf" ]]; then
  cp -f "${OUT}/${TEX%.tex}.pdf" "${OUT}/main.pdf"
fi

echo "artifact=${OUT}/main.pdf"
ls -la "${OUT}/main.pdf"
