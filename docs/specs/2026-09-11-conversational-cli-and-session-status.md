# Vera 普通对话、会话上下文与状态命令规格

**状态：** Accepted
**日期：** 2026-09-11

## 目标

在已验证的安全编辑主链路之上，为 Vera CLI 增加自然对话能力和可理解的会话状态。用户从工程目录执行 `vera` 后，可以在同一个 `Vera >` 提示符中自由提问、讨论工程和发起代码修改，而不必把每次输入都写成严格的修改指令。

普通文本回复与代码修改共享同一套 Core 模型适配、工具和 Event 边界。只有真正修改文件或执行需要审批的验证命令时，才进入现有 Change Set、Checkpoint 和审批流程；普通对话不能降低任何写入安全要求。

第一版只提供当前进程内的会话上下文。退出 Vera 后不恢复对话，不建立长期记忆系统。

## 已确认原则

- 普通对话和编码任务使用统一的 `Vera >` 入口，由模型根据用户意图选择直接回答、使用只读工具或提出 Change Set。
- 同一 CLI 进程内默认保留会话上下文，支持“刚才”“继续”“把那个改成蓝色”等连续表达。
- `/new` 和 `/clear` 可以主动清空上下文；退出进程后上下文自动清空。
- 每次用户输入仍创建独立 run。每个实际修改继续拥有独立 Event Journal、审批、Checkpoint、验证和回滚边界。
- 会话上下文只保存必要的用户消息、助手文本和简短 run 结果，不重复塞入完整工具输出、Diff、日志或秘密。
- CLI 和未来桌面客户端消费相同的结构化 Core 能力；桌面客户端不得解析 CLI 文本。

## 用户体验

### 启动状态

从工程目录执行 `vera` 后，显示紧凑状态面板：

```text
Vera 0.1.0

Model       deepseek / deepseek-flash
Workspace   /Users/admin/Desktop/VeraTestDemo
Git         main · clean
Session     new · 0 messages
Approval    manual
Execution   current user · no OS sandbox

输入 /help 查看命令
Vera >
```

状态面板必须：

- 显示 Vera 版本、当前 Provider Profile 与模型名；
- 显示规范化绝对工作区；
- 工作区是 Git 仓库时显示分支和 clean/dirty，只做只读检查；
- 显示会话消息数量和是否已压缩；
- 明确显示审批模式与验证进程权限边界；
- 不显示 API Key、认证头、完整 Base URL 或私有环境文件内容。

非 Git 工程显示 `Git         not a repository`。状态读取失败只降级对应字段，不能阻止会话启动。

### 普通对话

示例：

```text
Vera > Hello
Vera：你好，我是 Vera。你可以让我解释工程、查看代码，或提出安全修改。
Vera > 这个工程的入口在哪里？
Vera：入口位于……
Vera > 把刚才提到的背景色改成红色
……进入 Diff 与审批流程……
```

模型返回非空文本且没有工具调用时：

1. Runtime 产生结构化 `assistant.message` Event；
2. 人类模式显示助手文本；JSON 模式输出原始 Event JSON；
3. run 产生 `run.completed`，其中 `state=completed`、`outcome=responded`；
4. 不创建 Change Set 或 Checkpoint，不修改工作区；
5. CLI 把本轮用户输入和助手回复加入会话上下文，然后返回 `Vera >`。

模型使用只读工具调查后给出最终文本时，同样以 `responded` 正常完成。模型既没有工具调用也没有非空文本时，才以 `empty_model_response` 失败。

### 编码任务

模型判断任务需要修改文件时，继续使用现有 `propose_changeset`。以下边界保持不变：

- 模型不能直接写文件；
- CLI 必须展示 Runtime 产生的权威统一 Diff 和内容哈希；
- Change Set 必须明确审批；
- 写入前必须创建 Checkpoint；
- 需要审批的验证命令必须再次独立审批；
- 后续输入可以引用本次目标和结果，但不会继承未完成审批或可变 Runtime 内部对象。

代码 run 完成后，会话上下文保存用户指令和一条确定性的简短结果摘要，例如“已应用 Change Set，验证通过，run ID 为……”。完整 Diff、工具结果和 Event 仍留在 run Journal 中，通过 `/show` 查询。

## 会话上下文

新增 UI 无关的 `ConversationContext`，由 Core 层定义并由 CLI 持有当前进程实例。未来桌面客户端复用该组件，而不是自行拼接模型消息。

`ConversationContext` 保存：

- 当前临时 `session_id`；
- 有顺序的用户消息和助手消息；
- 已完成代码 run 的简短结果摘要；
- 消息数量、UTF-8 字节数和压缩次数。

它不保存：

- 原始工具输出；
- 完整 Diff、stdout 或 stderr；
- Approval 对象、Checkpoint 内容或 Runtime 状态机；
- API Key、认证配置或环境变量；
- 跨进程可恢复的对话记录。

