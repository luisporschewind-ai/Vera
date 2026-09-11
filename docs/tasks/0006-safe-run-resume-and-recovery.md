# Vera 安全续跑与部分写入恢复实施计划

> **供 Cursor Agent 执行：** 使用单一主实现 Agent，按顺序执行。每项行为先写失败测试，再做最小实现并独立提交；禁止并行编辑同一工作树。

**状态：** In progress

**目标分支：** `feature/safe-run-resume-recovery`

**目标：** 在任务 0005 的确定分类之上，恢复等待中的 Change Set/验证审批、继续未开始的验证、放弃无副作用 run，并在精确哈希证据和独立审批后恢复部分写入。

**架构：** `RecoveryHydrator` 从 Snapshot 重建最小 `RunContext`；`RecoveryPlanner` 为部分写入生成不可变计划；`VeraRuntime` 继续作为执行权威。所有审批复用 `ApprovalGate`、`approval.required/resolved` 和 `ResolveApproval`，新增 `kind="recovery"`，不建立第二套审批协议。

**技术栈：** Python 3.12、Pydantic 2、Typer、pytest、Ruff、Mypy、uv；不新增第三方依赖。

**规格：** [阶段二总规格](../specs/2026-09-11-phase-2-recovery-compatibility-policy.md)

**依赖：** 任务 0005 已合并到 `main`。

## 全局约束

- 只能对 `RecoveryReport.allowed_actions` 中的动作执行后续步骤。
- 每次 resume 前重新读取 Snapshot、Journal、Checkpoint 和工作区哈希。
- 模型推理中断、tool loop 中断和 `verification_in_flight=True` 一律不续跑。
- Resume 不恢复普通对话会话，不调用 ModelAdapter。
- Change Set 审批恢复后仍执行现有 Checkpoint → Apply → Verification 链路。
- 部分恢复只接受全部目标处于 BEFORE/AFTER 的混合状态；任意 UNKNOWN 立即 manual_required。
- 恢复审批绑定 `recovery_id`、`recovery_hash`、工作区身份；任务 0008 再加入 `policy_hash`。
- 重复 Resume、Abandon 或 ResolveApproval 不重复文件与命令副作用。
- 不运行 live 测试，不读取真实 Key，不修改真实验收工程。

## 文件结构

```text
src/vera/
├── contracts/recovery.py               # ResumeRun/AbandonRun/RecoveryPlan
├── runtime/{approval,context,engine}.py # rehydrate 后仍由 Runtime 执行
├── recovery/{hydrator,planner,coordinator}.py
├── workspace/apply.py                  # 精确 partial restore
├── cli.py
├── cli_presenter.py
└── cli_session.py

tests/
├── recovery/{test_hydrator,test_planner,test_resume}.py
├── runtime/test_recovery_resume.py
├── workspace/test_partial_recovery.py
├── cli/test_recovery_actions.py
└── e2e/test_crash_recovery.py
```

---

### Task 1：扩展恢复 Command、计划与审批契约

**文件：**

- Modify: `src/vera/contracts/commands.py`
- Modify: `src/vera/contracts/approvals.py`
- Modify: `src/vera/contracts/recovery.py`
- Modify: `src/vera/recovery/models.py`
- Modify: `src/vera/runtime/context.py`
- Modify: `src/vera/runtime/approval.py`
- Modify: `tests/contracts/test_recovery_models.py`
- Modify: `tests/runtime/test_approval.py`

**接口：**

- Produces: `ResumeRun(run_id: str)`
- Produces: `AbandonRun(run_id: str)`
- Produces: `RecoveryPlan(recovery_id, run_id, workspace_identity, files, recovery_hash)`
- Produces: `ApprovalKind.RECOVERY`
- Produces: `ApprovalGate.restore(request: ApprovalRequest) -> ApprovalGate`
- Produces: `RecoverySnapshot.recovery_plan: RecoveryPlan | None = None`
- Produces: `RunContext.pending_recovery_plan: RecoveryPlan | None = None`

- [x] **Step 1：编写契约与恢复审批失败测试**

