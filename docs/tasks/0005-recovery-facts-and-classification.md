# Vera 恢复事实与只读分类实施计划

> **供 Cursor Agent 执行：** 使用单一主实现 Agent，逐项执行本计划。每个生产行为先写失败测试，再做最小实现；每个可审阅任务独立提交。不要派发并行编辑 Agent。

**状态：** In progress

**目标分支：** `feature/recovery-facts-classification`

**目标：** 为普通编码 run 原子保存版本化恢复快照，并在新进程中只读扫描 Journal、Checkpoint 和工作区哈希，产生确定恢复分类，不执行恢复写入。

**架构：** `RecoverySnapshotStore` 保存私有事实；`WorkspaceEvidenceProbe` 生成文件哈希证据；`RecoveryClassifier` 是纯判定器；`RecoveryCoordinator.scan()` 隔离损坏 run。Runtime 只在稳定边界写快照，CLI 在本任务只展示恢复报告。

**技术栈：** Python 3.12、Pydantic 2、Typer、pytest、Ruff、Mypy、uv；不新增第三方依赖。

**规格：** [阶段二总规格](../specs/2026-09-11-phase-2-recovery-compatibility-policy.md)

**架构决策：** [ADR-0005](../decisions/ADR-0005-deterministic-run-recovery.md)、[ADR-0006](../decisions/ADR-0006-versioned-state-codecs.md)

## 全局约束

- 从最新干净 `main` 创建目标分支，不直接在 `main` 开发。
- 测试只使用 `tmp_path`；不运行 `tests/live`，不加载真实 Provider 环境。
- Snapshot 固定为 `<state_dir>/runs/<run_id>/recovery.json`，POSIX 权限 `0600`。
- Snapshot 使用同目录临时文件、flush、`os.fsync` 和 `os.replace`。
- 稳定 Event 先持久化，Snapshot 再引用该 sequence，成功后才暴露 Event 或进入副作用。
- 扫描、`InspectRecovery` 和 `/recover` 绝不写工作区、执行命令或调用模型。
- Compaction run 与已有终止 run 不进入待恢复列表。
- 阶段一无 Snapshot 的未终止 run 标记 `legacy_not_resumable`，不能伪造快照。
- 单个损坏 run 必须隔离，不能阻止其他 run 扫描。
- 本任务不升级公共 `schema_version=1`。

## 文件结构

```text
src/vera/
├── contracts/recovery.py
├── persistence/recovery_snapshot.py
├── recovery/{__init__,models,probe,classifier,coordinator}.py
├── runtime/{context,engine}.py
├── bootstrap.py
├── cli.py
├── cli_presenter.py
└── cli_session.py

tests/
├── contracts/test_recovery_models.py
├── persistence/test_recovery_snapshot.py
├── recovery/{test_probe,test_classifier,test_coordinator}.py
├── runtime/test_recovery_snapshots.py
└── cli/test_recovery_inspection.py
```

---

### Task 1：固定恢复契约与 Snapshot 模型

**文件：**

- Create: `src/vera/contracts/recovery.py`
- Create: `src/vera/recovery/__init__.py`
- Create: `src/vera/recovery/models.py`
- Modify: `src/vera/contracts/commands.py`
- Create: `tests/contracts/test_recovery_models.py`

**接口：**

- Produces: `RecoveryClassification`、`FileRecoveryState`、`RecoveryStage`
- Produces: `RecoveryEvidence`、`RecoveryReport`
- Produces: `InspectRecovery(run_id: str | None = None)`
- Produces: `PersistedChangeSet`、`RecoverySnapshot`

- [x] **Step 1：编写失败的 round-trip 测试**

