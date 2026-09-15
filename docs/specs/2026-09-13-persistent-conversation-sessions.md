# Vera 持久化对话会话与个人主力 CLI

**状态：** Accepted
**日期：** 2026-09-13

## 背景

Vera 已有进程内 `ConversationContext`，能够在同一次 CLI 进程中保留用户消息、助手回复、run 结果摘要和压缩摘要；现有 `RunStore`、Event Journal 与 RecoverySnapshot 则负责保存工具、Diff、审批、Checkpoint、验证和中断恢复事实。

当前进程退出后会丢弃活动对话。用户已确认：桌面开发顺延到阶段八，阶段七先把 CLI 提升为本人愿意长期使用的主力 Coding Agent；Codex、Claude Code 和 Grok Build 只作为核心交互质量参考，不要求复制它们的云端、多 Agent、插件市场或全部扩展能力。退出后恢复完整对话是这一目标的必需能力。

本规格取代“退出后不恢复自然语言对话”的旧范围限制，但不把对话恢复与未完成 run 恢复混为一套机制。

## 目标

- 在 Vera 退出、Terminal.app 关闭或机器重启后，恢复同一 workspace 的自然语言对话并继续任务。
- 保持 `vera` 默认创建新会话；提供明确的最近会话继续和历史会话选择入口。
- 会话持久化由 UI 无关的 Core 服务提供，TUI、Plain、JSON 与未来桌面客户端不得各自实现存储逻辑。
- 把自然语言上下文与权威 run 证据分开：对话只引用 `run_id`，工具、Diff、审批和恢复事实继续以 Run Journal 为准。
- 在崩溃、损坏、版本不兼容、workspace 不匹配或磁盘写入失败时保留原证据并给出可行动结果。
- 通过真实 Terminal.app、真实工程和持续 dogfood 验证其达到个人主力 CLI 的使用标准。

## 非目标

- 不实现长期用户画像、跨工程知识记忆、RAG、向量数据库或语义检索。
- 不恢复已经中断的模型推理或任意工具循环；未完成 run 仍只在现有确定性稳定边界恢复。
- 不把完整工具输出、Diff、stdout、stderr、Checkpoint、Provider 请求或环境变量复制进会话日志。
- 不自动跨 workspace 注入历史上下文，不自动把移动后的目录重新绑定为旧 workspace。
- 不新增 Multi-Agent、MCP/插件市场、后台任务、云同步或账号系统。
- 不启动阶段八，不添加 Electron、Tauri、Wails 或其他桌面端代码与依赖。
- 不以功能数量追平竞品；阶段七只验证日常编码主链路的质量和可控性。

## 产品行为

### 启动入口

| 入口 | 行为 |
|---|---|
| `vera` | 始终创建新会话；即使当前 workspace 有历史会话，也不隐式恢复 |
| `vera -c` / `vera --continue` | 恢复当前 workspace 最近一个可恢复会话；没有匹配项时明确失败，不静默创建新会话 |
| `vera -r` / `vera --resume` | 在交互式 TTY 中打开当前 workspace 的历史会话选择器 |
| `vera -r <session-id>` | 恢复指定会话；会话不存在、损坏或不属于当前 workspace 时拒绝加载 |
| `vera --plain -r <session-id>` | 恢复指定会话并进入 Plain 模式 |
| `vera --json -r <session-id>` | 恢复指定会话并以结构化 Event 报告加载结果，不输出选择器或 ANSI |

`-r` 没有参数且当前不是交互式 TTY 时，不读取 stdin 猜测选择；列出可用会话的精简标识并提示传入明确的 `session-id`。

现有 `/resume <run-id>` 在本增量中继续表示“恢复中断的 run”，帮助、补全和错误文案必须明确写出 run，避免与 `vera --resume` 的对话会话含义混淆。若后续真实使用仍造成混淆，再独立评审命令迁移，不在本增量中破坏已有命令。

### 会话列表与状态

- `/sessions` 只读列出当前 workspace 的会话，至少显示标题、短 ID、更新时间、消息数、最近 run 状态与是否可恢复。
- `/sessions` 不在有活动 run 或未决审批时切换上下文；第一版只提供查看与重启提示，恢复通过启动参数完成。
- `/status` 显示当前 `session_id`、新建或恢复来源、消息数、压缩次数和持久化状态。
- `/new` 创建新的持久化会话并清空活动模型上下文；旧会话仍保留。
- `/clear` 保持 `/new` 的会话语义，并清理当前终端展示。
- `/compact` 保留完整可查看历史，同时把模型后续收到的活动上下文替换为压缩摘要和压缩后的新消息。
- 第一条有效用户输入生成确定性的本地标题；不为标题额外调用模型。

### 恢复后的展示与上下文

