# 任务 0048：走查发现 47（上下文占用要显示真实字节）

> 供主实现 Agent 执行：阶段七第 4 项走查。不开始阶段八。

**状态：** In progress
**执行就绪：** 是
**分支：** `phase-7/0041-product-acceptance`
**依赖：** 任务 0041 自动门禁
**规格：** [阶段七 CLI 体验收口](../specs/2026-09-13-cli-experience-and-personal-dogfood.md)、[视觉 Token](../specs/2026-09-13-vera-cli-visual-tokens.md)

## 背景

用户 2026-09-17 在 80×24 看底部状态带：短条应表示**当前会话上下文占用**，并要看到真实数据。此前只显示整数百分比或 `<1%`，看不出 `ConversationStats.context_bytes / max_bytes`。底栏还可能停在启动时的 `session.status`，回合结束后不刷新。

## 目标与边界

- 状态带左侧短条旁显示 `已用/上限` 字节，与 `/status` 同源。
- TUI 按当前 `conversation_stats()` 刷新占用，不重探 Git。
- 不在每轮结束后额外发出 `session.status`，以免 Plain 重打状态面板。
- 不改审批、不读取真实 Key、不引入桌面框架。

## 实施步骤

- [x] `render_footer_status` 显示 `used/max`。
- [x] `_tick_status` 用 `conversation_stats()` 更新占用。
- [x] 不在 `_finish_active_run` 额外发 `session.status`（Plain 语义保持）。

## 验证

```bash
uv run pytest tests/presentation/test_footer_status.py tests/terminal/test_status_line.py tests/terminal/test_app.py tests/session/test_controller.py tests/cli/test_session.py tests/cli/test_json_session.py tests/e2e/test_phase_7_cli_semantics.py tests/e2e/test_core_client_contract_parity.py tests/e2e/test_phase_7_product_matrix.py -q
git diff --check
```

## 验证证据

- 2026-09-17：上列测试 `90 passed`；`ruff check` / `ruff format --check` 通过；`mypy` 对改动模块通过；`git diff --check` 无空白错误。
- 未把 Textual Pilot 当作 Terminal.app 证据。发现 47 待用户在 80×24 复验短条旁 `已用/上限` 与 `/status` 同源。

## 未决

- 发现 47 待 Terminal.app 复验。
- 未收到「CLI 版本达到预期，可以封存」。
