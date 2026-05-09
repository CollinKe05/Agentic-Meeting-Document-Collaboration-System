#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
mkdir -p logs

export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
echo "启动 Ollama: $OLLAMA_HOST"
ollama serve
