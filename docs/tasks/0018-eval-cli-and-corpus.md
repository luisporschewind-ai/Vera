# Vera Eval CLI 与 14 个冻结任务实施计划

> **供 Agent 执行：** REQUIRED SUB-SKILL: 使用 `superpowers:executing-plans` 按 Task 顺序实施；只使用一个主实现 Agent，每个生产增量独立提交。

**状态：** Planned

**目标分支：** `feature/eval-cli-corpus`

**目标：** 交付 `vera eval validate/list/run`，把 14 个冻结 Fake Model case 随 wheel 分发，并同时提供人类摘要、严格 JSON 和私有证据输出。

**架构：** Corpus 是 `vera.evals` 包内只读资源；manifest 由仓库脚本确定性生成并由 Loader 强制校验。`cli_eval.py` 只调用 EvalSuiteRunner，不装配真实 Provider；Presenter 只消费 EvalReport，不参与评分。

**技术栈：** Python 3.12、Typer、Pydantic 2、`importlib.resources`、pytest、Ruff、Mypy、uv。

**规格：** [阶段四评测与内部就绪](../specs/2026-09-12-evals-and-internal-readiness.md)

## 全局约束

- 依赖任务 0017 已合并。
- Corpus case ID、文件字节、期望 hash、Event 断言与 manifest 一起接受审阅；不得在运行时生成期望值。
- 每个 script 的 ModelTurn 和 approval 数量必须恰好消费完。
- `vera eval` 不调用 `build_runtime()`、`load_provider_environment()` 或 OpenAI-compatible Adapter。
- JSON stdout 恰好一个 JSON document；日志、进度和人类提示不能混入。
- 不运行 live、不读取真实 Key、不修改 `VeraTestDemo`。

---

### Task 1：加入正确性与普通对话的 5 个 case

**文件：**

- Create: `src/vera/evals/corpus/create-file/case.json`
- Create: `src/vera/evals/corpus/create-file/script.json`
- Create: `src/vera/evals/corpus/create-file/expect.json`
- Create: `src/vera/evals/corpus/create-file/workspace/README.md`
- Create: `src/vera/evals/corpus/update-file/case.json`
- Create: `src/vera/evals/corpus/update-file/script.json`
- Create: `src/vera/evals/corpus/update-file/expect.json`
- Create: `src/vera/evals/corpus/update-file/workspace/hello.txt`
- Create: `src/vera/evals/corpus/multi-file-edit/case.json`
- Create: `src/vera/evals/corpus/multi-file-edit/script.json`
- Create: `src/vera/evals/corpus/multi-file-edit/expect.json`
- Create: `src/vera/evals/corpus/multi-file-edit/workspace/first.txt`
- Create: `src/vera/evals/corpus/multi-file-edit/workspace/second.txt`
- Create: `src/vera/evals/corpus/plain-answer/case.json`
- Create: `src/vera/evals/corpus/plain-answer/script.json`
- Create: `src/vera/evals/corpus/plain-answer/expect.json`
- Create: `src/vera/evals/corpus/plain-answer/workspace/README.md`
- Create: `src/vera/evals/corpus/verification-passes/case.json`
- Create: `src/vera/evals/corpus/verification-passes/script.json`
- Create: `src/vera/evals/corpus/verification-passes/expect.json`
- Create: `src/vera/evals/corpus/verification-passes/workspace/check.txt`
- Create: `src/vera/evals/corpus/manifest.json`
- Create: `scripts/build_eval_manifest.py`
- Create: `tests/evals/test_corpus_correctness_cases.py`
- Create: `tests/evals/test_manifest_builder.py`

**接口：**

- Produces: case IDs `create-file`、`update-file`、`multi-file-edit`、`plain-answer`、`verification-passes`

- [x] **Step 1：先写期望行为测试**

```python
@pytest.mark.parametrize(
    "case_id",
    ["create-file", "update-file", "multi-file-edit", "plain-answer", "verification-passes"],
)
def test_correctness_case_passes_and_source_is_unchanged(eval_runner, corpus_loader, case_id) -> None:
    before = corpus_loader.validate().manifest_hash
    report = eval_runner.run_case(case_id)
    assert report.status is EvalStatus.PASS
    assert corpus_loader.validate().manifest_hash == before
```

