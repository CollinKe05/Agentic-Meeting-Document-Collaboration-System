#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_NAME="${OLLAMA_MODEL:-qwen2.5:1.5b}"

cd "$PROJECT_DIR"
mkdir -p logs

if ! command -v zstd >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y zstd
fi

if ! command -v ollama >/dev/null 2>&1; then
  OLLAMA_INSTALLER="/tmp/ollama-install.sh"
  curl --retry 5 --retry-delay 3 --retry-all-errors -fsSL https://ollama.com/install.sh -o "$OLLAMA_INSTALLER"
  sh "$OLLAMA_INSTALLER"
fi

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

echo "Pulling model: $MODEL_NAME"
ollama pull "$MODEL_NAME"

echo "Current Ollama models:"
ollama list
