# 架构决策

架构决策记录长期有效的技术选择、理由与取舍。

## 约定

- 文件按下一个连续编号命名为 `ADR-NNNN-<topic>.md`。
- 状态只使用 `Proposed`、`Accepted` 或 `Superseded`。
- 记录背景、备选方案、决策、后果，以及验证或重新评审的触发条件。
- 已接受决策需要变更时，新建决策并标记取代关系；保留原有理由。

## 当前决策

- [ADR-0001：Python Core 与 Runtime](ADR-0001-python-core-runtime.md)
- [ADR-0002：Command → VeraRuntime → Event 公共契约](ADR-0002-command-event-contract.md)
- [ADR-0003：私有状态与 Checkpoint](ADR-0003-private-state-and-checkpoints.md)
- [ADR-0004：进程内会话上下文与状态边界](ADR-0004-ephemeral-conversation-context.md)

Core Runtime、协议、持久化模型、关键依赖、安全边界或桌面框架等长期选择应建立决策记录；常规实现细节写入任务记录。
