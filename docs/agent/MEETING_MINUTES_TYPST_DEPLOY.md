# 会议纪要 Typst 部署与端侧迁移指南

目标：在 Windows 上开发代码后，直接复制到端侧 Linux，端侧能够开箱运行会议纪要排版功能，并生成：

- `minutes.json`：结构化会议纪要数据。
- `minutes.md`：Markdown 会议纪要。
- `minutes.typ`：Typst 排版源码。
- `minutes.pdf`：Typst 编译后的 PDF。
- `transcript.txt`：本次使用的会议转写副本。

## 1. 功能调用链

会议纪要排版不是让模型直接写 Typst，而是走稳定的“结构化 JSON + 模板渲染”链路：

```text
会议转写 txt
  -> Agent Planner 确定调用 FORMAT_MEETING_MINUTES
  -> agent_edge/local_actions.py
  -> agent_edge/meeting_formatter.py
  -> LLM 整理为 minutes.json
  -> templates/meeting_minutes/standard.typ 渲染 minutes.typ
  -> typst compile minutes.typ minutes.pdf
```

相关文件：

```text
agent_edge/meeting_formatter.py
agent_edge/local_actions.py
agent_edge/graph.py
agent_edge/event_agent.py
skills/meeting_minutes_skill.md
templates/meeting_minutes/standard.typ
scripts/install_typst_linux.sh
scripts/check_meeting_minutes_typst.py
```

核心工具名：

```text
FORMAT_MEETING_MINUTES
```

推荐用户提示：

```text
请将会议转写文件 meeting_2026-06-01_20-32-10.txt 格式化排版成会议纪要，使用 Typst 模板并导出 PDF。
```

注意：会议转写文件必须位于 `workspace_files/` 下，不能传绝对路径。会议记录结束后会自动归档到 `workspace_files/meeting_records/`，右侧“会议纪要导出”会直接列出这个目录。

## 2. Windows 开发，Linux 运行

代码写在 Windows 项目目录：

```powershell
C:\Users\19653\Desktop\agent
```

WSL 中对应路径：

```bash
/mnt/c/Users/19653/Desktop/agent
```

端侧 Linux 推荐路径：

```bash
/home/sunrise/llama/llama.cpp/agent-main
```

端侧真正需要的是同一套项目文件：

```text
agent_edge/
skills/
templates/
scripts/
index.html
agent-ui-runtime.js
tailwind.min.js
requirements.txt
pyproject.toml
workspace_files/
```

不建议复制这些运行产物：

```text
.git/
__pycache__/
.runtime/logs/
workspace_files/ocr_outputs/
workspace_files/meeting_outputs/
workspace_files/uploads/  # 视情况，测试上传文件可不复制
```

## 3. Typst 部署方式

`agent_edge/meeting_formatter.py` 会按下面顺序寻找 Typst：

```text
1. TYPST_BIN 环境变量
2. 项目内 .runtime/bin/typst
3. PATH 中的 typst
```

因此最稳妥的端侧部署方式是把 Typst 放进项目内：

```text
/home/sunrise/llama/llama.cpp/agent-main/.runtime/bin/typst
```

这样复制项目时不会依赖系统全局安装。

### 3.1 在线安装

端侧 Linux 有网络时，在项目根目录执行：

```bash
cd /home/sunrise/llama/llama.cpp/agent-main
bash scripts/install_typst_linux.sh
```

脚本会根据 CPU 架构自动选择：

```text
x86_64  -> typst-x86_64-unknown-linux-musl.tar.xz
aarch64 -> typst-aarch64-unknown-linux-musl.tar.xz
```

默认安装到：

```text
.runtime/bin/typst
```

验证：

```bash
.runtime/bin/typst --version
```

### 3.2 离线安装

如果端侧不能联网，在 Windows 或其他有网机器下载 Linux 版 Typst 压缩包。

下载来源：

- Typst 官方开源页面：https://typst.app/open-source/
- Typst GitHub Releases：https://github.com/typst/typst/releases

根据端侧架构选择：

```bash
uname -m
```

常见选择：

```text
x86_64  下载 typst-x86_64-unknown-linux-musl.tar.xz
aarch64 下载 typst-aarch64-unknown-linux-musl.tar.xz
```

把压缩包复制到端侧，例如：

```text
/home/sunrise/typst-aarch64-unknown-linux-musl.tar.xz
```

然后在项目根目录安装：

```bash
cd /home/sunrise/llama/llama.cpp/agent-main
TYPST_ARCHIVE=/home/sunrise/typst-aarch64-unknown-linux-musl.tar.xz bash scripts/install_typst_linux.sh
```

验证：

```bash
.runtime/bin/typst --version
```

## 4. 字体部署

中文 PDF 需要 CJK 字体。模板已优先使用：

```text
Noto Sans CJK SC
Noto Serif CJK SC
DejaVu Sans
```

端侧有网络时：

```bash
sudo apt update
sudo apt install -y fonts-noto-cjk fontconfig
fc-cache -fv
```

端侧离线时，把字体复制到用户字体目录：

