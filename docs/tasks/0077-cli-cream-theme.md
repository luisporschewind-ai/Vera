# 任务 0077：CLI 奶油风主题

**状态：** Done（2026-09-24）
**来源：** 用户要求再加一套温暖、阳光感的奶油风主题
**规格：** [Vera CLI 视觉 Token 与标识](../specs/2026-09-13-vera-cli-visual-tokens.md)（同日增补 Cream 列）
**关联：** 任务 [0076](0076-cli-light-theme.md)、`/theme`

## 交付

- 内置主题 ID：`cream`；显示名：`奶油`；`/theme cream` 与 `/theme 奶油` 均可。
- 配色为暖奶油纸面 + 阳光琥珀强调：背景 `#FBF6EC`、表面 `#FFFCF5`、抬升面 `#F3E8D4`、正文 `#3D3429`、强调/字标 `#C4843A`。
- 与冷色 `light` 并列的浅色选项；`Theme.dark=False`；Chrome、Composer、Skill 浮层、补全高亮与 Markdown（`ansi_light`）按暖色浅底可读性调整。
- 仍为会话级内置主题：不写配置文件、不加载可执行主题、不引入主题市场。

## 验证

- `uv run pytest tests/terminal/test_theme.py`：含 cream 切换、Logo/Token、`/theme 奶油` 归一化。
- Skill 浮层主题参数化已含 `cream`。
- 视觉 Token 规格与 STATUS 已同步为五套内置主题。

## 边界

不改变默认深海主题，不改变 Core/审批语义，不启动阶段十。
