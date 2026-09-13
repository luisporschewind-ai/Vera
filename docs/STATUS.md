# Vera 状态

**更新日期：** 2026-09-13
**当前阶段：** 阶段 6——CLI 产品化与体验完善（In progress / Ready for manual acceptance）
**仓库状态：** 阶段五停在 Ready for manual acceptance。任务 0025–0028 已完成；任务 0029 自动部分完成，停在 Ready for manual acceptance。不引入 Electron 代码。暂无远程时可不推送。

## 已完成

- 阶段一、阶段二、阶段三、阶段四全部任务
- [任务 0029：阶段六产品验收](tasks/0029-phase-6-product-acceptance.md)（自动完成，Ready for manual acceptance）
- [任务 0028：终端兼容、可访问性与性能](tasks/0028-terminal-compatibility-accessibility-performance.md)
- [任务 0027：时间线、Diff、审批与错误体验](tasks/0027-timeline-diff-approval-and-errors.md)
- [任务 0026：路径引用、命令目录与诊断](tasks/0026-path-mentions-commands-and-diagnostics.md)
- [任务 0025：Composer、历史、粘贴与单条队列](tasks/0025-composer-history-paste-and-queue.md)
- [任务 0024：契约冻结与阶段五验收](tasks/0024-phase-5-contract-freeze-and-acceptance.md)（自动完成，Ready for manual acceptance）
- [任务 0030：不可信内容与提示词投毒防御](tasks/0030-untrusted-content-and-prompt-injection.md)
- [任务 0023：代表性工程与安装升级](tasks/0023-representative-projects-and-install-upgrade.md)
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

- [阶段六执行顺序](tasks/phase-6-execution-order.md)：0025–0029 自动部分已完成；0029 与阶段六停在 Ready for manual acceptance。
- [阶段五执行顺序](tasks/phase-5-execution-order.md)：0024 自动门禁已完成；人工 dogfood 不足，阶段五保持 Ready for manual acceptance。
- [ADR-0013：阶段七首个桌面底版采用 Electron](decisions/ADR-0013-electron-desktop-baseline.md)：Accepted；只固定未来实施方向，不改变 CLI 封存门禁，当前不引入 Electron 代码或依赖。
- [阶段七：桌面 Agent 工作台与 UI](specs/2026-09-12-desktop-agent-workbench-ui.md)：Draft；不启动阶段七。
- [不可信内容、提示词投毒与内容安全](specs/2026-09-12-untrusted-content-and-prompt-injection-defense.md)：Accepted；由任务 0030 与 ADR-0015 实施。

## 最近验证

- 任务 0029：[phase-6-cli-product-acceptance](evals/phase-6-cli-product-acceptance.md)；人工走查见 [phase-6-manual-walkthrough](evals/phase-6-manual-walkthrough.md)，七项均为 Not run
- 任务 0028：终端能力探测、尺寸矩阵、时间线预算与兼容记录
- 任务 0027：时间线披露、Diff 浏览、过期审批与退出码
- 任务 0026：`@path`、统一 Catalog 与七个只读诊断命令
- 任务 0025：Composer 历史、粘贴净化、单条队列与外部编辑器
- 完整非 live：736 passed / 2 deselected
- 任务 0024：[phase-5-core-hardening](evals/phase-5-core-hardening.md)
- 任务 0030：[untrusted-content-and-prompt-injection](evals/untrusted-content-and-prompt-injection.md)
- 完整非 live：683 passed / 2 deselected
- 任务 0023：[representative-projects-and-install-upgrade](evals/representative-projects-and-install-upgrade.md)
- 完整非 live：634 passed / 2 deselected
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

1. 等待用户在真实 Terminal.app 与真实工程中完成阶段六走查；未经「CLI 版本达到预期，可以封存」不得封存。
2. 阶段五仍缺 20 次真实 dogfood 与三类真实工程走查，不得把阶段五标为 Complete。
3. 未经确认「CLI 版本达到预期，可以封存」，不得将阶段六标为 Complete、不得开始阶段七、不得引入 Electron 或其他桌面端代码。