```bash
mkdir -p ~/.local/share/fonts
cp /path/to/NotoSansCJK*.otf ~/.local/share/fonts/
cp /path/to/NotoSerifCJK*.otf ~/.local/share/fonts/
fc-cache -fv
```

也可以使用项目内字体目录：

```bash
mkdir -p .runtime/fonts
cp /path/to/NotoSansCJK*.otf .runtime/fonts/
export TYPST_FONT_PATHS="$PWD/.runtime/fonts"
```

建议把下面这行写入 `.runtime/edge.env`：

```bash
export TYPST_FONT_PATHS=/home/sunrise/llama/llama.cpp/agent-main/.runtime/fonts
```

## 5. 端侧环境变量

建议 `.runtime/edge.env` 至少包含：

```bash
export AGENT_PROJECT_DIR=/home/sunrise/llama/llama.cpp/agent-main
export AGENT_RUNTIME_DIR=$AGENT_PROJECT_DIR/.runtime
export AGENT_WORKSPACE_DIR=$AGENT_PROJECT_DIR/workspace_files
export AGENT_SKILLS_DIR=$AGENT_PROJECT_DIR/skills
export AGENT_DB_PATH=$AGENT_RUNTIME_DIR/agent_tasks.sqlite3

export LLAMA_CPP_BIN=/home/sunrise/llama/llama.cpp/build/bin/llama-server
export LLAMA_CPP_MODEL_PATH=/root/agent_models/MiniCPM5-1B-Q4_K_M.gguf
export LLAMA_CPP_MODEL=MiniCPM5-1B-Q4_K_M
export LLAMA_CPP_BASE_URL=http://127.0.0.1:8080/v1
export LLAMA_CPP_THREADS=4
export LLAMA_CPP_CTX_SIZE=2048
export LLAMA_CPP_FLASH_ATTN=off

export OCR_PC_PROJECT_DIR=$AGENT_PROJECT_DIR/OCR_pc/OCR_pc
export SHERPA_ASR_DIR=$AGENT_PROJECT_DIR/sherpa_asr/sherpa_asr

export TYPST_BIN=$AGENT_PROJECT_DIR/.runtime/bin/typst
export TYPST_FONT_PATHS=$AGENT_PROJECT_DIR/.runtime/fonts
export PATH=$AGENT_PROJECT_DIR/.runtime/bin:$PATH

export AGENT_UI_HOST=127.0.0.1
export AGENT_UI_PORT=7860
```

启动：

```bash
cd /home/sunrise/llama/llama.cpp/agent-main
source .runtime/edge.env
python -m agent_edge.web_app
```

## 6. Windows 到端侧 Linux 的复制

### 6.1 使用压缩包

在 Windows PowerShell：

```powershell
cd C:\Users\19653\Desktop\agent

Compress-Archive -Force -DestinationPath agent_edge_release.zip -Path `
  agent_edge,skills,templates,scripts,index.html,agent-ui-runtime.js,tailwind.min.js,requirements.txt,pyproject.toml,README.md
```

上传到端侧后：

```bash
cd /home/sunrise/llama/llama.cpp
mkdir -p agent-main
unzip -o /path/to/agent_edge_release.zip -d agent-main
cd agent-main
mkdir -p .runtime/logs workspace_files
```

### 6.2 使用 rsync

如果 Windows 可以通过 WSL 或 Git Bash 使用 `rsync`：

```bash
rsync -av --delete \
  --exclude '.git/' \
  --exclude '__pycache__/' \
  --exclude '.runtime/logs/' \
  --exclude 'workspace_files/ocr_outputs/' \
  --exclude 'workspace_files/meeting_outputs/' \
  /mnt/c/Users/19653/Desktop/agent/ \
  sunrise@端侧IP:/home/sunrise/llama/llama.cpp/agent-main/
