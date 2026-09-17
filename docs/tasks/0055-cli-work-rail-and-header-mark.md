# 任务 0055：工作轨、状态组收起与顶栏字标

> 供主实现 Agent 执行：阶段七 CLI 信息层级。不开始阶段八。

**状态：** Done
**执行就绪：** 是
**分支：** `phase-7/0041-product-acceptance`
**依赖：** 任务 0041 自动门禁；用户 2026-09-17 确认三点
**规格：** [阶段七 CLI 体验收口](../specs/2026-09-13-cli-experience-and-personal-dogfood.md)、[视觉 Token](../specs/2026-09-13-vera-cli-visual-tokens.md)

## 背景

用户确认：工作状态固定到输入框上方；底栏不再显示「正在读取 / 已完成」；时间线「状态 · N 项」默认收起；进场强化已有 `VERA` 字标，Welcome 并入顶栏，不引入新图形。

## 目标与边界

- 工作轨在 Composer 上方：运行中显示当前动作/目标与本轮步骤；失败可见；空闲隐藏。
- 底栏只保留会话上下文、模型、推理；取消提示跟工作轨。
- 状态组与工具组一样默认收起，失败展开。
- 顶栏 80×24 两行字标强调色；会话事实并入第二行；Welcome 不再单独占行。
- 不改审批语义、不读取真实 Key、不引入桌面框架。

## 实施步骤

- [x] 回写视觉 Token 与阶段七规格中的工作轨/顶栏约定。
- [x] `WorkRail` 投影与 Widget；`ActivityPresenter` 记录目标与步骤。
- [x] 底栏去掉活动文案；状态组默认收起。
- [x] Header 合并 Welcome 事实，字标使用强调色。

## 验证

```bash
uv run pytest tests/presentation/test_footer_status.py tests/presentation/test_activity.py tests/presentation/test_work_rail.py tests/presentation/test_disclosure.py tests/terminal/test_status_line.py tests/terminal/test_welcome.py tests/terminal/test_work_rail.py tests/terminal/test_blocks.py tests/terminal/test_app.py tests/terminal/test_layout.py tests/terminal/test_layout_matrix.py tests/terminal/test_bridge.py tests/terminal/test_theme.py tests/e2e/test_phase_7_product_matrix.py -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
git diff --check
```

## 验证证据

- 2026-09-17 聚焦测试 `102 passed in 30.95s`。
- `ruff check` / `ruff format --check` / `mypy src` / `git diff --check` 通过。
- 未改审批默认值、未读真实 Key、未引入桌面框架。
- 2026-09-17 Codex 按用户授权在原生 Terminal.app 代测：顶栏 `VERA`、Composer 上方状态层、默认收起的「状态 · 1 项」和空闲时不占底栏均符合现行信息层级；底栏只保留会话/审批/模型/推理事实。

## 未决

- 2026-09-17 用户原文确认「CLI 版本达到预期，可以封存」。
