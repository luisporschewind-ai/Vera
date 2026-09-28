# Core Trace 与运行可观测性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于 Run Journal 建立轻量、私有、可重放的 Trace 投影，让开发者能查看每次模型 attempt、Context 组成、工具和验证耗时、Token 用量及失败原因。

**Architecture:** `run_id` 同时作为 `trace_id`；Recorder 将有界 Trace 事实追加到既有 `events.jsonl`，不创建第二个事实库。纯 Core 投影把新旧 Run Events 转成 `RunTrace`，Session CLI 展示该结构，未来客户端复用相同契约。

**Tech Stack:** Python 3.12、Pydantic 2、现有 `EventEnvelope`/`EventJournal`/`RunStore`、Typer、Textual、pytest、Ruff、Mypy；不新增第三方依赖。

**Spec:** [Core Trace 与运行可观测性](../../specs/2026-09-26-core-trace-observability.md)

## Global Constraints

- `trace_id` 在 v1 中等于对应 `run_id`，不再生成第二个顶层 ID。
- 复用 `EventEnvelope` 与 `events.jsonl`；旧 Journal 无需迁移，Trace payload 使用 additive Event 和可选字段。
- 不保存完整 Prompt/消息、文件正文、Tool arguments/output、Verification stdout/stderr、原始 Provider 响应、Key/Secret、完整 Endpoint 或异常堆栈。
- Provider Token 仅采信 `ModelUsage`；未知值不解释为零；v1 不计算 `estimated_cost`，也不增加 Tokenizer 或声称精确 Context Token 分段。
- Context Snapshot 最多保留 256 个条目、规范 JSON 序列化最多 65,536 字节；超限时执行规格定义的确定性省略并记录 omitted counts/bytes。
- Span 耗时使用 monotonic clock；没有结束事实的跨度保留 unknown/interrupted，不伪造结束时间或耗时。
- Trace 不参与 Agent 决策、Policy、Approval、Workspace 写入、Verification 判定或 Recovery 状态转移；不新增 SQLite、远程导出或 APM 依赖。
- 用户于 2026-09-26 明确批准阶段十与阶段八/九并行实施，并自行验证阶段八、九；以 ADR-0023 和任务 0086 为准。不得因此改写阶段八/九状态或验收证据；阶段十一桌面仍须等待阶段八、九、十全部 Complete。
- 任务步骤包含验证命令，但本计划获批本身不代表执行、提交、合并或推送授权；这些操作遵循届时有效的用户授权与仓库规则。

## Review Focus

1. Provider 缺 usage、错误重试、流中断或旧 Event 时，不把未知 token 记为 0；由 Task 3 与 Task 5 的 usage projection 测试覆盖。
2. Trace 写入/读取时意外保存 Prompt、Key、Endpoint、文件或工具内容；由 Task 2、Task 4、Task 5 的禁存断言覆盖。
3. Span 在 Provider/Tool/Verification 异常及进程恢复后未配对；由 Task 2、Task 3、Task 4、Task 5 的生命周期与旧 Journal 测试覆盖。
4. Context 归因偏离实际 `ModelRequest`、重复内容口径因来源或压缩而漂移；由 Task 1 与 Task 3 的消息/Schema 分类、重复和压缩测试覆盖。
5. `/trace` 的 Run 选择跨 Workspace、损坏 Journal 或旧数据时泄漏路径或丢失可读事实；由 Task 5、Task 6 的查询与展示测试覆盖。

---

## 文件与接口图

| 单元 | 职责 |
| --- | --- |
| `src/vera/contracts/trace.py` | 跨客户端稳定的 `TraceSpan`、`ContextSnapshot`、`RunTrace` 等序列化契约 |
| `src/vera/trace/context_inventory.py` | 纯计算：从实际 `ModelRequest` 和 Run 内存来源构造受限 Context Snapshot |
| `src/vera/trace/recorder.py` | Span 生命周期与 Trace Event 追加；只依赖 Run Journal 和时钟 |
| `src/vera/trace/projector.py` | 纯只读：从新旧 `EventEnvelope` 派生 Span、Run 汇总和完整性诊断 |
| `src/vera/models/base.py`, `src/vera/models/openai_compatible.py`, `src/vera/bootstrap.py` | 暴露不含密钥/Endpoint 的安全模型身份 |
| `src/vera/runtime/engine.py` | 在模型 attempt、Tool Call、Verification 命令边界接入 Recorder |
| `src/vera/session/queries.py`, `src/vera/session/controller.py`, `src/vera/session/command_catalog.py` | 选择 Run、关联当前 Workspace 的 Session、提供 `/trace [run-id]` 查询 |
| `src/vera/cli_session.py`, `src/vera/cli_plain_session.py`, `src/vera/cli_json_session.py`, `src/vera/presentation/projector.py`, `src/vera/presentation/event_copy.py` | 以同一 `RunTrace` 结构显示可读文本并保留 JSON 事实 |

