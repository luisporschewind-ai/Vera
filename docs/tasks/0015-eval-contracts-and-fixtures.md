# Vera 评测契约、Corpus 与夹具隔离实施计划

> **供 Agent 执行：** REQUIRED SUB-SKILL: 使用 `superpowers:executing-plans` 按 Task 顺序实施；只使用一个主实现 Agent，每个生产增量独立提交。

**状态：** Planned

**目标分支：** `feature/eval-contracts-fixtures`

**目标：** 固定阶段四版本化评测契约、Corpus manifest 校验和临时 workspace/state 隔离，使后续 Runner 只接收已验证的离线输入。

**架构：** Pydantic Contract 描述 case、脚本、期望、Worker 协议与报告；CorpusLoader 只读取内置资源并校验 SHA-256 manifest；FixtureIsolator 在系统临时目录创建每 case 的 workspace、state 和 evidence staging，不原地执行 corpus。

**技术栈：** Python 3.12、Pydantic 2、`importlib.resources`、`hashlib`、`tempfile`、pytest、Ruff、Mypy、uv。

**规格：** [阶段四评测与内部就绪](../specs/2026-09-12-evals-and-internal-readiness.md)

## 全局约束

- 开始前确认阶段三已合并到干净 `main`。
- 评测 schema 第一版固定 `schema_version=1`，所有 Model 必须 `frozen=True, extra="forbid"`。
- 第一版 `EvalCase.model` 只允许 `fake`；不得预留会静默联网的 fallback。
- Corpus 文件树、manifest 和 expectation 路径禁止符号链接、设备、FIFO、Socket、绝对路径、`..` 路径、供应商 Key 名和值模式；安全 case 的模型参数可包含经 schema 限定的越界字面量，但 Loader 不能解析或访问它。
- 不运行 Runtime、不启动子进程、不读取供应商环境文件。
- 不运行 live 测试，不修改 `VeraTestDemo`。

---

### Task 1：定义 Case、Script、Expectation 与 Report 契约

**文件：**

- Create: `src/vera/evals/__init__.py`
- Create: `src/vera/evals/contracts.py`
- Create: `tests/evals/__init__.py`
- Create: `tests/evals/test_contracts.py`

**接口：**

- Produces: `EvalTag`、`EvalScenario`、`EvalStatus`、`DimensionStatus`
- Produces: `EvalContract`（全部评测契约的冻结、严格基类）
- Produces: `EvalCase`、`EvalScript`、`EvalExpectation`、`EvalFileExpectation`
- Produces: `FileFact`、`EvalMetrics`、`EvalScore`、`EvalReport`、`EvalSuiteReport`
- Produces: `EvalWorkerRequest`、`EvalWorkerResult`
- Produces: `EvalSuiteReport.case(case_id: str) -> EvalReport`

- [x] **Step 1：编写严格 round-trip 与非法字段测试**

```python
def test_eval_case_round_trips_and_forbids_live() -> None:
    case = EvalCase(
        case_id="create-file",
        title="创建文件",
        goal="创建 hello.txt",
        tags=(EvalTag.CORRECTNESS,),
        model="fake",
        timeout_seconds=30,
        scenario=EvalScenario.STANDARD,
    )
    assert EvalCase.model_validate_json(case.model_dump_json()) == case
    with pytest.raises(ValidationError):
        EvalCase.model_validate({**case.model_dump(), "model": "live"})
```

覆盖非法 `case_id`、重复 tag、0/121 秒 timeout、未知 scenario、绝对 expectation path、重复允许路径、usage 缺失保持 `None`、Report 的空 score 和额外字段。

