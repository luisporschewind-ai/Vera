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
- [阶段三执行顺序](phase-3-execution-order.md)
- [任务 0010：流式 RuntimeOutput](0010-streaming-runtime-output.md)
- [任务 0011：Textual TUI 外壳与模式路由](0011-textual-tui-shell.md)
- [任务 0012：TUI 时间线与披露策略](0012-tui-timeline-and-disclosure.md)
- [任务 0013：TUI Composer、审批与任务控制](0013-tui-composer-and-approvals.md)
- [任务 0014：Terminal 模式兼容与阶段三验收](0014-terminal-modes-and-acceptance.md)
- [阶段四执行顺序](phase-4-execution-order.md)
- [任务 0015：评测契约、Corpus 与夹具隔离](0015-eval-contracts-and-fixtures.md)
- [任务 0016：Worker、Runner 与基础评分](0016-eval-runner-and-scoring.md)
- [任务 0017：恢复场景、指标与确定性](0017-eval-recovery-and-metrics.md)
- [任务 0018：评测 CLI 与 14 个冻结任务](0018-eval-cli-and-corpus.md)
- [任务 0019：阶段四完整验收](0019-eval-phase-4-acceptance.md)
- [阶段五执行顺序](phase-5-execution-order.md)
- [任务 0020：文件系统与审批事实加固](0020-workspace-filesystem-and-approval-hardening.md)
- [任务 0021：命令、进程与秘密加固](0021-command-process-and-secret-hardening.md)
- [任务 0022：状态、恢复与长会话加固](0022-state-recovery-and-long-run-hardening.md)
- [任务 0023：代表性工程与安装升级](0023-representative-projects-and-install-upgrade.md)
- [任务 0030：不可信内容与提示词投毒防御](0030-untrusted-content-and-prompt-injection.md)
- [任务 0024：契约冻结与阶段五验收](0024-phase-5-contract-freeze-and-acceptance.md)
- [阶段六执行顺序](phase-6-execution-order.md)
- [任务 0025：Composer、历史、粘贴与单条队列](0025-composer-history-paste-and-queue.md)
- [任务 0026：路径引用、命令目录与诊断](0026-path-mentions-commands-and-diagnostics.md)
- [任务 0027：时间线、Diff、审批与错误体验](0027-timeline-diff-approval-and-errors.md)
- [任务 0028：终端兼容、可访问性与性能](0028-terminal-compatibility-accessibility-performance.md)
- [任务 0029：阶段六产品验收](0029-phase-6-product-acceptance.md)
- [任务 0031：CLI 版本身份与 `--version`](0031-cli-version-identity.md)
- [任务 0032：时间线信息层次与错误保真](0032-timeline-and-error-fidelity.md)
- [任务 0033：用户消息、工具块与 tool_call_id](0033-cli-dogfood-bugs.md)
- [阶段七实施计划](phase-7-execution-order.md)
- [任务 0034：会话记录契约与 Codec](0034-session-record-contracts-and-codec.md)
- [任务 0035：安全 Session Journal、Store 与修复副本](0035-session-journal-store-and-repair.md)
- [任务 0036：Context 与 Controller 事务接入](0036-session-controller-persistence.md)
- [任务 0037：CLI 新建、继续、选择与会话维护](0037-cli-session-startup-and-resume.md)
- [任务 0038：CLI 视觉原型与设计 Token 冻结](0038-cli-visual-prototypes-and-tokens.md)
- [任务 0039：Vera 标识、主题与启动状态实现](0039-cli-brand-theme-and-startup-chrome.md)
- [任务 0040：时间线、Composer 与导航收口](0040-timeline-composer-and-navigation-polish.md)
- [任务 0041：阶段七产品验收与个人 dogfood](0041-phase-7-product-acceptance-and-dogfood.md)
- [任务 0044：走查发现 38–41（propose 回写与 sticky）](0044-cli-dogfood-propose-and-sticky.md)
- [任务 0054：走查发现 51–52（虚构审批卡与验证命令找不到）](0054-cli-dogfood-claimed-changeset-and-ruff.md)
- [任务 0055：工作轨、状态组收起与顶栏字标](0055-cli-work-rail-and-header-mark.md)
- [任务 0056：进场欢迎卡、缩行路径与底栏事实](0056-cli-welcome-card-and-footer-facts.md)
- [任务 0057：对话表格/Diff 渲染与进场波动可见](0057-cli-markdown-table-diff-and-wave.md)
- [任务 0058：缩放右侧残留与底栏显示不全](0058-cli-resize-remnant-and-footer-clip.md)
- [任务 0042：验证产物隔离与工作区无污染](0042-verification-artifact-isolation.md)
- [任务 0043：项目指令发现与 `VERA.md` 初始化](0043-project-instructions-and-init.md)