另断言 create/update/multi 的精确 after hash；plain-answer 没有文件变化且产生 `assistant.message`；verification-passes 使用 `$VERA_EVAL_PYTHON -c` 并产生 `verification.completed`。

- [ ] **Step 2：创建冻结 JSON、workspace 字节和安全 manifest 工具**

每个 `expect.json` 明确列出 `allowed_changed_paths`、目标文件 SHA-256、允许的 terminal Event、required/forbidden Event。`plain-answer` 的 allowlist 为空；`verification-passes` 只允许 `check.txt` 的既定变化。不得用测试运行结果回填 hash，先用独立 `shasum -a 256` 核对预期字节。

Builder 只遍历 `src/vera/evals/corpus` 常规文件，排除 `manifest.json` 自身，拒绝 symlink/特殊文件，按 POSIX 相对路径排序并用原子替换写 manifest。`--check` 只比较计算值，不写文件；`--write` 是唯一写入模式。

- [x] **Step 3：运行 5 个 case 并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run python scripts/build_eval_manifest.py --write src/vera/evals/corpus
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run python scripts/build_eval_manifest.py --check src/vera/evals/corpus
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_corpus_correctness_cases.py tests/evals/test_manifest_builder.py -v
git add src/vera/evals/corpus scripts/build_eval_manifest.py tests/evals/test_corpus_correctness_cases.py tests/evals/test_manifest_builder.py docs/tasks/0018-eval-cli-and-corpus.md
git commit -m "test: add evaluation correctness corpus"
```

---

### Task 2：加入安全与 usage 的 4 个 case

**文件：**

- Create: `src/vera/evals/corpus/reject-keeps-original/case.json`
- Create: `src/vera/evals/corpus/reject-keeps-original/script.json`
- Create: `src/vera/evals/corpus/reject-keeps-original/expect.json`
- Create: `src/vera/evals/corpus/reject-keeps-original/workspace/hello.txt`
- Create: `src/vera/evals/corpus/path-escape-denied/case.json`
- Create: `src/vera/evals/corpus/path-escape-denied/script.json`
- Create: `src/vera/evals/corpus/path-escape-denied/expect.json`
- Create: `src/vera/evals/corpus/path-escape-denied/workspace/inside.txt`
- Create: `src/vera/evals/corpus/forbidden-command/case.json`
- Create: `src/vera/evals/corpus/forbidden-command/script.json`
- Create: `src/vera/evals/corpus/forbidden-command/expect.json`
- Create: `src/vera/evals/corpus/forbidden-command/workspace/check.txt`
- Create: `src/vera/evals/corpus/usage-null-safe/case.json`
- Create: `src/vera/evals/corpus/usage-null-safe/script.json`
- Create: `src/vera/evals/corpus/usage-null-safe/expect.json`
- Create: `src/vera/evals/corpus/usage-null-safe/workspace/README.md`
- Modify: `src/vera/evals/corpus/manifest.json`
- Create: `tests/evals/test_corpus_safety_cases.py`

**接口：**

- Produces: case IDs `reject-keeps-original`、`path-escape-denied`、`forbidden-command`、`usage-null-safe`

- [x] **Step 1：编写零写入、拒绝 Event 与 null usage 测试**

```python
def test_path_escape_case_denies_and_preserves_parent(eval_runner, eval_temp_root) -> None:
    sentinel = eval_temp_root / "outside.txt"
    sentinel.write_text("guard\n", encoding="utf-8")
    report = eval_runner.run_case("path-escape-denied")
    assert report.status is EvalStatus.PASS
    assert sentinel.read_text(encoding="utf-8") == "guard\n"


def test_missing_usage_remains_null(eval_runner) -> None:
    report = eval_runner.run_case("usage-null-safe")
    assert report.metrics.usage is None
```

另断言 reject 后原 hash 不变；forbidden command 没有 `verification.started` 且包含稳定 deny/rejected Event；四个 case 都没有期望外文件变化。

- [ ] **Step 2：创建只触发既有安全边界的冻结脚本**

`path-escape-denied` 使用 `../outside.txt` 作为模型工具参数，但 corpus 自身不得包含绝对路径。`forbidden-command` 使用固定 `rm -rf forbidden-target` argv 验证策略拒绝，测试不得实际启动该命令。usage case 的唯一 ModelTurn 显式 `usage: null`。

- [ ] **Step 3：运行 4 个 case 并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run python scripts/build_eval_manifest.py --write src/vera/evals/corpus
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run python scripts/build_eval_manifest.py --check src/vera/evals/corpus
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_corpus_safety_cases.py -v
git add src/vera/evals/corpus tests/evals/test_corpus_safety_cases.py docs/tasks/0018-eval-cli-and-corpus.md
git commit -m "test: add evaluation safety corpus"
```

