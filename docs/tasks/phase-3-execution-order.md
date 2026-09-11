# Vera 阶段三执行顺序

**状态：** Complete
**规格：** [阶段三：富交互 Terminal UI](../specs/2026-09-11-rich-terminal-ui.md)

## 目标

阶段三为稳定 Vera Core 增加可滚动、可折叠、可流式的终端客户端，同时保留 Plain 与 JSON 自动化入口。它不增加 Core 执行权限，也不引入桌面框架。

## 协作前提

- Cursor 先完成阶段二任务 0005–0009 并合并到 `main`。
- 将本规划分支 rebase 到阶段二最终 `main`，重新检查 Runtime、恢复 Command、Codec 与 PolicyEngine 的真实接口；有冲突先同步规格，不能让实现猜测。
- 每次只由一个主实现 Agent 执行一份编号任务。
- 不运行 `tests/live`，不读取用户真实 DeepSeek/GLM Key，不修改 `VeraTestDemo`。

## 相对阶段二最终接口的复核结论（2026-09-11）

以下与当前 `main` 对齐；实施时不得回退到规划期草稿假设：

| 组件 | 真实接口 / 约束 |
| --- | --- |
| `VeraRuntime.handle(command)` | 继续只产出持久 `EventEnvelope`；恢复/审批/写入/验证路径保持阶段二语义 |
| `VeraRuntime` 构造 | 注入 `policy_engine`、`retry_policy`、`sleep`；模型调用经 `_complete_with_retry` |
| `ModelAdapter` | `Protocol`：`capabilities` + `complete()`；假适配器在 `vera.models.base.FakeModelAdapter` |
| `ModelCapabilities` | 现有字段：`tool_calling`、`parallel_tool_calls`、`context_tokens`、`usage`、`request_id`；阶段三在 0010 **新增** `streaming: bool = False`，默认关闭 |
| 错误类型 | 使用 `ModelProviderError` / `ModelErrorCode`，不再使用已移除的 `ModelAdapterError` |
| `PolicyEngine` | `decide(PolicyAction) -> PolicyDecision`，含 `policy_hash`；审批绑定 `workspace_identity`/`policy_hash` |
| `ContractCodec` | 只编解码公共 Command/Event；`StreamFrame` 不进 Codec、不进 Journal |
| Recovery | `InspectRecovery` / `ResumeRun` / `AbandonRun` 与只读分类/续跑语义保持；流式不得伪造恢复事实 |
| CLI JSON | `vera run <goal> --json` 继续只输出 EventEnvelope 行 |

规划文档已按上表同步；若实施发现新冲突，先改规格/ADR/任务，再改代码。

## 顺序

1. [任务 0010：流式 RuntimeOutput 契约](0010-streaming-runtime-output.md)
2. [任务 0011：Textual TUI 外壳与模式路由](0011-textual-tui-shell.md)
3. [任务 0012：对话时间线与披露策略](0012-tui-timeline-and-disclosure.md)
4. [任务 0013：Composer、审批与任务控制](0013-tui-composer-and-approvals.md)
5. [任务 0014：Plain/JSON 兼容与阶段三验收](0014-terminal-modes-and-acceptance.md)

前一任务必须完成失败测试、最小实现、局部验证、完整离线门禁、文档同步、提交与本地合并，下一任务才可开始。

## 规格覆盖

| 能力 | 主任务 |
| --- | --- |
| 流式模型输出、瞬时帧和兼容 Adapter | 0010 |
| 默认 TUI、Textual 生命周期、SessionController | 0011 |
| 滚动、折叠、Diff、失败展开、渲染节流 | 0012 |
| 多行输入、Slash Command、审批焦点、取消 | 0013 |
| `--plain`、`--json`、终端兼容、性能与总验收 | 0014 |

## 完成定义

只有任务 0010–0014 全部合并，并对总规格 15 条验收标准逐条留下测试或人工证据，才能把阶段三标记为 Complete。
