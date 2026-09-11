# Vera 阶段二执行顺序

**状态：** Planned
**规格：** [阶段二：恢复、兼容性与策略扩展](../specs/2026-09-11-phase-2-recovery-compatibility-policy.md)

## 目标

阶段二把 Vera Core 加固为可恢复、可兼容、可解释且可继续扩展的最小版本。CLI 继续作为完整验收客户端；本阶段不引入桌面框架。

## 执行规则

- Cursor 每次只执行一份编号任务，使用一个主实现 Agent。
- 每份任务从最新、干净的 `main` 创建其指定功能分支。
- 按失败测试 → 最小实现 → 局部验证 → 完整验证 → 文档同步 → 提交 → 合并推进。
- 前一任务完整合并并复核后，才能开始下一任务。
- 不运行 `tests/live`，不读取或使用用户真实 DeepSeek/GLM Key。
- 不修改 `/Users/admin/Desktop/VeraTestDemo`。
- 每份任务允许独立拒绝、返工或回滚，不把五个增量压成一个不可审阅提交。

## 顺序

1. [任务 0005：恢复事实与只读分类](0005-recovery-facts-and-classification.md)
2. [任务 0006：安全续跑与部分写入恢复](0006-safe-run-resume-and-recovery.md)
3. [任务 0007：版本化 Codec 与兼容迁移](0007-versioned-codecs-and-migration.md)
4. [任务 0008：统一 PolicyEngine 与审批指纹](0008-unified-policy-engine.md)
5. [任务 0009：ModelAdapter 韧性与阶段二验收](0009-model-resilience-and-phase-2-acceptance.md)

## 规格覆盖关系

| 阶段二能力 | 主实施任务 | 最终证据 |
| --- | --- | --- |
| 重启后的事实采集与确定性分类 | 0005 | Snapshot、Probe、Classifier 与只读 CLI 测试 |
| 安全续跑、部分写入恢复和放弃 | 0006 | 跨 Runtime 恢复、故障注入与 CLI E2E |
| Schema、Journal、Snapshot 版本兼容 | 0007 | Codec、legacy/future Fixture 与非破坏迁移测试 |
| 路径、工具、命令、写入和恢复统一策略 | 0008 | PolicyEngine 决策矩阵、策略指纹与审批失效测试 |
| 供应商能力、错误、有限重试和阶段收口 | 0009 | DeepSeek/GLM 离线 Fixture、重试副作用测试与 12 条退出条件验收 |

任务 0009 的验收记录必须逐条反向链接总规格的 12 条退出条件；不能用“全部测试通过”替代能力级证据。

## 阶段完成定义

只有任务 0005–0009 全部合并、阶段二规格的 12 条退出条件逐项留下证据，才能把路线图阶段二标记为 Complete。
