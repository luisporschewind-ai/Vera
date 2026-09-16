# 任务 0045：走查发现 43（无效工具参数不得杀死 Run）

> 供主实现 Agent 执行：阶段七 Terminal.app 继续编辑路径上，截断/非法 tool JSON 应回写 tool 错误并让模型重试。不新开规格，不开始阶段八。

**状态：** In progress
**执行就绪：** 是；任务 0044 已 Done
**分支：** `phase-7/0041-product-acceptance`
**依赖：** 任务 0041 自动门禁、任务 0044
**规格：** [阶段七 CLI 体验收口](../specs/2026-09-13-cli-experience-and-personal-dogfood.md)

## 背景

用户 2026-09-16 在原生 Terminal.app / VeraTestDemo 用 `vera -c` 后续输入「新建第五页并从第四页接入跳转」。

任务失败 `model_error`，诊断 `provider_invalid_response · provider returned invalid tool arguments`。无工作区副作用。这是流式拼接大 `propose_changeset` JSON 时参数截断后，适配器把解析失败当成整轮供应商错误。

## 目标与边界

- 工具名齐全但参数不是 JSON 对象时，保留 `ModelToolCall` 并标记 `parse_error=invalid_tool_arguments`。
- Runtime 必须带 `call_id` 写回 `role=tool`，不得 `run.failed` / `model_error`。
- 缺工具名仍按任务 0010 抛 `INVALID_RESPONSE`。
- 不放宽审批、不关闭 thinking、不读取真实 Key、不引入桌面框架。

## 实施步骤

- [x] `decode_tool_arguments`：截断 JSON、数组、非对象 → 空 dict + `invalid_tool_arguments`。
- [x] 流式聚合与 OpenAI 兼容适配器共用该解析；缺 name 仍失败。
- [x] `_execute_tool` 在 propose/registry 前 `_reject_tool`。
- [x] 失败矩阵：非法参数后模型可再提完整 Change Set，thinking 轮次的 `tool_calls`/`reasoning_content` 仍保留。

## 验证

```bash
uv run pytest tests/models/test_tool_arguments.py tests/models/test_streaming.py tests/models/test_openai_compatible.py tests/runtime/test_safe_editing_flow.py -q
git diff --check
```

## 验证证据

- 局部测试：`tests/models/test_tool_arguments.py`、`test_streaming.py`、`test_openai_compatible.py`、`tests/runtime/test_safe_editing_flow.py`、`tests/presentation/test_errors.py` 共 44 passed。
- `ruff check` / `ruff format --check` / `mypy src` / `git diff --check` 通过。
- 真实 Terminal.app 复验待用户：同一句「新建第五页并从第四页接入跳转」。

## 未决

- 主路径其余步骤（`/runs`）和 20 次 dogfood 仍归 0041。
- 未收到「CLI 版本达到预期，可以封存」。