- 恢复时，模型上下文由最近一次有效压缩摘要加其后的用户/助手消息组成。
- 完整历史仍保留在 Session Journal；压缩不得删除或重写旧记录。
- TUI 恢复用户消息、助手最终回复和简短 run 结果，不把旧工具输出和完整 Diff 铺回时间线。
- 历史较长时采用有界首屏和增量加载，不能一次创建无限 Widget 或阻塞输入。
- Plain 模式恢复时显示精简的恢复确认和最近上下文，不把全部历史自动打印到 scrollback。
- JSON 模式产生稳定的结构化 `session.loaded`、`session.load_failed` 等结果；客户端不得解析人类文案。
- 输入历史从已恢复会话的用户消息重建，使上方向浏览与 `Ctrl+R` 在重启后仍有意义。

## 存储架构

### 权威边界

```text
Vera 私有状态目录
├── runs/<run-id>/...                 # 既有权威运行证据
└── sessions/<session-id>/
    └── session.jsonl                 # 新增：权威会话记录
```

`ConversationSessionStore` 是 UI 无关的唯一会话存储入口。TUI、Plain 与 JSON 只通过 SessionController 和结构化结果使用该服务。未来桌面客户端复用同一服务，不读取或解析 TUI 输出。

Session Journal 与 Run Journal 分离：

- Session Journal 回答“这段对话是什么、按什么顺序发生、下次给模型什么上下文”；
- Run Journal 回答“工具做了什么、用户批准了什么、工作区发生了什么变化、怎样恢复或回滚”；
- 会话记录只通过 `run_id` 关联运行证据，不复制其完整 Payload。

### Session Record

Session Journal 使用 UTF-8 JSON Lines、连续 `sequence`、稳定 `record_id`、`session_id`、时间戳和独立的 `session_format_version`。第一版至少支持：

- `session.created`：版本、workspace 身份、规范化路径、创建时间；
- `turn.committed`：用户消息、助手最终消息或确定性 run 摘要、关联 `run_id`；
- `context.compacted`：压缩摘要、压缩前序号边界、压缩次数；
- `session.renamed`：确定性标题或后续显式标题；
- `session.closed`：正常关闭事实；缺少该记录不表示损坏。

会话记录允许保存用户主动输入的项目文本，因此 Vera 必须如实说明：私有会话目录可能包含用户提示、路径和粘贴的源码片段。写入前继续使用 Redactor 处理可识别凭据，但不能声称自动识别所有敏感内容。

### 写入顺序

每轮只有在 run 到达稳定终态后才提交对话：

```text
StartRun
→ 收集结构化 Event
→ 生成脱敏的 Conversation Turn
→ 追加并 fsync Session Journal
→ 更新内存 ConversationContext
→ 返回持久化成功状态
```

若 run 在稳定终态前中断，会话保持在上一轮完整状态；未完成 run 由现有 `RecoveryCoordinator` 检查。若 run 已完成但会话追加失败，工作区与 Run Journal 事实不回滚，当前进程可保留该轮内存上下文，但 `/status` 必须显示 `unsaved`，退出前给出明确警告。

压缩采用追加记录，不覆写旧消息。恢复投影器从最后一个有效 `context.compacted` 记录开始构建模型上下文，同时保留完整展示历史。

### 索引与发现

- 第一版以 `sessions/` 下的合法会话目录和 Journal 为权威来源。
- 可增加可重建的派生索引优化选择器，但索引不能成为唯一证据；删除索引后必须能从 Journal 重建。
- `--continue` 只在当前 workspace 身份完全匹配且格式可恢复的会话中选择更新时间最新者。
- 明确 `session-id` 指向其他 workspace 时拒绝加载，并显示期望 workspace；不提供隐式跨目录授权。

## 崩溃、损坏与版本行为

- 每次追加写入必须保持目录 `0700`、文件 `0600`，拒绝符号链接目标，并在返回成功前 `fsync`。
- 尾部不完整 JSON、sequence 断裂、中间记录损坏和字段校验失败必须分类，不得静默跳过后继续注入模型。
- 仅有明确尾部截断且此前记录连续时，可以提出“从有效前缀创建修复副本”；该操作必须显式确认，原 Journal 保持不变。
- 中间损坏或证据矛盾进入 `manual_required`，只能检查，不自动修复。
- 未知未来 `session_format_version` 返回 `unsupported_version`；旧版本通过纯 Decoder 在内存中读取。
- 必须迁移磁盘格式时，沿用 dry-run、备份、原子派生写入和结果校验原则，不原地重写唯一历史。
- workspace 身份不匹配、私有状态目录不可写或 Redactor/Codec 失败时，恢复或保存必须失败关闭，不得退化为未经声明的非持久化模式。

## 与现有组件的关系

- `ConversationContext` 继续负责活动模型上下文、容量、压缩和统计，但不直接操作磁盘。
- 新增纯投影边界，把 terminal run 的 Event 转换为可提交的 Conversation Turn；内存与磁盘必须消费同一结果，避免两套摘要逻辑。
- `ConversationSessionStore` 负责创建、追加、加载、列出和验证会话。
- `SessionController` 编排 Store、Context 与 Runtime，不直接拼接 JSON 或自行判断磁盘格式。
- `RunStore`、Event Journal、RecoverySnapshot、Checkpoint 与 `RecoveryCoordinator` 的职责保持不变。
- 会话恢复不改变 `Command -> VeraRuntime -> Event` 的任务执行边界，也不扩大工具或审批权限。

