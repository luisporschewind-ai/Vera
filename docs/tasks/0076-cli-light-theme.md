# 任务 0076：CLI Light 主题

**状态：** Done（2026-09-24）
**来源：** 用户要求新增命名为 Light 的内置会话主题
**规格：** [Vera CLI 视觉 Token 与标识](../specs/2026-09-13-vera-cli-visual-tokens.md)（同日增补 Light 列）
**关联：** 任务 [0039](0039-cli-brand-theme-and-startup-chrome.md)、`/theme`

## 交付

- 内置主题 ID：`light`；显示名：`Light`；`/theme light` 与 `/theme Light` 均可。
- 配色为深海青绿的浅色纸面对照：背景 `#F3F6F9`、表面 `#FFFFFF`、强调/字标 `#2F6F82`、正文 `#1A2B36`。
- Textual `Theme.dark=False`；Chrome、Composer、Skill 浮层、补全高亮与 Markdown（`ansi_light`）按浅色可读性调整。
- 仍为会话级内置主题：不写配置文件、不加载可执行主题、不引入主题市场。

## 验证

- 聚焦 `tests/terminal/test_theme.py` 等：含 Light 切换、Logo 色、状态文案；`39 passed`（主题/补全/浮层相关套件）。
- 提交：`f32fb58 feat: add Light session theme`。

## 边界

不改变默认深海主题、不改变 Core/审批语义、不启动阶段十。
