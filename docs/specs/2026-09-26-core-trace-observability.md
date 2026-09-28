# Core Trace 与运行可观测性

**状态：** Accepted（用户于 2026-09-26 确认）
**日期：** 2026-09-26
**所属范围：** Core 运行事实与诊断；本规格不改变当前阶段、阶段八/九验收状态或阶段十入口

## 目的

让 Vera 的使用者能够从一次 Run 的本地事实中回答：模型调用了几次、实际报告了多少 Token、请求 Context 如何增长、哪些工具和验证耗时最长、发生了哪些重试与失败，以及重复内容大致来自哪里。能力必须服务普通开发者排查一次任务，不建设远程 APM 或通用监控平台。

本规格以现有 `EventEnvelope`、Run Journal、`ModelUsage`、`RunStore` 和结构化 Runtime Event 为基础，为其补充有界的 Span 关联事实、请求 Context 清单、只读聚合投影和 CLI 查看入口。Trace 不参与模型决策、Policy、Approval、文件变更、Recovery 或验证结果判定。

## 当前实现基线

- `EventEnvelope` 已提供 `event_id`、`run_id`、顺序号、UTC 时间、类型和 JSON payload；`EventJournal` 将 Run 事件写入用户状态目录中的私有 `events.jsonl`，追加时执行 Redactor、flush 与 fsync。
- Runtime 已发出 `run.started`/终态、`model.requested`、`model.completed`、`model.failed`、`model.retrying`、`tool.started`/`tool.completed`、`verification.started`/`verification.completed`、压缩和恢复等事件。
- `model.completed` 已包含 Provider usage（若返回）、finish reason、attempt、请求 ID 和耗时；`ModelUsage` 已提供 input/output/total 与可选 cache hit/miss 输入 Token。`/usage` 已从 Run Journal 对单 Run 汇总这些用量。
- Tool 事件已有 tool name、`call_id`、成功状态、截断标记、错误码及工具结果内容 hash；`ToolResult` 和 Verification 结果已有部分输出截断信息。Verification 结果已有耗时，但当前 Runtime 事件投影没有保留该字段。
- `RunStore` 已支持历史 Run 列举和事件读取。TUI Timeline 展示执行过程，但不是可展开的诊断 Trace Viewer。
- 目前没有 `trace_id`、通用 Span 模型、`task_id`、一等 `message_id`、费用汇率/费率表或标准 Python Logging 管线。现有 `tool_call_id` 对应 `ModelToolCall.call_id`，`session_id` 属于 Session Journal。

以上是规格接受时的仓库基线；实施前必须重新核对代码与阶段记录。

## 目标与非目标

### 目标

1. 每个 Run 可从现有事件派生一份确定性的 `RunTrace`，并以 `run_id` 作为 Trace 标识。
2. 将一次模型请求的实际 Provider attempt、Tool 执行和 Verification 命令表示为可关联的 Span；失败、中断和不完整记录不能伪装成成功完成。
3. 在不保存 Prompt、文件正文或 Tool 全量输入/输出的前提下，记录 Context 组成、大小、内容指纹及逐次增长事实。
4. 复用 Run Journal 保存 Trace 事件，通过只读投影提供单 Run 的耗时、Token、调用、重试、工具、验证和错误摘要。
5. 提供 CLI `/trace [run-id]` 文本查看入口；未来 UI 直接消费 Core 的结构化 `RunTrace`，不得解析 CLI 文本。
6. 对 Provider 缺失、旧 Journal、记录截断、取消、恢复和事件损坏保持兼容与明确的未知状态。

### 非目标

