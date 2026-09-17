# 任务 0056：进场欢迎卡、缩行路径与底栏事实

> 供主实现 Agent 执行：阶段七 CLI 进场与底栏。不开始阶段八。只改用户点名的顶栏、底栏与用户时间。

**状态：** In progress
**执行就绪：** 是
**分支：** `phase-7/0041-product-acceptance`
**依赖：** 任务 0055；用户 2026-09-17 确认方案 A、密集点阵、缩行贴近全路径
**规格：** [阶段七 CLI 体验收口](../specs/2026-09-13-cli-experience-and-personal-dogfood.md)、[视觉 Token](../specs/2026-09-13-vera-cli-visual-tokens.md)

## 背景

用户确认：进场为无框欢迎卡；左侧三行密集点阵 `VERA`；右侧 `Vera` 与包版本、全路径、模型与推理。本进程第一次发出任务后收成一行 `VERA  ~/path`，彼此靠近，`/new` 也不展开。波动只出现在欢迎卡，方向左下到右上、节奏加快。底栏左为分支（无则省略）、`审批 manual`、上下文占用；右为模型与推理。用户卡片时间为 `9:21 PM`。其它现有样式不动。

2026-09-17 Terminal.app：波动方向/速率、底栏右侧模型被裁切、进场右侧浅色块需修；其余显示通过。

## 目标与边界

- 欢迎卡无边框，上下左右只留现有量级的 margin。
- 点阵为盲文点拼成的三行 `VERA`；ASCII 用 `.` 同一轮廓。不引入 V 星点或新图形。
- 缩行显示全路径（家目录写 `~`）；`VERA` 与路径以两个空格分隔，不拉到两端。
- 底栏不再写「非 Git」；无分支就跳过分支。
- 不改 Composer、审批卡、时间线组、工作轨、主题色。
- 不改审批语义、不读真实 Key、不引入桌面框架。

## 实施步骤

- [x] 回写视觉 Token 与阶段七规格。
- [x] 点阵字标、欢迎卡投影、缩行、进场波动。
- [x] 底栏分支/审批/模型；用户时间为 12 小时 AM/PM。
- [x] 波动改为左下→右上并加快；底栏按 padding 预留宽度；去掉点阵 `dim` 与顶栏右侧未铺色空隙。

## 验证

```bash
uv run pytest tests/terminal/test_brand.py tests/terminal/test_welcome.py tests/presentation/test_footer_status.py tests/presentation/test_timeline_time.py tests/presentation/test_timeline.py tests/terminal/test_layout.py tests/terminal/test_layout_matrix.py tests/terminal/test_app.py tests/terminal/test_status_line.py tests/e2e/test_phase_7_product_matrix.py -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
git diff --check
```

## 验证证据

- 2026-09-17 聚焦测试 `74 passed in 21.97s`（含波动方向、底栏 76 列内宽、布局、欢迎卡、AM/PM）。
- `ruff check` / `ruff format --check` / `mypy src` / `git diff --check` 通过。
- 未改审批默认值、未读真实 Key、未引入桌面框架。

## 未决

- 待用户 Terminal.app 看波动方向与速率、底栏右侧模型、进场右侧是否还有浅色块。
- 发现 42、50 仍待复验。
- 未收到「CLI 版本达到预期，可以封存」。
