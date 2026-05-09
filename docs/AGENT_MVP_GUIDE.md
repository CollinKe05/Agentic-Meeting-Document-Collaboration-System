# 离线 Edge LangGraph Agent MVP 说明文档

本文档说明这个项目做了什么、为什么这样建、每个程序文件有什么用、如何运行、如何修改，以及它是否满足“端侧离线 Agent”的 MVP 要求。

## 1. 当前完成状态

当前项目已经完成一个可本地运行的离线 Agent MVP：

- WSL 默认发行版已配置为 `Ubuntu-22.04`。
- Ubuntu 实际版本为 `Ubuntu 22.04.5 LTS`。
- WSL 内已在 root 用户下安装 Miniforge。
- WSL 内已在 root 用户下创建 conda 环境 `agent`。
- `agent` 环境中已安装本项目和 `langgraph` 依赖。
- WSL 内已安装 Ollama。
- WSL 内已拉取模型 `qwen2.5:1.5b`。
- Agent 已用真实本地模型跑通过一次完整冒烟测试。

最终冒烟测试中，Agent 完成了：

- 读取本地技能索引 `skills/skills_index.md`
- 读取本地技能说明 `skills/read_file_skill.md`
- 通过本地工具读取 `workspace_files/demo_input.txt`
- 通过本地工具统计用户输入字符数

这说明核心链路已经跑通：

```text
用户输入
  -> Planner 节点生成计划
  -> Executor 节点执行 ReAct 循环
  -> Python 工具拦截器执行本地文件 I/O
  -> Observation 写入状态
  -> Reflexion 历史进入下一轮
  -> 所有任务完成
```

## 2. 是否满足“端侧离线 Agent”要求

就 MVP 范围而言，已经满足。

### 已满足的部分

- **不调用云 API**：运行时模型走本地 Ollama，工具走本地 Python 函数。
- **轻量状态机**：使用 `langgraph.graph.StateGraph`，没有使用 AutoGPT、MetaGPT 等重框架。
- **Global State**：使用 `AgentState(TypedDict)` 保存用户输入、计划、历史和当前响应。
- **Planner Node**：读取本地 `skills_index.md`，生成任务队列。
- **Executor Node**：按 ReAct 思路执行任务，带 `past_steps` 作为 Reflexion 记忆。
- **本地 Markdown 技能系统**：技能是 `skills/` 目录下的 `.md` 文件。
- **Python Tool Interceptor**：`execute_local_action()` 拦截 `READ_SKILL` 和 `USE_TOOL`。
- **跨 Windows/Ubuntu 文件 I/O**：路径处理使用 `pathlib.Path.resolve()` 和 `relative_to()`，防止路径穿越。
- **可在 WSL 本地运行**：已在 `Ubuntu-22.04` 上验证。

### MVP 的边界

这个项目是一个 MVP，不是完整生产级 Agent 平台。当前仍然故意保持简单：

- Planner 和 Executor 仍通过提示词让小模型输出 JSON/ReAct。
- 工具集是 dummy 工具，只覆盖读文件、写文件、统计字符、列技能等基础能力。
- 没有做复杂长期记忆、权限系统、多用户隔离、并发任务队列。
- 没有加入 GUI 或 Web 服务。
- 安装依赖、安装 Ollama、拉模型时需要联网；但模型和依赖准备好之后，运行时可以离线。

### 对 RDK X5 / 端侧设备的意义

这个项目的结构是端侧友好的：

- Agent 主体是普通 Python。
- 状态机轻量。
- 工具调用是本地函数。
- 技能是本地 Markdown。
- LLM 后端被隔离在 `agent_edge/llm.py` 中，后续可替换为 RDK X5 上的本地 SLM 服务。

注意：Ollama 是否适合某个 ARM 端侧设备，要看该设备系统、CPU 架构和模型推理栈支持情况。若 Ollama 不合适，可把 `llm.py` 替换为 llama.cpp、RKNN、ONNX Runtime、FastAPI 本地推理服务或厂商 SDK。

## 3. 整体体系结构

核心文件：

```text
agent_edge/
  state.py          定义 AgentState
  graph.py          定义 LangGraph 节点和图流
  llm.py            本地 LLM 后端适配
  parsing.py        解析 JSON plan 和 ReAct 输出
  local_actions.py  本地工具拦截器
  paths.py          跨平台路径和安全文件 I/O
  __main__.py       命令行入口

skills/
  skills_index.md
  read_file_skill.md
  local_tool_skill.md

workspace_files/
  demo_input.txt

scripts/
  setup_wsl.sh
  run_wsl.sh
  run_agent_wsl.ps1
  ensure_ollama_model_wsl.sh
  check_wsl_status.sh
  start_ollama_wsl.sh

tests/
  test_local_actions.py
  test_parsing.py
```

