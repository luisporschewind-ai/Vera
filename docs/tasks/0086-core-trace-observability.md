# 任务 0086：Core Trace 与运行可观测性

**状态：** In progress
**所属阶段：** 阶段十——Core Trace 与运行可观测性
**上游规格：** [Core Trace 与运行可观测性](../specs/2026-09-26-core-trace-observability.md)（Accepted）
**阶段决策：** [ADR-0023](../decisions/ADR-0023-insert-core-observability-before-desktop.md)（Accepted）
**实施计划：** [逐任务实施计划](../superpowers/plans/2026-09-26-core-trace-observability.md)
**执行方式：** 用户选择由当前主 Agent 在本会话中逐任务执行。
**授权记录：** 用户于 2026-09-26 明确授权阶段十与阶段八/九并行实施，并由用户自行验证阶段八、九；不包含提交、合并、推送或远程发布授权。

## 目标

在不引入独立事实库或远程观测服务的前提下，基于 Run Journal 建立可重放的 Core Trace 投影和 CLI 查询，让用户理解模型 attempt、Context 组成、Token 用量、工具/验证耗时及不完整事实。

## 范围

按实施计划依次完成七项工作：

1. Trace 公共契约与有界 Context Inventory；
2. TraceRecorder 与 Span Event 生命周期；
3. LLM attempt 与 Context Snapshot 接入；
4. Tool 与 Verification Span 接入；
5. 新旧 Journal 的确定性 RunTrace 投影与 Session 关联；
6. 只读 `/trace [run-id]` Plain/TUI/JSON 展示；
7. 聚焦回归、静态检查、人工可读性验收与状态记录。

详细字段、接口、测试和逐步命令以链接的实施计划和 Accepted 规格为准。

## 前置门禁

- 通常入口要求阶段八任务 0059–0066 与阶段九任务 0067–0072 所属阶段均 Complete；本任务依据 ADR-0023 记录的用户明确并行例外启动。
- 阶段八、九状态与验收仍由各自任务/阶段记录独立维护；用户将自行验证，Trace 实施不得将其标记为 Complete 或代填验收证据。
- 代码实施前复核当前 `STATUS.md`、路线图、Accepted 规格/决策、工作区及计划；若接口或门禁变化，先修订任务记录和计划。
- 本任务已根据用户的明确授权进入 In progress；继续保持与阶段八/九任务边界分离，不并入或改写其验收结果。

## 不在范围

- Electron/Tauri/Wails 桌面代码；
- OpenTelemetry、远程 APM/导出、SQLite、费用推算或 Tokenizer；
- 修改既有业务 Event、Approval、Policy、Workspace、Recovery 或 Verification 决策语义；
- 提交、合并、推送或远程发布。

## 验收与验证

- 完成实施计划七项任务，逐项记录 RED→GREEN 测试和所有偏离规格的裁定。
- 新旧 Journal 可重放，未知/损坏事实局部降级；隐私字段和资源上限测试通过。
- 相关 contracts/models/runtime/trace/persistence/session/cli/presentation 回归、Ruff、Mypy、格式与 `git diff --check` 通过；环境阻断原样记录，不得记作通过。
- 用户按规格完成本地真实 Run 的人工 Trace 可读性验收。
- 确认现有 `/usage`、Runtime Event 顺序、Recovery、Policy、Approval、Workspace 写入、Verification 结果及 Run 终态无回归。
- 只有全部证据齐备后，才能将任务与阶段转为相应验收状态；本任务与计划本身不代表阶段十已 Started 或 Complete。
