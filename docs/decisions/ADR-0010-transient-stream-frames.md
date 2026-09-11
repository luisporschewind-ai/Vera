# ADR-0010：持久 Event 与瞬时 Stream Frame

**状态：** Accepted
**日期：** 2026-09-11

## 背景

模型回答需要流式展示，但把每个文字增量写入 Event Journal 会扩大私有状态、拖慢恢复并重复保存最终回答。完全绕过 Core 直接把 Provider chunk 交给 TUI，又会破坏统一客户端契约。

## 决策

- `EventEnvelope` 继续表示持久、权威、可恢复的事实。
- 新增 Pydantic `StreamFrame` 表示进程内瞬时输出；第一版只允许 `assistant.delta`。
- Stream Frame 带 `run_id`、`stream_id` 和单调 `index`，但不写 Journal、Snapshot 或 ConversationContext。
- 正常结束必须产生带同一 `stream_id` 的完整 `assistant.message`；只有该 Event 能进入会话上下文。
- Runtime 新增 `stream()`；旧 `handle()` 继续只暴露持久 Event，并通过消费同一执行实现保持语义一致。
- Adapter 流式 Tool Call 必须完整聚合、校验后才能交给 Runtime；片段本身不能触发工具。
- 瞬时输出不能参与审批、策略、恢复分类或终态判断。
- 流式路径对齐阶段二最终接口：`ModelAdapter` Protocol、`ModelCapabilities.streaming`、`ModelProviderError`、`RetryPolicy`；`ContractCodec` 不处理 StreamFrame。

## 后果

- TUI 可以实时呈现，恢复与审计仍基于紧凑的最终事实。
- 进程中断时可能看到没有持久保存的部分文本，UI 必须明确标为未完成。
- RuntimeOutput 成为 `EventEnvelope | StreamFrame` 联合类型，新的流式消费者必须穷尽处理两类记录。
- JSON Session 可以选择输出 Stream Frame；旧一次性 JSON 接口继续过滤它们。

## 验证与重审触发器

- 契约 round-trip、重复/缺口 frame、失败 partial、最终文本一致性和 Journal 无 delta 测试必须通过。
- 若未来需要音频、图片或结构化增量，为 StreamFrame 增加新类型并做版本兼容，不能复用 `assistant.delta` 改变含义。
- 若某个 Stream Frame 开始影响副作用或恢复，它必须升级为持久 Event，而不是扩大瞬时层权力。
