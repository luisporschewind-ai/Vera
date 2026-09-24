# Vera CLI 活动状态与回答呈现

**状态：** Accepted
**日期：** 2026-09-24
**范围：** 阶段七封存后的定向 CLI 呈现修正
**授权：** 用户审阅 Claude Code 的终端状态动效分析后，确认把该交互原则融入 Vera，并确认修订方案。

## 意图

在 Vera 既有工作轨与流式回答上，以稳定的小动效、准确文字和必要的语义色展示当前活动。思考与回复在视觉上可区分；完成结果可回看；回答按视觉行逐步出现，同时保持真实流式内容和操作响应。

## 状态事实

UI 层枚举为 `Idle`、`Processing`、`Thinking`、`Replying`、`Working`、`Planning`、`AwaitingApproval`、`Verifying`、`Recovering`、`Done`、`Cancelled`、`Failed`。工具名称、目标和步骤是状态的细节，不另设顶层状态。`Thinking` 仅表示 `model.requested` 后尚未收到文本，不宣称获得模型内部推理。

- `run.started` → `Processing`；`model.requested` → `Thinking`；当前 Run 的首个 `assistant.delta` → `Replying`。
- `tool.started` → `Working`；`propose_changeset` 工具开始时 → `Planning`；`tool.completed`、`changeset.proposed`、`changeset.applied` 和 `verification.completed` 后，若无下一项权威活动，回到 `Processing`。
- `approval.required` → `AwaitingApproval`；`verification.started` → `Verifying`；恢复事件 → `Recovering` 或相应静态待处理状态。
- `run.completed`、`run.cancelled`、`run.failed` 分别 → `Done`、`Cancelled`、`Failed`。旧 Run 的迟到帧不得覆盖新 Run 或终态。

## 动效与布局

工作轨使用共用时钟、固定宽度动效位与现有语义 Token：Thinking 是慢速呼吸微光，Replying 是短笔画展开，Working/Planning/Verifying/Recovering 是轻扫；后者用文字和语义色区分实际动作。等待审批及三个终态为静态标记。动效不表示任务百分比，也不使用 Claude 的字形或文案。减少动效、无色、非 Unicode 或屏幕阅读器场景必须保留可读静态文字。

工作轨仍位于 Composer 上方，空闲及完成后隐藏。`Done` 在本轮最后一条回答旁保留；若没有回答，则在时间线末尾保留单行结果。失败与取消也必须可回看。状态结果只由对应的终态 Event 决定。

## 回答呈现

`assistant.delta` 与最终 `assistant.message` 继续是内容来源，Core、Journal、Plain、JSON 语义不变。TUI 可把一次到达的多行内容按当前终端宽度排版后逐行揭示；短增量尽快显示。显示节奏以约 50–80 ms/视觉行为起点，并在积压时加速，不无限延迟真实内容。模型不支持流式时，也可对最终完整回答应用同一呈现方式。

`assistant.message` 是完整正文权威值。`run.completed` 已到但仍有待显示行时，界面继续呈现回答，最后一行可见后才显示 `Done`。审批、失败、取消等需要注意的事实立即展示；滚离底部时不强制拉回；禁用动效时取消刻意的逐行节奏，仍保留真实增量。复制、滚动、Resize 和 Markdown 表格/代码不得得到与最终正文不一致的内容。

## 验收

- 通过事件时序覆盖思考→回复→工具→再思考、审批、验证、完成、失败、取消、恢复及迟到帧。
- 测试单次多行增量与非流式完整回答的逐行显示、积压追赶、最终正文、Done 时序和取消/审批优先级。
- 60×16、80×24、120×40、Resize、无色、减少动效、Plain/JSON 与原生 Terminal.app 走查。