```python
def test_recovery_report_round_trips() -> None:
    report = RecoveryReport(
        run_id="run_1",
        classification=RecoveryClassification.RESUMABLE_APPROVAL,
        stage=RecoveryStage.AWAITING_CHANGESET_APPROVAL,
        workspace_root=Path("/tmp/project"),
        evidence=(
            RecoveryEvidence(
                path="app.py",
                before_hash="a" * 64,
                after_hash="b" * 64,
                current_hash="a" * 64,
                state=FileRecoveryState.BEFORE,
            ),
        ),
        allowed_actions=("resume", "abandon"),
        reason_code="awaiting_changeset_approval",
    )
    assert RecoveryReport.model_validate_json(report.model_dump_json()) == report


def test_inspect_recovery_is_a_core_command() -> None:
    command: CoreCommand = InspectRecovery(run_id="run_1")
    assert command.schema_version == 1
```

- [x] **Step 2：运行测试并确认恢复类型不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/contracts/test_recovery_models.py -v
```

预期：导入 `vera.contracts.recovery` 失败。

- [x] **Step 3：实现精确模型**

```python
class RecoveryClassification(StrEnum):
    RESUMABLE_APPROVAL = "resumable_approval"
    RESUMABLE_VERIFICATION = "resumable_verification"
    SAFE_TO_ABANDON = "safe_to_abandon"
    RECOVERABLE_PARTIAL_APPLY = "recoverable_partial_apply"
    MANUAL_REQUIRED = "manual_required"
    LEGACY_NOT_RESUMABLE = "legacy_not_resumable"


class FileRecoveryState(StrEnum):
    BEFORE = "before"
    AFTER = "after"
    UNKNOWN = "unknown"


class RecoveryStage(StrEnum):
    STARTED = "started"
    AWAITING_CHANGESET_APPROVAL = "awaiting_changeset_approval"
    CHECKPOINT_READY = "checkpoint_ready"
    AWAITING_VERIFICATION_APPROVAL = "awaiting_verification_approval"
    VERIFYING = "verifying"
    TERMINAL = "terminal"
```

公共模型继承 `ContractModel`；私有模型使用冻结、`extra="forbid"` 的 `BaseModel`。`RecoverySnapshot` 字段固定为：

```python
snapshot_version: Literal[1] = 1
run_id: str
workspace_root: Path
workspace_identity: str
command: StartRun
stage: RecoveryStage
last_event_sequence: int
built_changeset: PersistedChangeSet | None = None
checkpoint_id: str | None = None
pending_approval: ApprovalRequest | None = None
verification_index: int = 0
verification_failed: bool = False
verification_in_flight: bool = False
workspace_write_started: bool = False
created_at: datetime
updated_at: datetime
vera_version: str
```

`PersistedChangeSet` 保存 `change_set: ChangeSet` 与 `intended_content_b64: dict[str, str]`。加载时使用严格 Base64 解码，并核对 create/update 的 `after_hash`。

- [x] **Step 4：运行契约和静态检查**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/contracts/test_recovery_models.py tests/contracts/test_models.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check \
  src/vera/contracts src/vera/recovery tests/contracts
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交契约**

```bash
git add src/vera/contracts/commands.py src/vera/contracts/recovery.py \
  src/vera/recovery tests/contracts/test_recovery_models.py \
  docs/tasks/0005-recovery-facts-and-classification.md
git commit -m "feat: define recovery facts and reports"
```

---

### Task 2：实现原子 SnapshotStore

**文件：**

- Create: `src/vera/persistence/recovery_snapshot.py`
- Create: `tests/persistence/test_recovery_snapshot.py`

**接口：**

- Produces: `RecoverySnapshotError`
- Produces: `RecoverySnapshotStore(state_dir: Path, replace: Callable[[Path, Path], None] = os.replace, fsync: Callable[[int], None] = os.fsync)`
- Produces: `save(snapshot) -> None`、`load(run_id) -> RecoverySnapshot`、`exists(run_id) -> bool`

- [x] **Step 1：编写原子性、权限和损坏测试**

```python
def test_snapshot_save_is_atomic_and_private(tmp_path: Path, snapshot) -> None:
    store = RecoverySnapshotStore(tmp_path / "state")
    store.save(snapshot)

    target = tmp_path / "state" / "runs" / snapshot.run_id / "recovery.json"
    assert store.load(snapshot.run_id) == snapshot
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert not target.with_suffix(".json.tmp").exists()


