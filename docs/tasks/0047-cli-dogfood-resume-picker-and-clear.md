# 任务 0047：走查发现 44–45（`-r` 选择器与清屏）

> 供主实现 Agent 执行：阶段七 Terminal.app 会话维护走查。不开始阶段八。

**状态：** Done
**执行就绪：** 否；本任务已 Done
**分支：** `phase-7/0041-product-acceptance`
**依赖：** 任务 0041 自动门禁
**规格：** [持久化对话会话](../specs/2026-09-13-persistent-conversation-sessions.md)、[对话 CLI 与会话状态](../specs/2026-09-11-conversational-cli-and-session-status.md)

## 背景

用户 2026-09-16 在原生 Terminal.app 走查第 2 项：

- 发现 44 High：`vera -r` 无参数时报 `Option '-r' requires an argument`。Typer 0.16 已忽略 `flag_value`，Click 把 `-r` 当成必填选项。
- 发现 45 High：`/new` 与 `/clear` 后上一会话时间线仍在。用户期望两者都清屏。旧规格曾让 `/new` 保留终端内容；本任务按走查结论对齐：两者都清空展示，磁盘上的旧会话仍保留。

## 目标与边界

- 裸 `vera -r` / `vera --resume` 在解析前补上内部哨兵，TTY 打开选择器；非 TTY 仍拒绝并提示传入 ID。
- `/new` 与 `/clear` 只发出 `clear_display`；TUI 回到干净首屏（品牌/Welcome/空时间线/Composer），不回放状态面板或恢复提示。确认只在状态栏。
- 清屏时隐藏 sticky、清空 Composer 输入历史、清零未读条数，并保持在顶部。
- 不改审批、不读取真实 Key、不引入桌面框架。

## 实施步骤

- [x] `normalize_resume_argv`：裸 `-r`/`--resume` 补 `__PICKER__`。
- [x] `SessionFlagGroup.parse_args` 在 Click 解析前规范化 argv。
- [x] `/new` 与 `/clear` 共用清屏；TUI 回到干净首屏，不回放 bootstrap。
- [x] 回写规格：`/new`/`/clear` 恢复干净首屏，不回放启动状态。

## 验证

```bash
uv run pytest tests/cli/test_session_flags.py tests/cli/test_session.py tests/session/test_controller.py tests/terminal/test_app.py -q
git diff --check
```

## 验证证据

- 局部测试：`tests/cli/test_session.py`、`tests/session/test_controller.py`、`tests/terminal/test_app.py`、`tests/presentation/test_projector.py` 等 86 passed。
- 完整非 live：`1081 passed, 2 deselected`；滚动 sticky 一项仍是既有 Pilot 抖动。
- `ruff check` / `ruff format --check` / `mypy src` / `git diff --check` 通过。
- 用户 2026-09-16 复验：`-r` 选择器通过；`/new`/`/clear` 仍回放状态面板、恢复提示和「4 条新消息」，已改为干净首屏，待再验。

## 未决

- 发现 44/45 需用户在原生 Terminal.app 复验后才能关闭。
- 发现 42 Low：Markdown 路径折行。
- 未收到「CLI 版本达到预期，可以封存」。
