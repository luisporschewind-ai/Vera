# Vera 版本化 Codec 与兼容迁移实施计划

> **供 Cursor Agent 执行：** 使用一个主实现 Agent，按任务顺序执行 TDD、独立提交和验证。禁止并行编辑同一工作树。

**状态：** Done

**目标分支：** `feature/versioned-state-codecs`

**目标：** 集中管理 Command/Event、Journal 与 RecoverySnapshot 的版本读取，使阶段一历史保持可读、损坏 run 被隔离、未知未来版本失败关闭，并提供可预览、可备份的 manifest 迁移。

**架构：** `ContractCodec` 处理公共协议，`JournalCodec` 与 `SnapshotCodec` 处理私有格式；`RunManifest` 明确 Journal 版本。`StateMigrationService` 只生成或更新派生 manifest，不重写 Event Journal；所有应用先计划、备份、原子写入和复读验证。

**技术栈：** Python 3.12、Pydantic 2、Typer、pytest、Ruff、Mypy、uv；不新增依赖。

**规格：** [阶段二总规格](../specs/2026-09-11-phase-2-recovery-compatibility-policy.md)

**架构决策：** [ADR-0006](../decisions/ADR-0006-versioned-state-codecs.md)

**依赖：** 任务 0005、0006 已合并到 `main`。

## 全局约束

- `schema_version`、`journal_format_version`、`snapshot_version` 独立演进。
- 产品版本只用于诊断，不能推断数据格式。
- 已知旧格式通过明确 Decoder 读取；未知更高版本返回 `unsupported_version`。
- 任何 Codec 都不能静默忽略未知版本或部分返回损坏对象。
- Event Journal 永远追加，不原地重写、排序或删除。
- 阶段一无 manifest 的目录按 legacy v1 读取，不获得恢复能力。
- 磁盘迁移必须先 dry-run；apply 前创建恢复副本，失败保持原数据。
- 不运行模型、命令或工作区操作；不读取用户 Provider Key。

## 文件结构

```text
src/vera/
├── contracts/codec.py
├── persistence/
│   ├── journal_codec.py
│   ├── snapshot_codec.py
│   ├── run_manifest.py
│   └── migration.py
├── contracts/commands.py
├── persistence/{journal,run_store,recovery_snapshot}.py
├── runtime/engine.py
└── cli.py

tests/
├── contracts/test_codec.py
├── persistence/{test_journal_codec,test_snapshot_codec,test_run_manifest,test_migration}.py
├── fixtures/state/legacy-v1/run_legacy/events.jsonl
└── cli/test_state_migration.py
```

---

### Task 1：建立公共 ContractCodec

**文件：**

- Create: `src/vera/contracts/codec.py`
- Modify: `src/vera/contracts/commands.py`
- Create: `tests/contracts/test_codec.py`

**接口：**

- Produces: `ContractVersionError(code, version)`
- Produces: `CommandType`
- Produces: `ContractCodec.encode_command(command) -> bytes`
- Produces: `ContractCodec.decode_command(command_type, data) -> CoreCommand`
- Produces: `ContractCodec.encode_event(event) -> bytes`
- Produces: `ContractCodec.decode_event(data) -> EventEnvelope`

- [x] **Step 1：编写当前、旧版和未来版本测试**

```python
def test_command_codec_round_trips_each_type(tmp_path: Path) -> None:
    codec = ContractCodec()
    command = InspectRecovery(run_id="run_1")
    encoded = codec.encode_command(command)
    assert codec.decode_command(CommandType.INSPECT_RECOVERY, encoded) == command


def test_codec_rejects_future_schema_version() -> None:
    data = b'{"schema_version":99,"run_id":"run_1"}'
    with pytest.raises(ContractVersionError) as caught:
        ContractCodec().decode_command(CommandType.RESUME_RUN, data)
    assert caught.value.code == "unsupported_version"
    assert caught.value.version == 99
```

参数化覆盖现有全部 CoreCommand；Event 覆盖 version 1、非法 JSON、缺失版本、未来版本。