---

### Task 3：加入回滚与恢复的 5 个 case，并冻结 manifest

**文件：**

- Create: `src/vera/evals/corpus/rollback-after-apply/case.json`
- Create: `src/vera/evals/corpus/rollback-after-apply/script.json`
- Create: `src/vera/evals/corpus/rollback-after-apply/expect.json`
- Create: `src/vera/evals/corpus/rollback-after-apply/workspace/hello.txt`
- Create: `src/vera/evals/corpus/resume-after-approval/case.json`
- Create: `src/vera/evals/corpus/resume-after-approval/script.json`
- Create: `src/vera/evals/corpus/resume-after-approval/expect.json`
- Create: `src/vera/evals/corpus/resume-after-approval/workspace/hello.txt`
- Create: `src/vera/evals/corpus/restore-partial-apply/case.json`
- Create: `src/vera/evals/corpus/restore-partial-apply/script.json`
- Create: `src/vera/evals/corpus/restore-partial-apply/expect.json`
- Create: `src/vera/evals/corpus/restore-partial-apply/workspace/hello.txt`
- Create: `src/vera/evals/corpus/restore-partial-apply/workspace/second.txt`
- Create: `src/vera/evals/corpus/in-flight-manual/case.json`
- Create: `src/vera/evals/corpus/in-flight-manual/script.json`
- Create: `src/vera/evals/corpus/in-flight-manual/expect.json`
- Create: `src/vera/evals/corpus/in-flight-manual/workspace/hello.txt`
- Create: `src/vera/evals/corpus/idempotent-resume/case.json`
- Create: `src/vera/evals/corpus/idempotent-resume/script.json`
- Create: `src/vera/evals/corpus/idempotent-resume/expect.json`
- Create: `src/vera/evals/corpus/idempotent-resume/workspace/hello.txt`
- Modify: `src/vera/evals/corpus/manifest.json`
- Create: `tests/evals/test_corpus_recovery_cases.py`

**接口：**

- Produces: case IDs `rollback-after-apply`、`resume-after-approval`、`restore-partial-apply`、`in-flight-manual`、`idempotent-resume`
- Produces: `scripts/build_eval_manifest.py --check|--write`

- [x] **Step 1：编写恢复事实和 manifest 可重复测试**

```python
@pytest.mark.parametrize(
    "case_id",
    [
        "rollback-after-apply", "resume-after-approval", "restore-partial-apply",
        "in-flight-manual", "idempotent-resume",
    ],
)
def test_recovery_case_passes(eval_runner, case_id) -> None:
    assert eval_runner.run_case(case_id).status is EvalStatus.PASS


def test_manifest_builder_check_matches_committed_manifest(corpus_root) -> None:
    assert manifest_main(("--check", str(corpus_root))) == 0
```

分别断言 rollback before hash、resume 单次 apply、partial restore 全部 before hash、in-flight 仅 inspect、idempotent 第二次 Resume 零新增副作用。

- [x] **Step 2：创建 5 个冻结 case 与安全 manifest 工具**

复用已经验收的 manifest Builder 更新完整 14-case 文件集合；不改变 Builder 规则。

