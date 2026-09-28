# 任务 0075：CLI 窗口缩放闪动修正

**状态：** Ready for manual acceptance
**来源：** 2026-09-24 用户反馈“窗口扩大缩小时强烈闪动”
**规格：** [阶段七 CLI 体验收口](../specs/2026-09-13-cli-experience-and-personal-dogfood.md)
**关联：** [任务 0058：缩放右侧残留与底栏显示不全](0058-cli-resize-remnant-and-footer-clip.md)

## 现象与根因

0058 为消除 Terminal.app 缩放后的右侧旧边框，在每次 resize 的刷新回调中先向终端直接写 `CSI 2J` 清屏和 Home，再请求 Textual 重绘。连续拖动窗口时，每次尺寸变化都可能出现完整的空白帧；聚焦回归复现三次缩放产生六次整屏清除。

## 修正

- 尺寸变化时继续更新布局、Composer、底栏和时间线，但不逐帧清屏。
- 最后一次 resize 后等待 0.4 秒，再做一次旧边框修复；把清屏、完整画面和光标复位合成一次终端输出。
- 保留 0058 的底栏内宽限制和 Composer 不透明容器等修正。

## 验证

- 新回归测试先失败：三次缩放产生六次清屏；修正后验证拖动中无清屏、稳定后只有一次且同一输出包含画面。
- 布局、Footer 与终端测试：`166 passed`。
- `ruff check src tests`、`ruff format --check src tests`、`mypy src` 与 `git diff --check` 通过。
- 完整非 live 首轮 `1172 passed, 2 deselected, 8 warnings`，另有 1 failed、1 error；两项均为离线 wheel 安装缓存缺少 `openai`。补齐测试缓存后单独重跑这两项，`2 passed`。未重跑整个套件。
- 真实 PTY 驱动模拟 120×40 → 100×32 → 90×28 → 80×24：拖动阶段整屏清除 0 次，稳定后 1 次，清屏输出含完整 Vera 画面。
- 原生 Terminal.app 人工拖拽观感待复验；自动输出与布局测试不能替代视觉验收。

## 边界

本任务只修 CLI/TUI 缩放输出，不更改 Core、审批、Plain/JSON 语义或阶段状态，也不引入桌面框架。
