# 状态、恢复与长会话加固验收记录

更新日期：2026-09-12

## 结论

任务 0022 离线实现通过。Journal 只忽略可证明未提交的尾记录，中间损坏、校验失败、未知版本、缺字段和额外危险字段失败关闭并给出可执行建议。Resume / ResolveApproval / Cancel / Rollback 通过持久 `OperationReceipt` 重放，不重复副作用。磁盘/权限/编码错误不会发出 `run.completed`。长会话上下文与终端投影有明确 item/byte 上限，压缩后仍保留 changeset 路径引用、未决审批、Diff 与错误。

未运行 live，未读取真实 DeepSeek/GLM Key，未修改用户工程。不恢复退出后的自然语言对话，未引入数据库或后台守护进程。

## 规格验收对照

| # | 标准 | 结果 |
|---|---|---|
| 1 | 中断后只根据持久事实分类，不读旧进程内存或终端文本 | 通过 |
| 2 | 截断尾记录可忽略；中间损坏、未知版本失败关闭 | 通过 |
| 3 | 只读/ENOSPC/写入中断不覆盖旧状态、不产生成功 manifest | 通过 |
| 4 | 迁移失败保留原始字节和人工建议，不自动删除 | 通过 |
| 5 | Resume / ResolveApproval / Cancel / Rollback 重放无二次副作用 | 通过 |
| 6 | 权限、磁盘、编码错误明确是否写入、是否可回滚、下一步，且不发出 completed | 通过 |
| 7 | 长会话上下文与投影有界；未决审批、最新 Diff、失败事实可定位 | 通过 |
| 8 | 压缩不调用 Provider 生成摘要；下一轮不含被裁剪秘密或控制序列 | 通过 |

## 自动验证证据

- 任务聚焦：`tests/persistence tests/recovery tests/runtime tests/session tests/presentation tests/e2e/test_long_session.py` 202 passed
- `pytest -m "not live"`：611 passed，2 deselected
- Ruff / format / Mypy / `uv build` / `git diff --check`：通过

## 已知限制

- 会话跨轮次只保留结构化 `[facts]` 引用（run / changeset / 路径 / 操作），不回放 unified diff 正文
- Journal 无独立逐行 checksum 字段；连续性与 payload 校验作为 `checksum_mismatch`
- 阶段五三类真实工程与 20 次 dogfood 仍待任务 0024
