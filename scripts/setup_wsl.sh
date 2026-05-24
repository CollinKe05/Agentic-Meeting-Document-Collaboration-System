#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_NAME="${ENV_NAME:-agent}"
PYTHON_VERSION="${PYTHON_VERSION:-3.11}"
MINIFORGE_DIR="${MINIFORGE_DIR:-$HOME/miniforge3}"

cd "$PROJECT_DIR"
mkdir -p logs

echo "[1/5] Checking base system tools"
if ! command -v curl >/dev/null 2>&1 || ! command -v zstd >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y curl ca-certificates zstd
  else
    echo "Missing curl or zstd, and apt-get is unavailable."
    exit 1
  fi
fi

echo "[2/5] Checking conda/miniforge"
if command -v conda >/dev/null 2>&1; then
  CONDA_BIN="$(command -v conda)"
elif [ -x "$MINIFORGE_DIR/bin/conda" ]; then
  CONDA_BIN="$MINIFORGE_DIR/bin/conda"
else
  echo "Installing Miniforge to $MINIFORGE_DIR"
  TMP_INSTALLER="/tmp/miniforge.sh"
  curl -L --fail -o "$TMP_INSTALLER" "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh"
  bash "$TMP_INSTALLER" -b -p "$MINIFORGE_DIR"
  CONDA_BIN="$MINIFORGE_DIR/bin/conda"
fi

echo "[3/5] Creating or reusing conda env: $ENV_NAME"
if ! "$CONDA_BIN" env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  "$CONDA_BIN" create -n "$ENV_NAME" "python=$PYTHON_VERSION" pip -y
elif ! "$CONDA_BIN" run -n "$ENV_NAME" python -m pip --version >/dev/null 2>&1; then
  "$CONDA_BIN" install -n "$ENV_NAME" pip -y
fi

echo "[4/5] Installing Python package"
"$CONDA_BIN" run -n "$ENV_NAME" python -m pip install --upgrade pip
"$CONDA_BIN" run -n "$ENV_NAME" python -m pip install -e .

echo "[5/5] Preparing CPU-only llama.cpp and Qwen GGUF"
bash scripts/ensure_llama_cpp_wsl.sh

echo "Running smoke test with llama.cpp backend"
"$CONDA_BIN" run -n "$ENV_NAME" python -m agent_edge --show-trace "Please read demo_input.txt and count the length of my input."

echo "Done. Next run: bash scripts/run_wsl.sh \"your task\""
