# 任务 0027：时间线、Diff、审批与错误体验

> 供 Cursor 执行：按 `superpowers:executing-plans` 实施；Presenter 只投影 Core 事实，不重新决定权限或成功状态。

**状态：** Done
**执行就绪：** 任务 0026 合并后
**分支：** `phase-6/0027-timeline-diff-approval-errors`
**依赖：** 任务 0026 已合并
**规格：** [阶段六 CLI 产品化](../specs/2026-09-12-cli-productization-and-polish.md)

## 目标与边界

建立成熟的信息层次：工具/日志默认折叠，Diff/审批/失败默认展开；Diff 可导航复制；审批默认安全；验证和错误说明副作用与下一步；滚动不被流式输出抢占。

## 实施步骤

### 1. 权威披露状态模型

**修改：**

- `src/vera/presentation/projector.py`
- `src/vera/terminal/disclosure.py`
- `src/vera/terminal/widgets/timeline.py`
- `tests/presentation/test_projector.py`
- `tests/terminal/test_disclosure.py`
- `tests/terminal/test_timeline.py`

**测试先行：** 对 user/final/tool/log/diff/approval/verification/recovery/failure 建表测试默认展开、摘要字段和显式展开状态。相邻只读工具可成组，但每个 Event 保留独立引用。未知 Event 安全降级，不伪装成功。

### 2. 文件级 Diff 浏览与复制

**修改：**

- 新增 `src/vera/terminal/widgets/diff_view.py`
- `src/vera/terminal/widgets/timeline.py`
- `src/vera/terminal/app.py`
- 新增 `tests/terminal/test_diff_view.py`
- `tests/terminal/test_app.py`

用 Textual Pilot 覆盖多文件跳转、行号、增加/删除语义、长行换行/水平滚动、纯文本复制、空 Diff 和超大 Diff 截断提示。复制内容来自权威 Diff，不包含 Rich markup 或控制序列。

### 3. 安全审批卡与过期反馈

**修改：**

- `src/vera/terminal/widgets/approval.py`
- `src/vera/terminal/app.py`
- `src/vera/cli_session_presenter.py`
- `tests/terminal/test_approval.py`
- `tests/cli/test_session_presenter.py`

测试首层展示动作、目标、风险、Diff/argv、workspace 和实际效果；默认焦点 Cancel，Approve 无单字母快捷键。审批期间允许滚动、复制和只读 `/permissions`，禁止新任务。`approval.expired` 明确要求重新生成，不继续使用旧决定。

### 4. 验证卡、错误模型与退出码

**修改：**

- `src/vera/contracts/errors.py`
- `src/vera/presentation/projector.py`
- 新增 `src/vera/cli_exit_codes.py`
- `src/vera/cli.py`
- `src/vera/terminal/widgets/timeline.py`
- `tests/contracts/test_errors.py`
- `tests/cli/test_exit_codes.py`
- `tests/cli/test_json_session.py`
- `tests/terminal/test_timeline.py`

建立配置、workspace、Provider、策略拒绝、用户取消、验证失败、恢复失败和内部错误映射。卡片必须显示“发生什么、是否有副作用、下一步”；JSON 始终输出合法协议记录，stdout 无 traceback/动画。

### 5. Scroll anchor 与流式合并

**修改：**

- `src/vera/terminal/widgets/timeline.py`
- `src/vera/terminal/streaming.py`
- `tests/terminal/test_timeline.py`
- `tests/terminal/test_streaming.py`

测试离开底部后新帧不抢滚动、显示新更新计数、End 回底部、Resize 保持锚点；持续 stream 不重复 block、不改变审批焦点。

## 验证与提交

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/presentation tests/terminal tests/cli/test_plain_session.py tests/cli/test_json_session.py tests/cli/test_session_presenter.py tests/contracts/test_errors.py tests/cli/test_exit_codes.py -q
```

再运行[阶段六共同门禁](phase-6-execution-order.md)，更新任务证据并提交：

```bash
git commit -m "feat: polish timeline diffs approvals and errors"
```

## 验收标准

- 默认披露严格符合规格，失败不会埋在折叠日志中。
- Diff 可按文件导航和复制，超大内容有明确截断事实。
- 审批默认焦点安全，过期审批不可使用。
- 错误、取消、拒绝、恢复和完成语义及退出码不混淆。
- 流式更新、滚动和 Resize 不丢输入或改变用户选择。

## 验证证据

日期：2026-09-13

- 披露表覆盖 user/final/tool/log/diff/approval/verification/error；失败与取消默认展开。
- DiffView 支持文件跳转、增减语义、纯文本复制和截断提示。
- 审批默认 Cancel；过期审批投影为必须重新生成的错误卡。
- 失败文案包含发生什么、副作用和下一步；退出码区分取消/验证失败/运行失败。
- 任务测试 89 passed；ruff/mypy 通过。
