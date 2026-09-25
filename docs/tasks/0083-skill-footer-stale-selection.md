# 任务 0083：底栏"已选择 Skill"不随消费或清除更新

**状态：** Done
**来源：** 2026-09-25 用户在 Terminal.app 看到底栏一直显示"已选择 user:interview-term-brief · 1.0.0，等待下一次任务"，询问如何清除。
**规格：** [Skill 交互列表](../specs/2026-09-24-skills-interactive-picker.md)

## 背景

浮层选中 Skill 后，TUI 在底栏写入"已选择 … 等待下一次任务"。这是一次性提示，之后不再更新：

- 下一次任务 Run 绑定 Snapshot 时 Core 已一次性消费选择，并发出 `skill.selection.changed`（未选择），底栏仍显示"已选择"；
- `/skills clear` 清除后同样如此；
- 直接输入 `/skills use <id>` 选中时，底栏反而没有提示。

结果是底栏与 Core 事实不一致，用户误以为 Skill 仍会作用于下一次任务，且找不到清除方式。

## 目标与边界

- TUI 收到任何 `skill.selection.changed` 时按其中的 `selection` 同步底栏：`status=selected` 显示"已选择 … 等待下一次任务"（含实际版本）；否则若底栏当前是 Skill 提示，则移除该提示。
- 不覆盖与 Skill 无关的其他底栏提示。
- 浮层确认流程、Core 选择/消费语义、`/status` 与会话持久化不变。

## 实施步骤

- [x] `VeraTerminalApp` 对所有 `skill.selection.changed` 同步底栏提示；浮层确认复用同一文案。
- [x] `VeraStatusLine` 暴露只读 `notice`。
- [x] 规格补充底栏提示须跟随 Core 选择事实。
- [x] Pilot 回归：`/skills clear` 清除提示；Run 绑定后清除提示；`/skills use` 命令显示提示；无关提示不被清除。

## 验证

```bash
uv run pytest tests/terminal/test_skill_picker_integration.py tests/session/test_skill_commands.py -q
uv run ruff check src tests && uv run ruff format --check src tests
uv run mypy src
git diff --check
```

## 验证证据

- 2026-09-25：`test_skill_picker_integration`、`test_skill_commands`、`test_app`、`test_status_line` 共 `49 passed`；`tests/terminal` 与 `tests/session` 共 `285 passed, 1 failed`，失败项 `test_layout.py::test_resize_burst_does_not_clear_each_frame` 为缩放防抖计时测试，单独重跑 3 次为 2 过 1 败，与本改动无关。`ruff check`、`ruff format --check`、`mypy src`、`git diff --check` 通过。未运行全量测试。
- 2026-09-25：用户在 Terminal.app 复验选中、提问后消失与 `/skills clear` 后消失，确认"没问题，都已验证"，任务关闭。
- 提交：`d215bcd`（未推送）。

## 未决

- 无。缩放防抖计时测试不稳定属既有问题，不在本任务范围。