- 不引入 OpenTelemetry SDK/exporter、远程采集服务、后台上传或 APM 平台。
- 不引入 SQLite、独立数据库、跨设备同步、复杂索引、采样或后台聚合服务。
- 不保存完整 Prompt、模型响应、文件内容、工具参数、工具输出、验证 stdout/stderr 或原始 Provider 响应。
- 不推算统一费用、缓存节省金额、推理 Token 或 Provider 未报告的失败调用用量。
- 不按模型自述给调用分配 Planner/Coder/Verification 角色。当前 Core 没有独立 Planner/Coder Agent 阶段。
- 不为桌面 Viewer 引入桌面框架或改变阶段十门禁。
- 不把 Trace Event 当作 Recovery Snapshot 的稳定状态转移，不依赖 Trace 构造安全或恢复决策。

## 领域模型与标识

### Trace 与 Run

- `trace_id` 在 v1 中等于对应 `run_id`，不再生成第二个顶层 ID。
- Trace 根区间由 `run.started` 和对应 Run 终态事件派生，不额外写根 Span。
- Trace 至少提供 `run_id`、可选 `session_id`、开始/结束时间、运行状态、总耗时、已知 Token 汇总和数据完整性状态。运行状态沿用 `active`、`awaiting_approval`、`completed`、`failed`、`cancelled`、`unknown`；无终态时结束时间和总耗时未知。
- `session_id` 可由 Session Journal 中 `turn.committed` 的 `run_id` 关联得到；若 Run 尚未提交为会话轮次或没有 Session Journal，返回 `null`。Core Run 不为满足展示而伪造会话关联。
- v1 不定义 `task_id` 或 `message_id`。同一会话内的一轮以 Run 作为可查询边界。

### Span

每个 Span 由不可变的 `span_id` 标识，并包含 `trace_id`、可选 `parent_span_id`、类别、名称、开始/结束时间、单调时钟持续时间、状态、有限 attributes 与相关业务 Event 引用。`duration_ms` 在同进程内以 monotonic clock 测量；墙钟时间仅用于显示和跨记录排序，不能用来测量耗时。

v1 只支持这些 Span 类别：

- `llm`：每次真实 Provider attempt 一个 Span，重试的每次 attempt 分开记录。
- `tool`：每个收到并处理的模型 Tool Call 一个 Span，含拒绝/参数无效等结束状态；`propose_changeset` 也属于工具调用。
- `verification`：每条验证命令一个 Span。
- `context`：模型调用前生成的 Context Snapshot，不计为外部操作；它作为相应 `llm` Span 的子项或引用，不另行嵌套耗时区间。

v1 不创建单独的 `agent`、`planning`、`editing` 或 `retry` Span。Run 是根区间，重试用独立 LLM attempt Span 和已有 retry Event 表达，Planning/Coding 分析只有在 Runtime 后续引入明确、可验证阶段契约后才能加入。

### Event 与存储表示

复用 `EventEnvelope` 与 `events.jsonl`。新增的 `trace.span.started`、`trace.span.finished` 与 `trace.context.snapshot` 是附加诊断事件；现有 `model.*`、`tool.*`、`verification.*` 等业务事件继续保留，并可增加 `span_id` 作为关联字段。Trace 事件的 payload 不含正文或不受控 Provider 数据。

- `trace.span.started` 至少记录 `span_id`、可选 `parent_span_id`、`kind`、`name`、开始时间及允许的低基数属性。
- `trace.span.finished` 至少记录 `span_id`、结束时间、`duration_ms`、`status`，以及对应类型允许的有限摘要属性。
- `trace.context.snapshot` 记录 `span_id` 或其引用、请求序号、字节数、组成明细与组成条目的内容指纹。
- Span 状态限定为 `ok`、`error`、`rejected`、`cancelled`、`interrupted`、`unknown`。没有结束事件的 Span 在投影时标记 `interrupted` 或 `unknown`，结束时间和耗时保持未知。
- 事件追加沿用当前 Journal 顺序和 Redactor。Span 事件是非稳定进度事实，不触发 Recovery Snapshot；已存在的稳定业务事件语义不变。
- 旧 Journal 无 Trace 事件时，投影从现存业务事件构造尽可能完整的兼容视图；无法配对的事实显示为 incomplete/unknown，不伪造 Span 边界。
- Trace 写入不得静默吞掉 Journal 的持久化故障。若诊断事件写入失败且影响共享 Journal 的追加能力，遵循现有 Runtime 持久化错误处理；不得继续宣称该 Run 的 Trace 完整。