- [x] **Step 2：运行测试并确认 Codec 不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/contracts/test_codec.py -v
```

- [x] **Step 3：实现显式版本注册表**

`CommandType` 使用稳定字符串：`start_run`、`resolve_approval`、`cancel_run`、`rollback_run`、`inspect_recovery`、`resume_run`、`abandon_run`。Codec 先使用标准库 JSON 只读取 `schema_version`，再按 `(command_type, version)` 选择模型；不通过字段猜测命令类型。

```python
_COMMAND_DECODERS: dict[tuple[CommandType, int], type[ContractModel]] = {
    (CommandType.START_RUN, 1): StartRun,
    (CommandType.RESOLVE_APPROVAL, 1): ResolveApproval,
}
```

补齐全部已支持命令。编码使用当前对象声明版本；不存在注册项统一抛 ContractVersionError。

- [x] **Step 4：运行契约回归**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/contracts -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/contracts tests/contracts
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 ContractCodec**

```bash
git add src/vera/contracts/codec.py src/vera/contracts/commands.py \
  tests/contracts/test_codec.py docs/tasks/0007-versioned-codecs-and-migration.md
git commit -m "feat: decode versioned core contracts"
```

---

### Task 2：建立 RunManifest、JournalCodec 与 SnapshotCodec

**文件：**

- Create: `src/vera/persistence/run_manifest.py`
- Create: `src/vera/persistence/journal_codec.py`
- Create: `src/vera/persistence/snapshot_codec.py`
- Modify: `src/vera/persistence/journal.py`
- Modify: `src/vera/persistence/recovery_snapshot.py`
- Create: `tests/persistence/test_run_manifest.py`
- Create: `tests/persistence/test_journal_codec.py`
- Create: `tests/persistence/test_snapshot_codec.py`

**接口：**

- Produces: `RunManifest(manifest_version=1, journal_format_version=1, run_id, created_at)`
- Produces: `JournalCodec.decode_line(data, run_id, expected_sequence) -> EventEnvelope`
- Produces: `SnapshotCodec.decode(data) -> RecoverySnapshot`

- [x] **Step 1：编写格式版本与未来拒绝测试**

```python
def test_snapshot_codec_rejects_future_version() -> None:
    data = b'{"snapshot_version":99,"run_id":"run_1"}'
    with pytest.raises(StateVersionError, match="unsupported_version"):
        SnapshotCodec().decode(data)


def test_manifest_is_written_before_first_event(tmp_path: Path) -> None:
    journal = EventJournal(tmp_path, "run_1", Redactor([]))
    journal.append("run.started", {})
    manifest = RunManifestStore(tmp_path).load("run_1")
    assert manifest.journal_format_version == 1
```

再测试 future journal format、manifest run_id 不匹配、sequence 不连续、Snapshot version 缺失和损坏 JSON。

- [x] **Step 2：运行测试并确认专用 Codec 不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/persistence/test_run_manifest.py tests/persistence/test_journal_codec.py \
  tests/persistence/test_snapshot_codec.py -v
```

- [x] **Step 3：实现独立格式分派**

RunManifest 保存到 run 目录 `manifest.json`，权限 `0600`，原子写入。EventJournal 新 run 在首次 append 前确保 manifest 存在；加载旧目录时不自动写 manifest。JournalCodec 使用 ContractCodec 解 Event，再检查 run_id 和 sequence。RecoverySnapshotStore 通过 SnapshotCodec 解码，不再直接调用当前 Pydantic 模型。

- [x] **Step 4：运行持久化与恢复回归**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/persistence tests/recovery -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/persistence tests/persistence
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 State Codec**

```bash
git add src/vera/persistence tests/persistence \
  docs/tasks/0007-versioned-codecs-and-migration.md
git commit -m "feat: version Vera state formats"
```

---

### Task 3：兼容阶段一 legacy run 并隔离损坏项

**文件：**

- Create: `tests/fixtures/state/legacy-v1/run_legacy/events.jsonl`
- Modify: `src/vera/persistence/run_store.py`
- Modify: `src/vera/recovery/coordinator.py`
- Create: `tests/persistence/test_legacy_state.py`
- Modify: `tests/recovery/test_coordinator.py`

**接口：**

- Produces: `RunFormatStatus.CURRENT | LEGACY | CORRUPT | UNSUPPORTED`
- Produces: `RunStore.format_status(run_id) -> RunFormatStatus`

- [x] **Step 1：添加冻结 legacy Fixture 与读取测试**

Fixture 从提交 `08b1017` 后的阶段一真实 Event 结构构造，固定 run.started、changeset.proposed、approval.required，不含 manifest/Snapshot/秘密。

```python
def test_legacy_run_remains_visible_but_not_resumable(copied_legacy_state) -> None:
    store = RunStore(copied_legacy_state)
    assert store.format_status("run_legacy") is RunFormatStatus.LEGACY
    assert store.read_events("run_legacy")[-1].type == "approval.required"

    report = coordinator(copied_legacy_state).scan("run_legacy")[0]
    assert report.classification is RecoveryClassification.LEGACY_NOT_RESUMABLE
```

