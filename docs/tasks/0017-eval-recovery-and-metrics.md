# Vera Eval 恢复场景、指标与确定性实施计划

> **供 Agent 执行：** REQUIRED SUB-SKILL: 使用 `superpowers:executing-plans` 按 Task 顺序实施；只使用一个主实现 Agent，每个生产增量独立提交。

**状态：** Planned

**目标分支：** `feature/eval-recovery-metrics`

**目标：** 让离线评测覆盖重启恢复、部分写入、in-flight 人工处理、幂等续跑和回滚，并产出不虚构缺失数据的 latency/usage 与可重复 canonical 证据。

**架构：** EvalFailpoint 只在 eval RuntimeFactory 注入可控 SnapshotStore/FileWriter；RecoveryScenarioRunner 捕获模拟中断、丢弃旧 Runtime、从同一临时 state 创建新 Runtime 并继续发送既有恢复 Command。MetricsExtractor 与 CanonicalComparator 都是 Event 驱动纯组件。

**技术栈：** Python 3.12、Pydantic 2、Vera Recovery Contracts、pytest、Ruff、Mypy、uv。

**规格：** [阶段四评测与内部就绪](../specs/2026-09-12-evals-and-internal-readiness.md)

## 全局约束

- 依赖任务 0016 已合并。
- Failpoint 只能由 `model=fake` 且内置 corpus 的冻结 scenario 启用，不能接受任意 Python 路径或用户代码。
- 模拟中断后必须销毁旧 Runtime 引用，从持久 state/workspace 事实创建新 Runtime。
- 部分文本 Stream Frame、终端输出和内存 RunContext 不能参与恢复评分。
- usage 任一模型调用缺失时，聚合 usage 整体为 `null`，不能把缺失项当 0。
- 不运行 live、不读取真实 Key、不修改 `VeraTestDemo`。

---

### Task 1：提取 Event latency 与完整 usage

**文件：**

- Create: `src/vera/evals/metrics.py`
- Create: `tests/evals/test_metrics.py`
- Modify: `src/vera/evals/contracts.py`

**接口：**

- Produces: `MetricsExtractor.extract(events, wall_duration_seconds) -> EvalMetrics`
- Guarantee: usage 只有全部 `model.completed.usage` 存在时才聚合
- Guarantee: timestamp 不完整时保留 `None`，不使用当前时间填补

- [x] **Step 1：编写完整、部分缺失和无模型指标测试**

```python
def test_usage_is_null_when_any_model_event_lacks_usage() -> None:
    metrics = MetricsExtractor().extract(
        events=(model_completed(usage={"total_tokens": 5}), model_completed(usage=None)),
        wall_duration_seconds=0.25,
    )
    assert metrics.usage is None
    assert metrics.wall_duration_seconds == 0.25


def test_event_duration_uses_first_started_and_last_terminal() -> None:
    metrics = MetricsExtractor().extract(timestamped_completed_run(), 1.0)
    assert metrics.event_duration_seconds == 0.4
```

另测负时间差标记 `invalid_event_time`、多次重试 usage、无 terminal Event、输入/输出 token 任一缺失和数值溢出保护。

- [x] **Step 2：运行失败测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_metrics.py -v
```

- [x] **Step 3：实现纯指标提取**

保留 `wall_duration_seconds` 和 `event_duration_seconds` 两个字段。usage 使用现有 `ModelUsage` 形状；只有每个 `model.completed` 都含三个非负整数时才逐字段求和，否则整个字段为 `None`。reason code 随 metrics 一起返回给 Report 组装器。

- [x] **Step 4：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_metrics.py tests/runtime/test_model_resilience.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/evals tests/evals
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/evals/contracts.py src/vera/evals/metrics.py tests/evals/test_metrics.py docs/tasks/0017-eval-recovery-and-metrics.md
git commit -m "feat: extract evaluation latency and usage"
```

---

### Task 2：建立冻结 Failpoint 与 Runtime 重建