```python
def test_resume_and_abandon_are_core_commands() -> None:
    commands: tuple[CoreCommand, ...] = (
        ResumeRun(run_id="run_1"),
        AbandonRun(run_id="run_1"),
    )
    assert [item.model_dump()["schema_version"] for item in commands] == [1, 1]


def test_restored_gate_rejects_wrong_recovery_hash(recovery_request) -> None:
    gate = ApprovalGate.restore(recovery_request)
    with pytest.raises(ApprovalMismatch):
        gate.resolve(
            ResolveApproval(
                run_id="run_1",
                approval_id=recovery_request.approval_id,
                target_hash="wrong",
                decision="approve",
            )
        )
```

- [x] **Step 2：运行测试并确认命令和 kind 不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/contracts/test_recovery_models.py tests/runtime/test_approval.py -v
```

- [x] **Step 3：实现向后兼容扩展**

`ApprovalRequest.kind` 扩为 `Literal["changeset", "command", "recovery"]`。`ApprovalGate.restore()` 校验 request.run_id 与 gate run_id，不生成新 ID。`RecoveryPlan.recovery_hash` 对规范化 workspace identity、有序 path、before/after/current hash 和目标动作计算 SHA-256。

- [x] **Step 4：运行契约与静态检查**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/contracts tests/runtime/test_approval.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/contracts src/vera/runtime/approval.py tests/contracts
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交恢复动作契约**

```bash
git add src/vera/contracts src/vera/recovery/models.py src/vera/runtime/context.py \
  src/vera/runtime/approval.py \
  tests/contracts tests/runtime/test_approval.py \
  docs/tasks/0006-safe-run-resume-and-recovery.md
git commit -m "feat: define resumable recovery commands"
```

---

### Task 2：重建可恢复 RunContext

**文件：**

- Create: `src/vera/recovery/hydrator.py`
- Create: `tests/recovery/test_hydrator.py`
- Modify: `src/vera/workspace/changeset.py`

**接口：**

- Produces: `PersistedChangeSet.to_built() -> BuiltChangeSet`
- Produces: `RecoveryHydrator.hydrate(snapshot, journal) -> RunContext`

- [x] **Step 1：编写审批与验证边界重建测试**

```python
def test_hydrate_changeset_approval_restores_exact_context(snapshot, journal) -> None:
    context = RecoveryHydrator().hydrate(snapshot, journal)
    assert context.machine.state is RunState.AWAITING_APPROVAL
    assert context.built_change_set == snapshot.built_changeset.to_built()
    assert context.approval_gate.pending_approval == snapshot.pending_approval
    assert context.journal.read_all() == journal.read_all()


def test_hydrate_refuses_in_flight_verification(snapshot_factory, journal) -> None:
    snapshot = snapshot_factory(verification_in_flight=True)
    with pytest.raises(RecoveryHydrationError, match="verification_in_flight"):
        RecoveryHydrator().hydrate(snapshot, journal)
```

再覆盖 verification_index、verification_failed、checkpoint manifest 缺失、Journal sequence 与 Snapshot 不一致、intended bytes hash 不符。

- [x] **Step 2：运行测试并确认 Hydrator 不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/recovery/test_hydrator.py -v
```

- [x] **Step 3：实现最小重建**

Hydrator 只接受 `resumable_approval` 和 `resumable_verification` 对应 Snapshot。审批阶段恢复 `RunState.AWAITING_APPROVAL`；验证阶段恢复 `RunState.VERIFYING`。不恢复 model messages 或 tool loop；`messages=[]`，因为续跑路径禁止进入 `_drive()`。

`PersistedChangeSet.to_built()` 严格 Base64 解码 intended bytes，并再次核对 FileChange.after_hash。

- [x] **Step 4：运行恢复与 ChangeSet 回归**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/recovery/test_hydrator.py tests/workspace/test_changeset.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/recovery src/vera/workspace tests/recovery
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Hydrator**

```bash
git add src/vera/recovery/hydrator.py src/vera/workspace/changeset.py \
  tests/recovery/test_hydrator.py docs/tasks/0006-safe-run-resume-and-recovery.md
git commit -m "feat: rehydrate stable Vera runs"
```

---

### Task 3：恢复 Change Set 审批与验证流程

**文件：**

