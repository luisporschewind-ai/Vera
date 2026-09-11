# Vera 状态

**更新日期：** 2026-09-12
**当前阶段：** 阶段 4——评测与内部就绪（任务 0015 完成，待实施 0016–0019）
**仓库状态：** 任务 0015 已在 `feature/eval-contracts-fixtures` 完成非 live 验收；暂无远程，未推送。

## 已完成

- 阶段一、阶段二、阶段三全部任务
- [任务 0010：流式 RuntimeOutput](tasks/0010-streaming-runtime-output.md)
- [任务 0011：Textual TUI 外壳与模式路由](tasks/0011-textual-tui-shell.md)
- [任务 0012：对话时间线与披露策略](tasks/0012-tui-timeline-and-disclosure.md)
- [任务 0013：Composer、审批与任务控制](tasks/0013-tui-composer-and-approvals.md)
- [任务 0014：模式兼容与阶段三验收](tasks/0014-terminal-modes-and-acceptance.md)
- [任务 0015：评测契约、Corpus 与夹具隔离](tasks/0015-eval-contracts-and-fixtures.md)

## 活动任务

- [阶段四执行顺序](tasks/phase-4-execution-order.md)
- [任务 0016：Worker、Runner 与基础评分](tasks/0016-eval-runner-and-scoring.md)
- [任务 0017：恢复场景、指标与确定性](tasks/0017-eval-recovery-and-metrics.md)
- [任务 0018：评测 CLI 与 14 个冻结任务](tasks/0018-eval-cli-and-corpus.md)
- [任务 0019：阶段四完整验收](tasks/0019-eval-phase-4-acceptance.md)

## 最近验证

- 任务 0015：[eval-contracts-and-fixtures](evals/eval-contracts-and-fixtures.md)
- 新增评测测试 44 项通过；覆盖率 90%；未跑 live、未读 Key
- 阶段三总验收：[phase-3-rich-terminal-ui](evals/phase-3-rich-terminal-ui.md)

## 下一检查点

从干净 `main` 创建 `feature/eval-runner-scoring`，实施任务 0016。完成阶段四后停止，不提前进入桌面端。
