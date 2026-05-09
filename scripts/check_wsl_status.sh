#!/usr/bin/env bash
set -euo pipefail

echo "== os =="
cat /etc/os-release | grep PRETTY_NAME || true

echo "== zstd =="
if command -v zstd >/dev/null 2>&1; then
  zstd --version
else
  echo "missing"
fi

echo "== ollama =="
if command -v ollama >/dev/null 2>&1; then
  ollama --version || true
else
  echo "missing"
fi

echo "== ollama api =="
if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "running"
  curl -fsS http://127.0.0.1:11434/api/tags || true
else
  echo "not running"
fi

echo "== conda agent =="
if [ -x /root/miniforge3/bin/conda ]; then
  /root/miniforge3/bin/conda run -n agent python -c 'import langgraph, requests; print("python deps ok")'
else
  echo "missing conda"
fi
