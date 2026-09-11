# 安全续跑与部分写入恢复验收记录

更新日期：2026-09-11

## 结论

任务 0006 离线实现、完整非 live 验收、静态检查和包构建通过。Vera 现在可以在新进程中重新分类后续跑 Change Set/验证审批、继续未完成验证、放弃无副作用 run，并在独立 `kind=recovery` 审批后按精确哈希恢复部分写入。Resume 不调用 ModelAdapter，不恢复普通对话。

自动验收没有运行 live 测试，没有读取或使用用户真实 DeepSeek/GLM Key，也没有修改 `/Users/admin/Desktop/VeraTestDemo`。

## 规格验收对照

| # | 标准 | 结果 |
|---|---|---|
| 1 | 跨 Runtime 续跑 Change Set 审批，审批 ID 不变，只创建一次 Checkpoint、只应用一次 | 通过 |
| 2 | 跨 Runtime 从 `verification_index` 继续，不重跑已完成命令，不调模型 | 通过 |
| 3 | `verification_in_flight` 与哈希 UNKNOWN 不续跑，进入人工处理 | 通过 |
| 4 | 部分写入只把 AFTER 恢复为 BEFORE，BEFORE 文件不动 | 通过 |
| 5 | 恢复前哈希变化、Checkpoint blob 损坏、writer 失败时零成功声明，不整体误写 | 通过 |
| 6 | 恢复计划需独立审批；错误 `recovery_hash` 拒绝；拒绝不写文件且 run 仍可扫描 | 通过 |
| 7 | Abandon 只接受 `allowed_actions` 含 `abandon` 的分类 | 通过 |
| 8 | CLI `/resume` `/abandon` 与 `vera recover resume/abandon --json` | 通过 |
| 9 | 非交互恢复审批安全取消；退出码 0/2/3/4/5 | 通过 |
| 10 | 跨实例 failpoint：审批、Checkpoint、每文件应用、applied、verification started/completed | 通过 |
| 11 | 重复 Resume/Abandon/ResolveApproval 不重复文件副作用 | 通过 |
| 12 | 公共 `schema_version` 仍为 1 | 通过 |

## 自动验证证据

- `UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" --cov=vera --cov-report=term-missing`：210 passed，2 deselected（live）。
- 覆盖率：90%。
- Ruff check / format --check、Mypy、`uv build`、`git diff --check`：全部通过。
- 非 live fixture 继续清除供应商变量；未读取真实 DeepSeek/GLM Key。


## 已知限制与解释

- 拒绝部分恢复计划时不把 Journal 标为 `run.cancelled` 终态，否则混合写入会从扫描列表消失；拒绝后仍为 `recoverable_partial_apply`，可再次 Resume。
- 非交互取消 `kind=recovery` 审批只丢弃内存 run，不写终态事件，退出码 5。
- Codec/迁移属于任务 0007；PolicyEngine 属于任务 0008；ModelAdapter 韧性与阶段二 12 条退出条件总验收属于任务 0009。
- 退出后普通对话恢复、长期记忆、桌面客户端仍不在范围内。
