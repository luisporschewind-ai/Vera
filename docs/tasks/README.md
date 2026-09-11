# 任务记录

任务记录把已接受规格拆成可执行、可验证、可独立提交的实施步骤。

## 约定

- 文件按下一个连续编号命名为 `NNNN-<topic>.md`。
- 状态只使用 `Planned`、`In progress`、`Blocked` 或 `Done`。
- 存在上游规格或架构决策时必须链接。
- 明确记录目标、范围、验收检查和验证证据。
- 每项任务只分配一个主实现 Agent；除非明确转移所有权，其他 Agent 或工具只负责只读研究与复核。
- 只有检查通过且文档与实际行为一致后才能关闭任务。

## 当前任务

- [任务 0001：建立 Vera 仓库](0001-bootstrap-repository.md)
- [任务 0002：Core 安全编辑垂直切片](0002-core-safe-editing-vertical-slice.md)
- [任务 0003：交互式 CLI 会话](0003-interactive-cli-session.md)
- [任务 0004：普通对话、会话上下文与状态命令](0004-conversational-cli-and-session-status.md)
- [阶段二执行顺序](phase-2-execution-order.md)
- [任务 0005：恢复事实与只读分类](0005-recovery-facts-and-classification.md)
- [任务 0006：安全续跑与部分写入恢复](0006-safe-run-resume-and-recovery.md)
- [任务 0007：版本化 Codec 与兼容迁移](0007-versioned-codecs-and-migration.md)
- [任务 0008：统一 PolicyEngine 与审批指纹](0008-unified-policy-engine.md)
- [任务 0009：ModelAdapter 韧性与阶段二验收](0009-model-resilience-and-phase-2-acceptance.md)
