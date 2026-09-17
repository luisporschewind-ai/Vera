# 任务 0044：走查发现 38–41（propose 回写与 sticky）

> 供主实现 Agent 执行：阶段七 Terminal.app 主路径走查的 High/Medium 修正。不新开规格，不开始阶段八。

**状态：** Done
**执行就绪：** 否；本任务已 Done
**分支：** `phase-7/0041-product-acceptance`
**依赖：** 任务 0041 自动门禁
**规格：** [阶段七 CLI 体验收口](../specs/2026-09-13-cli-experience-and-personal-dogfood.md)、[验证产物隔离](../specs/2026-09-14-verification-artifact-isolation.md)

## 背景

用户 2026-09-16 在原生 Terminal.app / VeraTestDemo 走查：给第四个页面加测试按钮。

1. 两次提出变更失败 `verification_artifact_isolation_unavailable`，随后 `model_error`：`provider_request_invalid · HTTP 400 · The reasoning_content in the thinking mode must be passed back to the API`。
2. 用户消息 sticky 不贴在标题下。
3. 缩放右侧残留。
4. 会话上下文条保持 0%。
5. 工程根没有长出 `build/`（通过）。

## 目标与边界

- propose 失败必须带 `call_id` 写回 `role=tool`，让模型看到隔离错误并重试；不得拆掉 thinking 轮次的 `tool_calls`/`reasoning_content`。
- sticky 进入正常顶部布局，不覆盖时间线，宽度不超过屏幕。
- 会话预算占用大于 0 时不显示 `0%`。
- 不放宽审批、不关闭 thinking、不读取真实 Key、不引入桌面框架。

## 实施步骤

- [x] 失败矩阵：无隔离 Profile 的 verification 拒绝后，Journal 有 tool 结果，下一轮请求仍保留 assistant.tool_calls 与 reasoning_content，并可再次提出无验证的 Change Set。
- [x] sticky 去掉 overlay/`width: 100%` 加左右 margin；贴在 header 下方；resize 重绘。
- [x] 上下文条：`used > 0` 且百分比为 0 时显示 `<1%`，进度条至少 1 格。

## 验证

```bash
uv run pytest tests/runtime/test_safe_editing_flow.py tests/presentation/test_footer_status.py tests/terminal/test_user_prompt_anchor.py -q
git diff --check
```

## 验证证据

- 局部测试：`test_safe_editing_flow`、`test_footer_status`、`test_user_prompt_anchor`、`test_scrolling`、phase-7 产品矩阵 38 passed（`b42ed76`）。
- 2026-09-16 用户在原生 Terminal.app / VeraTestDemo 对同一小改动复验通过：可进入审批路径，sticky 贴标题下，缩放无右侧残影，发现 38–41 关闭。

## 未决

- 主路径其余步骤（退出/`-c`/旧 run）和 20 次 dogfood 仍归 0041。
- 未收到「CLI 版本达到预期，可以封存」。