### Task 1：冻结 Trace 合同与 Context Inventory

**Files:**

- Create: `src/vera/contracts/trace.py`
- Create: `src/vera/trace/__init__.py`
- Create: `src/vera/trace/context_inventory.py`
- Test: `tests/contracts/test_trace_contracts.py`
- Test: `tests/trace/__init__.py`
- Test: `tests/trace/test_context_inventory.py`

**Interfaces:**

- `TraceSpanKind = Literal["llm", "tool", "verification", "context"]`。
- `TraceSpanStatus = Literal["ok", "error", "rejected", "cancelled", "interrupted", "unknown"]`。
- `ContextKind = Literal["system", "project_guidance", "skill", "conversation", "user_input", "assistant_tool_call", "tool_result", "compaction_summary", "tool_schema", "other"]`。
- `ContextPart`：`kind`、`source_ref`、`content_hash`、`byte_count`、`occurrence_count`、`message_count`、`schema_count`、`truncated`。
- `ContextKindTotal`：`kind`、`byte_count`、`entry_count`。
- `ContextSnapshot`：`snapshot_id`、`request_index`、`total_bytes`、`context_budget_bytes`、`message_count`、`tool_schema_count`、`parts`、`by_kind`、`truncated`、`omitted_entry_count`、`omitted_bytes`。
- `TraceSpan`：`span_id`、`trace_id`、`parent_span_id`、`kind`、`name`、`started_at`、`finished_at`、`duration_ms`、`status`、有限 JSON attributes、关联 Event ID。
- `RunTrace`：`run_id`、`trace_id`、`session_id`、Run 状态与时间、`duration_ms`、Span 列表、Token 汇总、重试/工具/验证计数、完整性与诊断码。
- `ContextInventory.build(request: ModelRequest, context: RunContext, *, request_index: int, context_budget_bytes: int) -> ContextSnapshot`。它只读已构造的 Request 与 Run 内存，不读 Workspace、不改消息；未知来源归类为 `other`。

- [x] **Step 1: 写 Trace 合同失败测试。** 在 `tests/contracts/test_trace_contracts.py` 覆盖允许的 Span/Run 状态、UTC 时间、非负字节/耗时、Trace ID 字段、JSON 编码与 `extra="forbid"`；非法枚举、负值和 naive datetime 必须被拒绝。
- [x] **Step 2: 运行新合同测试确认失败。** 运行：`uv run --offline pytest tests/contracts/test_trace_contracts.py -q`。Expected：缺少 Trace 合同而失败。
- [x] **Step 3: 实现 `contracts/trace.py`。** 按上面的字段和固定 Literal 建立不可变 Pydantic 合同，optional 值使用 `None`，不把未知值转成零。
- [x] **Step 4: 写 Context Inventory 失败测试。** 测试 system、project guidance、Skill、conversation、user input、assistant/tool call、tool result、Tool Schema 与 other 分类；总字节与消息/Schema 数必须对应输入对象；相同 `(kind, source_ref, content_hash)` 在后续请求中增加重复字节数，来源不同则不合并。增加超过 256 条与 65,536 字节的确定性省略测试。
- [x] **Step 5: 运行 Inventory 测试确认失败。** 运行：`uv run --offline pytest tests/trace/test_context_inventory.py -q`。Expected：缺少 `ContextInventory` 而失败。
- [x] **Step 6: 实现 `ContextInventory.build(...)`。** 以实际 `ModelRequest.messages`/`tools` 的规范序列化数据计算 UTF-8 字节和 SHA-256；仅对可由 RunContext 既有命令、项目说明和 Skill 快照确定匹配的消息细化来源；按首次出现顺序保留最多 256 条和 65,536 字节明细，汇总保留全量 kind totals。
- [x] **Step 7: 运行 Task 1 测试。** 运行：`uv run --offline pytest tests/contracts/test_trace_contracts.py tests/trace/test_context_inventory.py -q`。Expected：全部 PASS，且同输入重复运行生成相同快照字段（除 snapshot_id 外）。