图流如下：

```text
START
  -> planner_node
  -> executor_node
  -> 条件路由:
       react_loop -> executor_node
       next_task  -> executor_node
       end        -> END
```

状态结构如下：

```python
class AgentState(TypedDict):
    user_input: str
    plan: List[dict]
    past_steps: List[tuple]
    current_response: str
```

字段含义：

- `user_input`：用户原始任务。
- `plan`：Planner 生成的任务队列。
- `past_steps`：执行历史，格式近似 `((Action, Action Input), Observation)`。
- `current_response`：当前节点输出，也携带内部路由标记。

## 4. 每个程序为什么这样建

### `agent_edge/state.py`

定义全局状态 `AgentState`。

为什么需要它：

- LangGraph 的节点之间靠 state 传递信息。
- Agent 需要保存任务队列、历史观察和当前响应。
- TypedDict 轻量，不引入复杂类系统。

可以改哪里：

- 如果以后要加入长期记忆，可以增加 `memory: List[dict]`。
- 如果要加入文件白名单，可以增加 `allowed_paths: List[str]`。
- 如果要加入多轮对话，可以增加 `messages: List[dict]`。

### `agent_edge/graph.py`

这是 Agent 的核心状态机。

主要内容：

- `planner_node(state)`：读取技能索引，调用本地模型生成计划。
- `executor_node(state)`：执行队首任务。
- `route_after_executor(state)`：决定是否循环、继续下个任务或结束。
- `build_agent_graph()`：构建 `StateGraph`。
- `run_agent(user_input)`：运行 Agent。

为什么这样建：

- Planner 和 Executor 分离，便于以后替换任意一个节点。
- Executor 使用队列式执行，简单、可调试。
- 每次工具调用都会生成 Observation，并写入 `past_steps`，便于 Reflexion。
- 对小模型增加了确定性护栏，避免 `qwen2.5:1.5b` 输出格式不稳定时卡死。

关键护栏：

- 如果模型输出 `Action: READ_SKILL | USE_TOOL | FINISH`，解析器会提取合法动作。
- 如果任务还没有 Observation，Executor 不允许模型提前 `FINISH`。
- 如果模型输出坏格式，Executor 会根据当前 task schema 兜底执行确定性动作。

可以改哪里：

- 修改 `planner_node()` 的 prompt，可以改变计划风格。
- 修改 `_normalize_plan()`，可以强制计划包含某些步骤。
- 修改 `_expected_action_for_task()`，可以改变任务到动作的映射。
- 修改 `MAX_ATTEMPTS_PER_STEP`，可以调整反复尝试次数。

### `agent_edge/llm.py`

本地 LLM 后端适配层。

主要内容：

- `llm_call(prompt)`：统一模型调用入口。
- `ollama_generate(prompt)`：调用本机 Ollama HTTP API。
- `mock_llm_call(prompt)`：不用模型的确定性 mock。
- `fallback_plan(user_input)`：Planner 输出不可解析时的后备计划。

为什么这样建：

- Agent 其他部分不关心模型来自哪里。
- 当前用 Ollama，未来可以换成本地 SLM HTTP 服务。
- mock 后端便于在没有模型时测试状态机。

可以改哪里：

- 修改 `DEFAULT_MODEL` 切换默认模型。
- 设置环境变量 `OLLAMA_MODEL` 切换模型。
- 设置环境变量 `OLLAMA_BASE_URL` 切换 Ollama 地址。
- 如果你在端侧设备上有自己的推理服务，只需要改 `llm_call()` 或新增一个 backend。

示例：改成本地 HTTP SLM

```python
def my_local_slm_generate(prompt: str) -> str:
    response = requests.post(
        "http://127.0.0.1:8000/generate",
        json={"prompt": prompt},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["text"]
```

然后在 `llm_call()` 中增加：

```python
if backend == "my_slm":
    return my_local_slm_generate(prompt)
```

### `agent_edge/local_actions.py`

这是 Python Tool Interceptor。

主要入口：

```python
execute_local_action(action: str, action_input: str) -> str
```

支持动作：

- `READ_SKILL`：读取 `skills/` 下的 `.md` 文件。
- `USE_TOOL`：解析 JSON 后执行本地 dummy 工具。

当前本地工具：

- `LOCAL_ECHO`：回显文本。
- `COUNT_TEXT_CHARS`：统计字符数。
- `LIST_SKILLS`：列出本地技能文件。
- `SAFE_READ_TEXT_FILE`：安全读取 `workspace_files/` 下的文件。
- `SAFE_WRITE_TEXT_FILE`：安全写入 `workspace_files/` 下的文件。