## LLM 用量与 Context 事实

### LLM attempt

每个 `llm` Span 至少暴露：Provider Profile 名称、Provider 类型、模型标识、attempt 序号、开始/结束时间、持续时间、finish reason、request ID（若有）、状态、错误码、`retry_of_span_id`（重试时）以及实际收到的 `ModelUsage` 字段。`model_profile` 与公开模型身份只能来自 Vera 已选择的配置；Endpoint、Key 引用、Key 值和原始 Provider payload 不得进入 Trace。

现有 `input_tokens`、`output_tokens`、`total_tokens` 与 `cache_hit_input_tokens`、`cache_miss_input_tokens` 语义不变，缺失仍为 `null`/`unavailable`。成功响应未提供 usage 时用量未知。失败的 Provider attempt 若错误响应未提供受信任且已归一化的 usage，则该 attempt Token 用量未知；不得以提示词大小冒充 Provider Token。

`reasoning_tokens` 在当前适配器没有归一化 Provider 字段之前保持 unavailable。v1 不包含 `estimated_cost`。费用需另立版本化费率规格，按 Provider、模型、日期、输入/输出及缓存计价语义明确后实施。

### Context Snapshot

在构造每个 `ModelRequest` 后、调用 Adapter 前，由纯 Core 模块对实际请求对象生成 Snapshot。Snapshot 至少包含：

- `request_index`、消息数、工具 Schema 数、总字节数及当前 Context 字节预算占用；
- 每个有界组成条目的 `kind`、`source_ref`、`content_hash`、UTF-8 `byte_count`、截断标记、出现次数及消息/Schema 数；
- `kind` 限定为 `system`、`project_guidance`、`skill`、`conversation`、`user_input`、`assistant_tool_call`、`tool_result`、`compaction_summary`、`tool_schema`、`other`；只有请求中实际存在的组成才输出。

`content_hash` 是稳定内容指纹，不是脱敏或匿名化。不得将其用于跨用户、跨机器或跨 Provider 关联。Trace 本地文件必须继续沿用用户状态目录的私有权限，并由 Redactor 处理敏感字段。任意用户内容、文件、工具结果只记录指纹与大小，不记录原文。

### 大小、估算与重复内容

- UTF-8 字节数和请求中消息/Schema 数是可重复验证的精确本地事实；Provider 报告的 Token 数是精确用量事实。
- 本地 Context 条目不能被描述为精确 Token 分段。v1 不增加 Tokenizer；UI 将总 Provider Token 与 Context byte breakdown 分开展示。
- 对同一 Run 的请求快照，按 `(kind, source_ref, content_hash)` 精确匹配相同内容。`repeated_content_bytes` 定义为后续请求中再次出现的内容字节数之和；首次出现只作为基线，每个条目同时给出重复次数。同一快照中的重复项按请求顺序计为后续出现。角色/来源不同的内容不合并。
- 重复内容报告只能称为“重复发送内容字节数/重复项”，不得命名为精确重复 Token 或“重复成本”。Provider cache hit/miss 是独立的 Provider 报告事实。
- Context 膨胀趋势按请求序号展示总字节数和各组成字节数的变化；压缩前后作为普通连续 Snapshot 比较。不根据少数样本推断 Token 超额或费用。

## Tool 与 Verification 事实

### Tool Span

Tool Span 记录 `tool_name`、`tool_call_id`、开始/结束/持续时间、终态、错误码、`input_bytes`、`output_bytes`、截断状态及适用时的 `input_hash`/`output_hash`。参数的字节数由规范化 JSON 编码计算；结果大小定义为 Runtime 实际交给后续 ModelMessage 的 UTF-8 字节数。哈希只针对实际输入/输出内容，且不可替代权限校验或内容安全检查。

