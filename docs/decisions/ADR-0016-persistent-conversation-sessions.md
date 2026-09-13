# ADR-0016：持久化对话会话与 Run 恢复分离

**状态：** Accepted
**日期：** 2026-09-13

## 背景

ADR-0004 为第一版连续对话建立了 UI 无关的 `ConversationContext`，但刻意把范围限制在单个进程；退出后不会恢复对话。该限制避免了早期同时引入会话索引、格式迁移、隐私和崩溃一致性，却已经成为 Vera 作为个人主力 Coding Agent CLI 的明确使用障碍。

Vera 已有两类持久事实：Run Journal 记录模型、工具、审批和终态 Event；RecoverySnapshot 只在确定性稳定边界支持未完成 run 的恢复。直接从 Run Journal 猜测对话边界会把“自然语言连续性”和“副作用恢复”混在一起，也无法可靠表达压缩、标题和 workspace 内的多会话。

## 决策

- 新增 UI 无关的 `ConversationSessionStore`，以独立、版本化、追加式 Session Journal 保存可恢复对话。
- Session Journal 与 Run Journal 分离；会话通过 `run_id` 引用运行证据，不复制工具输出、Diff、审批、Checkpoint 或 Provider 请求。
- `ConversationContext` 继续是活动模型上下文的内存模型，不承担文件 IO；Store 加载后用经过验证的投影水合 Context。
- Session Journal 具有独立的 `session_format_version`、连续 sequence 和稳定 record id，不复用产品版本、公共 `schema_version` 或 `journal_format_version`。
- 每轮只在 run 到达稳定终态后提交 Conversation Turn；先持久化并 `fsync`，再更新内存 Context。
- 压缩追加 `context.compacted` 记录，不删除历史。展示投影可保留完整对话，模型投影只使用最近摘要与后续消息。
- `vera` 默认新建会话；`vera -c` 恢复当前 workspace 最近会话；`vera -r` 选择历史或恢复明确 ID。
- workspace 身份必须匹配。对其他 workspace、未知版本或损坏 Journal 失败关闭，不把内容注入模型。
- 会话损坏修复遵循非破坏原则：只允许从已验证前缀生成新副本，不原地重写唯一历史。
- 未完成模型推理不跨进程续传；审批、验证、部分应用和回滚继续由 `RecoveryCoordinator` 依据现有确定性事实处理。
- TUI、Plain、JSON 和未来桌面客户端必须消费同一 Store/Controller 结构化能力，不解析其他客户端的人类输出。

## 取代关系

本 ADR 只取代 ADR-0004 的以下决定和后果：

- “会话退出后丢弃活动上下文，不从历史 Journal 自动恢复”；
- “conversation 退出后不可恢复；长期记忆和 `/resume` 仍需独立规格”。

ADR-0004 对 `ConversationContext`、上下文内容限制、压缩安全级别、每轮独立 run 和客户端共享 Core 边界的其他决定继续有效。

本 ADR 不取代 ADR-0005。自然语言会话恢复与未完成 run 恢复是两个独立状态机：前者恢复已提交对话，后者只在已验证稳定边界继续副作用流程。

## 备选方案

### 从 Run Journal 重建对话

改动较小，但既有 Run Journal 没有可靠的会话边界、压缩生命周期和会话标题；部分 goal 还可能只保留哈希。该方案会让展示事实、模型上下文和恢复事实互相猜测，因此拒绝。

### 覆盖单个 session.json 快照

实现直接，但每轮覆盖会削弱追加证据、崩溃定位和非破坏迁移；还会让完整展示历史与压缩后的活动上下文难以同时保留，因此拒绝。

### 独立追加式 Session Journal

增加一种持久格式和 Codec，但职责清楚、可检测截断、可保留完整历史、可独立迁移，也能让未来桌面客户端复用，因此采用。

## 后果

- 用户可以在退出后恢复自然语言上下文，Vera CLI 开始具备主力工具所需的任务连续性。
- 私有状态可能保存用户提示、路径和主动粘贴的源码片段；需要明确隐私说明、严格权限、脱敏和后续可恢复的归档/清理入口。
- 会话与 run 形成引用关系，列表和展示必须容忍关联 run 缺失，但不能伪造其状态。
- SessionController 需要编排持久化失败状态；已完成的工作区副作用不能因为会话保存失败而回滚或重复执行。
- 增加 Session Codec、Journal、Store、恢复投影、CLI 入口和跨进程测试，但不改变 VeraRuntime 的工具与审批权威。
- 阶段六退出条件提高：自动测试通过仍不足，必须经过真实 Terminal.app 的退出—恢复—继续任务走查和持续个人 dogfood。

## 验证与重审触发器

- 在追加前、追加中、追加后注入崩溃，验证旧 turn 完整、新 turn 不重复、工作区副作用不重复。
- 对 current、已知旧版、未知未来版、尾部截断、中间损坏、sequence 断裂和 workspace 不匹配建立冻结 Fixture。
- 验证会话文件权限、符号链接拒绝、Redactor、容量上限和包外安装路径。
- 验证 TUI、Plain、JSON 对新建、继续、明确恢复和加载失败产生一致结构化事实。
- 若未来需要跨设备同步、长期用户记忆、跨 workspace 会话、分支会话或云端会话，应建立新的规格与 ADR，不扩张本地 Session Journal 的隐含语义。

## 关联

- [持久化对话会话与个人主力 CLI 规格](../specs/2026-09-13-persistent-conversation-sessions.md)
- [ADR-0003：私有状态与 Checkpoint](ADR-0003-private-state-and-checkpoints.md)
- [ADR-0004：进程内会话上下文与状态边界](ADR-0004-ephemeral-conversation-context.md)
- [ADR-0005：确定性 Run 恢复边界](ADR-0005-deterministic-run-recovery.md)
- [ADR-0006：版本化 Codec 与非破坏迁移](ADR-0006-versioned-state-codecs.md)
