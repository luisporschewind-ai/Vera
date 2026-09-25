# 任务 0077：CLI 奶油风主题

**状态：** Done（2026-09-25；可读性修正经用户复验通过）
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

## 2026-09-25 人工测试发现与修正

用户在原生 Terminal.app、`VeraTestDemo` 的只读回答中发现：奶油主题下文件名呈青字黑底，正文呈低对比灰色，难以阅读。行内代码使用了 Rich 默认的 `markdown.code` 样式；切换主题时，已有回答的 Rich Text 没有按新主题重新渲染。

修正后 Light/奶油主题的行内代码使用各自的 `text_primary` 与 `surface_elevated` Token；主题切换时重新渲染已有助手回答。自动回归覆盖两套浅色主题的正文/行内代码，以及切换到奶油后已有回答的字色。原生 Terminal.app 观感仍待用户复验。

聚焦终端测试 `39 passed`；Mypy 对两个受影响源文件通过。全量回归由用户按此前约定执行。

用户随后补充 Light 同样有行内代码问题，其他主题也会出现用户消息背景不明显或消失；跨主题修正统一记录于 [0080](0080-cli-theme-readability.md)。
