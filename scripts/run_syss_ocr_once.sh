#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

INPUT=""
OUTPUT_ROOT=""
SYSS_DIR="${SYSS_PROJECT_DIR:-}"
SYSS_IMPORT="${SYSS_IMPORT_NAME:-}"
PYTHON_BIN="${OCR_PC_PYTHON:-${PYTHON:-python3}}"

usage() {
  cat <<'EOF'
Usage:
  scripts/run_syss_ocr_once.sh -i INPUT [-o OUTPUT_ROOT] [--syss-project-dir DIR] [--syss-import-name NAME]

Examples:
  scripts/run_syss_ocr_once.sh -i workspace_files/uploads/demo.pdf
  scripts/run_syss_ocr_once.sh -i /tmp/demo.png -o /tmp/ocr_outputs

Defaults:
  SYSS_PROJECT_DIR is optional. When omitted, the project-native sys_core.syss package is used.
  OUTPUT_ROOT=workspace_files/ocr_outputs
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -i|--input)
      INPUT="${2:-}"
      shift 2
      ;;
    -o|--output-root|--output-dir)
      OUTPUT_ROOT="${2:-}"
      shift 2
      ;;
    --syss-project-dir)
      SYSS_DIR="${2:-}"
      shift 2
      ;;
    --syss-import-name)
      SYSS_IMPORT="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "${INPUT}" ]]; then
  echo "Missing required --input" >&2
  usage >&2
  exit 2
fi

if [[ -z "${OUTPUT_ROOT}" ]]; then
  OUTPUT_ROOT="${PROJECT_ROOT}/workspace_files/ocr_outputs"
fi

export AGENT_OCR_BACKEND=syss
if [[ -n "${SYSS_DIR}" ]]; then
  export SYSS_PROJECT_DIR="${SYSS_DIR}"
else
  unset SYSS_PROJECT_DIR
fi
if [[ -n "${SYSS_IMPORT}" ]]; then
  export SYSS_IMPORT_NAME="${SYSS_IMPORT}"
fi

cd "${PROJECT_ROOT}"
cmd=(
  "${PYTHON_BIN}" -m agent_edge.syss_ocr_once
  --input "${INPUT}"
  --output-root "${OUTPUT_ROOT}"
)
if [[ -n "${SYSS_PROJECT_DIR:-}" ]]; then
  cmd+=(--syss-project-dir "${SYSS_PROJECT_DIR}")
fi
if [[ -n "${SYSS_IMPORT:-}" ]]; then
  cmd+=(--syss-import-name "${SYSS_IMPORT}")
fi

exec "${cmd[@]}"