每个 `StartRun` 通过向后兼容的可选 `conversation` 字段接收当前上下文快照，并增加默认值为 `agent` 的 `mode` 字段。Runtime 使用：固定系统策略、会话上下文、当前用户输入组成模型请求。旧客户端不传新字段时，行为保持兼容。

对话上下文默认容量为 200,000 UTF-8 字节，作为 `Limits.max_conversation_bytes` 的独立可降低配置。达到 70% 时在每轮结束后提示用户执行 `/compact` 或 `/new`；当前上下文加新输入超过上限时拒绝该输入，但仍允许 `/compact`、`/new`、`/clear` 和只读会话命令。`/context` 显示消息数、UTF-8 字节数、限制占比和压缩次数，不能静默丢弃消息。

## Core 契约

新增不可变、可序列化的 `ConversationMessage`，只允许 `user`、`assistant`、`summary` 三种角色和纯文本 `content`。`StartRun.conversation` 使用该类型的有序元组，默认空元组；`StartRun.mode` 只允许 `agent` 或 `compact`，默认 `agent`。

普通对话成功时新增：

- `assistant.message`：包含脱敏后的最终文本；
- `run.completed`：Payload 包含 `state=completed` 和 `outcome=responded`。

上下文压缩继续通过 `StartRun` 进入 `VeraRuntime`，使用 `mode=compact`，而不是让 CLI 直接调用 `ModelAdapter`。Runtime 在该模式下使用专用压缩 System Prompt、当前 `conversation` 和可选关注点，向模型发送不带任何工具定义的请求；成功产生 `conversation.compacted` 和 `run.completed`。`run.started` 必须记录 `kind=task` 或 `kind=compaction`，`RunStore.list_runs()` 默认排除 `kind=compaction`。

所有新增字段保持 `schema_version=1` 的向后兼容默认值；若实施发现必须改变既有字段含义或移除字段，必须升级协议版本，不能静默复用版本 1。

## 上下文压缩

`/compact [关注点]` 请求 Core 使用当前模型把已有对话压缩成一条结构化摘要：

- 压缩请求不提供项目工具，不能读写工作区或执行命令；
- 可选关注点只用于指导摘要，例如 `/compact 保留架构决策`；
- 成功后用摘要替换旧会话消息，保留当前 `session_id` 并增加压缩次数；
- 失败时保留原上下文，不做部分替换；
- 压缩会消耗一次模型请求，执行前 CLI 明确显示“正在压缩上下文”；
- 压缩结果进入结构化 Event，但普通 `/runs` 默认不把压缩显示成编码任务。

第一版不自动压缩。达到警戒线时只提示，由用户明确运行 `/compact` 或 `/new`。

## 斜杠命令

### 本增量实现

| 命令 | 行为 |
|---|---|
| `/help` | 显示支持的命令、参数和审批输入 |
| `/status` | 重新显示启动状态面板 |
| `/new` | 清空会话上下文并生成新 `session_id`，保留终端内容 |
| `/clear` | 执行 `/new` 的语义，并清理当前终端显示 |
| `/compact [关注点]` | 使用模型压缩当前上下文；空上下文不调用模型 |
| `/context` | 显示上下文统计，不显示消息正文 |
| `/model [profile]` | 无参数显示当前模型；指定已配置 Profile 时切换当前会话模型 |
| `/permissions` | 只读显示审批规则、验证命令策略和 OS 沙箱边界 |
| `/runs` | 保留：列出普通 run |
| `/show <run-id>` | 保留：显示脱敏 Event |
| `/rollback <run-id>` | 保留：通过 Core 安全回滚 |
| `/exit`、`/quit` | 保留：退出并清除内存会话上下文 |

所有命令都必须校验参数。未知命令、参数缺失或参数多余只显示帮助，不发送给模型、不退出会话。

### `/model` 规则

- `/model` 显示当前 Profile、模型名，不显示 Key 或完整 Base URL；
- `/model <profile>` 只能选择有效配置中已经存在的 Provider Profile；
- 切换只在两个 run 之间发生，不中断审批中的 run；
- 切换后保留会话文本上下文，但新 Runtime 继续读取同一私有状态目录；
- Profile 不存在或装配失败时保持原模型与 Runtime，不产生半切换状态。

模型切换由 UI 无关的运行时工厂完成。CLI 只能请求构建候选 Runtime；候选完全成功后才替换当前 Runtime 引用。当前 `ConversationContext` 和私有状态目录保持不变。

### `/permissions` 规则

第一版 `/permissions` 仅用于查看：

- Change Set 是否必须审批；
- 验证命令的 allow/deny/approval-required 分类；
- 当前真正注入 Runtime 并生效的用户命令前缀；
- 验证进程使用当前系统用户权限；
- 当前没有 OS 级沙箱。

该命令不能启用自动批准、绕过 CommandPolicy 或扩大工作区边界。

本增量必须把 `VeraConfig.user_allowed_command_prefixes` 注入 Runtime 使用的 `CommandPolicy`。若配置未注入或策略状态无法确认，`/permissions` 显示 `unavailable`，不能把仅存在于配置文件但没有生效的前缀声称为有效授权。

