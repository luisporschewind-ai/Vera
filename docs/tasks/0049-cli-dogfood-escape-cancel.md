# 任务 0049：走查发现 48（Esc 取消无效）

> 供主实现 Agent 执行：阶段七第 2 项走查。不开始阶段八。

**状态：** In progress
**执行就绪：** 是
**分支：** `phase-7/0041-product-acceptance`
**依赖：** 任务 0041 自动门禁
**规格：** [CLI 产品化](../specs/2026-09-12-cli-productization-and-polish.md)、[富终端 UI](../specs/2026-09-11-rich-terminal-ui.md)

## 背景

用户 2026-09-17 走查第 2 项 C：运行中按 Esc 取消无效。状态带写着 `Esc/Ctrl-C 取消`，但 TUI 只绑定了 `ctrl+c`。规格要求运行中 Esc 与 Ctrl+C 都只发送一次取消。

## 目标与边界

- 运行中 Esc 发送一次 `CancelActiveRun`，不退出 TUI。
- 空闲 Esc 不清空草稿；若补全面板打开则关闭。
- Ctrl+C 空闲清空草稿的语义不变。
- 不改审批默认 Cancel、不读取真实 Key、不引入桌面框架。

## 实施步骤

- [x] 测试：运行中 Esc 取消且不退出；空闲 Esc 保留草稿。
- [x] App 绑定 `escape`（priority）并实现 `action_escape`。

## 验证

```bash
uv run pytest tests/terminal/test_keybindings.py tests/terminal/test_keyboard_flows.py -q
git diff --check
```

## 验证证据

- 2026-09-17：`tests/terminal/test_keybindings.py`、`test_keyboard_flows.py`、`test_session_picker.py` → `9 passed`；`ruff`/`mypy`/`git diff --check` 通过。
- 未把 Pilot 当作 Terminal.app 证据。发现 48 待用户复验运行中 Esc。

## 未决

- 发现 48 待 Terminal.app 复验。
- 未收到「CLI 版本达到预期，可以封存」。
