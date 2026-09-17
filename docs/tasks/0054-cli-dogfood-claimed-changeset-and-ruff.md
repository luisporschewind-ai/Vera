# 任务 0054：走查发现 51–52（虚构审批卡与验证命令找不到）

> 供主实现 Agent 执行：阶段七 Python 工程 dogfood。不开始阶段八。

**状态：** Done
**执行就绪：** 否；本任务已 Done
**分支：** `phase-7/0041-product-acceptance`
**依赖：** 任务 0041 自动门禁
**规格：** [阶段七 CLI 体验收口](../specs/2026-09-13-cli-experience-and-personal-dogfood.md)、[验证产物隔离](../specs/2026-09-14-verification-artifact-isolation.md)

## 背景

用户 2026-09-17 在 Python 示例工程请求添加网址分析：

1. Vera 文本写「已形成 Change Set，等待你审批」，任务以 `responded` 结束，时间线没有审批卡。用户回复「同意这个取舍」后才真正 `propose_changeset`。
2. 变更与 `ruff check webstats.py --no-cache` 两次审批通过后，验证失败 `[Errno 2] No such file or directory: 'ruff'`。工作区是标准库示例，验证子进程 PATH 不含 `ruff`。

## 目标与边界

- 纯文本声称已形成 Change Set / 等待审批时，催促一次去调用 `propose_changeset`；未调用该工具不得让用户以为审批卡已出现。
- Python 生态验证命令在规划阶段必须能解析到工作区虚拟环境或 PATH 上的可执行文件；缺失时回写 `verification_executable_missing`，不弹出审批卡。
- 验证子进程 PATH 前置工作区 `.venv/bin`（或 `venv/bin`）。
- 不改审批语义、不读取真实 Key、不引入桌面框架。

## 实施步骤

- [x] 系统提示禁止虚构 Change Set / 审批卡。
- [x] 文本声称等待审批时催促一次 `propose_changeset`。
- [x] 规划期拒绝找不到的 `ruff`/`pytest`/`mypy`；运行期把工作区虚拟环境加入 PATH。

## 验证

```bash
uv run pytest tests/runtime/test_conversation_response.py tests/runtime/test_untrusted_context.py tests/runtime/test_safe_editing_flow.py tests/verification/test_artifacts.py tests/verification/test_runner.py -q
git diff --check
```

## 验证证据

- 2026-09-17：`test_conversation_response`、`test_untrusted_context`、`test_safe_editing_flow`、`test_artifacts`、`test_runner` 共 `77 passed`；`ruff`/`mypy` 对改动模块通过。
- 用户 2026-09-17 在原生 Terminal.app 复验 Python 示例「添加网址分析」：会出审批卡；缺失 `ruff` 不再两次同意后才失败。发现 51、52 关闭。

## 未决

- 发现 42、50 仍待复验。
- 20 次 dogfood 仍归 0041。
- 未收到「CLI 版本达到预期，可以封存」。