**文件：**

- Create: `src/vera/evals/failpoints.py`
- Modify: `src/vera/evals/runtime_factory.py`
- Create: `tests/evals/test_failpoints.py`

**接口：**

- Produces: `EvalFailpoint.AWAITING_CHANGESET_APPROVAL|AFTER_FIRST_WRITE|VERIFICATION_IN_FLIGHT|VERIFYING_STABLE`
- Produces: `EvalFailpointSnapshotStore`
- Produces: `EvalFailpointFileWriter`
- Produces: `EvalRuntimeFactory.create(..., failpoint: EvalFailpoint | None)`
- Guarantee: failpoint 触发 `SimulatedCrash`，不产生伪造 Core Event

- [x] **Step 1：编写每个稳定边界恰好触发一次的测试**

```python
@pytest.mark.parametrize(
    "point",
    [
        EvalFailpoint.AWAITING_CHANGESET_APPROVAL,
        EvalFailpoint.AFTER_FIRST_WRITE,
        EvalFailpoint.VERIFICATION_IN_FLIGHT,
        EvalFailpoint.VERIFYING_STABLE,
    ],
)
def test_eval_failpoint_is_one_shot(point, runtime_factory, loaded_recovery_case, isolated) -> None:
    runtime = runtime_factory.create(loaded_recovery_case, isolated, failpoint=point)
    with pytest.raises(SimulatedCrash):
        run_until_terminal_or_crash(runtime, loaded_recovery_case)
    assert runtime_factory.trigger_count(point) == 1
```

再测 standard case 不能配置 failpoint、未知字符串被 Codec 拒绝、第二个 Runtime 默认无 failpoint、部分写入只改第一个文件。

- [x] **Step 2：运行失败测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_failpoints.py -v
```

- [x] **Step 3：从现有 Recovery Snapshot 阶段映射 Failpoint**

复用 `RecoveryStage` 和 `AtomicFileWriter`，不复制恢复分类规则。SnapshotStore 必须先成功原子保存事实再抛模拟中断；FileWriter 在第二次 replace 前抛中断，形成 before/after 混合事实。Eval RuntimeFactory 只接受枚举，不接受 callback/import path。

- [x] **Step 4：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_failpoints.py tests/e2e/test_crash_recovery.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/evals tests/evals
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/evals/failpoints.py src/vera/evals/runtime_factory.py tests/evals/test_failpoints.py docs/tasks/0017-eval-recovery-and-metrics.md
git commit -m "feat: add bounded evaluation failpoints"
```

---

### Task 3：实现恢复、幂等与回滚 ScenarioRunner

**文件：**

- Create: `src/vera/evals/scenarios.py`
- Modify: `src/vera/evals/script_driver.py`
- Create: `tests/evals/test_recovery_scenarios.py`
- Create: `tests/evals/test_rollback_scenario.py`

**接口：**

- Produces: `RecoveryScenarioRunner.execute(loaded, isolated) -> EvalExecution`
- Produces: `RollbackScenarioRunner.execute(loaded, isolated) -> EvalExecution`
- Consumes: `InspectRecovery`、`ResumeRun`、`ResolveApproval`、`RollbackRun`

- [x] **Step 1：编写五种场景的 Command/Event 断言**

```python
def test_resume_after_approval_rebuilds_runtime_and_applies_once(scenario_runner, case) -> None:
    execution = scenario_runner.execute(case("resume-after-approval"), isolated_case())
    assert execution.runtime_instance_count == 2
    assert execution.event_types.count("changeset.applied") == 1
    assert "recovery.detected" in execution.event_types


def test_in_flight_verification_never_resumes(scenario_runner, case) -> None:
    execution = scenario_runner.execute(case("in-flight-manual"), isolated_case())
    assert execution.recovery_classification == "manual_required"
    assert "run.completed" not in execution.event_types_after_restart
```

