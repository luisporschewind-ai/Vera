# 验收：恢复场景、指标与确定性

**规格：** [2026-09-12-evals-and-internal-readiness](../specs/2026-09-12-evals-and-internal-readiness.md)
**任务：** [0017](../tasks/0017-eval-recovery-and-metrics.md)
**日期：** 2026-09-12
**结果：** Pass（非 live；未跑 `tests/live`；未读真实 DeepSeek/GLM Key；未修改 VeraTestDemo）

## 质量门禁

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

- 完整非 live：462 passed / 2 deselected；覆盖率 90%
- `tests/evals` 96 passed（含 failpoints、recovery scenarios、rollback、metrics、determinism）
- Ruff、格式、Mypy、`uv build`、`git diff --check` 通过
- 未运行 live，未读取供应商 Key
- Worker 子进程仍是生命周期/超时隔离，不是 OS 沙箱

## 恢复场景证据

| 场景 | classification | allowed_actions | 写入/副作用 | 测试 |
| --- | --- | --- | --- | --- |
| `resume-after-approval` | `resumable_approval` | 含 `resume` | `changeset.applied` 恰好 1 次；hello/extra 均为 after | `test_resume_after_approval_rebuilds_runtime_and_applies_once` |
| `restore-partial-apply` | `recoverable_partial_apply` | 含 `restore` | 先按路径序写入 `extra.txt`，审批恢复后回到 before 字节 | `test_restore_partial_apply_restores_before_bytes` |
| `in-flight-manual` | `manual_required` | 仅 `inspect` | 重启后无 `run.completed`、无 `recovery.resume_started` | `test_in_flight_verification_never_resumes` |
| `idempotent-resume` | `resumable_approval` | 含 `resume` | 第二次 `ResumeRun` 不增加 `changeset.applied` / `recovery.resume_started` | `test_idempotent_resume_has_no_duplicate_side_effects` |
| `rollback` | 不适用 | 不适用 | `rollback.completed`；hello.txt hash 回到 checkpoint before | `test_rollback_after_apply_restores_checkpoint_before_hash` |

错误 classification 立即停止后续 Resume：`test_wrong_classification_stops_without_resume`。

## 指标与确定性

| 项 | 证据 |
| --- | --- |
| 任一 `model.completed.usage` 缺失则聚合 usage 为 `null`，不当 0 | `tests/evals/test_metrics.py` |
| 负时间差标记 `invalid_event_time`，不填补当前时间 | `test_negative_duration_is_invalid` |
| Worker 写入 wall/event duration 与 usage，latency/cost 有值才记 PASS | `src/vera/evals/worker.py`、`test_latency_and_cost_pass_when_metrics_are_present` |
| canonical 只经 `EvalCodec.canonical_report()`，忽略 id/耗时，保留 event 顺序、hash、reason、usage | `tests/evals/test_determinism.py` |
| 恢复失败 reason：`classification_mismatch`、`allowed_actions_mismatch`、`duplicate_side_effect`、`unexpected_resume` | `tests/evals/test_recovery_scoring.py` |

Failpoint 只接受冻结枚举；Snapshot 先原子保存再抛 `SimulatedCrash`；第二个 Runtime 默认无 failpoint。

## 已知限制

- 内置 14 个冻结 case 仍由任务 0018 写入包内 corpus 并接到 `vera eval`
- `src/vera/evals/corpus.py` 与规格中的 `corpus/<case_id>/` 包路径冲突尚未在本任务解决，避免静默改架构