不保存完整 arguments、文件内容、命令输出、Tool Result 或模型工具响应。现有业务事件可能包含用于审批、回放和用户可见行为所需的 payload；Trace 层不得复制这些内容。若已有事件自身需要收紧敏感数据，作为独立安全修复处理，不由此规格默许增加明文保存。

模型 Tool Call 被拒绝、解析失败、因策略拒绝或执行报错时，Span 必须以相应 `rejected`/`error` 状态结束，并保留可诊断的稳定错误码。`call_id` 是关联字段，不是 Vera 生成的授权凭据。

### Verification Span

每个执行的验证命令对应一个 Span；记录验证 profile（若有）、安全的命令摘要或受限 argv 摘要、开始/结束时间、`VerificationResult.duration_seconds`、状态、exit code、stdout/stderr 字节数、截断标记、cleanup 状态、污染检查状态与 reason code。stdout/stderr 正文不得复制到 Trace。

被 Policy 拒绝或需要审批但尚未执行的命令，记录 `rejected` 或不产生执行 Span；Viewer 明确区分计划/拒绝与实际运行。Verification 的结果仍由现有 `verification.completed` 业务事实决定。

## 关联、聚合与查询

新增 `TraceProjector`/`TraceQueryService` 一类只读 Core 投影，从 `RunStore.read_events(run_id)` 与必要的 Session Journal 关联数据构造 `RunTrace`。它不直接写 Journal、不操作 Workspace，也不复制业务决策。聚合规则：

- Run 总时长取 `run.started` 到首个有效终态的墙钟差；缺失、倒序或无法信任时间时标记 unavailable，并指出完整性问题。
- Provider Token 汇总维持现有 `/usage` 的兼容语义：仅当所有成功 `model.completed` 调用均有完整有效 usage 时显示完整总量；同时提供已知用量小计与未知调用数，并明确标为“至少/部分”，不得把小计伪装成 Run 总量。没有成功调用或无任何有效 usage 时，总量为 unavailable。
- Retry 数由 `model.retrying` 计数；LLM Span attempt 分开显示。失败 attempt 的 token 不加入已报告的成功 token 总量。
- Tool/Verification 汇总分别按调用数、成功/失败/拒绝数、耗时和截断/输出大小统计；缺失耗时不记为 0。
- Error 查询只暴露稳定错误码、事件引用和必要的脱敏摘要，不把异常堆栈、Key、Endpoint 或原始响应加入结果。
- 对异常终止、损坏或不完整 Journal，投影返回可读的部分结果和 `completeness`/诊断代码，不因一个损坏 Span 丢弃整个 Run 的可读事实。

历史查询沿用 `RunStore` 的本地 JSONL 扫描。一期 Run 数量与事件量较小时不建索引；如果实测查询耗时或读放大影响交互，另行评估可删除重建的索引。JSONL 仍是唯一事实源。

## CLI 查看体验

增加只读命令 `/trace [run-id]`，默认解析当前 Active Run 或最近一个本 Workspace 的 Run，与现有 `/usage`、`/runs`、`/show` 的 Run 选择规则保持一致。对未找到的 Run 显示稳定错误，不泄漏其他 Workspace 的绝对路径或用户状态路径。

首屏以普通开发者语言显示：

- Run ID、终态、总耗时、Provider 报告 Token、模型调用数、重试数、Tool 调用数、Verification 通过/失败数；
- 按开始时间排列的紧凑时间线：模型 attempt、Tool、Verification、Context 压缩和错误；
- 最慢操作、最大的请求 Context Snapshot、重复内容字节数，以及不完整/未知字段提示。

使用该终端的可用交互展示 Span 摘要和属性。长 ID、argv、路径、模型标识和内容 hash 应可读地换行/裁切；命令输出、输入正文和 Provider 私有信息不显示。JSON 客户端如暴露 Trace 查询，必须序列化同一 `RunTrace` 结构，不得要求消费者解析 Plain 文本。

