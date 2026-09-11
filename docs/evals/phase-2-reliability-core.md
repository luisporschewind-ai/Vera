# ModelAdapter 韧性与阶段二验收记录

更新日期：2026-09-11

## 结论

任务 0009 与阶段二收口完成。ModelAdapter 具备能力声明、稳定错误码、最多 2 次有限重试与 usage/request_id 证据。阶段二 12 条退出条件均有离线证据。

未运行 `tests/live`，未读取真实 DeepSeek/GLM Key，未修改 `/Users/admin/Desktop/VeraTestDemo`，未引入桌面框架。

## 阶段二 12 条退出条件对照

| # | 条件 | 证据 |
|---|---|---|
| 1 | 中断点确定分类 | 0005/0006 recovery + crash E2E |
| 2 | 审批/验证安全续跑 | 0006 resume 测试 |
| 3 | 部分写入哈希+审批恢复 | 0006 partial recovery |
| 4 | 未知状态停止 | classifier/manual_required |
| 5 | 幂等扫描/resume | crash + resume 测试 |
| 6 | legacy 可读、未来拒绝 | 0007 legacy/future fixtures |
| 7 | 统一策略与审批失效 | 0008 PolicyEngine |
| 8 | DeepSeek/GLM Fixture conformance | `tests/models/test_adapter_conformance.py` |
| 9 | 瞬时重试不重复本地副作用 | `tests/runtime/test_model_resilience.py` |
| 10 | CLI 只消费 Command/Event | CLI JSON 测试族 |
| 11 | 非 live + 静态 + 构建 | 下方证据 |
| 12 | 无真实 Key / 无真实验收工程 / 无桌面 | 本记录声明 |

## 自动验证证据

- `pytest -m "not live"`：268 passed，2 deselected；覆盖率 90%。
- Ruff / format / Mypy / `uv build` / `git diff --check`：合并前通过。
