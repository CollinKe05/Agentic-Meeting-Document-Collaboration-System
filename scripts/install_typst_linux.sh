#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
INSTALL_DIR="${TYPST_INSTALL_DIR:-${PROJECT_ROOT}/.runtime/bin}"
VERSION="${TYPST_VERSION:-0.14.2}"
ARCHIVE="${TYPST_ARCHIVE:-${1:-}}"

case "$(uname -m)" in
  x86_64|amd64)
    TARGET="x86_64-unknown-linux-musl"
    ;;
  aarch64|arm64)
    TARGET="aarch64-unknown-linux-musl"
    ;;
  *)
    echo "Unsupported CPU arch: $(uname -m)" >&2
    exit 2
    ;;
esac

mkdir -p "${INSTALL_DIR}"
TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

if [[ -z "${ARCHIVE}" ]]; then
  ARCHIVE="${TMP_DIR}/typst-${TARGET}.tar.xz"
  URL="https://github.com/typst/typst/releases/download/v${VERSION}/typst-${TARGET}.tar.xz"
  echo "Downloading Typst ${VERSION} for ${TARGET}"
  if command -v curl >/dev/null 2>&1; then
    curl -fL "${URL}" -o "${ARCHIVE}"
  elif command -v wget >/dev/null 2>&1; then
    wget -O "${ARCHIVE}" "${URL}"
  else
    echo "curl/wget not found. Set TYPST_ARCHIVE=/path/to/typst-${TARGET}.tar.xz for offline install." >&2
    exit 2
  fi
fi

if [[ ! -f "${ARCHIVE}" ]]; then
  echo "Typst archive not found: ${ARCHIVE}" >&2
  exit 2
fi

tar -xf "${ARCHIVE}" -C "${TMP_DIR}"
TYPST_BIN="$(find "${TMP_DIR}" -type f -name typst | head -n 1)"
if [[ -z "${TYPST_BIN}" ]]; then
  echo "typst binary not found in archive: ${ARCHIVE}" >&2
  exit 2
fi

install -m 0755 "${TYPST_BIN}" "${INSTALL_DIR}/typst"
"${INSTALL_DIR}/typst" --version

cat <<EOF

Typst installed:
  ${INSTALL_DIR}/typst

Recommended runtime env:
  export TYPST_BIN="${INSTALL_DIR}/typst"
  export PATH="${INSTALL_DIR}:\$PATH"
EOF
