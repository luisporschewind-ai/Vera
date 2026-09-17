# 任务 0050：走查发现 49（取消后 Error 与 Worker 失败）

> 供主实现 Agent 执行：阶段七取消路径。不开始阶段八。

**状态：** Done
**执行就绪：** 否；本任务已 Done
**分支：** `phase-7/0041-product-acceptance`
**依赖：** 任务 0049
**规格：** [CLI 产品化](../specs/2026-09-12-cli-productization-and-polish.md)

## 背景

用户 2026-09-17 在 Terminal.app 用 Esc 取消「解释第四个 VC」后看到：已取消、`queued: 是`、Error「当前有运行中的任务」、底栏 `Worker 失败`。取消成功后，原 StartRun 线程仍在模型请求中；CancelRun 把状态机打到 `cancelled` 后，原循环仍尝试 `generating`/`completed`，触发 `IllegalTransition`。同时取消清掉 `active_run_id` 后，残留事件又把它写回去，排队刷新被当成 `run_active`。

## 目标与边界

- 运行中取消后，原驱动在 `CANCELLED` 停住，不抛、不发 `run.completed`。
- 取消线程结束后，旧事件不得把 `active_run_id` 复活。
- 排队刷新不得因此报 `run_active`。
- 不改审批默认值，不读取真实 Key，不引入桌面框架。

## 实施步骤

- [x] Runtime `_drive` 把 `CANCELLED` 视为停止态。
- [x] Controller `_drive_epoch`：取消结束后丢弃旧流。
- [x] 并发取消与排队刷新测试。

## 验证

```bash
uv run pytest tests/runtime/test_cancel_in_flight.py tests/session/test_controller.py tests/runtime/test_safe_editing_flow.py -q
git diff --check
```

## 验证证据

- 2026-09-17：`tests/runtime/test_cancel_in_flight.py`、`tests/session/test_controller.py`、`tests/runtime/test_safe_editing_flow.py` 等 `49 passed`；`ruff`/`mypy`/`git diff --check` 通过。
- 用户 2026-09-17 在原生 Terminal.app 复验：Esc 取消后不再出现 Error / Worker 失败。发现 49 关闭。

## 未决

- 发现 42 Low：Markdown 路径折行。
- 20 次 dogfood 仍归 0041。
- 未收到「CLI 版本达到预期，可以封存」。