def test_corrupt_snapshot_has_stable_error(tmp_path: Path) -> None:
    target = tmp_path / "state" / "runs" / "run_1" / "recovery.json"
    target.parent.mkdir(parents=True)
    target.write_text("{broken", encoding="utf-8")
    with pytest.raises(RecoverySnapshotError, match="invalid_snapshot"):
        RecoverySnapshotStore(tmp_path / "state").load("run_1")
```

注入失败的 `replace`，断言旧正式文件逐字节不变。

- [x] **Step 2：运行测试并确认 Store 不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/persistence/test_recovery_snapshot.py -v
```

- [x] **Step 3：实现同目录原子替换**

构造函数允许注入 `replace: Callable[[Path, Path], None] = os.replace` 和 `fsync: Callable[[int], None] = os.fsync`。`save()` 校验安全 run ID，目录 `0700`、文件 `0600`；使用排序键紧凑 JSON，flush + fsync 后 replace。异常删除临时文件、保留旧正式文件并抛 `RecoverySnapshotError("snapshot_write_failed")`。

- [x] **Step 4：运行持久化回归**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/persistence -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check \
  src/vera/persistence tests/persistence
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Store**

```bash
git add src/vera/persistence/recovery_snapshot.py \
  tests/persistence/test_recovery_snapshot.py \
  docs/tasks/0005-recovery-facts-and-classification.md
git commit -m "feat: persist atomic recovery snapshots"
```

---

### Task 3：实现工作区证据与纯分类器

**文件：**

- Create: `src/vera/recovery/probe.py`
- Create: `src/vera/recovery/classifier.py`
- Create: `tests/recovery/__init__.py`
- Create: `tests/recovery/test_probe.py`
- Create: `tests/recovery/test_classifier.py`

**接口：**

- Produces: `workspace_identity(workspace: Path, installation_id: str) -> str`
- Produces: `WorkspaceEvidenceProbe.inspect(snapshot: RecoverySnapshot) -> tuple[RecoveryEvidence, ...]`
- Produces: `RecoveryClassifier.classify(snapshot, evidence) -> RecoveryReport`

- [x] **Step 1：编写 before/after/unknown 与分类表测试**

```python
def test_probe_classifies_exact_hashes(tmp_path: Path, snapshot_factory) -> None:
    target = tmp_path / "app.py"
    target.write_text("before\n", encoding="utf-8")
    snapshot = snapshot_factory(tmp_path, before=b"before\n", after=b"after\n")
    probe = WorkspaceEvidenceProbe("install-1")
    assert probe.inspect(snapshot)[0].state is FileRecoveryState.BEFORE

    target.write_text("after\n", encoding="utf-8")
    assert probe.inspect(snapshot)[0].state is FileRecoveryState.AFTER

    target.write_text("user\n", encoding="utf-8")
    assert probe.inspect(snapshot)[0].state is FileRecoveryState.UNKNOWN
```

参数化分类固定 STARTED/空证据 → safe_to_abandon，审批/全 BEFORE → resumable_approval，验证/全 AFTER 且 `verification_in_flight=False` → resumable_verification，Checkpoint/BEFORE+AFTER → recoverable_partial_apply，任意 UNKNOWN 或 `verification_in_flight=True` → manual_required。再覆盖 create/delete、工作区缺失、身份不符、符号链接逃逸和路径集合矛盾。