为什么这样建：

- 不使用 `@tool` 装饰器，不让工具系统依赖云服务。
- LLM 只负责提出动作，真正权限判断在 Python 里执行。
- 所有工具输出统一是字符串 Observation，方便写入 `past_steps`。

可以改哪里：

要新增工具，就在 `_execute_dummy_tool()` 里增加分支。

例如增加一个简单加法工具：

```python
if tool_name == "ADD_NUMBERS":
    a = float(args.get("a", 0))
    b = float(args.get("b", 0))
    return json_observation({"ok": True, "result": a + b})
```

然后更新 `skills/local_tool_skill.md` 和 `skills/skills_index.md`。

### `agent_edge/paths.py`

跨平台路径和安全文件 I/O。

主要内容：

- `PROJECT_ROOT`
- `SKILLS_DIR`
- `WORKSPACE_DIR`
- `ensure_demo_assets()`
- `safe_child_path()`
- `read_limited_text()`
- `write_limited_text()`

为什么这样建：

- Windows 和 Ubuntu 路径分隔符不同，不能靠字符串拼路径。
- `Path.resolve()` 会规范化路径。
- `relative_to()` 用来确认目标没有逃逸出允许目录。
- 限制文件大小，避免小设备上读入大文件打爆内存。

安全边界：

- 技能只能读 `skills/*.md`。
- 文件工具只能访问 `workspace_files/`。
- `../secret.txt` 会被拒绝。
- 绝对路径逃逸会被拒绝。

可以改哪里：

- 调整 `MAX_LOCAL_FILE_BYTES` 改最大文件大小。
- 设置 `AGENT_SKILLS_DIR` 改技能目录。
- 设置 `AGENT_WORKSPACE_DIR` 改工作目录。

### `agent_edge/parsing.py`

解析模型输出。

主要内容：

- `parse_json_list()`：从 Planner 输出中提取 JSON list。
- `parse_react_output()`：从 Executor 输出中提取 Thought、Action、Action Input。
- `strip_markdown_fence()`：去掉模型可能输出的 Markdown 代码块。

为什么这样建：

- 小模型经常不严格遵守输出格式。
- Planner 可能在 JSON 前后加解释。
- Executor 可能把 Action 选项原样抄出来。
- 解析层集中处理这些毛刺，可以让图逻辑保持干净。

可以改哪里：

- 如果换了更强模型，可以收紧解析规则。
- 如果模型输出格式更散，可以继续增强容错。

### `agent_edge/__main__.py`

命令行入口。

可以这样运行：

```bash
python -m agent_edge --backend ollama --model qwen2.5:1.5b "请读取 demo_input.txt，并统计我的输入长度。"
```

参数：

- `--backend ollama`：使用本地 Ollama。
- `--backend mock`：使用确定性 mock。
- `--model qwen2.5:1.5b`：指定 Ollama 模型。
- `--base-url http://127.0.0.1:11434`：指定 Ollama API 地址。
- `--show-trace`：显示 plan 和 past_steps。

为什么这样建：

- 方便直接命令行测试。
- 方便脚本调用。
- 以后可接 Web API 或桌面 UI。

## 5. skills 目录说明

### `skills/skills_index.md`

本地技能索引。

Planner 会先读取这个文件，了解有哪些技能。

新增技能时需要更新这里。

### `skills/read_file_skill.md`

说明如何安全读取本地文本文件。

Executor 如果要读文件，会先读取这个技能，再调用 `SAFE_READ_TEXT_FILE`。

### `skills/local_tool_skill.md`

列出当前可用 dummy 工具。

新增工具后也要更新这个文件，让 Planner/Executor 知道工具存在。

## 6. workspace_files 目录说明

`workspace_files/` 是 Agent 的安全工作区。

当前示例文件：

```text
workspace_files/demo_input.txt
```

本地读写工具默认只能访问这个目录，不能读整个磁盘。

如果你希望 Agent 处理更多文件，建议把文件放进这个目录，而不是放开全盘访问。

## 7. scripts 目录说明

### `scripts/setup_wsl.sh`

完整部署脚本。

它会做：

- 检查基础系统工具。
- 安装 Miniforge。
- 创建 conda 环境 `agent`。
- 安装 Python 项目依赖。
- 安装 Ollama。
- 启动 Ollama。
- 拉取 `qwen2.5:1.5b`。
- 运行一次冒烟测试。

什么时候用：

- 第一次部署。
- 环境坏了要重建。
- 换新 WSL 后重新安装。

