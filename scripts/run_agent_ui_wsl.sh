#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${ENV_NAME:-agent}"

if command -v conda >/dev/null 2>&1; then
  CONDA_BIN="$(command -v conda)"
elif [ -x "$HOME/miniforge3/bin/conda" ]; then
  CONDA_BIN="$HOME/miniforge3/bin/conda"
elif [ -x "/root/miniforge3/bin/conda" ]; then
  CONDA_BIN="/root/miniforge3/bin/conda"
else
  echo "conda not found. Run: bash scripts/setup_wsl.sh" >&2
  exit 1
fi

exec "$CONDA_BIN" run -n "$ENV_NAME" python -m agent_edge.web_app