- [x] **Step 2：运行测试并确认接口不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/recovery/test_probe.py tests/recovery/test_classifier.py -v
```

- [x] **Step 3：实现只读 Probe 和穷尽分类**

`workspace_identity` 对 `installation_id + "\0" + str(workspace.resolve())` 计算 SHA-256。Probe 使用 `WorkspacePaths.resolve_mutation()` 重新验证路径，只读取字节并与 before/after hash 比较；不存在使用 `ABSENT_HASH`。异常生成 UNKNOWN，不执行 Git、Shell 或模型。

Classifier 不访问文件系统。UNKNOWN、身份错误、Checkpoint 缺失或证据矛盾优先 manual_required；只有所有条件都满足时返回可恢复状态。

- [x] **Step 4：运行恢复和 Workspace 回归**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/recovery tests/workspace -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check \
  src/vera/recovery tests/recovery
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交证据分类**

```bash
git add src/vera/recovery tests/recovery \
  docs/tasks/0005-recovery-facts-and-classification.md
git commit -m "feat: classify recovery evidence"
```

---

### Task 4：在 Runtime 稳定边界写 Snapshot

**文件：**

- Modify: `src/vera/runtime/context.py`
- Modify: `src/vera/runtime/engine.py`
- Create: `tests/runtime/test_recovery_snapshots.py`

**接口：**

- Produces: `VeraRuntime(adapter, registry, state_dir, limits=None, command_policy=None, *, snapshot_store: RecoverySnapshotStore | None = None, installation_id: str | None = None)`
- Guarantee: `snapshot.last_event_sequence` 等于最近稳定 Event sequence

- [x] **Step 1：编写边界顺序与失败关闭测试**

```python
def test_changeset_approval_snapshot_references_required_event(runtime_fixture) -> None:
    runtime, store, command = runtime_fixture.proposing_changeset()
    events = tuple(runtime.handle(command))
    snapshot = store.load(events[0].run_id)

    assert snapshot.stage is RecoveryStage.AWAITING_CHANGESET_APPROVAL
    assert snapshot.last_event_sequence == events[-1].sequence
    assert events[-1].type == "approval.required"
    assert snapshot.pending_approval is not None
    assert snapshot.built_changeset is not None
```

再覆盖 started、checkpoint.created、changeset.applied、验证命令 approval.required、verification.started、每条 verification.completed、所有终止 Event。`verification.started` 快照设置 `verification_in_flight=True`，完成后恢复 False。注入 save 失败，断言不进入下一副作用并产生 `run.failed(reason="snapshot_write_failed")`。

- [x] **Step 2：运行测试并确认 Runtime 不写 Snapshot**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/runtime/test_recovery_snapshots.py -v
```

- [x] **Step 3：实现 `_stable_event`**

```python
def _stable_event(
    self,
    context: RunContext,
    event_type: str,
    payload: dict[str, Any],
    stage: RecoveryStage,
) -> EventEnvelope:
    event = context.journal.append(event_type, payload)
    snapshot = self._snapshot_from_context(context, stage, event.sequence)
    self.snapshot_store.save(snapshot)
    return event
```

只在规格稳定边界使用。普通 model/tool 中间 Event 保持 Journal-only。Snapshot 成功后才 yield 或继续 Checkpoint、Apply、Verification；Compaction run 不建 Snapshot。`RunContext` 增加 `checkpoint_manifest`，使验证边界快照不依赖猜测。

若 Snapshot 保存失败，Runtime 使用不经过 `_stable_event` 的原始 Journal append 记录一次 `run.failed(reason="snapshot_write_failed")`，随后立即停止；失败路径不得递归尝试再写 Snapshot，也不得进入下一项副作用。

- [x] **Step 4：运行 Runtime 全回归**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/runtime tests/workspace tests/persistence tests/recovery -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests/runtime tests/recovery
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Runtime 集成**

```bash
git add src/vera/runtime/context.py src/vera/runtime/engine.py \
  tests/runtime/test_recovery_snapshots.py \
  docs/tasks/0005-recovery-facts-and-classification.md
git commit -m "feat: snapshot stable runtime boundaries"
```

