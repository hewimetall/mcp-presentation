#!/usr/bin/env bash
# Build PDF from workspace mounted at /work.
# Expects main.tex|presentation.tex|slides.tex (IR is compiled to main.tex by the host worker).
# Always refreshes out/slides/slide.NNN.png from the PDF (pdftoppm).
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
  echo "hint: host BuildWorker emits main.tex from presentation.ir.json before the container runs" >&2
  exit 1
fi

# XeLaTeX for Unicode / Cyrillic fonts; latexmk drives rebuilds.
latexmk -xelatex -interaction=nonstopmode -halt-on-error \
  -outdir="${OUT}" \
  "${TEX}"

# Normalize artifact name for TaskStore
src_pdf="${OUT}/${TEX%.tex}.pdf"
if [[ -f "${src_pdf}" && "${src_pdf}" != "${OUT}/main.pdf" ]]; then
  cp -f "${src_pdf}" "${OUT}/main.pdf"
fi

if [[ ! -f "${OUT}/main.pdf" ]]; then
  echo "error: missing ${OUT}/main.pdf after latexmk" >&2
  exit 1
fi

# Refresh slide PNGs on every PDF rebuild (1-based: slide.001.png …).
SLIDES="${OUT}/slides"
rm -rf "${SLIDES}"
mkdir -p "${SLIDES}"
pdftoppm -png -r 144 "${OUT}/main.pdf" "${SLIDES}/page"
i=1
shopt -s nullglob
pages=("${SLIDES}"/page-*.png)
if [[ ${#pages[@]} -eq 0 ]]; then
  echo "error: pdftoppm produced no pages from ${OUT}/main.pdf" >&2
  exit 1
fi
# Sort numerically by page index embedded in page-N.png
mapfile -t pages < <(printf '%s\n' "${pages[@]}" | sort -V)
for f in "${pages[@]}"; do
  printf -v dest "${SLIDES}/slide.%03d.png" "${i}"
  mv "${f}" "${dest}"
  i=$((i + 1))
done

echo "artifact=${OUT}/main.pdf"
echo "slides=${SLIDES} (count=$((i - 1)))"
ls -la "${OUT}/main.pdf" "${SLIDES}"
