# 统一 PolicyEngine 与审批指纹验收记录

更新日期：2026-09-11

## 结论

任务 0008 离线实现通过。Vera 现在以 `PolicyEngine` 统一命令/路径/工具判定，审批绑定 `workspace_identity` 与 `policy_hash`；策略变化使待审批失效。`CommandPolicy` 成为兼容适配器。`/permissions` 展示策略版本与 hash 前缀。

未运行 live，未读取真实 DeepSeek/GLM Key。

## 规格验收对照

| # | 标准 | 结果 |
|---|---|---|
| 1 | 决策矩阵：特权/Shell/删除硬禁止，用户前缀允许，内置安全允许，其余审批 | 通过 |
| 2 | `policy_hash` 稳定且不含展示文案/秘密 | 通过 |
| 3 | 敏感路径 deny；WorkspacePaths 纵深逃逸防护保留 | 通过 |
| 4 | 策略变化 → `approval.invalidated`，工作区不变 | 通过 |
| 5 | 权限展示含 policy version / hash 前缀 / hard denies | 通过 |
| 6 | 现有命令策略回归保持 | 通过 |

## 自动验证证据

- `pytest -m "not live"`：247 passed，2 deselected；覆盖率 90%。
- Ruff / Mypy / build：见合并前检查。

## 已知限制

- 工具/写入路径判定已入引擎，但部分执行组件仍保留独立边界复核（预期纵深）。
- ModelAdapter 韧性与阶段二 12 条总验收属于任务 0009。