- Modify: `src/vera/recovery/coordinator.py`
- Modify: `src/vera/runtime/engine.py`
- Create: `src/vera/recovery/resume.py`
- Create: `tests/recovery/test_resume.py`
- Create: `tests/runtime/test_recovery_resume.py`

**接口：**

- Produces: `RecoveryCoordinator.prepare_resume(run_id) -> RecoveryReport`
- Produces: `RunResumer.load_context(run_id) -> RunContext`
- Consumes: `ResumeRun`
- Produces: `recovery.resume_started`、`recovery.resumed`、`approval.invalidated`

- [x] **Step 1：编写跨 Runtime resume 测试**

```python
def test_new_runtime_resumes_changeset_approval(recovery_fixture) -> None:
    first = recovery_fixture.runtime()
    approval = next(
        event for event in first.handle(recovery_fixture.start())
        if event.type == "approval.required"
    )

    second = recovery_fixture.runtime()
    resumed = tuple(second.handle(ResumeRun(run_id=approval.run_id)))
    pending = next(event for event in resumed if event.type == "approval.required")

    assert pending.payload["approval_id"] == approval.payload["approval_id"]
    assert second.adapter.requests == []
```

再批准 pending，断言只创建一次 Checkpoint、只应用一次 Change Set。验证恢复测试从新 Runtime 继续 `verification_index`，只运行未完成且不在 in-flight 状态的命令。

- [x] **Step 2：运行测试并确认新 Runtime 找不到 run**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/recovery/test_resume.py tests/runtime/test_recovery_resume.py -v
```

- [x] **Step 3：实现 resume 分派**

`VeraRuntime.handle(ResumeRun)` 必须先 `prepare_resume()` 重新分类，再 hydrate。对于 resumable_approval，发出 `recovery.resume_started` 后重新发出同一 pending `approval.required`；对于 resumable_verification，直接进入 `_verify()`。结束后发 `recovery.resumed`。其他分类只发 recovery.detected 或 manual_required，不建立内存 run。

重复 Resume 若 run 已在当前 `self.runs` 或 Journal 已终止，返回当前报告，不重复动作。

- [x] **Step 4：运行 Runtime 与 CLI driver 回归**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/runtime tests/recovery tests/cli/test_driver.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests/runtime tests/recovery
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交安全续跑**

```bash
git add src/vera/recovery src/vera/runtime/engine.py \
  tests/recovery tests/runtime/test_recovery_resume.py \
  docs/tasks/0006-safe-run-resume-and-recovery.md
git commit -m "feat: resume stable Vera runs"
```

---

### Task 4：规划并审批部分写入恢复

**文件：**

- Create: `src/vera/recovery/planner.py`
- Modify: `src/vera/recovery/coordinator.py`
- Modify: `src/vera/runtime/engine.py`
- Modify: `src/vera/workspace/apply.py`
- Create: `tests/recovery/test_planner.py`
- Create: `tests/workspace/test_partial_recovery.py`

**接口：**

- Produces: `RecoveryPlanner.plan(report, snapshot) -> RecoveryPlan`
- Produces: `ChangeApplier.restore_partial(plan, manifest) -> RollbackResult`
- Produces: `recovery.restore_proposed`、`recovery.restored`

- [ ] **Step 1：编写精确恢复和冲突测试**

```python
def test_partial_restore_only_reverts_after_files(partial_fixture) -> None:
    plan = RecoveryPlanner().plan(partial_fixture.report, partial_fixture.snapshot)
    result = partial_fixture.applier.restore_partial(plan, partial_fixture.manifest)

    assert result.status is RollbackStatus.ROLLED_BACK
    assert partial_fixture.before_file.read_bytes() == b"before-a\n"
    assert partial_fixture.after_file.read_bytes() == b"before-b\n"
```

再覆盖恢复前文件变为 UNKNOWN、Checkpoint blob 损坏、恢复中 writer 失败、重复批准、错误 recovery_hash。断言 UNKNOWN 时零文件写入。

- [ ] **Step 2：运行测试并确认部分恢复接口不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/recovery/test_planner.py tests/workspace/test_partial_recovery.py -v
```

- [ ] **Step 3：实现计划与 recovery approval**

