# Vera Eval Worker、Runner 与基础评分实施计划

> **供 Agent 执行：** REQUIRED SUB-SKILL: 使用 `superpowers:executing-plans` 按 Task 顺序实施；只使用一个主实现 Agent，每个生产增量独立提交。

**状态：** Done

**目标分支：** `feature/eval-runner-scoring`

**目标：** 用受控 Worker 子进程运行标准离线 case，建立硬超时、Core 驱动、文件哈希评分和原子私有证据包。

**架构：** 父进程 CaseProcessRunner 只启动 `python -m vera.evals.worker` 并读取版本化结果；Worker 通过 EvalRuntimeFactory 构造 FakeModelAdapter + VeraRuntime，由 ScriptedRunDriver 发送 Core Command；Scorer 对 before/after 文件事实和 Event 做纯函数评分；EvidenceWriter 最后原子发布允许保留的证据。

**技术栈：** Python 3.12、Pydantic 2、subprocess、hashlib、pytest、Ruff、Mypy、uv。

**规格：** [阶段四评测与内部就绪](../specs/2026-09-12-evals-and-internal-readiness.md)

## 全局约束

- 依赖任务 0015 已合并。
- Worker 只能构造 `FakeModelAdapter`，不能调用 `build_runtime()`、`load_provider_environment()` 或 OpenAI-compatible Adapter。
- 进程启动必须 `shell=False`；timeout 后 TERM 等待最多 2 秒，再 kill 精确 PID。
- 文件清单只记录相对路径、类型、大小和 SHA-256，不读取或保存工作区正文到报告。
- stdout 的 JSON 模式只由父 CLI 输出；Worker stdout/stderr 不能成为协议或评分输入。
- 不运行 live，不读取真实 Key，不修改 `VeraTestDemo`。

---

### Task 1：建立 FileInventory 与纯基础 Scorer

**文件：**

- Create: `src/vera/evals/files.py`
- Create: `src/vera/evals/scoring.py`
- Create: `tests/evals/test_files.py`
- Create: `tests/evals/test_scoring.py`

**接口：**

- Produces: `FileInventory.capture(root: Path) -> tuple[FileFact, ...]`
- Produces: `FileInventoryError(code, path, message)`
- Produces: `Scorer.score(case, expect, before_files, after_files, events, metrics) -> tuple[EvalScore, ...]`
- Produces: stable reason codes `file_hash_mismatch`、`unexpected_file_change`、`terminal_event_mismatch`、`required_event_missing`、`forbidden_event_seen`

- [x] **Step 1：编写文件增删改和终态评分测试**

```python
def test_safety_fails_for_change_outside_allowlist(tmp_path: Path) -> None:
    before = (file_fact("allowed.txt", "old"), file_fact("guard.txt", "same"))
    after = (file_fact("allowed.txt", "new"), file_fact("guard.txt", "changed"))
    scores = Scorer().score(
        safety_case(), safety_expect(allowed_changed_paths=("allowed.txt",)),
        before, after, completed_events(), empty_metrics(),
    )
    assert score(scores, "safety").status is DimensionStatus.FAIL
    assert "unexpected_file_change" in score(scores, "safety").reason_codes
```

另测新增、删除、目录变文件、特殊文件、期望不存在、SHA-256 不符、必需 Event 缺失、禁止 Event 出现，以及未声明维度为 `not_applicable`。

- [x] **Step 2：运行失败测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_files.py tests/evals/test_scoring.py -v
```

- [x] **Step 3：实现确定排序的文件事实与评分**

`FileInventory` 使用 `lstat()`，拒绝跟随 symlink；常规文件分块计算 SHA-256，目录只记录 kind，不遍历 corpus 之外路径。Scorer 不读取磁盘，按 `(path, kind, sha256)` 映射比较，并按维度名和 reason code 排序输出。

- [x] **Step 4：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_files.py tests/evals/test_scoring.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/evals tests/evals
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/evals/files.py src/vera/evals/scoring.py tests/evals docs/tasks/0016-eval-runner-and-scoring.md
git commit -m "feat: score evaluation file and event facts"
```

---

### Task 2：构造离线 Runtime 与脚本化 Core 驱动器

**文件：**

- Create: `src/vera/evals/runtime_factory.py`
- Create: `src/vera/evals/script_driver.py`
- Create: `tests/evals/test_runtime_factory.py`
- Create: `tests/evals/test_script_driver.py`

**接口：**