```

注意：如果端侧已经有 OCR/ASR/model 文件，不要用 `--delete` 覆盖这些目录，或者加额外 exclude。

## 7. 端侧自检

### 7.1 Typst 自检

```bash
cd /home/sunrise/llama/llama.cpp/agent-main
source .runtime/edge.env
typst --version
```

如果 `typst` 找不到：

```bash
echo "$TYPST_BIN"
ls -lh "$TYPST_BIN"
"$TYPST_BIN" --version
```

### 7.2 会议纪要工具自检

这个自检不调用 LLM，只验证模板、Typst 路径和输出链路：

```bash
cd /home/sunrise/llama/llama.cpp/agent-main
source .runtime/edge.env
python scripts/check_meeting_minutes_typst.py
```

如果成功，会在：

```text
workspace_files/meeting_outputs/
```

生成一套自检文件。

### 7.3 使用真实会议转写测试

把会议转写放进 `workspace_files/`：

```bash
cp sherpa_asr/sherpa_asr/录音记录_2026-06-01_20-32-10.txt workspace_files/meeting_test.txt
```

启动 UI：

```bash
python -m agent_edge.web_app
```

提交任务：

```bash
curl -fsS http://127.0.0.1:7860/api/tasks \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"请将会议转写文件 meeting_test.txt 格式化排版成会议纪要，使用 Typst 模板并导出 PDF。","backend":"llama_cpp","attachments":[]}'
```

查询任务：

```bash
curl -s http://127.0.0.1:7860/api/tasks/你的TASK_ID
```

成功结果里应包含：

```text
JSON
Markdown
Typst
PDF
输出目录
```

## 8. 前端使用方式

右侧“可用功能”里有：

```text
会议纪要导出
```

使用方式：

1. 上传或准备一个会议转写 `.txt`。
2. 点击“会议纪要导出”。
3. 选择会议转写文件。
4. Agent 会调用 `FORMAT_MEETING_MINUTES`。
5. 输出文件写入 `workspace_files/meeting_outputs/`。

## 9. 常见问题

### 9.1 只生成 `.typ`，没有 PDF

原因：Typst 未安装或 Agent 找不到 Typst。

检查：

```bash
source .runtime/edge.env
echo "$TYPST_BIN"
ls -lh "$TYPST_BIN"
"$TYPST_BIN" --version
```

修复：

```bash
bash scripts/install_typst_linux.sh
```

或者：

```bash
export TYPST_BIN=/absolute/path/to/typst
```

### 9.2 PDF 中文乱码或方块

原因：端侧缺少 CJK 字体。

修复：

```bash
sudo apt install -y fonts-noto-cjk fontconfig
fc-cache -fv
```

离线时复制字体到：

```text
.runtime/fonts/
```

并设置：

```bash
export TYPST_FONT_PATHS=$PWD/.runtime/fonts
```

### 9.3 `FileNotFoundError`

原因：工具只允许访问 `workspace_files/` 下的相对路径。

错误示例：

```text
/home/sunrise/xxx/meeting.txt
../meeting.txt
```

正确示例：

```text
meeting_test.txt
uploads/xxx-meeting.txt
```

在 prompt 里写：

```text
请将会议转写文件 meeting_test.txt 格式化排版成会议纪要，使用 Typst 模板并导出 PDF。
```

### 9.4 LLM 输出 JSON 失败

原因：小模型没有稳定遵守 JSON 输出。

建议：

- 用 Qwen 这类更适合 Agent/结构化输出的模型做会议纪要整理。
- MiniCPM 可先用于轻量直聊或短摘要，不建议承担复杂 Planner。
- 如果只想测试 Typst 链路，运行：

```bash
python scripts/check_meeting_minutes_typst.py
```

该脚本不调用 LLM。

### 9.5 Windows 复制到 Linux 后不能执行 typst

原因：执行权限丢失。

修复：

```bash
chmod +x .runtime/bin/typst
.runtime/bin/typst --version
```

## 10. 开箱即用验收清单

端侧执行：

```bash
cd /home/sunrise/llama/llama.cpp/agent-main
source .runtime/edge.env

python - <<'PY'
import importlib
for name in ["requests", "langgraph", "fastapi", "uvicorn"]:
    importlib.import_module(name)
print("Python deps ok")
PY

test -x "$LLAMA_CPP_BIN" && echo "llama-server ok"
test -f "$LLAMA_CPP_MODEL_PATH" && echo "model ok"
test -x "$TYPST_BIN" && "$TYPST_BIN" --version
python -m py_compile agent_edge/meeting_formatter.py agent_edge/local_actions.py agent_edge/graph.py
python scripts/check_meeting_minutes_typst.py
```

全部通过后，启动：

```bash
python -m agent_edge.web_app
```

浏览器打开：

```text
http://127.0.0.1:7860
```

然后测试：

```text
请将会议转写文件 meeting_test.txt 格式化排版成会议纪要，使用 Typst 模板并导出 PDF。
```

## 11. 当前会议纪要交互规则

会议按钮 `OFF` 结束录音后，接口会返回：

```text
transcript_path                原始 ASR 转写路径
workspace_transcript_path       归档到 workspace_files/meeting_records 的绝对路径
workspace_transcript_relpath    可直接给 Agent 工具使用的相对路径
transcript                      本次会议转写内容
```

右侧“会议纪要导出”不会再打开系统文件选择框，而是直接列出：

```text
workspace_files/meeting_records/
```

选中某条会议记录后，Agent 会提交：

```text
请将会议转写文件 meeting_records/xxx.txt 格式化排版成会议纪要，使用 Typst 模板并导出 PDF。
```

PDF 编译成功后会生成两份：

```text
workspace_files/meeting_outputs/.../minutes.pdf
桌面/日期_会议标题.pdf
```

桌面路径查找顺序：

```text
1. MEETING_MINUTES_DESKTOP_DIR
2. AGENT_DESKTOP_DIR
3. 项目父目录如果就是 Desktop/桌面，则使用项目父目录
4. 当前用户 HOME 下的 Desktop/桌面
```

会议纪要内容生成采用分部分生成：

```text
概览/重点内容
议题与结论
待办/风险/待确认
```

要求：

- `key_points` 尽量至少 5 条。
- 每个主要议题的 discussion 尽量至少 5 条。
- 风险/待确认事项尽量至少 5 条。
- 信息密度越高，条数自然增加。
- 如果 ASR 信息不足，不编造，用“转写信息不足/需复核”说明缺口。
