# ADR-0004：进程内会话上下文与状态边界

**状态：** Accepted
**日期：** 2026-09-11

> 后续关系：ADR-0016 已取代“退出后丢弃活动上下文”和“对话不可跨进程恢复”两项限制；本 ADR 的进程内上下文、内容限制、压缩安全级别、每轮独立 run 和客户端共享 Core 边界继续有效。

## 背景

Vera 已经通过真实 iOS 工程验证安全编辑主链路，但当前每个 `StartRun` 只包含固定 System Prompt 和本轮目标。持续 CLI 虽然复用同一个 Runtime，却不能理解“刚才”“继续”等会话指代；模型返回普通文本而不调用工具时还会被错误标记为 `no_changes_proposed`。

会话上下文若只由 CLI 私自拼接，未来桌面客户端将重复实现上下文、压缩和状态规则，破坏已接受的 Core-first 与结构化契约边界。若现在直接建立跨进程长期记忆，又会提前引入恢复、隐私、淘汰和检索问题。

## 决策

- 新增 UI 无关的 `ConversationContext` Core 组件，统一管理当前进程内的用户消息、助手消息、run 结果摘要、容量和压缩次数。
- CLI 持有一个 `ConversationContext` 实例，未来桌面客户端复用同一组件；任何客户端都不能自行注入完整工具输出、Diff 或秘密。
- `StartRun` 以向后兼容的可选字段接收上下文快照，并以 `mode=agent|compact` 区分普通 Agent run 与无工具压缩 run。
- 普通文本通过结构化 `assistant.message` Event 输出；压缩通过 `conversation.compacted` Event 输出。CLI 和未来桌面客户端只渲染 Event。
- 每次用户输入仍是独立 run，审批、Checkpoint、验证和回滚边界不合并到 conversation。
- 会话退出后丢弃活动上下文，不从历史 Journal 自动恢复。普通回复仍作为私有、脱敏的 run Event 留存，以支持审计和 `/show`。
- 启动状态、上下文统计和权限状态由 UI 无关的结构化状态服务提供；CLI 不直接执行 Git、不推断有效权限，也不读取秘密。
- `/compact` 必须经过 Core 和当前 `ModelAdapter`，请求不携带工具定义；CLI 不直接调用供应商 SDK。
- `VeraConfig.user_allowed_command_prefixes` 必须注入实际 `CommandPolicy` 后才能被状态服务声明为有效。

## 备选方案

### 每个输入完全独立

实现最简单，但无法支持自然追问和指代，CLI 仍要求用户反复提交严格施工单，因此不采用。

### CLI 私有维护消息数组

短期修改较少，但会让 CLI 和未来桌面客户端分叉，并使上下文容量、压缩和结果摘要脱离 Core 测试，因此不采用。

### 立即持久化完整对话并支持恢复

体验最完整，但需要额外定义会话索引、恢复选择、隐私保留期、版本迁移和崩溃一致性，超出当前增量，因此延后。

## 后果

- 普通对话和安全编辑共享模型与工具能力，但写入审批边界不变。
- CLI 会话可以连续理解上下文，并通过 `/new`、`/clear` 和 `/compact` 控制容量。
- 增加少量向后兼容 Command/Event 字段与新 Event 类型；必须补充序列化 round-trip 测试。
- conversation 退出后不可恢复；长期记忆和 `/resume` 仍需独立规格。
- 上下文摘要是模型生成内容，作为 `summary` 或普通 assistant 级别上下文处理，绝不能提升为 System 指令。

## 验证与重审触发器

- Fake Model 证明第二个 run 收到前一轮用户/助手文本，但不收到原始工具回执和完整 Diff。
- 普通文本、只读工具后文本、压缩成功/失败、容量上限和清空操作都有确定性测试。
- CLI 与 JSON 模式只消费结构化 Event；启动状态不包含 Key 或 Base URL。
- 当需要退出后恢复、长期项目记忆、RAG 或多个并行会话时，重新评审本 ADR，不能直接扩展当前内存对象为数据库。
