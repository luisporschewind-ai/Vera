# 任务 0058：缩放右侧残留与底栏显示不全

> 供主实现 Agent 执行：阶段七 CLI dogfood 修正。不开始阶段八。不改波动节奏、表格与白块铺色。

**状态：** Done
**执行就绪：** 是
**分支：** `phase-7/0041-product-acceptance`
**依赖：** 任务 0057
**规格：** [阶段七 CLI 体验收口](../specs/2026-09-13-cli-experience-and-personal-dogfood.md)、[视觉 Token](../specs/2026-09-13-vera-cli-visual-tokens.md)

## 背景

用户 2026-09-17 Terminal.app 截图：窗口放大缩小后，右侧留下输入框圆角边框残段；底栏最右模型名被切成 `deepseek-flas`。发现 40 曾修过 sticky 溢出，这次是 Composer 透明底未重绘、底栏按窗口宽排字却被 padding/`overflow: hidden` 裁掉右侧。

## 目标与边界

- 缩放后 Composer、顶栏、底栏不超出屏幕，右侧不留旧边框。
- 底栏按内容区宽度排版并铺满，模型名与推理不被裁掉最后一个字。
- 不改审批、波动、表格渲染、主题色板；不读真实 Key；不引入桌面框架。

## 实施步骤

- [x] 失败测试：120→80 后底栏仍含模型与推理，Composer/底栏/顶栏 `region.right` 不超过屏宽。
- [x] 底栏用实际内宽；缩放后强制 layout+repaint；Composer 用不透明底并 `overflow: hidden`。

## 验证

```bash
uv run pytest tests/terminal/test_layout.py tests/terminal/test_status_line.py tests/terminal/test_app.py tests/presentation/test_footer_status.py -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
git diff --check
```

## 验证证据

- 2026-09-17 聚焦测试 `37 passed in 15.30s`（layout/status_line/app/footer_status）。
- `ruff check` / `ruff format --check` / `mypy src` / `git diff --check` 通过。
- 未改审批默认值、未读真实 Key、未引入桌面框架。
- 2026-09-17 Codex 原生 Terminal.app 复现 1000×700 → 800×550 后右侧旧边框与白块；补充失败测试后，在 resize 全量重绘前显式清屏并回到 Home，复验不再残留，Composer 边框闭合，`deepseek-flash` 与推理事实完整。
- 同轮发现 footer 在布局追赶 resize 时可能短暂用旧 widget 宽度；内容宽度改为不超过最新终端列数。resize/footer 回归与滚动时序测试连续 12 轮 `24/24` 通过。

## 未决

- 发现 54 已由 Codex 按用户授权在原生 Terminal.app 代测关闭。
- 2026-09-17 用户原文确认「CLI 版本达到预期，可以封存」。