### `scripts/run_wsl.sh`

WSL 内运行脚本。

它会做：

- 找到 conda。
- 检查 Ollama。
- 如果 Ollama 没启动，就自动启动。
- 如果模型不存在，就自动拉取。
- 运行 `python -m agent_edge`。

推荐日常使用它，而不是手敲长命令。

### `scripts/run_agent_wsl.ps1`

Windows PowerShell 入口。

推荐你在 Windows 下这样运行：

```powershell
cd C:\Users\19653\Desktop\agent
.\scripts\run_agent_wsl.ps1 "请读取 demo_input.txt，并统计我的输入长度。"
```

它会自动把 Windows 路径转换成 WSL 路径，并调用 `scripts/run_wsl.sh`。

注意：当前 MVP 的 WSL Miniforge 安装在 root 用户下，因此这个脚本会使用 `wsl.exe -u root` 运行 Agent。这样你不需要把 root 下的 conda 环境重复安装到普通用户 `default` 下面。

如果你的 PowerShell 执行策略阻止 `.ps1`，可以改用：

```powershell
.\scripts\run_agent_wsl.cmd "请读取 demo_input.txt，并统计我的输入长度。"
```

这个 `.cmd` 文件只是一个包装器，会用 `ExecutionPolicy Bypass` 调起 `run_agent_wsl.ps1`。

### `scripts/ensure_ollama_model_wsl.sh`

只处理 Ollama 和模型。

它会：

- 检查 `zstd`。
- 检查 Ollama。
- 启动 Ollama 服务。
- 拉取 `qwen2.5:1.5b`。
- 打印模型列表。

什么时候用：

- 只想确认模型是否存在。
- Ollama 被关掉后想重新启动。
- 不想重跑完整部署脚本。

### `scripts/check_wsl_status.sh`

状态检查脚本。

它会检查：

- Ubuntu 版本。
- `zstd` 是否存在。
- Ollama 是否安装。
- Ollama API 是否运行。
- conda `agent` 环境是否能 import `langgraph`。

运行：

```powershell
wsl -u root --cd /mnt/c/Users/19653/Desktop/agent bash scripts/check_wsl_status.sh
```

### `scripts/start_ollama_wsl.sh`

手动启动 Ollama 的脚本。

正常情况下你不需要用它，因为 `run_wsl.sh` 会自动启动 Ollama。

## 8. tests 目录说明

### `tests/test_local_actions.py`

测试本地工具拦截器。

覆盖：

- 能读取技能文件。
- 拒绝路径穿越。
- 能安全读取 demo 文件。

### `tests/test_parsing.py`

测试解析器。

覆盖：

- 能从文本中解析 JSON list。
- 能解析 ReAct 输出。

运行测试：

```bash
python -m unittest discover -s tests
```

或在 WSL agent 环境中：

```bash
/root/miniforge3/bin/conda run -n agent python -m unittest discover -s tests
```

## 9. 使用方法

### 推荐：Windows PowerShell 一键运行

```powershell
cd C:\Users\19653\Desktop\agent
.\scripts\run_agent_wsl.ps1 "请读取 demo_input.txt，并统计我的输入长度。"
```

如果 `.ps1` 被拦截：

```powershell
.\scripts\run_agent_wsl.cmd "请读取 demo_input.txt，并统计我的输入长度。"
```

快速测试，不调用 Ollama：

```powershell
.\scripts\run_agent_wsl.cmd -Mock "请读取 demo_input.txt，并统计我的输入长度。"
```

`-Mock` 模式会使用确定性 mock LLM，几秒内验证 LangGraph、技能读取和本地工具拦截器。真实模型模式不加 `-Mock`，会调用 Ollama 的 `qwen2.5:1.5b`，一次完整运行可能需要几分钟。

### WSL 内运行

```bash
cd /mnt/c/Users/19653/Desktop/agent
sudo bash scripts/run_wsl.sh "请读取 demo_input.txt，并统计我的输入长度。"
```

如果你忘了加 `sudo`，脚本会尝试自动用 sudo 重新执行。因为当前部署的 conda 环境在 `/root/miniforge3/envs/agent`。

### 直接调用 Python 入口

```bash
cd /mnt/c/Users/19653/Desktop/agent
/root/miniforge3/bin/conda run -n agent python -m agent_edge --backend ollama --model qwen2.5:1.5b "请读取 demo_input.txt，并统计我的输入长度。"
```

### 不用模型，测试状态机和工具链

```bash
python -m agent_edge --backend mock --show-trace "请读取 demo_input.txt，并统计我的输入长度。"
```

### 显示详细执行轨迹

