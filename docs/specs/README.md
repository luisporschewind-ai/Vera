# 产品规格

产品规格在实施前定义可观察行为、边界和验收标准。

## 约定

- 文件命名为 `YYYY-MM-DD-<topic>.md`。
- 状态只使用 `Draft`、`Accepted` 或 `Superseded`。
- 包含目标、非目标、用户流程或系统行为、边界、失败行为和可验证验收标准。
- 链接约束设计的架构决策和实现该规格的任务。
- 除非用户明确批准限时 Spike，否则不能实施 Draft 规格。

每份规格应保持为可独立验证的产品增量；跨多个增量的阶段总规格必须明确拆分和退出条件。

## 当前规格

- [Core 安全编辑垂直切片](2026-09-10-core-safe-editing-vertical-slice.md)
- [交互式 CLI 会话](2026-09-10-interactive-cli-session.md)
- [普通对话、会话上下文与状态命令](2026-09-11-conversational-cli-and-session-status.md)
- [阶段二：恢复、兼容性与策略扩展](2026-09-11-phase-2-recovery-compatibility-policy.md)
- [阶段三：富交互 Terminal UI](2026-09-11-rich-terminal-ui.md)
- [阶段四：评测与内部就绪](2026-09-12-evals-and-internal-readiness.md)
- [阶段五：Core 安全、权限与可靠性加固](2026-09-12-core-security-and-reliability-hardening.md)
- [阶段六：CLI 功能与可靠性收口](2026-09-12-cli-productization-and-polish.md)
- [验证产物隔离与工作区无污染](2026-09-14-verification-artifact-isolation.md)
- [阶段七：CLI 体验收口与个人主力化](2026-09-13-cli-experience-and-personal-dogfood.md)
- [持久化对话会话与个人主力 CLI](2026-09-13-persistent-conversation-sessions.md)
- [项目指令发现与 `VERA.md` 初始化](2026-09-14-project-instructions-and-vera-init.md)
- [Vera CLI 视觉 Token 与标识](2026-09-13-vera-cli-visual-tokens.md)
- [不可信内容、提示词投毒与内容安全](2026-09-12-untrusted-content-and-prompt-injection-defense.md)
- [阶段八：Core 工具集与风险分级 Policy v2（Accepted）](2026-09-17-core-tooling-and-risk-tiered-policy.md)
- [阶段八：Vera 原生 Git 能力（Accepted）](2026-09-17-native-git-capability.md)
- [阶段九：Core 原生 Skills 系统（Accepted）](2026-09-15-core-native-skills-system.md)
- [阶段十：桌面 Agent 工作台与 UI（Draft）](2026-09-12-desktop-agent-workbench-ui.md)
- [工作区权限沙盒（Accepted）](2026-09-26-workspace-permission-sandbox.md)
- [Apple iOS 构建系统服务授权边界（Accepted；实施验证中）](2026-09-28-apple-ios-build-service-boundary.md)