### Task 2：实现 TraceRecorder 与 Span Event 生命周期

**Files:**

- Create: `src/vera/trace/recorder.py`
- Test: `tests/trace/test_recorder.py`
- Reference only: `src/vera/persistence/journal.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class SpanHandle:
    span_id: str
    trace_id: str
    parent_span_id: str | None
    kind: TraceSpanKind
    name: str
    started_at: datetime
    monotonic_started: float

class TraceRecorder:
    def __init__(self, journal: EventJournal, *,
                 monotonic: Callable[[], float] = time.monotonic,
                 clock: Callable[[], datetime] = utc_now) -> None: ...
    def start_span(self, kind: TraceSpanKind, name: str, *,
                   parent_span_id: str | None = None,
                   attributes: dict[str, JsonValue] | None = None) -> SpanHandle: ...
    def finish_span(self, handle: SpanHandle, status: TraceSpanStatus, *,
                    attributes: dict[str, JsonValue] | None = None) -> EventEnvelope: ...
    def record_context(self, handle: SpanHandle, snapshot: ContextSnapshot) -> EventEnvelope: ...
```

- [x] **Step 1: 写 Recorder 生命周期失败测试。** 使用注入的固定 UTC clock 与 monotonic 序列，断言 `trace.span.started`/`trace.span.finished` 与 `trace.context.snapshot` payload、parent span、毫秒耗时及 Journal 顺序；重复 finish、负 monotonic delta 与无效 attrs 不可输出成功 Span。
- [x] **Step 2: 运行 Recorder 测试确认失败。** 运行：`uv run --offline pytest tests/trace/test_recorder.py -q`。Expected：缺少 Recorder 接口而失败。
- [x] **Step 3: 实现 `TraceRecorder`。** `trace_id` 固定取 `journal.run_id`；ID 使用 UUID；duration 使用 monotonic delta；时间戳使用 UTC clock；事件通过 `EventJournal.append()` 写入并沿用其 Redactor/权限；只接受有限、JSON-safe 的低基数属性。
- [x] **Step 4: 增加 Journal 回环和隐私断言。** 将 Recorder Events 重新加载后验证 payload 可读；断言传入的敏感字段经 Redactor 处理，Recorder 不接受正文/大对象字段作为专用参数。
- [x] **Step 5: 运行 Recorder 与合同测试。** 运行：`uv run --offline pytest tests/contracts/test_trace_contracts.py tests/trace/test_recorder.py -q`。Expected：全部 PASS；Trace Event 不触发 Recovery Snapshot 写入。

### Task 3：接入 LLM attempt 与 Context Snapshot

**Files:**

- Modify: `src/vera/models/base.py`
- Modify: `src/vera/models/openai_compatible.py`
- Modify: `src/vera/bootstrap.py`
- Modify: `src/vera/runtime/context.py`
- Modify: `src/vera/runtime/engine.py`
- Test: `tests/models/test_adapter_conformance.py`
- Test: `tests/runtime/test_model_resilience.py`
- Test: `tests/runtime/test_context_compaction.py`
- Test: `tests/runtime/test_streaming_output.py`
- Test: `tests/trace/test_context_inventory.py`

**Interfaces:**

- `ModelIdentity`：`provider_type: str | None`、`profile_name: str | None`、`model_name: str | None`；不含 base URL、Key 值或 Key 环境变量名。
- `ModelAdapter.identity -> ModelIdentity | None`；`OpenAICompatibleAdapter` 接受可选 `profile_name`，bootstrap 传入已选 Profile；Fake Adapter 默认身份为 `None`。
- `RunContext.trace_recorder: TraceRecorder` 与每次模型 attempt 喂给 Inventory 的单调 `request_index`；hydrated Run 重新创建 Recorder 绑定原 `EventJournal`，不恢复未闭合 Span。
- 每个实际 attempt 的 `model.requested`、`model.completed`、`model.failed` 可选增加 `span_id`；`model.completed` 保留原 usage、duration、request ID 语义。

