#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_NAME="${ENV_NAME:-agent}"
PROMPT="${*:-Please read demo_input.txt and count the length of my input.}"

cd "$PROJECT_DIR"

if command -v conda >/dev/null 2>&1; then
  CONDA_BIN="$(command -v conda)"
elif [ -x "$HOME/miniforge3/bin/conda" ]; then
  CONDA_BIN="$HOME/miniforge3/bin/conda"
elif [ -x "/root/miniforge3/bin/conda" ]; then
  CONDA_BIN="/root/miniforge3/bin/conda"
else
  if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
    echo "conda was not found for user $(id -un). Re-running with sudo because the MVP may be installed under root."
    exec sudo -E bash "$0" "$@"
  fi
  echo "conda not found. Run: bash scripts/setup_wsl.sh"
  exit 1
fi

RUNTIME_DIR="${AGENT_RUNTIME_DIR:-$PROJECT_DIR/.runtime}"
LLAMA_CPP_BIN="${LLAMA_CPP_BIN:-$RUNTIME_DIR/llama.cpp/build/bin/llama-server}"
LLAMA_CPP_MODEL_PATH="${LLAMA_CPP_MODEL_PATH:-$RUNTIME_DIR/models/qwen2.5-1.5b-instruct-q4_k_m.gguf}"
if [ ! -x "$LLAMA_CPP_BIN" ] || [ ! -f "$LLAMA_CPP_MODEL_PATH" ]; then
  echo "llama.cpp runtime or Qwen model is missing."
  echo "Run: bash scripts/ensure_llama_cpp_wsl.sh"
  exit 1
fi

"$CONDA_BIN" run -n "$ENV_NAME" python -m agent_edge "$PROMPT"