- Produces: `EvalRuntimeFactory.create(loaded, isolated) -> VeraRuntime`
- Produces: `ScriptedRunDriver.execute(runtime, loaded, isolated) -> EvalExecution`
- Produces: `EvalExecution(run_ids, events, before_files, after_files, runtime_instance_count, restart_event_offset, side_effect_counts)`
- Produces: `EvalExecutionError(code, message)`
- Consumes: `$VERA_EVAL_PYTHON` only inside verification argv

- [x] **Step 1：编写无 Provider、审批耗尽和替换占位符测试**

```python
def test_factory_uses_fake_adapter_and_never_provider_loader(loaded_case, isolated, monkeypatch) -> None:
    monkeypatch.setattr("vera.bootstrap.load_provider_environment", forbidden_call)
    runtime = EvalRuntimeFactory().create(loaded_case, isolated)
    assert isinstance(runtime.adapter, FakeModelAdapter)


def test_driver_fails_closed_when_approval_script_is_exhausted(runtime, loaded_case) -> None:
    with pytest.raises(EvalExecutionError, match="approval_script_exhausted"):
        ScriptedRunDriver().execute(runtime, loaded_case.with_script_approvals(()), isolated_case())
```

再覆盖未知工具、剩余未消费 ModelTurn、剩余审批决定、`cancel` 转 `CancelRun`、`reject`/`approve` 绑定动态 approval ID/hash，以及非 `$VERA_EVAL_PYTHON` 环境语法拒绝。

- [x] **Step 2：运行失败测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_runtime_factory.py tests/evals/test_script_driver.py -v
```

- [x] **Step 3：实现与 bootstrap 同边界的离线装配**

Factory 注册 `ReadFileTool`、`ListDirectoryTool`、`SearchTextTool`，使用临时 WorkspacePaths、固定 `installation_id=f"eval-{case_id}"`、临时 RecoverySnapshotStore、PolicyEngine 和只允许 `(sys.executable, "-c")` 的 CommandPolicy。Driver 只调用 `drive_run()`/`runtime.handle()`，标准场景从 `StartRun` 开始；本任务对非 `standard` 场景返回 `unsupported_scenario`。

`EvalExecution.event_types` 是全部 Event 的顺序投影；`event_types_after_restart` 从 `restart_event_offset` 切片。没有重启时 `runtime_instance_count=1`、offset 为 `None`。副作用计数使用稳定 key（例如 `changeset.applied`、`rollback.completed`），供恢复评分使用。

- [x] **Step 4：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_runtime_factory.py tests/evals/test_script_driver.py tests/runtime -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/evals tests/evals
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/evals/runtime_factory.py src/vera/evals/script_driver.py tests/evals docs/tasks/0016-eval-runner-and-scoring.md
git commit -m "feat: drive scripted evaluations through Vera core"
```

---

### Task 3：实现版本化 Worker 入口

**文件：**

- Create: `src/vera/evals/worker.py`
- Create: `tests/evals/test_worker.py`

**接口：**

- Produces: `run_worker(request: EvalWorkerRequest) -> EvalWorkerResult`
- Produces: module entry `python -m vera.evals.worker --request <path> --result <path>`
- Guarantee: Worker 不向 stdout 写协议，不加载用户 Provider 配置

- [x] **Step 1：编写成功、Runtime 异常和结果原子写测试**

```python
def test_worker_returns_report_from_core_facts(worker_request) -> None:
    result = run_worker(worker_request)
    assert result.report is not None
    assert result.report.status is EvalStatus.PASS
    assert result.report.event_types[-1] == "run.completed"


def test_worker_maps_uncaught_runtime_error(worker_request, monkeypatch) -> None:
    monkeypatch.setattr(ScriptedRunDriver, "execute", raising_runtime_error)
    result = run_worker(worker_request)
    assert result.error_code == "runtime_exception"
    assert "secret" not in result.model_dump_json()
```

再测 request schema 错误、result 目标已存在、部分写失败、没有 Event、source manifest 在运行后改变和 stderr 不包含 fixture 正文。

- [x] **Step 2：运行失败测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_worker.py -v
```

- [x] **Step 3：实现单 case Worker**

Worker 顺序固定：解码 request → 重新校验 corpus → 捕获 before → 构造 Runtime → 执行脚本 → 捕获 after → 提取最小 metrics → 评分 → 验证源 hash → 原子写 result。任何异常映射稳定 code，不序列化 traceback、环境或原始文件正文。

- [x] **Step 4：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_worker.py tests/evals/test_script_driver.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/evals tests/evals
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/evals/worker.py tests/evals/test_worker.py docs/tasks/0016-eval-runner-and-scoring.md
git commit -m "feat: add isolated evaluation worker"
```

---

### Task 4：实现父进程硬超时与安全环境

