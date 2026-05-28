# ASR/会议记录技能

当用户要求会议记录、实时转写、语音输入、会议总结、提取会议待办时，使用 ASR/会议流程。

重要说明：

- ASR 不是普通 `USE_TOOL` 本地工具。
- 会议开始和结束由 UI 或 Web API 控制：
  - `POST /api/meeting/start`：开启会议实时记录。
  - `POST /api/meeting/stop`：关闭会议记录并返回本次 transcript。
  - `POST /api/meeting/summary`：读取当前会议 transcript，并创建 LLM 总结任务。
- 输入框旁的麦克风按钮走短语音输入：
  - `POST /api/voice-input/start`
  - `POST /api/voice-input/stop`

推荐用户操作：

- 想开始会议记录：点击页面右下角会议按钮 `ON`。
- 想结束会议记录：点击页面右下角会议按钮 `OFF`。
- 想总结会议：点击右侧“会议总结”，或输入“请总结当前会议记录”。
- 想语音填充输入框：点击输入框旁的麦克风按钮，再次点击停止。

当 prompt 中包含会议转写内容时，例如：

```text
<meeting_transcript>
……
</meeting_transcript>
```

应该直接总结 transcript，输出：

- 会议主题。
- 关键结论。
- 待办事项。
- 风险或待确认事项。

资源规则：

- 当前 ASR 第一版按 CPU 运行，不占 BPU。
- ASR 会议进程可以在会议期间常驻。
- ASR 本身不阻塞 OCR，但会议总结请求需要进入 LLM 队列。
- 如果正在进行短语音输入，不应同时开启会议记录，因为两个流程都会使用麦克风。
