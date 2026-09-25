# 任务 0082：模型把工具调用写进正文（DSML 标记泄漏）

**状态：** Done
**来源：** 2026-09-25 用户在 Terminal.app 以 `deepseek-flash` 对 `VeraTestDemo` 提问，回答末尾出现大段 `<｜DSML｜function_calls>`、`<｜DSML｜invoke name="propose_changeset">`、`<｜DSML｜parameter …>` 与转义 `\n`，看起来像乱码，随后显示 `✓ Done`。
**规格：** [会话 CLI](../specs/2026-09-11-conversational-cli-and-session-status.md)；[ADR-0008](../decisions/ADR-0008-model-capabilities-and-errors.md)

## 背景

模型本想调用 `propose_changeset` 创建根目录 `VERA.md`，但供应商没有把模型内部的工具调用标记解析成 `tool_calls`，标记原样落进了 `content`。OpenAI 兼容适配器把 `content` 当普通文本流式上屏；Runtime 看到"无工具调用、有文本"，按 `responded` 完成。

后果：

- 用户看到的是原始标记，不是回答；
- 提案工具从未执行，没有 Diff、没有审批，却显示 Done；
- 泄漏正文（含整份拟写文件）进入对话上下文，后续轮次可能继续模仿。

## 目标与边界

- 适配器流式输出遇到泄漏标记后不再推送文本增量；标记之前的正常文字照常显示。累积的完整文本仍交给 Runtime 判断。
- Runtime 在"无工具调用且正文含泄漏标记"时，不产生 `assistant.message`、不按 `responded` 完成；上下文里该轮助手正文只保留标记前的文字，保留 `reasoning_content`，并回写一次纠正提示，让模型经函数调用接口重新发起。
- 纠正后仍泄漏，以 `leaked_tool_call_markup` 失败，失败文案说明工具没有执行。
- 工具上限收尾与 `/compact` 两条无工具路径：只采用标记前的文字；为空时按原有失败码失败。
- 不从正文解析并执行泄漏的调用，不新增 Event 类型，不改审批、Policy 或写入边界。

识别的标记：`<｜DSML｜`、`</｜DSML｜`、`<|DSML|`、`</|DSML|`、`<｜tool▁calls▁begin｜>`、`<｜tool▁call▁begin｜>`。

## 实施步骤

- [x] `vera.models.leaked_markup`：标记识别与流式过滤（跨 chunk 切分的标记前缀先暂存）。
- [x] OpenAI 兼容适配器流式路径接入过滤。
- [x] Runtime 主循环、工具上限收尾、`/compact` 接入识别与一次纠正。
- [x] 失败文案 `leaked_tool_call_markup`。
- [x] 规格补充泄漏标记的完成语义。
- [x] 回归测试：识别、跨 chunk 过滤、适配器不推送标记、纠正后提案进入审批、纠正后纯文本回答、纠正后仍泄漏失败、`/compact` 丢弃标记。

## 验证

```bash
uv run pytest tests/models/test_leaked_markup.py tests/models/test_openai_stream.py tests/runtime/test_conversation_response.py tests/runtime/test_context_compaction.py tests/runtime/test_limits.py -q
uv run ruff check src tests && uv run ruff format --check src tests
uv run mypy src
git diff --check
```

## 验证证据

- 2026-09-25：上述聚焦命令 `31 passed`；扩展到 `tests/models`、`tests/runtime`、`tests/presentation`、`tests/cli/test_session.py`、`tests/evals` 共 `416 passed`。`ruff check`、`ruff format --check`、`mypy src`（184 个源文件）通过。未运行全量测试，未用真实 Provider 复现。
- 2026-09-25：用户在 Terminal.app 复验后确认"没问题，都已验证"，任务关闭。
- 提交：`8ad463d`（未推送）。

## 未决

- 泄漏属供应商偶发行为；日常使用中如再出现 `leaked_tool_call_markup` 失败或残留标记，另开任务跟进。