`ResumeRun` 遇到 recoverable_partial_apply 时生成 plan，追加 `recovery.restore_proposed`，并把 plan 写入稳定 Snapshot，再通过以下调用发出现有 `approval.required`：

```python
request = context.approval_gate.require(
    ApprovalKind.RECOVERY,
    plan.recovery_id,
    plan.recovery_hash,
    "恢复部分应用的 Change Set",
    "high",
)
```

`ResolveApproval(approve)` 前再次扫描并重算相同 hash；一致才执行 `restore_partial`。拒绝产生 approval.resolved 与 run.cancelled，不写文件。

`restore_partial` 预检所有路径后，只把 AFTER 文件恢复为 BEFORE；已经 BEFORE 的文件保持不动。任一预检失败时整体不写。

- [ ] **Step 4：运行恢复与 Workspace 全回归**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/recovery tests/workspace tests/runtime -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests/recovery tests/workspace
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [ ] **Step 5：提交部分恢复**

```bash
git add src/vera/recovery src/vera/runtime/engine.py src/vera/workspace/apply.py \
  tests/recovery tests/workspace/test_partial_recovery.py \
  docs/tasks/0006-safe-run-resume-and-recovery.md
git commit -m "feat: restore partial changes with approval"
```

---

### Task 5：实现放弃、CLI 操作与跨进程故障验收

**文件：**

- Modify: `src/vera/runtime/engine.py`
- Modify: `src/vera/cli.py`
- Modify: `src/vera/cli_presenter.py`
- Modify: `src/vera/cli_session.py`
- Create: `tests/cli/test_recovery_actions.py`
- Create: `tests/e2e/test_crash_recovery.py`
- Create: `docs/evals/safe-run-resume-and-recovery.md`
- Modify: `README.md`
- Modify: `docs/STATUS.md`

- [ ] **Step 1：编写 abandon 和 CLI 测试**

```python
def test_abandon_only_accepts_safe_to_abandon(recovery_runtime) -> None:
    safe_events = tuple(recovery_runtime.handle(AbandonRun(run_id="run_safe")))
    unsafe_events = tuple(recovery_runtime.handle(AbandonRun(run_id="run_partial")))

    assert safe_events[-1].type == "recovery.abandoned"
    assert unsafe_events[-1].type == "recovery.manual_required"
```

CLI 覆盖 `/resume`、`/abandon`、`vera recover resume/abandon --json`、审批 EOF 安全取消、退出码 0/2/3/4/5 和输出脱敏。

- [ ] **Step 2：编写真实跨实例 failpoint 测试**

`tests/e2e/test_crash_recovery.py` 使用参数化 failpoint，在 Change Set 审批、Checkpoint、每文件应用、changeset.applied、verification.started/completed 处抛出 `SimulatedCrash`。每次丢弃旧 Runtime，创建新 Runtime 扫描；断言分类、允许动作和文件字节。不要复用旧 `RunContext`。

- [ ] **Step 3：实现 Abandon 与 CLI 命令**

Abandon 每次重新分类，只接受 safe_to_abandon；追加 `recovery.abandoned` 和终止 Snapshot。CLI Help 增加恢复命令，所有人类输出来自 Event Presenter。

- [ ] **Step 4：运行完整离线验收**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

所有检查通过且覆盖率不低于 90%。

- [ ] **Step 5：记录证据并提交**

验收记录逐项写明跨实例恢复、部分写入审批、in-flight 人工处理、幂等性、退出码、测试数和未执行 live。任务标记 Complete，STATUS 指向 0007。

```bash
git add src/vera/runtime/engine.py src/vera/cli.py src/vera/cli_presenter.py \
  src/vera/cli_session.py tests/cli/test_recovery_actions.py \
  tests/e2e/test_crash_recovery.py README.md docs/STATUS.md \
  docs/evals/safe-run-resume-and-recovery.md \
  docs/tasks/0006-safe-run-resume-and-recovery.md
git commit -m "test: verify safe run recovery"
```

- [ ] **Step 6：合并回 main 并复核**

```bash
git switch main
git merge --no-ff feature/safe-run-resume-recovery \
  -m "merge: integrate safe run recovery"
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git branch -d feature/safe-run-resume-recovery
```