Viewer 必须让用户区分：Provider 实测 Token、Context 本地字节数、重复内容字节数、缺失/未知值，以及可能来自旧 Journal 的不完整 Span。

## 安全、隐私与资源上限

- Trace 作为本地项目执行记录，继续保存在用户状态目录中 `0700` 目录与 `0600` 文件边界内；复用 Journal 权限与 Redactor，不在 Workspace 中写 Trace。
- 禁止保存 Provider Key/Secret、Key 环境变量名、Authorization Header、完整 Endpoint、完整 Prompt/消息、文件正文、Tool arguments/output、Verification stdout/stderr、原始 Provider 响应与异常堆栈。
- 允许记录受限标识、稳定错误码、字节数、Token 数、持续时间、内容哈希和事件引用。哈希按潜在敏感数据处理，不导出、不上传、不作为匿名标识。
- 每个 Context Snapshot 最多保留 256 个条目，规范 JSON 序列化后最多 65,536 字节。条目按请求中的首次出现顺序保留；超过条目数或字节上限时保留完整的各 `kind` 字节/条目汇总，在明细中保留可容纳前缀，并记录 `truncated=true`、`omitted_entry_count` 与 `omitted_bytes`。若单条明细超过剩余字节预算，则省略该明细及其后的明细，不截断哈希或字段值。
- Snapshot 不保留完整 Tool Schema，只记录规范化 Schema 指纹、字节数、工具名和数量。
- 查询与渲染不得重新加载 Workspace 文件以还原历史正文；完全依赖 Run 的本地事件事实。
- 新增 Trace 事实不得放宽现有 Redactor、内容安全、Approval、Policy、Workspace 或恢复边界。

## 失败、恢复与兼容

- Retry 每次 Provider attempt 都有独立 Span；`retry_of_span_id` 指向前一次 attempt。实际等待由已有 retry Event 提供，Viewer 可将等待显示为该调用间隔，不另造模型耗时。
- 进程在 Span 完成前退出时，投影显示中断/未知；不能把当前时间当作可信结束时间。
- `ResumeRun` 追加的后续操作仍归属于原 `run_id` Trace；新进程启动的 Span 使用新 ID。已存在未闭合 Span 保留 `interrupted`，恢复行为不会回写或篡改历史跨度。
- Event `schema_version=1` 的兼容格式继续使用 additive event types 与可选 payload 字段。旧读取器忽略未知 Event；旧 Journal 可读且无需迁移。若 Core Compatibility Manifest 要声明该能力，则由实现任务更新兼容清单与测试。
- Span/Trace 投影接受 Trace 事件重复缺失、乱序关联、未知 enum 和旧事件 payload；无效条目局部降级为 `unknown` 并带诊断码，不破坏原有 Run 恢复。
- Trace 完整性永远不能覆盖 Run Journal、Recovery Snapshot、`verification.completed` 或 Provider usage 的原始事实。

## 实施边界与阶段门禁

本规格的实现属于 Core-first 能力，应该按可独立验收的增量实施：基础投影与契约、Context Snapshot、LLM/Tool/Verification 观测、CLI 查询。桌面 Viewer 只在相应桌面阶段及其门禁通过后接入相同 Core 契约。

本规格接受后也不自动授权实施。当前阶段八仍 In progress，阶段九仍为 Ready for manual acceptance；Trace 不属于现有阶段八 0059–0066 授权任务，也不应悄然插入其执行顺序。建立新阶段/任务、决定阶段九收口前后顺序、修改路线图或开始代码实现，均需先对照最新 STATUS、相关 Accepted 决策和用户授权。本规格不改变阶段十必须等待阶段八与阶段九 Complete 的门禁。

## 验收标准

