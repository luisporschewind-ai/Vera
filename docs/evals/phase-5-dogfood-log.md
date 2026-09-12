# 阶段五 dogfood 记录

**状态：** 模板已建立，真实 20 次记录尚未由用户填写  
**校验：** `vera eval dogfood-check <path> --json`

本文件只说明字段。真实记录应保存为独立 JSON（不要写入源码正文、完整请求、Key/Token 或 Diff）。

## 字段

| 字段 | 含义 |
|---|---|
| `index` | 从 1 递增的序号 |
| `recorded_at` | UTC 时间 |
| `project_kind` | `swift` / `python` / `node` |
| `workflow` | 工作流短名，如 `readonly-then-edit` |
| `result` | `pass` / `fail` / `blocked` |
| `failure_class` | 失败时必填的稳定分类 |
| `recovery` | 恢复方式短名 |
| `metrics` | 仅聚合数字或短标签 |

自动测试只验证格式，并提供 1 条离线示例。`user_completed_20` 在校验摘要中恒为 `false`，除非用户提交通过校验的 20 条真实记录后由人工改写本页。

## 当前结论

尚未达到「20 次连续内部任务」退出条件。
