#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${AGENT_RUNTIME_DIR:-$PROJECT_DIR/.runtime}"
LLAMA_CPP_DIR="${LLAMA_CPP_SOURCE_DIR:-$RUNTIME_DIR/llama.cpp}"
MODEL_DIR="${LLAMA_CPP_MODEL_DIR:-$RUNTIME_DIR/models}"
MODEL_FILE="${LLAMA_CPP_MODEL_FILE:-qwen2.5-1.5b-instruct-q4_k_m.gguf}"
MODEL_REPO="${LLAMA_CPP_MODEL_REPO:-Qwen/Qwen2.5-1.5B-Instruct-GGUF}"

cd "$PROJECT_DIR"
mkdir -p "$RUNTIME_DIR/logs" "$MODEL_DIR"

echo "[1/4] Checking build tools"
if command -v apt-get >/dev/null 2>&1; then
  missing=()
  for tool in git cmake make g++ python3; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      missing+=("$tool")
    fi
  done
  if [ "${#missing[@]}" -gt 0 ]; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y git cmake build-essential python3 python3-pip
  fi
fi

echo "[2/4] Preparing llama.cpp source"
if [ ! -d "$LLAMA_CPP_DIR/.git" ]; then
  git clone https://github.com/ggml-org/llama.cpp "$LLAMA_CPP_DIR"
fi

echo "[3/4] Building CPU-only llama.cpp"
cmake -S "$LLAMA_CPP_DIR" -B "$LLAMA_CPP_DIR/build" -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON
cmake --build "$LLAMA_CPP_DIR/build" --target llama-server llama-cli -j"$(nproc)"

echo "[4/4] Downloading Qwen2.5-1.5B GGUF if needed"
if [ ! -f "$MODEL_DIR/$MODEL_FILE" ]; then
  python3 -m pip install -U huggingface_hub
  MODEL_REPO="$MODEL_REPO" MODEL_FILE="$MODEL_FILE" MODEL_DIR="$MODEL_DIR" python3 -c "from huggingface_hub import hf_hub_download; import os; hf_hub_download(repo_id=os.environ['MODEL_REPO'], filename=os.environ['MODEL_FILE'], local_dir=os.environ['MODEL_DIR'], local_dir_use_symlinks=False)"
fi

cat <<EOF
Done.
LLAMA_CPP_BIN=$LLAMA_CPP_DIR/build/bin/llama-server
LLAMA_CPP_MODEL_PATH=$MODEL_DIR/$MODEL_FILE
EOF