- [x] **Step 2：运行失败测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_contracts.py -v
```

- [x] **Step 3：实现冻结 Contract**

```python
class EvalCase(EvalContract):
    schema_version: Literal[1] = 1
    case_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1, max_length=120)
    goal: str = Field(min_length=1, max_length=2_000)
    tags: tuple[EvalTag, ...]
    model: Literal["fake"] = "fake"
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    scenario: EvalScenario = EvalScenario.STANDARD
```

`EvalScript` 包含 `turns: tuple[ModelTurn, ...]`、`text_deltas: tuple[tuple[str, ...], ...]` 和 `approvals: tuple[Literal["approve", "reject", "cancel"], ...]`。`EvalWorkerRequest` 只包含 evaluation/case ID 与父进程创建的 corpus、workspace、state、staging 绝对路径；Runner 必须再确认后三者位于本次受控临时根。`EvalWorkerResult` 包含可选 Report、持久 Event、before/after FileFact；失败时这些证据可为空，但必须包含稳定 `error_code`，且不能同时宣称 Pass。Corpus-relative 和 expectation 路径由共享 validator 拒绝空值、绝对路径、`.` 和 `..`。

- [x] **Step 4：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_contracts.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/evals tests/evals
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/evals tests/evals docs/tasks/0015-eval-contracts-and-fixtures.md
git commit -m "feat: define Vera evaluation contracts"
```

---

### Task 2：实现版本化 JSON Codec

**文件：**

- Create: `src/vera/evals/codec.py`
- Create: `tests/evals/test_codec.py`

**接口：**

- Produces: `EvalCodec.decode_case/script/expectation/worker_request/worker_result`
- Produces: `EvalCodec.encode_report()`、`encode_suite_report()`、`canonical_report()`
- Produces: `EvalCodecError(code, source, message)`

- [x] **Step 1：编写未知 schema、损坏 JSON 和 canonical 测试**

```python
def test_codec_rejects_future_schema_without_partial_decode() -> None:
    with pytest.raises(EvalCodecError) as caught:
        EvalCodec.decode_case('{"schema_version":2,"case_id":"x"}', source="case.json")
    assert caught.value.code == "unsupported_schema"


def test_canonical_report_excludes_nondeterministic_fields(report) -> None:
    canonical = EvalCodec.canonical_report(report)
    assert "evaluation_id" not in canonical
    assert "run_ids" not in canonical
    assert "wall_duration_seconds" not in canonical["metrics"]
    assert "event_duration_seconds" not in canonical["metrics"]
```

再覆盖 UTF-8、额外字段、非对象根节点、稳定 key 排序和 `usage=None` 编码为 JSON `null`。

- [x] **Step 2：运行失败测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_codec.py -v
```

- [x] **Step 3：实现显式 Codec 分派**

Codec 只能调用固定 Pydantic 类型，错误消息不得包含原始 JSON 全文。canonical projection 保留 `case_id/status/scores/reason_codes/before_files/after_files/event_types/usage`，对映射 key、文件事实、case 和 reason code 排序。

- [x] **Step 4：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_contracts.py tests/evals/test_codec.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/evals tests/evals
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/evals/codec.py tests/evals/test_codec.py docs/tasks/0015-eval-contracts-and-fixtures.md
git commit -m "feat: add evaluation codecs"
```

---

### Task 3：实现 Corpus manifest 与资源发现

**文件：**

- Create: `src/vera/evals/corpus.py`
- Create: `tests/evals/test_corpus.py`
- Create: `tests/fixtures/evals/valid/manifest.json`
- Create: `tests/fixtures/evals/valid/plain-answer/case.json`
- Create: `tests/fixtures/evals/valid/plain-answer/script.json`
- Create: `tests/fixtures/evals/valid/plain-answer/expect.json`
- Create: `tests/fixtures/evals/valid/plain-answer/workspace/README.md`

**接口：**

- Produces: `CorpusLoader(root: Traversable | Path)`
- Produces: `CorpusLoader.validate() -> CorpusValidation`
- Produces: `CorpusLoader.list_cases() -> tuple[EvalCase, ...]`
- Produces: `CorpusLoader.load(case_id) -> LoadedEvalCase`
- Produces: `CorpusValidation(manifest_hash, case_ids, file_count)`
- Produces: `CorpusError(code, source, message)`

- [ ] **Step 1：编写 manifest、路径和秘密拒绝测试**

```python
def test_loader_validates_manifest_and_returns_sorted_cases(valid_corpus) -> None:
    loader = CorpusLoader(valid_corpus)
    result = loader.validate()
    assert result.case_ids == ("plain-answer",)
    assert loader.load("plain-answer").case.goal


def test_loader_rejects_hash_mismatch(valid_corpus) -> None:
    (valid_corpus / "plain-answer" / "case.json").write_text("{}", encoding="utf-8")
    with pytest.raises(CorpusError, match="manifest_mismatch"):
        CorpusLoader(valid_corpus).validate()
```

