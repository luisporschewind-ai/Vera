# 任务 0033：桌面主工作流与安全审批

> 供 Cursor 执行：Renderer 只渲染阶段六冻结的结构化结果；发现契约缺口先更新规格/ADR。

**状态：** Planned
**执行就绪：** 否；任务 0032 合并后
**分支：** `phase-7/0033-desktop-primary-workflow`
**依赖：** 任务 0032 已合并
**规格：** [阶段七桌面集成](../specs/2026-09-12-desktop-integration.md)

## 目标与边界

完成 Workspace 内的桌面主闭环：输入目标 → 流式时间线 → 工具事实 → Change Set/Diff → 审批 → 写入 → 验证 → 完成/失败。不得直接读取文件生成审批 Diff，不得执行命令，不得把 Presenter 文本当状态。

## 逻辑文件

- `desktop/app/frontend/src/models/runtime.ts`：由 compatibility manifest 生成或校验的 TS model。
- `desktop/app/frontend/src/state/session.ts`：单 active run、pending approval、stream 与持久 Event reducer。
- `desktop/app/frontend/src/state/timeline.ts`：有界投影和分页引用。
- `desktop/app/frontend/src/views/AgentWorkspaceView.*`。
- `desktop/app/frontend/src/components/Composer.*`。
- `desktop/app/frontend/src/components/Timeline.*`。
- `desktop/app/frontend/src/components/ToolCard.*`。
- `desktop/app/frontend/src/components/DiffView.*`。
- `desktop/app/frontend/src/components/ApprovalCard.*`。
- `desktop/app/frontend/src/components/VerificationCard.*`。
- `desktop/app/frontend/src/components/ErrorCard.*`。
- 对应 unit/component/e2e tests。

具体扩展名和测试命令由任务 0031 的 UI ADR 写回。

## 结构化状态规则

- `EventEnvelope` 决定持久时间线、审批、失败和终态。
- `StreamFrame` 只更新当前临时 stream；index 缺口标记 incomplete。
- 未知 Event 使用 type/code 的安全 fallback，不显示原始 object dump。
- active run 时只允许 cancel 和只读查询；pending approval 时禁止新 prompt。
- 完成必须有 Core 终态 Event；UI 不以 stream 结束、进度 100% 或 exit code 0 猜测。

## 测试先行步骤

### 1. Reducer 与 Event parity

使用任务 0030 conformance fixtures：

- out-of-order/duplicate/gap；
- stream + final assistant.message；
- run completed/failed/cancelled；
- unknown additive Event；
- Renderer reload snapshot hydration；
- 与 CLI/Eval 的 run state、approval hash、Change Set hash、verification result 相同。

### 2. Composer 与任务控制

- 空输入、超长输入、CJK、多行和提交；
- active run 不提交第二任务；
- cancel 只发送一次 operation id；
- 发送失败保留用户原输入；
- 本任务不增加持久对话恢复或消息排队语义。

### 3. 时间线与工具卡

- 500 item 下保持有界 DOM/组件；
- 工具摘要显示 action/target/status/duration；
- stdout/stderr 截断事实可见，控制字符安全；
- 普通日志折叠，失败和审批展开；
- 不可信 Markdown/ANSI/OSC/双向字符不获得执行能力。

### 4. Diff

- 文件列表、hunk、行号、增删语义、横向滚动/安全换行；
- 10,000 行 fixture 使用 Core 页/截断，不一次性无限渲染；
- copy 输出可核对且不改变 target hash；
- Renderer 没有直接 file read API；
- Core 报告 baseline changed 时使审批 UI 过期。

### 5. 审批

- 首层展示 action、target、risk、Workspace、Diff/argv、policy/fact hash 和实际效果；
- 默认焦点 reject/cancel，Approve 无易误触快捷键；
- hash/Workspace/policy 变化显示 expired；
- 重复点击与重连不会重复副作用；
- reject/cancel 后 UI 不显示已应用。

### 6. 验证与错误

- argv/cwd/risk/approval/exit/duration/truncated；
- success/failure/cancelled/unknown effect 分开；
- 错误卡含“发生什么、是否有副作用、下一步”；
- traceback、env、Key、完整请求不进入 Renderer。

## 自动验证

- reducer golden 与 Core client parity；
- component accessibility/keyboard tests；
- 500 timeline/10,000 Diff 性能门禁；
- E2E Fake Model 安全编辑闭环；
- secret/control-character negative fixtures；
- 所选框架与阶段七共同门禁。

## 人工验证

- Intel macOS 上输入、流式、工具、单/多文件 Diff；
- approve/reject/cancel/expired；
- 验证成功/失败和可行动错误；
- CJK、缩放、高对比、键盘-only、复制与滚动。

## 验收标准

- 桌面主闭环与 CLI 共享同一 Core 事实。
- Renderer 没有 Workspace 写入、命令或审批逻辑。
- 大时间线/Diff 可用且有界。
- 所有危险状态默认安全，错误不虚假成功。

## 提交

```bash
git diff --check
git commit -m "feat: add desktop safe editing workflow"
```
