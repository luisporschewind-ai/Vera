# Vera 阶段三：富交互 Terminal UI

**状态：** Accepted
**日期：** 2026-09-11

## 背景

Vera 已通过内部 CLI 跑通普通对话和安全编辑闭环，阶段二正在补齐恢复、兼容、统一策略与供应商韧性。现有逐行 REPL 适合验证 Core，但长任务会把工具、日志、Diff、审批和失败信息平铺在终端中，用户难以保持上下文，也无法快速定位真正需要处理的内容。

阶段三把 `vera` 提升为 Claude Code/Codex 风格的富交互终端客户端。它仍是共享 Vera Core 的一个客户端，不成为新的 Runtime，也不提前引入桌面框架。

## 目标

- `vera` 在交互式终端中默认启动全屏富交互 TUI。
- 对话时间线可使用键盘和鼠标滚动；用户向上阅读时，新内容不能抢走当前位置。
- 工具和普通日志默认折叠；Diff 和审批默认展开；任何失败自动展开。
- 模型最终文本实时流式显示，任务阶段使用轻量动画和明确状态词。
- 输入区固定在底部，支持多行输入、Slash Command、取消和审批操作。
- 保留 `vera --plain` 和 `vera --json`，并保持现有 `vera run ... --json` 兼容。
- TUI、Plain 和 JSON 都消费同一个 Session/Core 契约，不解析彼此的人类输出。

## 非目标

- 不实现桌面窗口、Web UI、Wails、Tauri 或 Electron。
- 不增加跨进程会话记忆、长期记忆、RAG 或 Multi-Agent。
- 不实现插件市场、完整主题市场或可编程布局系统。
- 不为动画伪造进度百分比，也不让 TUI 推断 Core 状态。
- 不允许 TUI 直接读写项目、执行 Shell、调用 Provider SDK 或绕过审批。

## 技术选型

阶段三采用：

- Typer：保留顶层命令、参数和子命令路由；
- Textual `>=8.2,<9`：富交互 TUI、滚动容器、折叠组件、焦点、键盘、Worker 和测试；
- Rich `>=14,<15`：Markdown、Diff、语义颜色和无 ANSI 的测试渲染；
- 现有 Vera Core：Command、Event、审批、恢复、策略和 Workspace 的唯一权威。

不引入 `prompt_toolkit`。它适合轻量 REPL 和高度定制输入，但本阶段的滚动时间线、可折叠卡片、审批焦点和可测试状态树需要大量自建组件。Textual 与 `prompt_toolkit` 同时接管 stdin、焦点和刷新循环会形成双事件循环，不作为支持组合。

