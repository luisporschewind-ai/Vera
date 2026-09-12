# Vera 状态

**更新日期：** 2026-09-12
**当前阶段：** 阶段 5——Core 安全、权限与可靠性加固（进行中）
**仓库状态：** 任务 0022 离线实现已完成，待本地合并后从干净 `main` 执行 0023。阶段六封存门禁已写入规格。暂无远程，未推送。

## 已完成

- 阶段一、阶段二、阶段三、阶段四全部任务
- [任务 0022：状态、恢复与长会话加固](tasks/0022-state-recovery-and-long-run-hardening.md)
- [任务 0021：命令、进程与秘密加固](tasks/0021-command-process-and-secret-hardening.md)
- [任务 0020：文件系统与审批事实加固](tasks/0020-workspace-filesystem-and-approval-hardening.md)
- [任务 0010：流式 RuntimeOutput](tasks/0010-streaming-runtime-output.md)
- [任务 0011：Textual TUI 外壳与模式路由](tasks/0011-textual-tui-shell.md)
- [任务 0012：对话时间线与披露策略](tasks/0012-tui-timeline-and-disclosure.md)
- [任务 0013：Composer、审批与任务控制](tasks/0013-tui-composer-and-approvals.md)
- [任务 0014：模式兼容与阶段三验收](tasks/0014-terminal-modes-and-acceptance.md)
- [任务 0015：评测契约、Corpus 与夹具隔离](tasks/0015-eval-contracts-and-fixtures.md)
- [任务 0016：Worker、Runner 与基础评分](tasks/0016-eval-runner-and-scoring.md)
- [任务 0017：恢复场景、指标与确定性](tasks/0017-eval-recovery-and-metrics.md)
- [任务 0018：评测 CLI 与 14 个冻结任务](tasks/0018-eval-cli-and-corpus.md)
- [任务 0019：阶段四完整验收](tasks/0019-eval-phase-4-acceptance.md)

## 活动任务

- [阶段五执行顺序](tasks/phase-5-execution-order.md)：下一步从干净 `main` 执行任务 0023。
- [阶段六执行顺序](tasks/phase-6-execution-order.md)：阶段五完成前不开始；任务 0029 只能先进入 Ready for manual acceptance。

## 最近验证

- 任务 0022：[state-recovery-and-long-run-hardening](evals/state-recovery-and-long-run-hardening.md)
- 任务 0021：[command-process-and-secret-hardening](evals/command-process-and-secret-hardening.md)
- 完整非 live：587 passed / 2 deselected
- 任务 0020：[workspace-filesystem-and-approval-hardening](evals/workspace-filesystem-and-approval-hardening.md)
- 阶段四总验收：[phase-4-evals-and-internal-readiness](evals/phase-4-evals-and-internal-readiness.md)
- 阶段四独立安全与路线审查：[phase-4-independent-security-and-alignment-review](evals/phase-4-independent-security-and-alignment-review.md)，64/64 项已检查，无需报告的安全漏洞。
- 完整非 live：535 passed / 2 deselected；覆盖率 91%；manifest `8169f95abcb3bf1ccd30bfbadc1c2fee5464b7fdea3ce3909ea0fbc962a4d659`
- 仓库外 wheel smoke：`vera eval` validate/list/run/suite 均为 0，14/14 pass
- 任务 0018：[eval-cli-and-corpus](evals/eval-cli-and-corpus.md)
- 任务 0017：[eval-recovery-and-metrics](evals/eval-recovery-and-metrics.md)
- 阶段三总验收：[phase-3-rich-terminal-ui](evals/phase-3-rich-terminal-ui.md)

## 下一检查点

按任务 0020–0024 完成阶段五 Core 加固。阶段五人工证据不足时停在 Ready for manual acceptance，不得开始阶段六。

阶段六按 0025–0028 实施后，任务 0029 只能进入 Ready for manual acceptance，等待用户在真实 Terminal.app 和真实工程中体验。未经确认「CLI 版本达到预期，可以封存」，不得将阶段六标为 Complete、不得开始阶段七、不得引入 Wails/Tauri/Electron 或任何桌面端代码；Textual Pilot、快照和自动测试不能代替人工体验结论。人工体验发现问题继续作为阶段六修正任务。
