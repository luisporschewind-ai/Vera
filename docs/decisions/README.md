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
- [ADR-0005：确定性 Run 恢复边界](ADR-0005-deterministic-run-recovery.md)
- [ADR-0006：版本化 Codec 与非破坏迁移](ADR-0006-versioned-state-codecs.md)
- [ADR-0007：统一 PolicyEngine 与策略指纹](ADR-0007-unified-policy-engine.md)
- [ADR-0008：ModelAdapter 能力、错误与有限重试](ADR-0008-model-capabilities-and-errors.md)
- [ADR-0009：使用 Textual 构建富交互 Terminal UI](ADR-0009-textual-terminal-ui.md)
- [ADR-0010：以瞬时 Stream Frame 承载模型流式输出](ADR-0010-transient-stream-frames.md)
- [ADR-0011：评测工具作为隔离的 Core 客户端](ADR-0011-eval-harness-as-core-client.md)
- [ADR-0012：桌面集成延后至 Core 加固与 CLI 产品化之后](ADR-0012-delay-desktop-until-cli-hardening.md)
- [ADR-0013：首个桌面底版采用 Electron（历史标题为阶段八；当前由 ADR-0023 调整至阶段十一）](ADR-0013-electron-desktop-baseline.md)
- [ADR-0014：Core 客户端兼容契约](ADR-0014-core-client-compatibility-contract.md)
- [ADR-0015：不可信内容信任边界与提示词投毒分层防御](ADR-0015-untrusted-content-trust-boundary.md)
- [ADR-0016：持久化对话会话与 Run 恢复分离](ADR-0016-persistent-conversation-sessions.md)
- [ADR-0017：插入 CLI 体验阶段并顺延桌面路线](ADR-0017-insert-cli-experience-stage.md)
- [ADR-0018：验证产物必须在审批前规划并隔离](ADR-0018-isolate-verification-artifacts.md)
- [ADR-0019：以 `VERA.md` 作为原生项目指令并兼容 `AGENTS.md`](ADR-0019-native-vera-project-instructions.md)
- [ADR-0020：在 CLI 封存后、桌面之前插入 Core-native Skills 阶段](ADR-0020-stage-core-native-skills.md)
- [ADR-0021：桌面前插入 Core 工具集与 Git 能力阶段（阶段编号由 ADR-0023 取代）](ADR-0021-core-tools-before-desktop.md)

Core Runtime、协议、持久化模型、关键依赖、安全边界或桌面框架等长期选择应建立决策记录；常规实现细节写入任务记录。

## 补充索引（2026-09-26 对齐）

- [ADR-0022：BYOK Provider 配置由用户控制](ADR-0022-user-owned-byok-provider-configuration.md)
- [ADR-0023：在桌面集成前插入 Core Trace 与可观测性阶段（Accepted）](ADR-0023-insert-core-observability-before-desktop.md)