Textual 官方提供 [RichLog](https://textual.textualize.io/widgets/rich_log/)、[Collapsible](https://textual.textualize.io/widgets/collapsible/)、[Markdown](https://textual.textualize.io/widgets/markdown/)、[Worker](https://textual.textualize.io/guide/workers/) 和 [Pilot 测试](https://textual.textualize.io/guide/testing/)。Codex 官方也把无子命令入口定义为 TUI，并提供动画与 alternate-screen 配置；Vera 第一版固定使用 alternate screen，原生 scrollback 需求由 `--plain` 满足。

## 模式与入口

| 调用 | 行为 |
| --- | --- |
| `vera` | stdin/stdout 均为 TTY 时启动 Textual 全屏模式 |
| `vera --plain` | 启动现有逐行人类交互模式，不使用 alternate screen 或动态重绘 |
| `vera --json` | 启动 NDJSON Session 协议，不输出 ANSI、人类提示词或动画 |
| `vera run <goal>` | 保持现有一次性人类模式 |
| `vera run <goal> --json` | 保持现有逐 Event NDJSON 兼容模式，不输出瞬时流帧 |

`--plain` 与 `--json` 互斥。无标志的 `vera` 若不在 TTY、`TERM=dumb` 或终端缺少必要光标控制能力，则以退出码 2 失败，并在 stderr 指示使用 `--plain` 或 `--json`；不能静默改变协议。

## 架构边界

```text
Typer mode router
├── TextualTerminalApp ─┐
├── PlainSessionDriver ─┼── SessionController ── VeraRuntime ── Workspace/Model/Policy
└── JsonSessionDriver ──┘          │
                                   └── RuntimeOutput
                                       ├── EventEnvelope（持久、权威）
                                       └── StreamFrame（瞬时、仅展示）
```

`SessionController` 统一处理提交文本、Slash Command、审批决定、取消和退出。三个前端只发送结构化 `SessionAction` 并消费 `RuntimeOutput`。只有 Core/Session 层可以调用 Runtime；Textual Widget 不持有 Provider、Workspace writer 或 Shell runner。

## 持久 Event 与瞬时 Stream Frame

模型流式文本不能让每个片段进入恢复 Journal。新增 UI 无关的 `StreamFrame`：

```text
schema_version: 1
run_id: str
stream_id: str
index: int
type: assistant.delta
payload.text: str
```

- `EventEnvelope` 继续是状态转换、恢复、审批和审计的唯一权威，并写入 Journal。
- `StreamFrame` 只用于进程内实时显示，不写 Journal、不进入 Snapshot、不触发副作用。
- `index` 从 0 单调递增；TUI 遇到重复项忽略，遇到缺口停止拼接并等待最终 Event。
- 流正常结束时，Core 写入完整、脱敏的 `assistant.message`，其中包含相同 `stream_id`。
- 流失败时产生持久 `run.failed`；已显示的部分文本标为“未完成”，不能写入对话上下文。
- 旧 `VeraRuntime.handle()` 继续只返回持久 Event；新增 `VeraRuntime.stream()` 返回 `EventEnvelope | StreamFrame`，避免破坏现有消费者。

ModelAdapter 增加流式接口和默认兼容实现。`ModelCapabilities` 在阶段三扩展 `streaming: bool = False`；未声明或 `streaming=False` 的 Adapter 继续调用 `complete()`，只产生最终 `assistant.message`；OpenAI-compatible Adapter 在 `streaming=True` 时实现真实文本与 Tool Call chunk 聚合。所有 Tool Call 仍要聚合并验证完成后才能交给 Runtime 执行。流式路径必须遵守阶段二 `RetryPolicy` 与 `ModelProviderError` 语义，且不得重复本地副作用。

## Terminal View Model

TUI 不直接把 Event 映射为零散 `print`。纯函数 `TimelineProjector` 把 `RuntimeOutput` 转换为稳定 View Model：

- `UserMessageBlock`：用户输入，展开；
- `AssistantMessageBlock`：Markdown 回答，展开并接收流片段；
- `ToolBlock`：工具名称、状态和摘要，默认折叠；
- `LogBlock`：普通日志和诊断，默认折叠；
- `DiffBlock`：Change Set 和统一 Diff，默认展开；
- `ApprovalBlock`：审批原因、风险与操作，默认展开并获得焦点；
- `VerificationBlock`：成功默认折叠，失败自动展开；
- `ErrorBlock`：失败原因和安全建议，自动展开；
- `StatusBlock`：恢复、迁移或系统提示，根据风险决定展开状态。

折叠规则由 `DisclosurePolicy` 纯函数决定，不散落在 Widget 中。手动折叠或展开后，用户选择保持有效；只有一个 block 首次从非失败转为失败时强制展开一次，用户之后仍可再次折叠。

## 布局与滚动

```text
┌ Vera · model · git branch · context ─────────────────────────┐
│ ConversationTimeline（可滚动）                                │
│  用户消息                                                     │
│  助手 Markdown                                                │
│  ▸ read_file · completed                                      │
│  ▼ Diff · 2 files                                             │
│  ▼ Approval required · low risk                               │
│                                                               │
├───────────────────────────────────────────────────────────────┤
│ Composer（固定、多行）                                        │
├───────────────────────────────────────────────────────────────┤
│ ◐ 正在验证 · Esc/Ctrl-C 取消 · 3 条新消息 ↓                    │
└───────────────────────────────────────────────────────────────┘
```

- 默认跟随时间线底部。
- 用户滚轮、PageUp 或方向键离开底部后暂停自动跟随，并显示“新更新”计数。
- `End` 或激活新更新提示返回底部并恢复跟随。
- Resize 保留当前选中 block 与滚动锚点。
- 工具输出作为一个可延迟渲染的 block 保存，不能为每一行创建 Widget。
- 流式 Markdown 最多每 50 ms 刷新一次；多个 delta 合并，避免超过每秒 20 次完整 Markdown 更新。

## 输入、快捷键与审批

- `Enter`：提交单行输入；多行模式下由 `Ctrl+Enter` 提交。
- `Ctrl+J`：插入换行，作为不能区分 Shift+Enter 的终端兼容路径。
- `PageUp/PageDown`、鼠标滚轮：滚动时间线；`End`：回到底部。
- `Tab/Shift+Tab`：在审批操作或可聚焦 block 之间移动。
- `Enter`：切换当前折叠 block；在审批按钮上确认当前选择。
- `Ctrl+C`：有运行中任务时发送一次 `CancelRun`；空闲且输入非空时清空输入；空闲且输入为空时只提示使用 `/exit` 或 `Ctrl+D`。
- `Ctrl+D`：仅在空闲且输入为空时退出。
- `/exit`、`/quit`：仅在没有未决审批时退出；存在未决审批时先产生 cancel 决定。

审批卡默认选中 `Cancel`，不能把单个字母设为 Approve 快捷键。Change Set、验证命令和恢复计划的批准都必须发送现有结构化审批 Command；TUI 不能直接调用写入或验证函数。

Slash Command 使用现有 Session 解析和语义。TUI 增加命令名称补全和参数提示，但不能维护第二份命令实现。

## 状态、动画与通知

状态词从权威 Event 映射：正在思考、正在读取、正在规划修改、等待审批、正在写入、正在验证、正在恢复、已完成、已取消、失败。Spinner 只表示活动，不能显示无法证明的百分比。

- 动画默认开启，刷新率不超过 10 FPS。
- `ui.animations=false` 或 `VERA_NO_ANIMATIONS=1` 时使用静态符号。
- 所有状态同时包含文字或符号，不能只靠颜色表达。
- 第一版不发送系统桌面通知，不播放声音。

## Plain 与 JSON 契约

`--plain` 保持当前终端滚动历史、审批文字和 Slash Command 行为。它消费持久 Event，模型流式帧可合并后一次输出，不做光标回写。

`--json` 使用 NDJSON：stdin 每行一个 `SessionAction`，stdout 每行一个带 `record_type` 的 `SessionRecord`。允许输入 `prompt.submit`、`session.command`、`approval.resolve`、`run.cancel` 和 `session.close`。输出 `record_type=event|stream`；stderr 只用于进程级启动错误。解析失败返回结构化 `session.input_failed` 后继续读取下一行。任何 JSON 行都不得包含 ANSI 或未脱敏异常文本。

现有 `vera run ... --json` 保持只输出原始持久 `EventEnvelope` 的兼容行为，不加入 `record_type` 包装或 Stream Frame。

## 安全与失败行为

- 模型、工具和文件内容中的 ANSI/OSC 控制序列在渲染前转义或移除。
- Rich markup 默认按不可信文本处理；只有 Vera 自身生成的样式可作为 markup。
- TUI Worker 崩溃产生可读错误卡，并让 Core 按阶段二规则留下持久失败或恢复证据。
- TUI 自身崩溃不得伪造 `run.failed`；进程重启后由 RecoveryClassifier 根据事实判断。
- 退出、异常和 `SIGTERM` 必须恢复 alternate screen、光标与终端模式。
- 未决审批期间终端关闭等同于没有批准，绝不能默认 approve。
- TUI 不显示 Key、完整 Base URL、环境变量、Snapshot 原文或未经脱敏的 Provider 异常。

## 兼容性

- 支持 macOS Terminal.app、iTerm2、Warp、常见 Linux 终端和 Windows Terminal；第一阶段验收以 macOS Terminal.app 为必过环境。
- 主题使用 16/256 色安全调色，不依赖 true color。
- 最小可用尺寸为 60×16；更小时显示可恢复的小尺寸提示，不丢失输入和运行状态。
- 宽度小于 80 时隐藏次要 Header 字段，Diff 允许水平滚动或安全换行。
- Textual 不可导入、终端能力不足或启动失败时，不自动降级并混合输出；退出码 2 并提示显式使用 `--plain`。

## 验收标准

1. TTY 中执行 `vera` 默认进入全屏 Textual TUI，正常退出和异常退出后终端状态恢复。
2. 助手文本通过瞬时 `assistant.delta` 连续显示，最终持久 `assistant.message` 与拼接结果一致。
3. Stream Frame 不进入 Journal、Snapshot 或会话上下文；失败的部分文本不成为正式 assistant 消息。
4. 时间线可滚动，用户离开底部后不被新输出抢回，并能看到新更新计数。
5. 工具和日志默认折叠；Diff、审批默认展开；失败首次发生时自动展开。
6. Change Set、命令和恢复审批通过 Core Command 完成，默认焦点不是 Approve。
7. 长任务显示基于 Event 的状态词和轻量动画，禁用动画后行为完整可用。
8. Composer 支持多行、Slash Command 补全、取消、EOF 和终端 Resize。
9. `vera --plain` 保持阶段二的人类交互与原生 scrollback，不产生动态控制序列。
10. `vera --json` 完成 NDJSON Session round-trip；现有 `vera run ... --json` 输出保持兼容。
11. 60×16、80×24、120×40 三种尺寸及 256 色、无色、禁用动画模式通过确定性测试。
12. 500 个 block、10,000 行折叠工具输出和持续 delta 输入不会为每行创建 Widget，界面保持可操作。
13. 所有控制字符、秘密和原始异常脱敏测试通过；TUI 不新增项目执行权限。
14. 完整非 live 测试、Textual Pilot/SVG、PTY 生命周期测试、Ruff、格式、Mypy、构建和 `git diff --check` 通过，覆盖率不低于 90%。
15. 自动验收不读取真实 DeepSeek/GLM Key、不运行 `tests/live`、不修改 `VeraTestDemo`。

## 参考与关联

- [阶段二总规格](2026-09-11-phase-2-recovery-compatibility-policy.md)
- [普通对话与会话状态规格](2026-09-11-conversational-cli-and-session-status.md)
- [ADR-0002：Command → Runtime → Event](../decisions/ADR-0002-command-event-contract.md)
- [ADR-0004：进程内会话上下文](../decisions/ADR-0004-ephemeral-conversation-context.md)
- [ADR-0009：Textual Terminal UI 与三种呈现模式](../decisions/ADR-0009-textual-terminal-ui.md)
- [ADR-0010：持久 Event 与瞬时 Stream Frame](../decisions/ADR-0010-transient-stream-frames.md)
- [阶段三执行顺序](../tasks/phase-3-execution-order.md)
- [任务 0010：流式 RuntimeOutput](../tasks/0010-streaming-runtime-output.md)
- [任务 0011：Textual TUI 外壳与模式路由](../tasks/0011-textual-tui-shell.md)
- [任务 0012：TUI 时间线与披露策略](../tasks/0012-tui-timeline-and-disclosure.md)
- [任务 0013：TUI Composer、审批与任务控制](../tasks/0013-tui-composer-and-approvals.md)
- [任务 0014：Terminal 模式兼容与阶段三验收](../tasks/0014-terminal-modes-and-acceptance.md)
