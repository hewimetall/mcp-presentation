#!/usr/bin/env bash
# Build web (and optional PDF) from workspace mounted at /work.
# Always refreshes out/slides/slide.NNN.png when Marp source or a PDF is available.
set -euo pipefail

WORK="${WORK_DIR:-/work}"
OUT="${OUT_DIR:-${WORK}/out}"
DIST="${DIST_DIR:-${WORK}/dist}"
mkdir -p "${OUT}" "${DIST}"
cd "${WORK}"

TARGET="${1:-web}"

find_marp_src() {
  for candidate in slides.md presentation.md index.md deck.md; do
    if [[ -f "${candidate}" ]]; then
      echo "${candidate}"
      return 0
    fi
  done
  return 1
}

refresh_slide_pngs_from_marp() {
  local src="$1"
  local slides="${OUT}/slides"
  rm -rf "${slides}"
  mkdir -p "${slides}"
  marp "${src}" --images png --allow-local-files \
    --browser-path "${CHROME_PATH:-/usr/bin/chromium}" \
    -o "${slides}/slide.png"
  shopt -s nullglob
  local pngs=("${slides}"/slide.*.png)
  if [[ ${#pngs[@]} -eq 0 ]]; then
    echo "error: marp --images produced no PNGs" >&2
    exit 1
  fi
  echo "slides=${slides} (count=${#pngs[@]})"
}

refresh_slide_pngs_from_pdf() {
  local pdf="$1"
  local slides="${OUT}/slides"
  rm -rf "${slides}"
  mkdir -p "${slides}"
  pdftoppm -png -r 144 "${pdf}" "${slides}/page"
  local i=1
  shopt -s nullglob
  local pages=("${slides}"/page-*.png)
  if [[ ${#pages[@]} -eq 0 ]]; then
    echo "error: pdftoppm produced no pages from ${pdf}" >&2
    exit 1
  fi
  mapfile -t pages < <(printf '%s\n' "${pages[@]}" | sort -V)
  for f in "${pages[@]}"; do
    printf -v dest "${slides}/slide.%03d.png" "${i}"
    mv "${f}" "${dest}"
    i=$((i + 1))
  done
  echo "slides=${slides} (count=$((i - 1)))"
}

ensure_slide_pngs() {
  local src=""
  if src="$(find_marp_src)"; then
    refresh_slide_pngs_from_marp "${src}"
    return 0
  fi
  if [[ -f "${OUT}/web.pdf" ]]; then
    refresh_slide_pngs_from_pdf "${OUT}/web.pdf"
    return 0
  fi
  echo "error: cannot emit slide PNGs (need Marp markdown or out/web.pdf)" >&2
  exit 1
}

build_npm() {
  if [[ -f package-lock.json ]]; then
    npm ci
  elif [[ -f package.json ]]; then
    npm install
  else
    return 1
  fi
  if npm run | grep -qE '^  build'; then
    npm run build
  else
    echo "error: package.json has no build script" >&2
    exit 1
  fi
}

build_marp() {
  local src=""
  src="$(find_marp_src)" || return 1
  mkdir -p "${DIST}"
  marp "${src}" --html --allow-local-files -o "${DIST}/index.html"
  if [[ "${TARGET}" == "web-pdf" || "${TARGET}" == "pdf" ]]; then
    marp "${src}" --pdf --allow-local-files \
      --browser-path "${CHROME_PATH:-/usr/bin/chromium}" \
      -o "${OUT}/web.pdf"
  fi
}

case "${TARGET}" in
  web)
    if [[ -f package.json ]]; then
      build_npm
    elif build_marp; then
      :
    else
      echo "error: need package.json (npm build) or slides.md (Marp) in ${WORK}" >&2
      exit 1
    fi
    ensure_slide_pngs
    echo "artifact=${DIST}"
    ;;
  web-pdf|pdf)
    if build_marp; then
      ensure_slide_pngs
      echo "artifact=${OUT}/web.pdf"
      ls -la "${OUT}/web.pdf"
    elif [[ -f package.json ]]; then
      build_npm
      HTML=""
      for candidate in "${DIST}/index.html" index.html; do
        if [[ -f "${candidate}" ]]; then
          HTML="${candidate}"
          break
        fi
      done
      if [[ -z "${HTML}" ]]; then
        echo "error: no HTML to print after npm build" >&2
        exit 1
      fi
      chromium --headless --disable-gpu --no-sandbox \
        --print-to-pdf="${OUT}/web.pdf" \
        "file://${WORK}/${HTML}"
      ensure_slide_pngs
      echo "artifact=${OUT}/web.pdf"
    else
      echo "error: need Marp markdown or npm project for web-pdf" >&2
      exit 1
    fi
    ;;
  slide-image)
    # Images-only refresh (same PNG layout as full web/pdf builds).
    ensure_slide_pngs
    echo "artifact=${OUT}/slides"
    ls -la "${OUT}/slides"
    ;;
  *)
    echo "usage: entrypoint.sh [web|web-pdf|pdf|slide-image]" >&2
    exit 2
    ;;
esac