**文件：**

- Create: `src/vera/evals/process_runner.py`
- Create: `tests/evals/test_process_runner.py`

**接口：**

- Produces: `CaseProcessRunner.run(request, timeout_seconds) -> EvalWorkerResult`
- Produces: `sanitized_worker_environment(source: Mapping[str, str]) -> dict[str, str]`
- Produces: reason codes `case_timeout`、`worker_exit_error`、`worker_protocol_error`

- [x] **Step 1：编写环境清除、timeout 和坏结果测试**

```python
def test_worker_environment_removes_all_provider_values(monkeypatch) -> None:
    source = {
        "PATH": "/bin",
        "DEEPSEEK_API_KEY": "secret",
        "GLM_API_KEY": "secret-2",
        "VERA_LIVE_API_KEY": "secret-3",
    }
    result = sanitized_worker_environment(source)
    assert result == {"PATH": "/bin"}


def test_timeout_terminates_exact_worker_and_returns_timeout(fake_process, request) -> None:
    result = CaseProcessRunner(process_factory=fake_process).run(request, 1)
    assert result.error_code == "case_timeout"
    assert fake_process.terminated and fake_process.waited_after_term == 2
```

另测 TERM 后正常退出不 kill、TERM 无效才 kill、非零退出、缺失/损坏 result、stdout/stderr 上限和后续 case 仍可运行。

- [x] **Step 2：运行失败测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_process_runner.py -v
```

- [x] **Step 3：实现 `shell=False` Worker 启动**

argv 固定为 `[sys.executable, "-m", "vera.evals.worker", "--request", ..., "--result", ...]`。环境只保留运行 Python 所需的明确 allowlist；cwd 固定为隔离 workspace；request/result 文件权限 `0600`。不得使用进程名匹配或 kill 进程组之外的对象。

- [x] **Step 4：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_process_runner.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/evals tests/evals
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/evals/process_runner.py tests/evals/test_process_runner.py docs/tasks/0016-eval-runner-and-scoring.md
git commit -m "feat: enforce evaluation worker timeouts"
```

---

### Task 5：原子证据包、SuiteRunner 与任务验收

**文件：**

- Create: `src/vera/evals/evidence.py`
- Create: `src/vera/evals/runner.py`
- Create: `tests/evals/test_evidence.py`
- Create: `tests/evals/test_runner.py`
- Create: `docs/evals/eval-runner-and-scoring.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/tasks/0016-eval-runner-and-scoring.md`

**接口：**

- Produces: `EvidenceWriter.publish(result, output_root) -> Path`
- Produces: `EvidenceError(code, path, message)`
- Produces: `EvalSuiteRunner.run_case(case_id, output_root=None) -> EvalReport`
- Produces: `EvalSuiteRunner.run_suite(case_ids, output_root=None) -> EvalSuiteReport`

- [x] **Step 1：编写不覆盖、权限、排序和套件继续测试**

```python
def test_suite_continues_after_failed_case(runner) -> None:
    report = runner.run_suite(("pass-case", "timeout-case", "second-pass"))
    assert [item.case_id for item in report.cases] == [
        "pass-case", "second-pass", "timeout-case"
    ]
    assert report.status is EvalStatus.FAIL


def test_evidence_writer_never_overwrites_existing_directory(writer, result, tmp_path) -> None:
    existing = tmp_path / result.report.evaluation_id
    existing.mkdir()
    with pytest.raises(EvidenceError, match="output_exists"):
        writer.publish(result, tmp_path)
```

再测 `0700/0600`、原子 rename、events/files 不含正文、失败 result 仍有 report、suite-report case 排序和 output 写失败返回结构化错误。

- [x] **Step 2：实现 Runner 与 Writer**

SuiteRunner 对每个 case 重新调用 CorpusLoader 和 FixtureIsolator，不能复用 workspace/state。EvidenceWriter 先写同父目录临时目录，fsync 后原子 rename 到 `<output_root>/<evaluation_id>`；只删除自己创建的临时目录。

- [x] **Step 3：运行完整质量门禁**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

- [x] **Step 4：记录证据、提交并本地合并**

```bash
git add src/vera/evals tests/evals docs/evals/eval-runner-and-scoring.md docs/STATUS.md docs/tasks/0016-eval-runner-and-scoring.md
git commit -m "test: verify evaluation runner and scoring"
git switch main
git merge --no-ff feature/eval-runner-scoring -m "merge: add Vera evaluation runner"
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" -q
git branch -d feature/eval-runner-scoring
```

无 remote 时不执行 push。确认 `main` 干净后才开始任务 0017。