---

### Task 5：接入 Coordinator、只读 Command 与 CLI

**文件：**

- Create: `src/vera/recovery/coordinator.py`
- Modify: `src/vera/persistence/run_store.py`
- Modify: `src/vera/runtime/engine.py`
- Modify: `src/vera/bootstrap.py`
- Modify: `src/vera/cli.py`
- Modify: `src/vera/cli_presenter.py`
- Modify: `src/vera/cli_session.py`
- Create: `tests/recovery/test_coordinator.py`
- Create: `tests/cli/test_recovery_inspection.py`

**接口：**

- Produces: `RecoveryCoordinator.scan(run_id: str | None = None) -> tuple[RecoveryReport, ...]`
- Produces: `recovery.detected` Event
- Produces: `/recover [run-id]`
- Produces: `vera recover list|show`

- [ ] **Step 1：编写损坏隔离和只读 CLI 测试**

Coordinator Fixture 同时创建正常 Snapshot、损坏 Snapshot、legacy 未终止 Journal、已终止 run 和 compaction run。断言损坏项为 manual_required、legacy 为 legacy_not_resumable、终止与 compaction 不出现。

```python
def test_recover_list_never_calls_model_or_changes_workspace(
    tmp_path: Path, recovery_dependencies
) -> None:
    before = workspace_digest(tmp_path)
    result = CliRunner().invoke(app, ["recover", "list", "--json"])

    assert result.exit_code == 0
    assert '"type":"recovery.detected"' in result.stdout
    assert workspace_digest(tmp_path) == before
    assert recovery_dependencies.adapter.requests == []
```

再测试 `/recover`、指定 run、未知 run、无恢复项、JSON 无 ANSI/提示符，以及启动只在存在未完成 run 时显示计数。

- [ ] **Step 2：运行测试并确认命令未知**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/recovery/test_coordinator.py tests/cli/test_recovery_inspection.py -v
```

- [ ] **Step 3：实现扫描与展示**

RunStore 增加 `iter_run_ids() -> tuple[str, ...]`，只返回安全目录名并排序。Coordinator 逐 run 捕获 `JournalCorrupt`、`RecoverySnapshotError`、`OSError`、`ValueError`，输出脱敏 manual_required 报告。

Runtime 分派 `InspectRecovery` 并发出 recovery.detected。Bootstrap 在私有状态目录原子创建 `installation.json` 并注入同一 Coordinator。Typer 注册 `recover list/show`；InteractiveSession 处理 `/recover [run-id]`。Payload 只含分类、阶段、允许动作、相对路径哈希和 reason_code，不含文件正文或 Snapshot 原文。

- [ ] **Step 4：运行完整任务验收**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

全部退出码为 0，且总覆盖率不得低于当前 90%。

- [ ] **Step 5：记录证据并提交**

创建 `docs/evals/recovery-facts-and-classification.md`，记录 Snapshot 原子性、六类分类、损坏隔离、legacy、CLI 只读性、测试数、覆盖率和未执行 live。更新 README、STATUS 和任务状态。

```bash
git add src/vera/recovery src/vera/persistence/run_store.py \
  src/vera/runtime/engine.py src/vera/bootstrap.py src/vera/cli.py \
  src/vera/cli_presenter.py src/vera/cli_session.py tests/recovery \
  tests/cli/test_recovery_inspection.py README.md docs/STATUS.md \
  docs/evals/recovery-facts-and-classification.md \
  docs/tasks/0005-recovery-facts-and-classification.md
git commit -m "test: verify recovery classification"
```

- [ ] **Step 6：合并回 main 并复核**

```bash
git switch main
git merge --no-ff feature/recovery-facts-classification \
  -m "merge: integrate recovery classification"
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git branch -d feature/recovery-facts-classification
```

无 remote 时记录“已本地合并、未推送”。