再放置一个截断 JSONL、一个 future manifest；断言列表其他 run 正常，损坏项和不支持项有独立状态。

- [x] **Step 2：运行测试并确认 legacy 缺少统一状态**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/persistence/test_legacy_state.py tests/recovery/test_coordinator.py -v
```

- [x] **Step 3：实现只读 legacy Decoder**

无 manifest 但 events.jsonl 存在时按 journal format 1 只读；不可生成 RecoverySnapshot。RunStore 的 list/read 分别隔离 JournalCorrupt 和 StateVersionError，返回结构化诊断，不用空元组掩盖损坏。

- [x] **Step 4：运行历史与 CLI 回归**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/persistence tests/recovery tests/cli -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests/persistence tests/recovery
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 legacy 兼容**

```bash
git add tests/fixtures/state src/vera/persistence/run_store.py \
  src/vera/recovery/coordinator.py tests/persistence/test_legacy_state.py \
  tests/recovery/test_coordinator.py docs/tasks/0007-versioned-codecs-and-migration.md
git commit -m "feat: read legacy Vera run state"
```

---

### Task 4：实现非破坏迁移计划与 CLI 验收

**文件：**

- Create: `src/vera/persistence/migration.py`
- Modify: `src/vera/contracts/commands.py`
- Modify: `src/vera/runtime/engine.py`
- Modify: `src/vera/cli.py`
- Create: `tests/persistence/test_migration.py`
- Create: `tests/cli/test_state_migration.py`
- Create: `docs/evals/versioned-codecs-and-migration.md`
- Modify: `docs/STATUS.md`

**接口：**

- Produces: `InspectState(run_id: str | None = None)`
- Produces: `PlanStateMigration(run_id: str)`
- Produces: `ApplyStateMigration(run_id, migration_id, migration_hash)`
- Produces: `StateMigrationService.plan/apply`
- Produces: `state.migration_planned|completed|failed`

- [x] **Step 1：编写 dry-run、备份和失败原样测试**

```python
def test_migration_apply_never_rewrites_journal(legacy_state) -> None:
    events_path = legacy_state / "runs" / "run_legacy" / "events.jsonl"
    before = events_path.read_bytes()
    plan = StateMigrationService(legacy_state).plan("run_legacy")
    result = StateMigrationService(legacy_state).apply(plan)

    assert result.status == "completed"
    assert events_path.read_bytes() == before
    backup = events_path.parent / "migration-backup" / plan.migration_id / "events.jsonl"
    assert backup.read_bytes() == before
    assert RunManifestStore(legacy_state).load("run_legacy").journal_format_version == 1
```

注入 manifest replace 失败，断言旧状态和备份可读；错误 migration_hash、future state、重复 apply 不产生重复修改。

- [x] **Step 2：运行测试并确认迁移服务不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/persistence/test_migration.py tests/cli/test_state_migration.py -v
```

- [x] **Step 3：实现 Core 驱动迁移**

Plan 只读并计算 `migration_hash`。Apply 只接受完全匹配计划：先复制原相关文件到 run 内 `migration-backup/<migration-id>/`，fsync，再原子写派生 manifest，最后用 Codec 复读。任何失败发 state.migration_failed，不删除备份、不改 Journal。

CLI 提供 `vera state inspect`、`vera state migrate <run-id> --dry-run` 和显式 `--apply --migration-hash <hash>`；默认永远 dry-run。JSON 只输出 Event。

- [x] **Step 4：运行完整离线验收**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

保持覆盖率至少 90%，并确认无 live 请求。

- [x] **Step 5：记录、提交和合并**

验收记录列出三类版本、legacy、future reject、损坏隔离、dry-run、备份、失败原样和 Journal 字节未变。任务改 Complete，STATUS 指向 0008。

```bash
git add src/vera/contracts/commands.py src/vera/runtime/engine.py src/vera/cli.py \
  src/vera/persistence/migration.py tests/persistence/test_migration.py \
  tests/cli/test_state_migration.py docs/STATUS.md \
  docs/evals/versioned-codecs-and-migration.md \
  docs/tasks/0007-versioned-codecs-and-migration.md
git commit -m "test: verify compatible Vera state migration"
git switch main
git merge --no-ff feature/versioned-state-codecs \
  -m "merge: integrate versioned state codecs"
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" -q
git branch -d feature/versioned-state-codecs
```
