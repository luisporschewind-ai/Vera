# 任务 0032：时间线信息层次与错误保真

> 供 Cursor 执行：阶段六人工走查暴露的一组缺陷修正。规格条款早已接受，是实现未达成，因此不需要新规格。

**状态：** Done
**执行就绪：** 否；本任务已 Done
**分支：** `phase-6/0032-timeline-and-error-fidelity`
**依赖：** 任务 0029 自动部分已完成；任务 0031 已 cherry-pick 到本分支，`vera --version` 可用
**规格：** [阶段六 CLI 产品化](../specs/2026-09-12-cli-productization-and-polish.md)

## 背景

用户在真实 Terminal.app 与 `~/Desktop/VeraTestDemo` 走查时报告：时间线不自动跟随底部；状态显示「相当原始，没有收敛」。据此定位到四个同源缺陷，见 [人工走查发现清单](../evals/phase-6-manual-walkthrough.md) 发现 2–7。

共同根因：任务 0027 精修了证据类展示（Diff、审批、验证、失败卡），把模型往返、状态类事件与 Provider 错误细节留在开发期占位实现。

## 目标与边界

让时间线在未离开底部时可靠跟随；让展示层不再泄漏内部事件名与原始 payload；让失败文案依据实际事实而非硬编码常量；让 Provider 错误保留可诊断信息。

不新增 Core 权限，不改公共契约字段语义，不引入桌面端，不读取 Provider Key，不放宽审批边界。

## 实施步骤

### 1. 时间线跟随底部

**修改：**

- `src/vera/terminal/widgets/timeline.py`
- `tests/terminal/test_scrolling.py`

**缺陷：** `_append` 的 `mount()` 在 Textual 中是异步的，`apply()` 随即调用 `scroll_end()` 时新块尚未进入布局，`virtual_size` 仍为旧值，因此滚到上一条内容的底部。`apply`、`flush_scheduled`、`return_to_tail` 三处同源。

**测试先行：** 断言真实滚动位置——挂载若干超出视口的 block 后 `scroll_y` 必须到达 `max_scroll_y`；用户向上滚后不得被抢回；按 End 必须回到真实底部。现有测试只断言 `follow_tail` 标志与代码分支，这是漏检原因。

**最小实现：** 把跟随滚动改为在布局刷新之后执行；未挂载时不得调用。

### 2. 事件展示收敛

**修改：**

- `src/vera/presentation/projector.py`
- `src/vera/presentation/activity.py`
- `tests/presentation/test_projector.py`
- `tests/presentation/test_disclosure.py`

**缺陷：** `model.requested`、`model.completed`、`model.failed` 不在 handlers 表中，落入 `_unknown_event`（`title=event.type`、`body=str(payload)`）；`run.started`、`checkpoint.created`、`changeset.applied` 走 `_status_event` 的同样占位写法。

**要求：** 模型往返属过程噪音，不占时间线 block，只驱动状态行活动指示。状态类事件使用人类可读中文标题，不展示原始 dict。任何进入时间线的展示文本不得包含内部事件类型名。

### 3. 工具摘要的目标与耗时

**修改：**

- `src/vera/presentation/projector.py`
- `tests/presentation/test_projector.py`

规格要求工具摘要显示动作、目标、状态和耗时，并允许相邻同类只读工具视觉归组。当前仅有动作与状态。补齐目标与耗时；归组不得掩盖单个权威 Event 的可查看性。

### 4. 失败文案依据事实

**修改：**

- `src/vera/presentation/errors.py`
- `tests/presentation/test_errors.py`

**缺陷：** `explain_failure` 对 `run.failed` 硬编码「可能已产生部分工作区或状态变化」，不看本次 run 是否存在 `checkpoint.created` / `changeset.applied`。纯只读 run 也被告知可能有副作用并建议回滚，属状态误报，且违反产品的证据为准原则。

**要求：** 副作用结论必须由已观察事实推导：无写入类事件时明确说明未产生工作区变化；有写入时保留谨慎表述。不得在证据充分时输出「可能」。

### 5. Provider 错误保真

**修改：**

- `src/vera/models/openai_compatible.py`
- `src/vera/models/errors.py`
- `tests/models/test_openai_compatible.py`

**缺陷一：** `_map_exception` 中 `code = ModelErrorCode.SERVICE if status and status >= 500 else ModelErrorCode.SERVICE`，三元表达式两侧相同，4xx 与 5xx 未区分。

**缺陷二：** 错误文案被统一替换为 `"provider service error"`，Provider 返回的原始原因完全丢弃，私有日志亦无留存，导致 400 无法定性。

**要求：** 区分请求侧 4xx 与服务侧 5xx，前者不可重试且应指向请求构造问题。保留可诊断信息，且必须经 Redactor，不得写入 Key、请求正文或用户源码正文。公共 Event 仅承载稳定 code 与脱敏摘要。

### 6. 终态状态行

**修改：**

- `src/vera/terminal/widgets/status_line.py`
- `tests/terminal/test_status_line.py`

run 到达终态后状态行仍显示「Esc/Ctrl-C 取消」，语义错误。终态不得提示取消。

### 7. 走查与状态记录

**修改：**

- `docs/evals/phase-6-manual-walkthrough.md`
- `docs/STATUS.md`

发现 2、4、5、6、7 标为代码已修、待用户复验。发现 3（Provider 400）在步骤 5 落地后仍需用户复跑一次才能定性，保持 Blocked。不把任务 0029 或阶段六标为 Complete。

## 验证与提交

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest -m "not live" -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git diff --check
```

```bash
git commit -m "fix: converge timeline display and preserve error fidelity"
```

## 验收标准

- 未离开底部时新内容必达真实底部，断言基于 `scroll_y` 与 `max_scroll_y` 而非标志位。
- 时间线不出现 `model.requested` 一类内部事件名或原始 payload dict。
- 工具摘要含目标与耗时；同类只读工具归组后单个 Event 仍可查看。
- 纯只读失败 run 的副作用结论为「未产生工作区变化」。
- 4xx 与 5xx 映射到不同 code，4xx 不可重试，原始原因可脱敏诊断。
- 终态状态行不提示取消。
- 完整非 live、Ruff、格式、Mypy 与 `git diff --check` 通过。

## 验证证据

- 提交：`60e13ef fix: converge timeline display and preserve error fidelity`。
- Terminal.app：发现 2（跟随底部）、发现 9（工具目标/耗时）、发现 32（只读失败「未产生工作区变化」/「未写入」）、发现 33（人类输出不打印 `model.requested`）均已复验通过。
- 2026-09-16 文档对齐时本任务按已有复验关闭。
