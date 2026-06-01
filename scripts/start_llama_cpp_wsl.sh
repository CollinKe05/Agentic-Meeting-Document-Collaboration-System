#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${AGENT_RUNTIME_DIR:-$PROJECT_DIR/.runtime}"
LLAMA_CPP_BIN="${LLAMA_CPP_BIN:-$RUNTIME_DIR/llama.cpp/build/bin/llama-server}"
LLAMA_CPP_MODEL_PATH="${LLAMA_CPP_MODEL_PATH:-$RUNTIME_DIR/models/qwen2.5-1.5b-instruct-q4_k_m.gguf}"
LLAMA_CPP_MODEL="${LLAMA_CPP_MODEL:-qwen2.5-1.5b-instruct-q4_k_m}"
LLAMA_CPP_THREADS="${LLAMA_CPP_THREADS:-4}"
LLAMA_CPP_CTX_SIZE="${LLAMA_CPP_CTX_SIZE:-4096}"
LLAMA_CPP_FLASH_ATTN="${LLAMA_CPP_FLASH_ATTN:-1}"
LLAMA_CPP_HOST="${LLAMA_CPP_HOST:-127.0.0.1}"
LLAMA_CPP_PORT="${LLAMA_CPP_PORT:-8080}"

case "${LLAMA_CPP_FLASH_ATTN,,}" in
  1|true|yes|on)
    FLASH_ATTN_ARGS=(--flash-attn on)
    ;;
  0|false|no|off)
    FLASH_ATTN_ARGS=(--flash-attn off)
    ;;
  auto)
    FLASH_ATTN_ARGS=(--flash-attn auto)
    ;;
  "")
    FLASH_ATTN_ARGS=()
    ;;
  *)
    echo "Invalid LLAMA_CPP_FLASH_ATTN=$LLAMA_CPP_FLASH_ATTN. Use 1/0, on/off, or auto." >&2
    exit 1
    ;;
esac

cd "$PROJECT_DIR"

exec "$LLAMA_CPP_BIN" \
  -m "$LLAMA_CPP_MODEL_PATH" \
  --alias "$LLAMA_CPP_MODEL" \
  -c "$LLAMA_CPP_CTX_SIZE" \
  -t "$LLAMA_CPP_THREADS" \
  --host "$LLAMA_CPP_HOST" \
  --port "$LLAMA_CPP_PORT" \
  "${FLASH_ATTN_ARGS[@]}"
