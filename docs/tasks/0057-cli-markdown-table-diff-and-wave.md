# 任务 0057：对话表格/Diff 渲染与进场波动可见

> 供主实现 Agent 执行：阶段七 CLI dogfood 修正。不开始阶段八。白块已通过，不再改顶栏铺色。

**状态：** In progress
**执行就绪：** 是
**分支：** `phase-7/0041-product-acceptance`
**依赖：** 任务 0056
**规格：** [富终端 UI](../specs/2026-09-11-rich-terminal-ui.md)、[视觉 Token](../specs/2026-09-13-vera-cli-visual-tokens.md)

## 背景

用户 2026-09-17 Terminal.app：进场右侧白块已通过。对话里的 Markdown 表格看起来没有排成表；Diff 等格式折行也乱。进场点阵波动看不见。

根因：助手 Markdown 为避开路径切断，先按 256 列摊平再当段落折行，把 Rich 表格拆散。Diff 用 Syntax `word_wrap` 从标识符中间切断。波动去掉 `dim` 后只剩 `bold`，而字标 CSS 本身就是粗体，波峰波谷一样。

## 目标与边界

- 管道表格按内容宽度排成表，表头同一行可见各列。
- 发现 42 的路径/CJK 折行仍保持。
- Diff 按行着色（视觉 Token 的增减色），长行在词界折行，不从 `max_bytes` 中间切断。
- 进场波动用亮/暗青色对比，不用 `dim`，避免白块回潮。
- 不改 Composer、审批、工作轨、主题色板；不读真实 Key；不引入桌面框架。

## 实施步骤

- [x] 失败测试：80 列表头同列、Diff 不切标识符、波峰/波谷样式不同且无 `dim`。
- [x] 表格/围栏按内容宽度渲染；散文仍走路径感知折行；Diff 按行着色与折行；波动用色差。

## 验证

```bash
uv run pytest tests/terminal/test_blocks.py tests/terminal/test_brand.py tests/terminal/test_animation.py tests/terminal/test_welcome.py tests/presentation/test_timeline.py -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
git diff --check
```

## 验证证据

- 2026-09-17 聚焦测试 `52 passed in 26.03s`（blocks/brand/animation/welcome/timeline/app/layout）。
- `ruff check` / `ruff format --check` / `mypy src` / `git diff --check` 通过。
- 未改审批默认值、未读真实 Key、未引入桌面框架。

## 未决

- 待用户 Terminal.app 看表格、Diff 与进场波动。
- 发现 42、50 仍待复验。
- 未收到「CLI 版本达到预期，可以封存」。