- [x] **Step 1: 写模型身份与 LLM Span 失败测试。** Fake Adapter 的 identity 未提供时显示 unknown；OpenAI-compatible Adapter 只暴露 provider type/Profile/model；成功、Provider retry 后成功、最终失败、Capability mismatch 和流缺终块分别验证 Span 数、attempt 关联、usage 保真与状态。
- [x] **Step 2: 运行聚焦测试确认失败。** 运行：`uv run --offline pytest tests/models/test_adapter_conformance.py tests/runtime/test_model_resilience.py tests/runtime/test_streaming_output.py -q`。Expected：缺少 identity/Trace fields 的新增断言失败。
- [x] **Step 3: 添加安全 `ModelIdentity`。** 在 `models/base.py` 定义契约并由 Adapter 暴露；`bootstrap.py` 只传 Profile 名称，不传 Provider endpoint 或 credentials；兼容现有直接构造 Adapter 的调用。
- [x] **Step 4: 为每次 Provider attempt 接入 Span。** 在 `_complete_with_retry` 的每次真实 `adapter.stream(request)` 前启动 `llm` Span；所有成功、不可重试错误、可重试错误、一般异常路径均结束 Span；重试使用独立 `span_id` 并通过 `retry_of_span_id` 指向前一次 attempt。
- [x] **Step 5: 写并接入 Context Snapshot。** Adapter 调用前执行 `ContextInventory.build(request, context, request_index=..., context_budget_bytes=self.limits.max_context_bytes)`，写入 `trace.context.snapshot`，以 snapshot ID 关联当前 LLM Span；每次重试仍计为一次请求 Snapshot。
- [x] **Step 6: 运行 LLM、Context 与兼容回归。** 运行：`uv run --offline pytest tests/models/test_adapter_conformance.py tests/runtime/test_model_resilience.py tests/runtime/test_context_compaction.py tests/runtime/test_streaming_output.py tests/trace/test_context_inventory.py -q`。Expected：全部 PASS；原有 Run Event 顺序、StreamFrame 和 `/usage` payload 保持兼容。

### Task 4：接入 Tool 与 Verification Span

**Files:**

- Modify: `src/vera/runtime/engine.py`
- Modify: `src/vera/contracts/verification.py`（仅当类型需要暴露现有结果字段时；不改结果语义）
- Test: `tests/runtime/test_policy_approval.py`
- Test: `tests/runtime/test_safe_editing_flow.py`
- Test: `tests/runtime/test_recovery_resume.py`
- Test: `tests/recovery/test_hydrator.py`
- Test: `tests/verification/test_runner.py`
- Test: `tests/trace/test_runtime_spans.py`

**Interfaces:**

- `tool.started`、`tool.completed` 可选增加 `span_id`；Trace Tool attributes 使用 `tool_name`、`tool_call_id`、输入/输出 UTF-8 字节数、内容 hash、截断状态、状态与稳定 `error_code`。
- `verification.started`、`verification.completed` 可选增加 `span_id`；完成属性采信 `VerificationResult.duration_seconds`、status、exit code、stdout/stderr byte count、truncation、cleanup、workspace mutation 与 reason code，不写输出正文。

- [x] **Step 1: 写 Tool Span 失败测试。** 覆盖 read tool 成功/错误、参数解析拒绝、策略拒绝、`propose_changeset`、重复调用终止和 Tool 抛错；验证输入 bytes 对规范 JSON 计数，输出 bytes/hash 对 Runtime 实际加入 ModelMessage 的文本计数，Span 状态正确且 Trace Event 无 arguments/content。
- [x] **Step 2: 写 Verification Span 失败测试。** 覆盖通过、失败、超时、取消、Policy 拒绝/等待审批和工作区污染；只有实际运行命令产生执行 Span，耗时使用结果字段，不把 stdout/stderr 正文写进 Trace。
- [x] **Step 3: 运行 Tool/Verification 测试确认失败。** 运行：`uv run --offline pytest tests/runtime/test_policy_approval.py tests/runtime/test_safe_editing_flow.py tests/runtime/test_recovery_resume.py tests/verification/test_runner.py tests/trace/test_runtime_spans.py tests/recovery/test_hydrator.py -q`。Expected：Span/Event 新断言失败。
- [x] **Step 4: 接入 Tool Span。** 在 `_execute_tool` 的可处理调用边界启用 `tool` Span；每个 early return、Generator 异常和正常完成都写唯一 finish event；`propose_changeset` 与普通 Tool 共用生命周期。
- [x] **Step 5: 接入 Verification Span。** 在 Policy/Approval 放行且即将执行 Runner 时开始 Span；执行结束后基于 `VerificationResult` 收尾，并把同一 span_id 加入现有业务 Event，不改稳定事件与 snapshot 转移规则。
- [x] **Step 6: 运行安全与恢复回归。** 运行：`uv run --offline pytest tests/runtime/test_policy_approval.py tests/runtime/test_safe_editing_flow.py tests/runtime/test_recovery_resume.py tests/runtime/test_approval.py tests/verification/test_runner.py tests/trace/test_runtime_spans.py tests/recovery/test_hydrator.py -q`。Expected：全部 PASS，Policy、Approval、Recovery、终态和 Workspace 结果不变。

