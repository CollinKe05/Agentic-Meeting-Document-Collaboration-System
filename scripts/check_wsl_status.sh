#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${AGENT_RUNTIME_DIR:-$PROJECT_DIR/.runtime}"

echo "== os =="
cat /etc/os-release | grep PRETTY_NAME || true

echo "== build tools =="
for tool in git cmake g++ python3; do
  if command -v "$tool" >/dev/null 2>&1; then
    echo "$tool: $(command -v "$tool")"
  else
    echo "$tool: missing"
  fi
done

echo "== llama.cpp =="
LLAMA_CPP_BIN="${LLAMA_CPP_BIN:-$RUNTIME_DIR/llama.cpp/build/bin/llama-server}"
if [ -x "$LLAMA_CPP_BIN" ]; then
  echo "llama-server: $LLAMA_CPP_BIN"
else
  echo "llama-server: missing"
fi

echo "== qwen gguf =="
LLAMA_CPP_MODEL_PATH="${LLAMA_CPP_MODEL_PATH:-$RUNTIME_DIR/models/qwen2.5-1.5b-instruct-q4_k_m.gguf}"
if [ -f "$LLAMA_CPP_MODEL_PATH" ]; then
  ls -lh "$LLAMA_CPP_MODEL_PATH"
else
  echo "model: missing"
fi

echo "== llama api =="
if curl -fsS http://127.0.0.1:8080/v1/models >/dev/null 2>&1; then
  echo "running"
  curl -fsS http://127.0.0.1:8080/v1/models || true
else
  echo "not running"
fi

echo "== conda agent =="
if [ -x /root/miniforge3/bin/conda ]; then
  /root/miniforge3/bin/conda run -n agent python -c 'import langgraph, requests; print("python deps ok")'
else
  echo "missing /root/miniforge3/bin/conda"
fi
