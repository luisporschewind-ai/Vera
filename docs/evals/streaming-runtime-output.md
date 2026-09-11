# 流式 RuntimeOutput 验收记录

更新日期：2026-09-11

## 结论

任务 0010 完成。`StreamFrame` 瞬时帧、`ModelAdapter.stream()`、OpenAI-compatible 流式映射与 `VeraRuntime.stream()` 已落地；`handle()` 与 `vera run --json` 仍只暴露持久 Event。

未运行 live，未读取真实 Key。

## 证据

| 项 | 结果 |
|---|---|
| StreamFrame 契约 | 通过 |
| Fake/默认 stream 包装 complete | 通过 |
| DeepSeek stream fixture | 通过 |
| Runtime 瞬时 delta + 持久 assistant.message | 通过 |
| handle 过滤 StreamFrame | 通过 |
| 非 live 全量 | 277 passed，2 deselected；覆盖率 90% |

## 已知限制

- OpenAI stream 默认 `capabilities.streaming=False`，需显式开启。
- GLM stream fixture 与完整 Tool Call 流式聚合可在后续任务补强。
- SessionController / Textual TUI 属于 0011+。
