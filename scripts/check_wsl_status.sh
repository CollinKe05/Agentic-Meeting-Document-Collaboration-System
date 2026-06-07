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
if command -v conda >/dev/null 2>&1; then
  CONDA_BIN="$(command -v conda)"
elif [ -x "$HOME/miniforge3/bin/conda" ]; then
  CONDA_BIN="$HOME/miniforge3/bin/conda"
elif [ -x /root/miniforge3/bin/conda ]; then
  CONDA_BIN="/root/miniforge3/bin/conda"
fi

if [ -n "${CONDA_BIN:-}" ]; then
  CHECK_SCRIPT="$(mktemp)"
  cat > "$CHECK_SCRIPT" <<'PY'
import importlib

mods = [
    "langgraph",
    "requests",
    "cv2",
    "onnxruntime",
    "fitz",
    "fastapi",
    "uvicorn",
    "numpy",
    "sounddevice",
    "soundfile",
    "sherpa_onnx",
]
missing = []
for name in mods:
    try:
        importlib.import_module(name)
    except Exception as exc:
        missing.append(f"{name}: {type(exc).__name__}: {exc}")
if missing:
    print("python deps missing or broken")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)
print("python deps ok")
PY
  "$CONDA_BIN" run -n "${ENV_NAME:-agent}" python "$CHECK_SCRIPT"
  rm -f "$CHECK_SCRIPT"
else
  echo "conda: missing"
fi
