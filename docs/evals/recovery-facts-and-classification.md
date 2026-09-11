# 恢复事实与只读分类验收记录

更新日期：2026-09-11

## 结论

任务 0005 离线实现、完整非 live 验收、静态检查和包构建通过。Vera 现在会在稳定边界原子写入私有 `RecoverySnapshot`，并在新进程中只读扫描 Journal、Checkpoint 与工作区哈希，产生六类确定恢复分类。CLI 的 `/recover` 与 `vera recover list|show` 只消费 `InspectRecovery` / `recovery.detected`，不写工作区、不执行命令、不调用模型。

自动验收没有运行 live 测试，没有读取或使用用户真实 DeepSeek/GLM Key，也没有修改 `/Users/admin/Desktop/VeraTestDemo`。

## 规格验收对照

| # | 标准 | 结果 |
|---|---|---|
| 1 | Snapshot 使用同目录临时文件、flush、fsync、`os.replace`，POSIX 文件 `0600` | 通过（持久化测试） |
| 2 | 替换失败时旧正式文件逐字节不变，临时文件被删除 | 通过 |
| 3 | 损坏 Snapshot 返回稳定 `invalid_snapshot` | 通过 |
| 4 | STARTED / 空证据 → `safe_to_abandon` | 通过 |
| 5 | 待审批且全部 BEFORE → `resumable_approval` | 通过 |
| 6 | 验证阶段全部 AFTER 且非 in-flight → `resumable_verification` | 通过 |
| 7 | Checkpoint 后 BEFORE+AFTER 混合 → `recoverable_partial_apply` | 通过 |
| 8 | UNKNOWN、身份不符、工作区缺失、Checkpoint 缺失、in-flight → `manual_required` | 通过 |
| 9 | 无 Snapshot 的未终止阶段一 run → `legacy_not_resumable` | 通过 |
| 10 | 终止 run 与 compaction run 不进入待恢复列表 | 通过 |
| 11 | 单个损坏 run 隔离，不阻止其他 run | 通过 |
| 12 | 扫描、`InspectRecovery`、`/recover` 不写工作区、不调模型 | 通过 |
| 13 | Snapshot 写入失败不进入下一副作用，并记录 `run.failed(reason="snapshot_write_failed")` | 通过 |
| 14 | 公共 `schema_version` 仍为 1 | 通过 |
| 15 | 完整非 live、Ruff、格式、Mypy、构建、`git diff --check` | 通过 |

## 自动验证证据

- `uv run pytest -m "not live" --cov=vera --cov-report=term-missing`：171 项通过、2 项 live 排除。
- 覆盖率：91%。
- `uv run ruff check src tests`：通过。
- `uv run ruff format --check src tests`：通过。
- `uv run mypy src`：通过。
- `uv build`：通过，生成 `dist/vera_agent-0.1.0.tar.gz` 与 `dist/vera_agent-0.1.0-py3-none-any.whl`。
- `git diff --check`：通过。
- 非 live fixture 继续清除供应商变量，并把 `VERA_PROVIDER_ENV_FILE` 指向测试隔离路径。

## 已知限制

- 本任务只做只读分类与报告，不执行 `ResumeRun`、放弃、部分写入恢复或验证续跑；这些属于任务 0006。
- 版本化 Codec、legacy/future Fixture 与非破坏磁盘迁移属于任务 0007。
- 统一 PolicyEngine 与审批指纹属于任务 0008。
- ModelAdapter 能力、错误分类、有限重试和阶段二 12 条退出条件总验收属于任务 0009。
- 退出后普通对话恢复、长期记忆、桌面客户端仍不在范围内。