- [x] **Step 3：生成并检查 14-case manifest**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run python scripts/build_eval_manifest.py --write src/vera/evals/corpus
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run python scripts/build_eval_manifest.py --check src/vera/evals/corpus
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/evals/test_corpus_recovery_cases.py tests/evals/test_manifest_builder.py -v
```

- [x] **Step 4：提交恢复 corpus**

```bash
git add src/vera/evals/corpus scripts/build_eval_manifest.py tests/evals docs/tasks/0018-eval-cli-and-corpus.md
git commit -m "test: freeze Vera offline evaluation corpus"
```

---

### Task 4：实现 `vera eval validate` 与 `list`

**文件：**

- Create: `src/vera/cli_eval.py`
- Modify: `src/vera/cli.py`
- Create: `tests/cli/test_eval_validate.py`
- Create: `tests/cli/test_eval_list.py`

**接口：**

- Produces: Typer subgroup `eval_app`
- Produces: `vera eval validate [--json]`
- Produces: `vera eval list [--json]`

- [ ] **Step 1：编写无 Provider 配置和排序测试**

```python
def test_eval_list_needs_no_provider(cli_runner, monkeypatch) -> None:
    monkeypatch.setattr("vera.bootstrap.build_runtime", forbidden_call)
    monkeypatch.setattr("vera.config.load_provider_environment", forbidden_call)
    result = cli_runner.invoke(app, ["eval", "list", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert [item["case_id"] for item in payload["cases"]] == sorted(
        item["case_id"] for item in payload["cases"]
    )
    assert len(payload["cases"]) == 14
```

另测 validate manifest hash、人类表格、JSON 无 ANSI/提示符、损坏 corpus 退出 5、未知参数和从非仓库 cwd 运行。

- [ ] **Step 2：实现独立 CLI 装配**

`cli.py` 只注册 `eval_app`；所有逻辑在 `cli_eval.py`。validate/list 仅创建 CorpusLoader，不读取用户配置或状态目录。人类 Presenter 显示 case ID、tags、timeout；JSON 使用版本化结构。

- [ ] **Step 3：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/cli/test_eval_validate.py tests/cli/test_eval_list.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/cli.py src/vera/cli_eval.py tests/cli
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/cli.py src/vera/cli_eval.py tests/cli docs/tasks/0018-eval-cli-and-corpus.md
git commit -m "feat: list and validate Vera evaluations"
```

---

### Task 5：实现 `vera eval run`、wheel 资源与任务验收

**文件：**

- Modify: `src/vera/cli_eval.py`
- Modify: `pyproject.toml`
- Create: `tests/cli/test_eval_run.py`
- Create: `tests/evals/test_packaged_corpus.py`
- Create: `docs/evals/eval-cli-and-corpus.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/tasks/0018-eval-cli-and-corpus.md`

**接口：**

- Produces: `vera eval run <case_id> [--json] [--output PATH]`
- Produces: `vera eval run --suite offline [--json] [--output PATH]`
- Guarantee: case ID 与 `--suite` 恰好选择一个

- [ ] **Step 1：编写退出码、单 JSON、取消和 wheel 资源测试**

```python
def test_eval_suite_json_is_one_document_without_ansi(cli_runner, isolated_env) -> None:
    result = cli_runner.invoke(app, ["eval", "run", "--suite", "offline", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert len(payload["cases"]) == 14
    assert "\x1b" not in result.stdout


def test_eval_run_rejects_case_and_suite_together(cli_runner) -> None:
    result = cli_runner.invoke(app, ["eval", "run", "plain-answer", "--suite", "offline"])
    assert result.exit_code == 5
```

再测 pass=0、断言失败/timeout=4、语料/输出错误=5、Ctrl+C=2、output 不覆盖、默认私有目录、供应商变量清除、从 wheel 安装环境发现 14 个 case。

- [ ] **Step 2：实现 Runner Presenter 与包资源配置**

CLI 默认 output root 取 `user_state_path("Vera") / "evals"`，但不调用 `load_config`。Human Presenter 只显示 case、状态、分数、reason code、duration/usage 和证据路径；不能显示事件 payload 或文件正文。构建配置必须让 `src/vera/evals/corpus/**` 进入 wheel/sdist。

- [ ] **Step 3：运行完整质量门禁**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests scripts
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests scripts
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

- [ ] **Step 4：记录证据、提交并本地合并**

```bash
git add src/vera/cli.py src/vera/cli_eval.py src/vera/evals/corpus pyproject.toml tests docs/evals/eval-cli-and-corpus.md docs/STATUS.md docs/tasks/0018-eval-cli-and-corpus.md
git commit -m "test: verify Vera offline evaluation CLI"
git switch main
git merge --no-ff feature/eval-cli-corpus -m "merge: add Vera offline evaluation corpus"
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" -q
git branch -d feature/eval-cli-corpus
```

无 remote 时不执行 push。验收记录必须包含 14 个 case ID、manifest hash、CLI 退出码矩阵、wheel 内容和未执行 live。确认 `main` 干净后才开始任务 0019。
