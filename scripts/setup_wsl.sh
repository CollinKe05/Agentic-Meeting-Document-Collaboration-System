#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_NAME="${ENV_NAME:-agent}"
PYTHON_VERSION="${PYTHON_VERSION:-3.11}"
MODEL_NAME="${OLLAMA_MODEL:-qwen2.5:1.5b}"
MINIFORGE_DIR="${MINIFORGE_DIR:-$HOME/miniforge3}"

cd "$PROJECT_DIR"
mkdir -p logs

echo "[0/6] 检查基础系统工具"
if ! command -v curl >/dev/null 2>&1 || ! command -v zstd >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y curl ca-certificates zstd
  else
    echo "缺少 curl 或 zstd，也没有 apt-get，无法继续自动部署"
    exit 1
  fi
fi

echo "[1/6] 检查 conda/miniforge"
if command -v conda >/dev/null 2>&1; then
  CONDA_BIN="$(command -v conda)"
elif [ -x "$MINIFORGE_DIR/bin/conda" ]; then
  CONDA_BIN="$MINIFORGE_DIR/bin/conda"
else
  echo "未发现 conda，开始安装 Miniforge 到 $MINIFORGE_DIR"
  TMP_INSTALLER="/tmp/miniforge.sh"
  curl -L --fail -o "$TMP_INSTALLER" "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh"
  bash "$TMP_INSTALLER" -b -p "$MINIFORGE_DIR"
  CONDA_BIN="$MINIFORGE_DIR/bin/conda"
fi

echo "[2/6] 创建或复用 conda 环境：$ENV_NAME"
if ! "$CONDA_BIN" env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  "$CONDA_BIN" create -n "$ENV_NAME" "python=$PYTHON_VERSION" pip -y
elif ! "$CONDA_BIN" run -n "$ENV_NAME" python -m pip --version >/dev/null 2>&1; then
  "$CONDA_BIN" install -n "$ENV_NAME" pip -y
fi

echo "[3/6] 安装 Python 依赖"
"$CONDA_BIN" run -n "$ENV_NAME" python -m pip install --upgrade pip
"$CONDA_BIN" run -n "$ENV_NAME" python -m pip install -e .

echo "[4/6] 检查 Ollama"
if ! command -v ollama >/dev/null 2>&1; then
  echo "未发现 Ollama，开始安装"
  OLLAMA_INSTALLER="/tmp/ollama-install.sh"
  curl --retry 5 --retry-delay 3 --retry-all-errors -fsSL https://ollama.com/install.sh -o "$OLLAMA_INSTALLER"
  sh "$OLLAMA_INSTALLER"
fi

echo "[5/6] 启动 Ollama 并拉取模型：$MODEL_NAME"
if ! curl -fsS "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
  nohup ollama serve > logs/ollama.log 2>&1 &
  sleep 3
fi
ollama pull "$MODEL_NAME"

echo "[6/6] 运行 agent 冒烟测试"
"$CONDA_BIN" run -n "$ENV_NAME" python -m agent_edge --backend ollama --model "$MODEL_NAME" --show-trace "请读取 demo_input.txt，并统计我的输入长度。"

echo "Done. Next run: bash scripts/run_wsl.sh \"your task\""