## 暂不支持

- 退出后 `/resume` 对话或自动恢复上一会话；
- 长期用户记忆、项目知识记忆、向量库或 RAG；
- `/memory`、`/agents`、`/tasks`、`/mcp`、`/fork`；
- `/review`、`/doctor`、交互式 `/config` 和自定义 Slash Command；
- `!shell` 或任何绕过 Vera 命令策略的直接 Shell 模式；
- 自动批准 Change Set 或验证命令；
- 自动压缩、后台任务、多 Agent 或跨会话消息；
- 全屏 TUI、命令补全、多行编辑器和主题系统。

`/diff`、`/review`、`/doctor`、`/config`、`@路径` 和输入历史属于后续 CLI 体验增量。

## 失败行为

- 普通对话的模型请求失败：run 产生 `run.failed`，保留此前会话上下文并返回提示符。
- 空模型响应：以 `empty_model_response` 失败，不再使用含义错误的 `no_changes_proposed`。
- 上下文过大：拒绝新的普通 run，提示 `/compact` 或 `/new`，不静默截断。
- 压缩失败：保留原上下文和当前模型。
- 模型切换失败：保留原 Runtime、Profile 和上下文。
- Git 状态检查失败：状态面板相应字段显示 `unavailable`，不退出。
- `/clear` 无法控制终端时：仍清空会话上下文，并打印确认信息。
- Event 展示继续经过脱敏；助手文本不得包含 Runtime 注入的秘密。

## 安全与隐私

- 自动测试继续强制隔离真实供应商变量和私有环境文件；不得使用用户 DeepSeek Key。
- 普通对话可以使用既有只读工具，但所有项目路径仍受 `WorkspacePaths` 约束。
- 会话上下文不得包含完整工具回执、私有配置或环境变量。
- `assistant.message` 会作为脱敏 Event 写入该 run 的私有 Journal；退出后不再加载进新会话，但 `/show` 仍可查询历史证据。
- 启动状态、`/status`、`/model` 和 `/permissions` 不得输出秘密。
- 新增状态能力必须以结构化 Core 数据提供，CLI 只负责渲染；不能让未来桌面客户端解析终端文本。
- Git 状态由 UI 无关的 Workspace 状态服务通过固定 argv、无 Shell、只读且带超时的 Git 查询产生；CLI 不直接执行 Git 或推断状态。

## 验收标准

1. 输入 `Hello` 时显示非空助手回复，run 以 `completed/responded` 结束并返回提示符。
2. 模型使用只读工具后返回文本时正常完成，不创建 Change Set、Checkpoint 或文件写入。
3. 同一会话第二个输入能在模型请求中看到此前用户与助手消息，并能理解指代。
4. 编码任务仍完整经过 Diff、Change Set 审批、Checkpoint、写入和验证审批，不因普通对话能力绕过边界。
5. 代码 run 完成后，后续上下文只收到简短结果摘要，不重复注入完整 Diff 或工具输出。
6. `/new` 清空上下文并生成新会话标识；终端内容保留。
7. `/clear` 清空上下文；终端清理不可用时安全降级。
8. `/compact` 成功后以摘要替换旧消息；失败时原消息字节完全不变；空上下文不调用模型。
9. `/context` 只显示统计，不显示消息正文或秘密。
10. 启动和 `/status` 显示版本、模型、工作区、Git、会话与安全状态；任何字段失败不会阻止启动。
11. `/model` 可查看并安全切换已配置 Profile；失败时保持原运行配置。
12. `/permissions` 只读展示边界，不能改变审批或命令策略。
13. 现有 `/runs`、`/show`、`/rollback`、`/exit`、`/quit` 和 `vera run --json` 保持兼容。
14. 所有新增 Event 和 Command 完成序列化 round-trip 测试；JSON 模式不包含人类提示符或 ANSI 控制字符。
15. 非 live 自动测试只使用 Fake Model 和临时工程，不读取用户真实 Key，不修改 `VeraTestDemo`。
16. 完整非 live 测试、Ruff、格式、Mypy、包构建和 `git diff --check` 全部通过。

## 参考与关联

- [Claude Code 官方 Commands](https://code.claude.com/docs/en/commands)
- [Codex CLI 官方 Developer commands](https://developers.openai.com/codex/cli/slash-commands)
- [Gemini CLI 官方 Commands](https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/commands.md)
- [交互式 CLI 会话规格](2026-09-10-interactive-cli-session.md)
- [ADR-0002：Command → VeraRuntime → Event 公共契约](../decisions/ADR-0002-command-event-contract.md)
- [ADR-0004：进程内会话上下文与状态边界](../decisions/ADR-0004-ephemeral-conversation-context.md)
- [任务 0004：普通对话、会话上下文与状态命令实施计划](../tasks/0004-conversational-cli-and-session-status.md)