### Task 5：实现确定性 RunTrace 投影与 Session 关联

**Files:**

- Create: `src/vera/trace/projector.py`
- Modify: `src/vera/session/queries.py`
- Modify: `src/vera/persistence/session_store.py`（仅在必须暴露现有只读记录查询时）
- Test: `tests/trace/test_projector.py`
- Test: `tests/session/test_queries.py`
- Test: `tests/persistence/test_session_store.py`

**Interfaces:**

```python
class TraceProjector:
    def project(self, run_id: str, events: tuple[EventEnvelope, ...], *,
                session_id: str | None = None) -> RunTrace: ...

def trace_snapshot(store: RunStore, run_id: str, *,
                   session_id: str | None = None) -> RunTrace: ...
```

- `TraceProjector.project()` 是纯函数式读投影；Run 总耗时取 `run.started` 至首个有效终态；不完整或倒序时间报完整性诊断。
- 已报告 Token 按现有 `usage_snapshot` 规则保持完整/未知语义；另提供 `known_token_subtotal` 与 `usage_unknown_calls`，仅完整时显示总量，partial subtotal 标成至少/部分。
- 新 Trace Event 优先构造精确 Span；旧 Event 仅构造能从 started/completed 配对的 Span，边界不明时 status/duration 为 unknown。
- Session 关联扫描当前 Workspace 的 `ConversationSessionStore.list_for_workspace()` 与对应 Session Records，只依据 `turn.committed.turn.run_id` 关联；损坏 Session Journal 不阻止 RunTrace 投影。

- [x] **Step 1: 写新格式与旧格式投影失败测试。** 覆盖正常树、未结束 Run/Span、重试、部分 usage、零 usage、Tool/Verification 汇总、旧 Journal 的业务事件配对、未知 Trace Event、重复/乱序 span_id、倒序时间和损坏事件局部降级。
- [x] **Step 2: 写 Session 关联失败测试。** 多 Session 同 Workspace、旧轮次、缺 run_id、已损坏 Session、其他 Workspace Session 均验证：只关联精确的 committed run_id，不读取其他 Workspace。
- [x] **Step 3: 运行投影测试确认失败。** 运行：`uv run --offline pytest tests/trace/test_projector.py tests/session/test_queries.py tests/persistence/test_session_store.py -q`。Expected：新 projector/API 缺失而失败。
- [x] **Step 4: 实现 `TraceProjector.project()`。** 先索引 Event ID/Span ID，再按 Journal 顺序验证配对；只聚合严格有效数值；保留部分结果与 diagnostics，不重写原始 Event。
- [x] **Step 5: 实现 `trace_snapshot()` 和 Session 查询。** 从 `RunStore.read_events(run_id)` 取事件；可选 Session id 由当前 Session 参数传入，历史关联只扫描同 Workspace 的 Session Store 只读记录。
- [x] **Step 6: 运行 RunTrace 投影回归。** 重跑 Step 3 命令；Expected：全部 PASS，old Journal 无需迁移，单个损坏 Trace 属性不丢弃其余 RunTrace。

### Task 6：增加 `/trace` 只读 CLI 展示

**Files:**

- Modify: `src/vera/session/command_catalog.py`
- Modify: `src/vera/session/controller.py`
- Modify: `src/vera/cli_session.py`
- Modify: `src/vera/cli_plain_session.py`
- Modify: `src/vera/cli_json_session.py`
- Modify: `src/vera/presentation/projector.py`
- Modify: `src/vera/presentation/event_copy.py`
- Test: `tests/session/test_command_catalog.py`
- Test: `tests/session/test_controller.py`
- Test: `tests/cli/test_plain_session.py`
- Test: `tests/cli/test_json_session.py`
- Test: `tests/presentation/test_projector.py`

**Interfaces:**

