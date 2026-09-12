# 任务 0022：状态、恢复与长会话加固

> 供 Cursor 执行：按 `superpowers:executing-plans` 实施；不得以删除损坏状态或重建用户数据作为自动修复。

**状态：** Done
**执行就绪：** 任务 0021 合并后
**分支：** `phase-5/0022-state-recovery-long-run`
**依赖：** 任务 0021 已合并
**规格：** [阶段五 Core 加固](../specs/2026-09-12-core-security-and-reliability-hardening.md)

## 目标与边界

让 Journal、Snapshot、Manifest、Checkpoint 和恢复操作在中断、损坏、未知版本、权限/空间错误及重复命令下失败关闭；让长会话的上下文、Event 和终端投影保持有界且可取消。

不恢复退出后的自然语言对话，不增加数据库、向量存储或后台守护进程。

## 设计约束

- 恢复分类只读取持久事实，不读取旧进程内存或终端文本。
- 每个持久格式保留独立 `schema_version`；未知新版本拒绝，已知旧版本经显式 Codec 迁移。
- Journal 只允许忽略可证明为未提交的尾记录；中间损坏必须失败关闭。
- Resume、ResolveApproval、Cancel、Rollback 使用 operation/idempotency key，重放返回已有结果而非再次副作用。
- 内存上限按事实定义：保留最近结构化摘要和权威持久引用，不能直接丢弃未决审批、Diff 或错误。

## 实施步骤

### 1. 损坏状态与版本矩阵

**修改：**

- `src/vera/persistence/journal.py`
- `src/vera/persistence/recovery_snapshot.py`
- `src/vera/persistence/run_manifest.py`
- `src/vera/persistence/journal_codec.py`
- `src/vera/persistence/snapshot_codec.py`
- `src/vera/persistence/migration.py`
- `tests/persistence/test_journal.py`
- `tests/persistence/test_recovery_snapshot.py`
- `tests/persistence/test_run_manifest.py`
- `tests/persistence/test_journal_codec.py`
- `tests/persistence/test_snapshot_codec.py`
- `tests/persistence/test_migration.py`

**测试先行：**

1. 截断尾记录、中间损坏、校验错误、未知版本、缺字段、额外危险字段分别有稳定分类。
2. 只读目录、写入中断和模拟 ENOSPC 不产生成功 manifest 或覆盖旧状态。
3. 迁移失败保留原始字节和可执行建议，不自动删除。
4. 先运行聚焦测试并记录预期失败原因，再实现共享 decode/validation/error mapping。

### 2. 全生命周期中断与幂等

**修改：**

- `src/vera/recovery/classifier.py`
- `src/vera/recovery/coordinator.py`
- `src/vera/recovery/planner.py`
- `src/vera/recovery/resume.py`
- `src/vera/runtime/engine.py`
- `tests/recovery/test_classifier.py`
- `tests/recovery/test_coordinator.py`
- `tests/runtime/test_recovery_resume.py`
- `tests/runtime/test_recovery_snapshots.py`

**测试先行：** 覆盖运行前、等待审批、部分写入、验证中、验证后、回滚中和 Journal append 中断；对 Resume、ResolveApproval、Cancel、Rollback 各重放两次，断言文件 hash、事件数和命令次数不增加。

**最小实现：** 增加持久 `OperationReceipt`（operation_id、input_hash、terminal_result、effect_refs），恢复入口先查询回执，再决定是否执行。

### 3. 权限、磁盘与编码错误

**修改：**

- `src/vera/workspace/apply.py`
- `src/vera/workspace/checkpoint.py`
- `src/vera/runtime/engine.py`
- `src/vera/contracts/errors.py`
- `tests/workspace/test_apply.py`
- `tests/workspace/test_checkpoint.py`
- `tests/runtime/test_safe_editing_flow.py`

**测试先行：** 以 monkeypatch/fake filesystem 注入 EACCES、EROFS、ENOSPC、占用、无效 UTF-8 和 fsync/rename 失败；每个结果必须明确是否写入、是否可回滚、下一步是什么，且不能发出 completed。

### 4. 长会话预算与有界投影

**修改：**

- `src/vera/runtime/context.py`
- `src/vera/runtime/engine.py`
- `src/vera/session/conversation.py`
- `src/vera/presentation/projector.py`
- `tests/runtime/test_context_compaction.py`
- `tests/session/test_conversation.py`
- `tests/presentation/test_projector.py`
- 新增 `tests/e2e/test_long_session.py`

**测试先行：**

1. 生成 500 次只读工具、100 次对话轮次和 10,000 行截断输出，断言投影与上下文不线性保留全文。
2. 未决审批、最新 Diff、失败与恢复事实在压缩后仍可定位。
3. 压缩期间取消只产生一次 cancel，下一轮上下文不包含被裁剪秘密或控制序列。

**最小实现：** 为上下文和投影建立显式 item/byte budget、确定性摘要引用和 `truncated` 元数据；不调用 Provider 生成摘要。

## 验证与提交

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/persistence tests/recovery tests/runtime tests/session tests/presentation tests/e2e/test_long_session.py -q
```

随后运行[阶段五共同门禁](phase-5-execution-order.md)。检查没有自动删除私有状态、吞掉持久错误或从 UI 文本推断恢复。更新任务记录后提交：

```bash
git commit -m "feat: harden recovery and long-running sessions"
```

## 验收标准

- 所有支持阶段均有中断和重放测试，重复操作不重复副作用。
- 损坏、未知版本、权限和磁盘错误均失败关闭并保留原数据。
- 长会话内存与上下文有明确上限，权威未决事实不丢失。
- 四类客户端仍消费同一 Runtime 事件和恢复结果。

## 验证结果

- 日期：2026-09-12
- 额外聚焦：`pytest tests/persistence tests/recovery tests/runtime tests/session tests/presentation tests/e2e/test_long_session.py` → 202 passed
- 完整非 live：611 passed / 2 deselected；Ruff、format、Mypy、`uv build`、`git diff --check` 通过
- 未读取真实 Provider Key，未运行 live，未修改用户工程，未引入桌面框架

## 未决事项

- 跨轮次只保留 changeset 路径与 ID 等 `[facts]` 引用，不回放 unified diff 正文
- 三类真实工程与 20 次 dogfood 属于任务 0024，本任务不关闭阶段五