1. RunTrace 投影对新旧 Journal 可确定性重放；缺少终态、Span 未配对、无效时间与损坏 Trace payload 都产生局部、明确的未知/不完整结果。
2. Trace ID 等于 Run ID；可从 Session Journal 关联已提交轮次的 `session_id`；不存在的一等 `task_id`/`message_id` 不会被合成。
3. LLM 每次实际 attempt 都可区分成功、失败与重试；成功调用准确透传 Provider 报告用量；无 usage、缓存字段无效、失败调用或旧 Event 的未知值不被当作零。
4. Context Snapshot 与实际发出的 `ModelRequest` 一致；系统/项目说明/Skill/会话/用户目标/工具结果/Tool Schema 分类可测试；重复内容字节规则有相同内容、不同来源、重复消息、压缩前后测试。
5. Tool 与 Verification Span 覆盖成功、失败、拒绝、取消/中断及输出截断；持续时间使用单调时钟；Trace 不含原文或完整命令输出。
6. 模型/工具/验证三类耗时和运行级汇总可从事实重算；token、字节、费用和重复内容分别标注其来源与精度，不生成费用或分段 Token 的猜测值。
7. `/trace` 对活跃 Run、完成/失败/取消 Run、旧 Run、无 Run、错误 Run ID 和部分损坏 Journal 有可理解的结果；Plain/TUI/JSON 若支持查询，呈现同一 Core 投影事实。
8. 测试确认 Key、Key 环境变量名、Authorization、Endpoint、Prompt 正文、文件内容、完整 Tool 参数/结果、验证输出和原始 Provider 响应均不会进入 Trace payload。
9. Trace append 与 projection 不改变 Tool 执行次数、Approval 决策、Workspace 写入、恢复快照语义、verification 状态、Run 终态或现有 `/usage` 字段。
10. 记录测试显示 Snapshot 256 条/65,536 字节上限及确定性省略规则有效，历史 Run 查询不会读取 Workspace 内容；本地文件仍符合 Journal 权限约束。

## 关联实现位置

- 事件契约：[contracts/events.py](../../src/vera/contracts/events.py)
- Runtime 编排与模型/工具/验证事件：[runtime/engine.py](../../src/vera/runtime/engine.py)
- Provider 中立模型请求与用量：[models/base.py](../../src/vera/models/base.py)、[models/provider_usage.py](../../src/vera/models/provider_usage.py)、[models/openai_compatible.py](../../src/vera/models/openai_compatible.py)
- 工具结果：[tools/definitions.py](../../src/vera/tools/definitions.py)、[tools/registry.py](../../src/vera/tools/registry.py)
- 验证结果：[contracts/verification.py](../../src/vera/contracts/verification.py)、[verification/runner.py](../../src/vera/verification/runner.py)
- 持久化及历史 Run 查询：[persistence/journal.py](../../src/vera/persistence/journal.py)、[persistence/run_store.py](../../src/vera/persistence/run_store.py)
- Session 关联与当前用量查询：[contracts/sessions.py](../../src/vera/contracts/sessions.py)、[session/queries.py](../../src/vera/session/queries.py)、[session/controller.py](../../src/vera/session/controller.py)
- 当前结构化 UI 时间线：[presentation/projector.py](../../src/vera/presentation/projector.py)、[presentation/timeline.py](../../src/vera/presentation/timeline.py)、[terminal/widgets/timeline.py](../../src/vera/terminal/widgets/timeline.py)
- Provider 缓存事实边界：[Provider 上下文缓存用量与稳定前缀](2026-09-25-provider-context-cache-usage.md)

## 参考

- [ADR-0002：Command/Event 契约](../decisions/ADR-0002-command-event-contract.md)
- [ADR-0005：确定性 Run 恢复](../decisions/ADR-0005-deterministic-run-recovery.md)
- [ADR-0014：Core 客户端兼容契约](../decisions/ADR-0014-core-client-compatibility-contract.md)
- [ADR-0021：桌面前先完成 Core 工具与 Policy](../decisions/ADR-0021-core-tools-before-desktop.md)
