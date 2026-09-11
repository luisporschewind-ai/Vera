# Vera 状态

**更新日期：** 2026-09-11
**当前阶段：** 阶段 2——恢复、兼容性与策略扩展（任务 0005–0007 已完成，待执行 0008–0009）
**仓库状态：** 任务 0005–0007 已本地合并到 `main`；暂无远程仓库，未推送。

## 已验证基线

- 工作目录：`/Users/admin/Vera`
- 当前分支：`main`
- Agent 实现：任务 0002–0007 的 Core、Runtime、恢复、版本化 Codec 与内部 CLI
- 依赖清单：`pyproject.toml`、`.python-version`、`uv.lock`

## 已完成任务

- [任务 0001：建立 Vera 仓库](tasks/0001-bootstrap-repository.md)
- 任务 0002–0004：Core / CLI / 会话
- [任务 0005：恢复事实与只读分类](tasks/0005-recovery-facts-and-classification.md)
- [任务 0006：安全续跑与部分写入恢复](tasks/0006-safe-run-resume-and-recovery.md)
- [任务 0007：版本化 Codec 与兼容迁移](tasks/0007-versioned-codecs-and-migration.md)

## 活动任务

- [阶段二执行顺序](tasks/phase-2-execution-order.md)
- 后续依次执行任务 0008–0009

## 最近验证

- 任务 0007：`ContractCodec` / `JournalCodec` / `SnapshotCodec`、`RunManifest`、legacy fixture、损坏/未来隔离、`vera state inspect|migrate`
- 任务 0007 离线验收：235 项非 live 测试通过、2 项 live 排除，覆盖率 90%；Ruff、格式、Mypy、包构建通过
- 凭据边界：未读取真实 DeepSeek/GLM Key，未运行 live
- Git：已本地合并 `feature/versioned-state-codecs`，未推送（无 remote）
- 验收记录：[版本化 Codec 与兼容迁移](evals/versioned-codecs-and-migration.md)

## 已接受方向

- 正式开发只在本仓库进行。
- `/Users/admin/Coding-harness` 保持只读。
- Core-first、内部 CLI-first、桌面 later。
- 阶段二采用确定性恢复、版本化 Codec、统一 PolicyEngine 和 ModelAdapter 有限重试设计。

## 仍待决策

- 更广泛的供应商行为和真实供应商评测频率
- 评测语料与阈值
- 桌面框架
- 许可证与发布策略
- 退出后会话恢复与长期记忆

## 下一检查点

从最新 `main` 创建 `feature/unified-policy-engine`，执行任务 0008。阶段二 12 条退出条件证据齐备前，不开始阶段三实现。