另测未登记文件、重复 case ID、目录名不匹配、符号链接、FIFO、绝对路径、`..`、`DEEPSEEK_API_KEY`/`GLM_API_KEY`/Bearer-like secret 和非 UTF-8 JSON。

- [ ] **Step 2：运行失败测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_corpus.py -v
```

- [ ] **Step 3：实现只读 Loader**

manifest 结构固定为 `schema_version=1`、`files[{path,sha256}]`。Loader 先验证完整文件集合和 hash，再解析 case；遍历与输出始终按相对路径排序。默认资源根由 `importlib.resources.files("vera.evals").joinpath("corpus")` 获取，但测试可注入 Path。

- [ ] **Step 4：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_corpus.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/evals tests/evals
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/evals/corpus.py tests/evals tests/fixtures/evals docs/tasks/0015-eval-contracts-and-fixtures.md
git commit -m "feat: validate bundled evaluation corpus"
```

---

### Task 4：实现临时 Fixture 隔离与文件类型防线

**文件：**

- Create: `src/vera/evals/isolation.py`
- Create: `tests/evals/test_isolation.py`

**接口：**

- Produces: `FixtureIsolator(temp_root: Path)`
- Produces: `FixtureIsolator.prepare(loaded) -> IsolatedEvalCase`
- Produces: `IsolatedEvalCase(workspace, state_dir, staging_dir, source_manifest_hash)`
- Produces: `IsolatedEvalCase.verify_source_unchanged(current_manifest_hash: str) -> None`
- Produces: `IsolatedEvalCase.cleanup() -> None`
- Produces: `IsolationError(code, path, message)`

- [ ] **Step 1：编写复制、权限和源不变测试**

```python
def test_isolator_never_runs_in_source_workspace(valid_loaded_case, tmp_path) -> None:
    isolated = FixtureIsolator(tmp_path).prepare(valid_loaded_case)
    assert isolated.workspace != valid_loaded_case.source_root / "workspace"
    assert (isolated.workspace / "README.md").read_bytes() == b"fixture\n"
    assert isolated.state_dir.parent == isolated.workspace.parent
    current = CorpusLoader(valid_loaded_case.corpus_root).validate().manifest_hash
    isolated.verify_source_unchanged(current)
```

用真实文件断言复制后字节一致、workspace/state/staging 都位于 case 临时根，目录权限 `0700`；再测试源目录被改、目标已存在、复制中断、符号链接竞态和 cleanup 幂等。

- [ ] **Step 2：运行失败测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_isolation.py -v
```

- [ ] **Step 3：实现先验证后复制的隔离器**

复制前后都用 `lstat()` 拒绝符号链接与特殊文件。目标 case 根必须由 `tempfile.mkdtemp(prefix="vera-eval-", dir=temp_root)` 新建；不得接受用户 workspace。失败时只清理本次创建且已确认位于 `temp_root` 下的精确目录。

- [ ] **Step 4：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_isolation.py tests/evals/test_corpus.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/evals tests/evals
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/evals/isolation.py tests/evals/test_isolation.py docs/tasks/0015-eval-contracts-and-fixtures.md
git commit -m "feat: isolate evaluation fixtures"
```

---

### Task 5：任务 0015 验收、记录与本地合并

**文件：**

- Create: `docs/evals/eval-contracts-and-fixtures.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/tasks/0015-eval-contracts-and-fixtures.md`

- [ ] **Step 1：运行完整质量门禁**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

- [ ] **Step 2：记录证据并提交**

记录 schema、manifest 负例、隔离路径、测试数、覆盖率、未运行 live 和未读取 Key；把任务状态改为 `Done`。

```bash
git add docs/evals/eval-contracts-and-fixtures.md docs/STATUS.md docs/tasks/0015-eval-contracts-and-fixtures.md
git commit -m "test: verify evaluation contracts and isolation"
```

- [ ] **Step 3：本地合并并复核**

```bash
git switch main
git merge --no-ff feature/eval-contracts-fixtures -m "merge: add Vera evaluation contracts"
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" -q
git branch -d feature/eval-contracts-fixtures
```

无 remote 时不执行 push。确认 `main` 干净后才开始任务 0016。