- 新命令 descriptor：`CommandDescriptor("/trace", "/trace [run-id]", "查看 Run 执行轨迹", "代码与证据", "trace", args="optional")`。
- `SessionController._cmd_trace(args: tuple[str, ...]) -> Iterator[RuntimeOutput]` 调用 `trace_snapshot()` 并输出 `session.trace`，payload 同时含结构化 `trace` 与 Plain/TUI 用的 `text`。
- Run 选择：显式 ID 优先；否则当前 Active Run；再否则当前 Workspace 最新 Run；验证显式 Run 归属当前 Workspace，未找到/跨 Workspace 返回稳定错误。

- [x] **Step 1: 写命令、Plain、JSON 和 Timeline 失败测试。** RED 覆盖 `/trace` 注册、显式 ID 优先、Active Run 优先于 latest、无参 latest、跨 Workspace 拒绝；Plain/TUI 展示安全摘要文本，JSON 保留结构化 `RunTrace`，不需解析 Plain 文本。
- [x] **Step 2: 运行 CLI Trace 测试确认失败。** RED：未注册命令、缺少 `session.trace` handler、跨 Workspace 目标被错误地当成未知命令；新增断言按预期失败。
- [x] **Step 3: 注册 `/trace` 并实现 Controller handler。** 默认选择当前 Active Run 或当前 Workspace 最新 Run，并检查显式 ID 的 Workspace 归属；不存在或跨 Workspace 返回稳定错误，不泄露外部路径。
- [x] **Step 4: 实现 Plain/JSON/TUI 投影。** Controller 输出同一 `RunTrace.model_dump(mode="json")` 和 body-free `text`；Plain/TUI 使用文本，JSON 保留完整结构；超长标识和名称裁切并清理终端控制符。
- [x] **Step 5: 运行 `/trace` 跨客户端测试。** `uv run --offline pytest -q tests/trace tests/session/test_command_catalog.py tests/session/test_controller.py tests/cli/test_plain_session.py tests/cli/test_json_session.py tests/presentation/test_projector.py` → 92 passed；Ruff/Mypy 检查通过，既有 `/usage` 测试兼容。活跃 Run 下其余 slash 命令保持原拒绝行为。

### Task 7：整体验收与任务记录

**Files:**

- Modify: `docs/tasks/README.md`（新增获批 Task ID/阶段归属后才添加实现记录）
- Modify: `docs/STATUS.md`
- Modify: `docs/specs/2026-09-26-core-trace-observability.md`（仅补充实现证据，不改变接受的契约）
- Test: 所有受影响 contracts/models/runtime/trace/persistence/session/cli/presentation 测试

- [x] **Step 1: 在实现授权与阶段任务记录具备后运行聚焦验收。** 实际仓库没有原计划写的 `tests/runtime/test_tool_executor.py`，已改为 `tests/tools/test_registry.py`、`test_builtin.py` 与 `test_command_policy.py`。重跑后 → 177 passed。
- [x] **Step 2: 运行静态检查。** `uv run --offline ruff check src/vera tests`、`uv run --offline ruff format --check src/vera tests`、`uv run --offline mypy src` 和 `git diff --check` 均通过。
- [ ] **Step 3: 完成人工 Trace 可读性验收。** 用真实但非敏感的本地 Run 查看成功、Tool、Retry、Verification 与失败/缺失 usage；确认普通开发者能回答“执行了什么、哪里耗时、用了多少 Provider 报告 Token、哪里不确定”，且 Trace 不展示正文或私密配置。
- [ ] **Step 4: 更新阶段/任务状态。** 仅在被授权的正式阶段记录中写入确切测试命令、结果、手工验收与未解决项；不因计划或自动测试将阶段八、九或十状态提前改为 Complete/Started。

## Spec Coverage

Task 1 覆盖公共合同、Context 分类/哈希/字节和尺寸上限；Task 2 覆盖 Event append、Span 生命周期与 monotonic duration；Task 3 覆盖 Provider identity、attempt、retry、usage 和 Context Snapshot；Task 4 覆盖 Tool/Verification 成败、拒绝、截断与无正文约束；Task 5 覆盖旧/新 Journal、部分聚合、损坏降级和 Session 关联；Task 6 覆盖 Run 选择、Workspace 隔离及 Plain/TUI/JSON；Task 7 覆盖安全、性能上限、静态与人工验收。

明确不实施：远程导出、OpenTelemetry/APM、SQLite、费用计算、reasoning token 猜测、精确 Context tokenization、Planner/Coder 自动归因、桌面 Trace Viewer。
