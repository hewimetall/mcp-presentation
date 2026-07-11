#!/usr/bin/env bash
# Build web (and optional PDF) from workspace mounted at /work.
set -euo pipefail

WORK="${WORK_DIR:-/work}"
OUT="${OUT_DIR:-${WORK}/out}"
DIST="${DIST_DIR:-${WORK}/dist}"
mkdir -p "${OUT}" "${DIST}"
cd "${WORK}"

TARGET="${1:-web}"

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
  for candidate in slides.md presentation.md index.md deck.md; do
    if [[ -f "${candidate}" ]]; then
      src="${candidate}"
      break
    fi
  done
  [[ -n "${src}" ]] || return 1
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
    echo "artifact=${DIST}"
    ;;
  web-pdf|pdf)
    if build_marp; then
      echo "artifact=${OUT}/web.pdf"
      ls -la "${OUT}/web.pdf"
    elif [[ -f package.json ]]; then
      build_npm
      # If build produced HTML, try headless print via chromium
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
      echo "artifact=${OUT}/web.pdf"
    else
      echo "error: need Marp markdown or npm project for web-pdf" >&2
      exit 1
    fi
    ;;
  *)
    echo "usage: entrypoint.sh [web|web-pdf|pdf]" >&2
    exit 2
    ;;
esac
