# Vera 状态

**更新日期：** 2026-09-11
**当前阶段：** 阶段 2 Complete；阶段 3 富交互 Terminal UI 规划已 rebase 并待本地合并后实施
**仓库状态：** 任务 0005–0009 已本地合并到 `main`；阶段三规划文档在 `planning/phase-3-terminal-ui`；暂无远程仓库，未推送。

## 已验证基线

- 工作目录：`/Users/admin/Vera`
- 当前分支：`main`
- 阶段一与阶段二 Core/CLI 离线验收完成

## 已完成任务

- 任务 0001–0008
- [任务 0009：ModelAdapter 韧性与阶段二验收](tasks/0009-model-resilience-and-phase-2-acceptance.md)

## 活动任务

- [阶段三执行顺序](tasks/phase-3-execution-order.md)
- [任务 0010：流式 RuntimeOutput](tasks/0010-streaming-runtime-output.md)
- [任务 0011：Textual TUI 外壳与模式路由](tasks/0011-textual-tui-shell.md)
- [任务 0012：TUI 时间线与披露策略](tasks/0012-tui-timeline-and-disclosure.md)
- [任务 0013：TUI Composer、审批与任务控制](tasks/0013-tui-composer-and-approvals.md)
- [任务 0014：Terminal 模式兼容与阶段三验收](tasks/0014-terminal-modes-and-acceptance.md)

## 最近验证

- 任务 0009：capabilities、ModelProviderError、RetryPolicy、Runtime 有限重试、DeepSeek/GLM fixture conformance
- 离线验收：268 项非 live 通过、2 项 live 排除，覆盖率 90%
- 阶段二退出条件证据：[phase-2-reliability-core](evals/phase-2-reliability-core.md)

## 已接受方向

- 正式开发只在本仓库进行。
- `/Users/admin/Coding-harness` 保持只读，仅作为原型参考。
- 产品交付遵循 Core-first、内部 CLI-first、桌面 later。
- 公开发布前先完成私有稳定性和评测证据。
- Runtime、Command/Event 契约、私有状态与 Checkpoint，以及进程内会话上下文设计已通过 ADR 接受。
- 阶段二采用确定性恢复、版本化 Codec、统一 PolicyEngine 和 ModelAdapter 有限重试设计。
- 阶段三采用 Textual 全屏 TUI；TUI、Plain、JSON 共用 UI 无关 SessionController。
- 模型增量文本使用不持久化的 Stream Frame，最终 `assistant.message` 仍是 Journal 与恢复的权威事实。
- 不引入 `prompt_toolkit`；不提前实现桌面端。

## 仍待决策

- 更广泛的供应商行为和真实供应商评测频率
- 评测语料与阈值
- 桌面框架
- 许可证与发布策略
- 退出后会话恢复与长期记忆

## 下一检查点

规划分支 rebase 与接口复核完成后，本地合并到 `main`，再严格按 0010→0014 顺序实施；未取得规格 15 条验收证据前不标记阶段三完成。
