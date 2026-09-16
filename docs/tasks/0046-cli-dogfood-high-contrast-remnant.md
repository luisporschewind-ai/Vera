# 任务 0046：走查发现 46（高对比度残影）

> 供主实现 Agent 执行：阶段七 Terminal.app 主题切换走查。不新开规格，不开始阶段八。

**状态：** In progress
**执行就绪：** 是
**分支：** `phase-7/0041-product-acceptance`
**依赖：** 任务 0041 自动门禁
**规格：** [阶段七 CLI 体验收口](../specs/2026-09-13-cli-experience-and-personal-dogfood.md)、[视觉 Token](../specs/2026-09-13-vera-cli-visual-tokens.md)

## 背景

用户 2026-09-16 在原生 Terminal.app 切到高对比度：有残影，右侧显示异常。高对比时间线曾画白边并去掉右边框，切换后右侧留下一列旧底色。

## 目标与边界

- 高对比时间线与默认主题一样无边框，避免左右宽度不一致。
- 切主题后强制重绘，并同步 sticky 宽度。
- 不改审批、不引入桌面框架。

## 实施步骤

- [x] 去掉高对比 `#timeline` 的 `border: solid` / `border-right: none`。
- [x] 补上 `.-theme-high-contrast #welcome` 黑底。
- [x] `_apply_theme` 在 `refresh_css` 后 `refresh()` 并 `_sync_sticky_offset()`。

## 验证

```bash
uv run pytest tests/terminal/test_theme.py -q
git diff --check
```

## 验证证据

- 局部测试：`tests/terminal/test_theme.py` 7 passed。
- `ruff check` / `git diff --check` 通过。
- 真实 Terminal.app 复验待用户：`/theme high-contrast` 后无右侧残影。

## 未决

- 发现 44：`vera -r` 无参数时报 Option requires an argument。
- 发现 45：`/new`/`/clear` 后时间线仍显示上一会话。
- 未收到「CLI 版本达到预期，可以封存」。