```bash
sudo bash scripts/run_wsl.sh "请读取 demo_input.txt，并统计我的输入长度。" --show-trace
```

注意：上面这个写法会把 `--show-trace` 当作用户 prompt 的一部分。要真正传 CLI 参数，请直接调用 Python：

```bash
/root/miniforge3/bin/conda run -n agent python -m agent_edge --backend ollama --model qwen2.5:1.5b --show-trace "请读取 demo_input.txt，并统计我的输入长度。"
```

## 10. 如何修改 Agent

### 修改默认模型

临时修改：

```bash
sudo env OLLAMA_MODEL=qwen2.5:3b bash scripts/run_wsl.sh "你的任务"
```

代码修改：

```python
# agent_edge/llm.py
DEFAULT_MODEL = "qwen2.5:1.5b"
```

### 修改 Ollama 地址

```bash
OLLAMA_BASE_URL=http://127.0.0.1:11434 python -m agent_edge --backend ollama "你的任务"
```

### 新增技能

1. 在 `skills/` 下新增 Markdown 文件，例如：

```text
skills/math_skill.md
```

2. 在 `skills/skills_index.md` 中登记它。

3. 如果技能需要新工具，在 `local_actions.py` 中新增工具。

### 新增本地工具

编辑：

```text
agent_edge/local_actions.py
```

在 `_execute_dummy_tool()` 中新增分支。

工具输入必须是 JSON：

```json
{
  "tool_name": "TOOL_NAME",
  "args": {}
}
```

工具输出建议使用：

```python
return json_observation({"ok": True, "result": result})
```

### 修改 Planner 行为

编辑：

```text
agent_edge/graph.py
```

重点看：

- `planner_node()`
- `_normalize_plan()`
- `fallback_plan()`，在 `agent_edge/llm.py`

如果你想让 Agent 总是先读某个技能，就在 fallback plan 或 normalize 里加固定步骤。

### 修改 Executor 行为

编辑：

```text
agent_edge/graph.py
```

重点看：

- `executor_node()`
- `_expected_action_for_task()`
- `_coerce_action_for_task()`
- `_finish_observed_task()`

如果你换了更强模型，可以减少兜底逻辑；如果你继续用 1.5B 小模型，建议保留这些护栏。

### 修改安全文件目录

临时指定：

```bash
sudo env AGENT_WORKSPACE_DIR=/some/safe/path bash scripts/run_wsl.sh "你的任务"
```

代码默认值：

```python
# agent_edge/paths.py
WORKSPACE_DIR = Path(os.environ.get("AGENT_WORKSPACE_DIR", PROJECT_ROOT / "workspace_files")).expanduser()
```

## 11. 常见问题

### 1. PowerShell 里运行脚本提示权限问题

可以用：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_agent_wsl.ps1 "请读取 demo_input.txt"
```

### 2. Ollama 没启动

运行：

```powershell
wsl -u root --cd /mnt/c/Users/19653/Desktop/agent bash scripts/ensure_ollama_model_wsl.sh
```

### 3. 模型不存在

运行：

```powershell
wsl -u root ollama pull qwen2.5:1.5b
```

或：

```powershell
wsl -u root --cd /mnt/c/Users/19653/Desktop/agent bash scripts/ensure_ollama_model_wsl.sh
```

### 4. 默认 WSL 不是 Ubuntu-22.04

检查：

```powershell
wsl --list --verbose
```

设置：

```powershell
wsl --set-default Ubuntu-22.04
```

### 5. 小模型输出格式不稳定

这是正常的。项目里已经加了兜底：

- Planner JSON 解析失败会使用 `fallback_plan()`。
- Executor ReAct 解析失败会根据 task schema 执行确定性动作。
- 未拿到 Observation 前不允许提前 FINISH。

### 6. 想完全不联网运行

先联网完成：

- Python 依赖安装
- Ollama 安装
- 模型拉取

之后运行 Agent 不需要云 API，也不需要外网。

## 12. 下一步建议

如果要继续把 MVP 推向可用产品，可以按这个顺序扩展：

1. 增加更多本地工具，例如文件搜索、表格处理、命令白名单执行。
2. 给工具加权限配置文件，而不是写死在代码中。
3. 把 `past_steps` 持久化到本地 SQLite。
4. 增加本地 Web API，让其他程序调用 Agent。
5. 在 RDK X5 上替换 `llm.py` 后端，接入设备原生推理服务。
6. 为每个工具增加单元测试。

当前版本已经足够作为“端侧离线 Agent”的 MVP 骨架：它能规划、能读技能、能执行本地工具、能在本地模型驱动下完成任务，并且运行时不依赖云服务。
