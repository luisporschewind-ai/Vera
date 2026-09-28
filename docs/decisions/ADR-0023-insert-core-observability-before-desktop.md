# ADR-0023：在桌面集成前插入 Core Trace 与可观测性阶段

**状态：** Accepted
**日期：** 2026-09-26
**接受：** 用户确认“顺延”，授权阶段十开始实施，并由用户自行验证阶段八、九

## 背景

ADR-0021 确立了 Core 工具集与 Git、Core-native Skills、桌面集成、私有预览的顺序，对应阶段八至十一。后续接受的 [Core Trace 与运行可观测性规格](../specs/2026-09-26-core-trace-observability.md)要求先在 UI 无关 Core 建立 RunTrace 契约、Journal 投影与 CLI 查询，再供未来客户端复用；它不属于阶段八 0059–0066，也不依赖桌面框架。

若将 Trace 作为普通补充增量，会绕过阶段顺序、任务记录与退出条件；若塞入阶段八或九，则改变已接受阶段范围和现有实施授权。需要在桌面之前建立独立 Core 阶段，同时保留阶段八、九尚未收口的事实。

## 候选方案

### A. 在桌面前新增独立 Core Trace 阶段（采用）

保留阶段八 Core 工具/Policy/Git 和阶段九 Core-native Skills；新增阶段十 Core Trace 与运行可观测性；桌面与私有预览分别顺延为阶段十一、十二。

优点是 Trace 以 Core/CLI 独立验收，并可成为桌面消费的稳定事实契约。代价是桌面启动继续顺延，路线图和阶段编号需要同步调整。

### B. 将 Trace 并入阶段八或九

可减少阶段编号变化，但会扩张已接受阶段范围、污染既有任务边界，并可能要求重开阶段验收与授权；不采用。

### C. 将 Trace 保持为无阶段补充增量

可维持桌面编号，但无法表达其先于桌面的 Core 基础设施关系，且容易绕过前序阶段门禁；不采用。

## 决策

1. 当前阶段顺序调整为：阶段八 Core 工具集、Policy v2 与原生 Git；阶段九 Core-native Skills；阶段十 Core Trace 与运行可观测性；阶段十一桌面集成；阶段十二私有预览与公开准备。
2. 阶段十仅实施已接受规格定义的 Core 契约、Journal Trace 事实、投影及 CLI 查询，不引入桌面框架、远程 APM、独立数据库或规格之外的观测能力。
3. 通常情况下阶段十入口要求阶段八与阶段九均为 Complete；用户于 2026-09-26 明确批准本次例外，允许阶段十与阶段八/九并行实施，并由用户自行验证阶段八、九。该例外不改变阶段八、九状态，也不替用户记录其验收结果。
4. 阶段十 Complete 后，且阶段八、九都经各自验收为 Complete，方可启动阶段十一桌面集成。
5. 用户授权阶段十按 [Trace 实施计划](../superpowers/plans/2026-09-26-core-trace-observability.md)由当前主 Agent 逐任务实施；不包含提交、合并、推送或远程发布授权。
6. ADR-0021 的阶段编号关系由本 ADR 取代；其 Core 工具集、Policy v2、原生 Git 与 Skills 范围、安全约束及桌面复用 Core 原则保持有效。

## 阶段退出条件

- Trace 合同和投影对新旧 Journal 保持可重放，对未知/损坏事实局部降级。
- LLM、Tool、Verification 与 Context Snapshot 按规格记录；Token、字节、耗时和重复内容来源及精度明确。
- Trace 隐私、Journal 权限、Snapshot 上限、恢复和 Workspace 隔离测试通过。
- CLI `/trace [run-id]` 在 Plain/TUI/JSON 中基于同一 `RunTrace` 事实工作；`/usage`、Policy、Approval、Recovery、Verification 及 Run 终态语义不变。
- 聚焦自动检查与规格要求的本地人工可读性验收通过，没有未关闭 Critical/High 正确性、可靠性或隐私问题。

## 后果

- Trace 是独立 Core 阶段，不改变阶段八 0059–0066、阶段九 0067–0072 的既有范围或验收记录。
- 桌面仍采用 ADR-0013 接受的 Electron 基线，但当前阶段编号从十顺延为十一；实现须满足阶段八、九、十 Complete 门禁。
- 私有预览和公开准备由阶段十一顺延为十二。
- 本 ADR 不改变阶段五人工验收、阶段八/九当前状态；阶段十已按用户的明确并行例外授权开始。

## 重新评审触发器

- 阶段八或九的实际收口证明其门禁、阶段顺序或任务归属需要调整。
- Trace 规格实施前发现必须破坏既有 Journal/客户端兼容契约，或超出独立 Core 阶段边界。
- 阶段十一桌面工作发现 Trace 对桌面没有预期复用价值，需重新评估阶段退出条件，而不是绕过阶段十。

## 关联

- [ADR-0021：桌面前插入 Core 工具集与 Git 能力阶段](ADR-0021-core-tools-before-desktop.md)
- [Core Trace 与运行可观测性规格](../specs/2026-09-26-core-trace-observability.md)
- [Core Trace 与运行可观测性实施计划](../superpowers/plans/2026-09-26-core-trace-observability.md)
- [任务 0086：Core Trace 与运行可观测性](../tasks/0086-core-trace-observability.md)
- [路线图](../ROADMAP.md)
