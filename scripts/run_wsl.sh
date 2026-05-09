#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_NAME="${ENV_NAME:-agent}"
MODEL_NAME="${OLLAMA_MODEL:-qwen2.5:1.5b}"
BACKEND="${AGENT_LLM_BACKEND:-ollama}"
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
    echo "conda was not found for user $(id -un). Re-running this script with sudo because the MVP was installed under root."
    exec sudo -E bash "$0" "$@"
  fi
  echo "conda not found. Run: bash scripts/setup_wsl.sh"
  echo "If the setup was installed under root, run: sudo bash scripts/run_wsl.sh \"$PROMPT\""
  exit 1
fi

if [ "$BACKEND" = "ollama" ]; then
  if ! command -v ollama >/dev/null 2>&1; then
    echo "ollama not found. Run: bash scripts/setup_wsl.sh"
    exit 1
  fi

  mkdir -p logs
  if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "Starting Ollama service..."
    nohup ollama serve > logs/ollama.log 2>&1 &
  fi

  for _ in $(seq 1 40); do
    if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  curl -fsS http://127.0.0.1:11434/api/tags >/dev/null

  if ! ollama list | awk 'NR > 1 {print $1}' | grep -qx "$MODEL_NAME"; then
    echo "Pulling model: $MODEL_NAME"
    ollama pull "$MODEL_NAME"
  fi
fi

"$CONDA_BIN" run -n "$ENV_NAME" python -m agent_edge --backend "$BACKEND" --model "$MODEL_NAME" "$PROMPT"
