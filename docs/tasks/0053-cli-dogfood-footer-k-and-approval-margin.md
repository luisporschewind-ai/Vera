# 任务 0053：状态带 K 单位、状态左置与审批卡边距

> 供主实现 Agent 执行：阶段七 dogfood 视觉微调。不开始阶段八。

**状态：** In progress
**执行就绪：** 是
**分支：** `phase-7/0041-product-acceptance`
**依赖：** 任务 0041 自动门禁
**规格：** [阶段七 CLI 体验收口](../specs/2026-09-13-cli-experience-and-personal-dogfood.md)、[视觉 Token](../specs/2026-09-13-vera-cli-visual-tokens.md)

## 背景

用户 2026-09-17 要求：底栏会话上下文占用改成 `K`；运行状态与「会话上下文」对调，状态在最左；审批卡上下 margin 略增大。

## 目标与边界

- 满 1000 字节起显示 `K`（如 `5.4K/200K`），不足 1000 仍显示整数。
- 状态带最左为运行状态，随后为会话上下文短条与占用。
- 审批卡 `margin: 1 2`，不超过一行分隔。
- 不改审批语义、不读取真实 Key、不引入桌面框架。

## 实施步骤

- [x] `format_context_k` 与状态/上下文对调测试。
- [x] 审批卡上下 margin 改为 1。
- [x] 回写阶段七规格中的状态带描述。

## 验证

```bash
uv run pytest tests/presentation/test_footer_status.py tests/terminal/test_status_line.py tests/terminal/test_app.py tests/terminal/test_approval.py tests/e2e/test_phase_7_product_matrix.py -q
git diff --check
```

## 验证证据

- 2026-09-17：`test_footer_status`、`test_status_line`、`test_app`、`test_approval`、`test_phase_7_product_matrix` 共 `50 passed`；`ruff` 通过。
- 待用户 Terminal.app 确认底栏与审批卡间距。

## 未决

- 待用户 Terminal.app 确认底栏与审批卡间距。
- 发现 42、50 仍待复验。
- 未收到「CLI 版本达到预期，可以封存」。
