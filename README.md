# 离线 Edge LangGraph Agent MVP

这是一个面向端侧设备的离线 Agent MVP。当前项目已经在 `Ubuntu-22.04` WSL 中跑通：

- 本地 `qwen2.5:1.5b` 模型由 Ollama 提供。
- Agent 使用 `langgraph.graph.StateGraph` 编排。
- 技能通过本地 Markdown 文件描述。
- 工具调用通过纯 Python 拦截器执行。
- 运行时不依赖云端 API。

完整设计、文件说明、修改方式和使用说明请阅读：

[docs/AGENT_MVP_GUIDE.md](docs/AGENT_MVP_GUIDE.md)

## 最快运行

在 Windows PowerShell 里进入项目目录：

```powershell
cd C:\Users\19653\Desktop\agent
.\scripts\run_agent_wsl.ps1 "请读取 demo_input.txt，并统计我的输入长度。"
```

如果 PowerShell 执行策略拦截 `.ps1`，使用：

```powershell
.\scripts\run_agent_wsl.cmd "请读取 demo_input.txt，并统计我的输入长度。"
```

快速测试，不调用 Ollama：

```powershell
.\scripts\run_agent_wsl.cmd -Mock "请读取 demo_input.txt，并统计我的输入长度。"
```

说明：当前 WSL 内的 Miniforge 和 `agent` 环境安装在 root 用户下，所以 Windows 入口会自动使用 `wsl -u root`。

真实模型模式第一次运行或小模型推理较慢时可能需要几分钟；看到长时间等待不一定是卡死。

或者在 WSL 里运行：

```bash
cd /mnt/c/Users/19653/Desktop/agent
sudo bash scripts/run_wsl.sh "请读取 demo_input.txt，并统计我的输入长度。"
```

## 快速自检

```powershell
wsl -u root --cd /mnt/c/Users/19653/Desktop/agent bash scripts/check_wsl_status.sh
```

## 重新部署

```powershell
wsl -u root --cd /mnt/c/Users/19653/Desktop/agent bash scripts/setup_wsl.sh
```

默认 WSL 已设置为 `Ubuntu-22.04`。
