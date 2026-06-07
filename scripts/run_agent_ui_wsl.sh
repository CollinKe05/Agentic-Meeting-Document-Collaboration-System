#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${ENV_NAME:-agent}"

CONDA_CANDIDATES=()
if command -v conda >/dev/null 2>&1; then
  CONDA_CANDIDATES+=("$(command -v conda)")
fi
CONDA_CANDIDATES+=("$HOME/miniforge3/bin/conda" "/root/miniforge3/bin/conda")

CONDA_BIN=""
for candidate in "${CONDA_CANDIDATES[@]}"; do
  if [ -x "$candidate" ] && "$candidate" env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
    CONDA_BIN="$candidate"
    break
  fi
done

if [ -z "$CONDA_BIN" ]; then
  echo "conda env '$ENV_NAME' not found. Checked:" >&2
  printf '  %s\n' "${CONDA_CANDIDATES[@]}" >&2
  echo "Run: bash scripts/setup_wsl.sh" >&2
  exit 1
fi

exec "$CONDA_BIN" run -n "$ENV_NAME" python -m agent_edge.web_app