## 失败行为

| 情况 | 行为 |
|---|---|
| `--continue` 没有匹配会话 | 明确提示没有可继续会话并退出；不静默新建 |
| 指定会话不存在 | 返回 `session_not_found` |
| workspace 不匹配 | 返回 `session_workspace_mismatch`，不加载任何消息 |
| 格式未知 | 返回 `unsupported_session_version`，不写回 |
| Journal 损坏 | 返回损坏分类和只读检查建议，不跳过坏记录 |
| 会话保存失败 | 保留 Run/工作区事实，当前会话标为 `unsaved` 并提示用户 |
| 恢复后上下文超过当前限制 | 不静默截断；要求先使用兼容的压缩恢复流程或新建会话 |
| 恢复记录关联的 run 已缺失 | 对话文本仍可恢复，但关联证据标记 unavailable，不伪造 run 状态 |
| TTY 选择器不可用 | 要求显式传入 `session-id`，不猜测输入 |

## 实施增量

本规格在阶段七内实施，使用一个主实现 Agent，按依赖顺序拆分：

1. 收口当前任务 0033、任务 0042 的真实 dogfood 缺陷与验证事实；
2. 定义版本化 Session Record、Codec、Journal 和 workspace 绑定；
3. 接入 `ConversationContext` 的创建、追加、加载、压缩和新建；
4. 实现 `vera -c`、`vera -r`、选择器、`/sessions` 与状态展示；
5. 加固损坏、迁移、权限、脱敏、超限和崩溃一致性；
6. 对齐 TUI、Plain、JSON、wheel 安装和真实 Terminal.app；
7. 进行个人长期 dogfood，阻断问题继续留在阶段七修正。

具体文件、测试和提交边界见[阶段七实施计划](../tasks/phase-7-execution-order.md)及任务 0034–0037。

## 验收标准

1. `vera` 即使发现历史也创建新会话，不隐式注入旧上下文。
2. `vera -c` 只恢复当前 workspace 最近的可恢复会话；没有匹配项时不静默新建。
3. `vera -r` 在真实 TTY 中可选择历史；明确 ID 可在 TUI、Plain 和 JSON 模式恢复。
4. 恢复后的第二轮模型请求包含此前必要用户/助手上下文，并能理解“继续”“刚才”等指代。
5. `/compact` 后重启只把摘要和后续消息注入模型，但完整旧对话仍可查看。
6. 会话仅关联 `run_id`；完整工具输出、Diff、审批、Checkpoint 和 Provider 请求不复制进 Session Journal。
7. 正常完成、失败、取消和已应用修改都产生确定、脱敏、可恢复的 turn；未完成模型推理不被伪装成可续跑。
8. Session Journal 权限、符号链接防护、sequence、版本和损坏分类通过确定性测试。
9. 崩溃发生在追加前、追加中和追加后时，不重复 turn、不丢失已确认的旧 turn、不重复工作区副作用。
10. workspace 不匹配、未知未来版本和中间损坏都拒绝注入模型上下文，且不修改原文件。
11. 会话写入失败不会回滚已完成的 Run 或工作区变化，但界面持续显示 `unsaved`，退出时再次警告。
12. TUI 恢复时间线不铺开旧工具噪音；长历史采用有界加载且不阻塞 Composer。
13. Plain 与 JSON 不依赖 TUI 文本；JSON 加载结果无 ANSI、提示符或人类日志。
14. 恢复后的输入历史、`/status`、`/context`、`/new`、`/clear`、`/compact` 和 `/sessions` 行为一致。
15. 自动测试不读取真实 Provider Key，不修改用户真实工程；包构建与仓库外 wheel smoke 覆盖新入口。
16. 完整非 live、Ruff、格式、Mypy、构建、安装 smoke 和 `git diff --check` 通过。
17. 用户在真实 Terminal.app 中至少完成：新建会话、两轮对话、代码修改、审批、验证、退出、`-c` 恢复、继续修改和查看旧 run 证据。
18. 阶段七持续 dogfood 没有未关闭的 Critical/High 使用缺陷，并由用户明确确认「CLI 版本达到预期，可以封存」。

## 参考与关联

- [普通对话、会话上下文与状态命令](2026-09-11-conversational-cli-and-session-status.md)
- [阶段六：CLI 功能与可靠性收口](2026-09-12-cli-productization-and-polish.md)
- [阶段七：CLI 体验收口与个人主力化](2026-09-13-cli-experience-and-personal-dogfood.md)
- [ADR-0003：私有状态与 Checkpoint](../decisions/ADR-0003-private-state-and-checkpoints.md)
- [ADR-0004：进程内会话上下文与状态边界](../decisions/ADR-0004-ephemeral-conversation-context.md)
- [ADR-0005：确定性 Run 恢复边界](../decisions/ADR-0005-deterministic-run-recovery.md)
- [ADR-0006：版本化 Codec 与非破坏迁移](../decisions/ADR-0006-versioned-state-codecs.md)
- [ADR-0016：持久化对话会话与 Run 恢复分离](../decisions/ADR-0016-persistent-conversation-sessions.md)