再覆盖 `restore-partial-apply` 经 `kind=recovery` 审批恢复 before 字节、`idempotent-resume` 第二次 Resume 无副作用、`rollback-after-apply` 恢复 checkpoint before hash，以及错误分类立即停止。

- [x] **Step 2：运行失败测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_recovery_scenarios.py tests/evals/test_rollback_scenario.py -v
```

- [x] **Step 3：实现显式场景状态机**

每个场景把动作写成固定 `match EvalScenario` 分支，不从 JSON 读取任意 Command 类名。动态 run/approval/checkpoint ID 只能从刚产生的 Event 提取。模拟中断后 `del runtime`，再用相同 workspace/state、无 failpoint 的 Factory 创建新 Runtime。

- [x] **Step 4：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_recovery_scenarios.py tests/evals/test_rollback_scenario.py tests/recovery tests/runtime/test_recovery_resume.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/evals tests/evals
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/evals/scenarios.py src/vera/evals/script_driver.py tests/evals docs/tasks/0017-eval-recovery-and-metrics.md
git commit -m "feat: evaluate Vera recovery scenarios"
```

---

### Task 4：完成恢复评分与 canonical 重跑比较

**文件：**

- Modify: `src/vera/evals/scoring.py`
- Create: `src/vera/evals/determinism.py`
- Create: `tests/evals/test_recovery_scoring.py`
- Create: `tests/evals/test_determinism.py`

**接口：**

- Produces: recovery reason codes `classification_mismatch`、`allowed_actions_mismatch`、`duplicate_side_effect`、`unexpected_resume`
- Produces: `CanonicalComparator.compare(first, second) -> DeterminismResult`
- Produces: `DeterminismResult(equal, first, second, differences)`

- [x] **Step 1：编写恢复失败不能被平均和动态字段忽略测试**

```python
def test_recovery_failure_forces_case_failure(scorer) -> None:
    scores = scorer.score(recovery_case(), wrong_recovery_expectation(), *recovery_facts())
    assert score(scores, "recovery").status is DimensionStatus.FAIL


def test_canonical_comparison_ignores_ids_but_not_event_order(report_factory) -> None:
    first = report_factory(evaluation_id="a", run_ids=("run_a",), event_types=("run.started", "run.completed"))
    second = report_factory(evaluation_id="b", run_ids=("run_b",), event_types=("run.completed", "run.started"))
    assert CanonicalComparator().compare(first, second).equal is False
```

另测时间戳/临时路径忽略、文件 hash/reason code/usage 差异保留、case/suite 排序、重复副作用计数。

- [x] **Step 2：实现恢复评分和显式 projection**

canonical 只从 `EvalCodec.canonical_report()` 构造，不能对任意 dict 递归删除看似动态的 key。Suite 比较先按 case ID 对齐；缺失或新增 case 都是差异。

- [x] **Step 3：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_recovery_scoring.py tests/evals/test_determinism.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/evals tests/evals
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/evals/scoring.py src/vera/evals/determinism.py tests/evals docs/tasks/0017-eval-recovery-and-metrics.md
git commit -m "feat: score deterministic recovery evidence"
```

---

### Task 5：任务 0017 验收、记录与本地合并

**文件：**

- Create: `docs/evals/eval-recovery-and-metrics.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/tasks/0017-eval-recovery-and-metrics.md`

- [ ] **Step 1：运行完整质量门禁**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

- [ ] **Step 2：记录证据、提交并本地合并**

```bash
git add docs/evals/eval-recovery-and-metrics.md docs/STATUS.md docs/tasks/0017-eval-recovery-and-metrics.md
git commit -m "test: verify evaluation recovery and metrics"
git switch main
git merge --no-ff feature/eval-recovery-metrics -m "merge: add Vera recovery evaluations"
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" -q
git branch -d feature/eval-recovery-metrics
```

验收记录必须列出每个恢复 case 的 classification、allowed actions、写入次数、usage 完整/缺失结果和 canonical 重跑结果。无 remote 时不执行 push；确认 `main` 干净后才开始任务 0018。
