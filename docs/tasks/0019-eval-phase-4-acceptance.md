# Vera 阶段四评测与内部就绪验收实施计划

> **供 Agent 执行：** REQUIRED SUB-SKILL: 使用 `superpowers:executing-plans` 按 Task 顺序实施；只使用一个主实现 Agent。本任务只补总验收缺口，不扩大产品范围。

**状态：** Planned

**目标分支：** `feature/eval-phase-4-acceptance`

**目标：** 对阶段四规格的 14 条退出条件建立端到端证据，确认 14-case 离线套件可重复、可安装、超时可控、凭据隔离，并封存阶段四。

**架构：** Phase4 E2E 从 CorpusLoader 和 EvalSuiteRunner 进入，只观察结构化报告与证据包；安全负例验证 Worker 环境、manifest、路径、timeout 和输出协议；wheel smoke 在仓库外临时环境运行 `vera eval`。本任务不新增评测维度或 case。

**技术栈：** Python 3.12、pytest、Typer CliRunner、subprocess、uv、Ruff、Mypy。

**规格：** [阶段四评测与内部就绪](../specs/2026-09-12-evals-and-internal-readiness.md)

## 全局约束

- 依赖任务 0015–0018 已合并。
- 14 个 case ID 和 manifest 已冻结；验收只能修复实现缺陷，不能为了通过而放宽 expect。
- 不增加 live 标志、不读取用户配置文件、不访问网络、不修改用户工程。
- 测试产物只写 pytest tmp_path、`/private/tmp` 或显式临时目录。
- 不运行 `tests/live`，不读取真实 DeepSeek/GLM Key，不修改 `VeraTestDemo`。

---

### Task 1：建立阶段四完整离线 E2E

**文件：**

- Create: `tests/e2e/test_phase_4_offline_evals.py`
- Create: `tests/e2e/test_phase_4_eval_cli.py`

**接口：**

- Evidence: 14 个 case 全部通过且四类 tag 均覆盖
- Evidence: 评分不解析 CLI/TUI/Stream Frame

- [x] **Step 1：编写总套件和 Core 边界测试**

```python
def test_phase4_offline_suite_passes_all_frozen_cases(eval_runner, corpus_loader) -> None:
    report = eval_runner.run_suite(tuple(case.case_id for case in corpus_loader.list_cases()))
    assert report.status is EvalStatus.PASS
    assert len(report.cases) == 14
    assert {tag for case in corpus_loader.list_cases() for tag in case.tags} == {
        EvalTag.CORRECTNESS, EvalTag.SAFETY, EvalTag.RECOVERY, EvalTag.CONVERSATION
    }


def test_eval_package_has_no_human_presenter_dependency() -> None:
    imported = imported_modules_under(Path("src/vera/evals"))
    assert "vera.cli_presenter" not in imported
    assert not any(name.startswith("vera.terminal") for name in imported)
```

`imported_modules_under()` 使用 AST 静态读取 `import` / `from ... import ...`，不导入目标模块；这样边界断言覆盖会在独立 Worker 进程加载的代码，而不是依赖无法跨进程传播的 monkeypatch。CLI E2E 参数化 validate/list/single/suite、人类/JSON、输出路径和退出码；断言 JSON 可由 `json.loads` 一次完整解析且前后无额外字符。

- [x] **Step 2：运行 E2E 并修复实现缺口**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/e2e/test_phase_4_offline_evals.py tests/e2e/test_phase_4_eval_cli.py -v
```

只修复与已接受规格不一致的实现；若发现规格本身需要改变，停止代码修改并先更新规格/ADR。

- [x] **Step 3：提交 E2E**

```bash
git add tests/e2e src/vera/evals src/vera/cli_eval.py docs/tasks/0019-eval-phase-4-acceptance.md
git commit -m "test: cover phase four evaluation flow"
```

---

### Task 2：补齐 timeout、秘密、Corpus 和证据负例

**文件：**

- Create: `tests/e2e/test_phase_4_eval_safety.py`
- Modify: `tests/conftest.py`

**接口：**

- Evidence: timeout 后套件继续
- Evidence: Provider 文件和环境永不读取
- Evidence: corpus/source/output 边界失败关闭

- [x] **Step 1：编写进程与凭据哨兵测试**

```python
def test_timeout_case_does_not_block_following_case(eval_runner_with_timeout) -> None:
    report = eval_runner_with_timeout.run_suite(("hang", "plain-answer"))
    assert report.case("hang").reason_codes == ("case_timeout",)
    assert report.case("plain-answer").status is EvalStatus.PASS


def test_eval_never_reads_provider_file(tmp_path, monkeypatch, cli_runner) -> None:
    provider_file = tmp_path / "must-not-read.env"
    provider_file.write_text("DEEPSEEK_API_KEY=sentinel-secret\n", encoding="utf-8")
    provider_file.chmod(0)
    monkeypatch.setenv("VERA_PROVIDER_ENV_FILE", str(provider_file))
    result = cli_runner.invoke(app, ["eval", "run", "plain-answer", "--json"])
    assert result.exit_code == 0
    assert "sentinel-secret" not in result.stdout
```

再测 symlink/FIFO、manifest mismatch、路径穿越、已有 output、不完整 Worker result、超大 stderr 截断、TERM→kill、源 corpus hash 前后不变和证据不含 workspace 正文。

- [x] **Step 2：运行安全负例并修复缺口**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/e2e/test_phase_4_eval_safety.py tests/evals/test_process_runner.py tests/evals/test_corpus.py -v
```

- [x] **Step 3：提交安全验收**

```bash
git add tests/conftest.py tests/e2e/test_phase_4_eval_safety.py src/vera/evals docs/tasks/0019-eval-phase-4-acceptance.md
git commit -m "test: harden offline evaluation boundaries"
```

---

### Task 3：验证重复运行与 wheel 安装

**文件：**

- Create: `tests/e2e/test_phase_4_repeatability.py`
- Create: `tests/e2e/test_phase_4_wheel_smoke.py`

**接口：**

- Evidence: 两次 suite canonical projection 相同
- Evidence: 仓库外安装 wheel 后可发现并运行 14 个 case

- [x] **Step 1：编写双跑和安装产物测试**

```python
def test_offline_suite_is_repeatable(eval_runner) -> None:
    first = eval_runner.run_suite(ALL_CASE_IDS)
    second = eval_runner.run_suite(ALL_CASE_IDS)
    comparison = CanonicalComparator().compare(first, second)
    assert comparison.equal, comparison.differences


def test_built_wheel_contains_runnable_corpus(installed_vera) -> None:
    listed = installed_vera.run("eval", "list", "--json")
    assert listed.exit_code == 0
    assert len(json.loads(listed.stdout)["cases"]) == 14
    run = installed_vera.run("eval", "run", "plain-answer", "--json")
    assert run.exit_code == 0
```

wheel 测试使用临时 venv、临时 HOME/state/output，显式移除供应商变量并禁止网络；使用 `python -m pip install --no-index <本轮本地 wheel>`，不得访问索引或安装仓库外制品。

- [x] **Step 2：运行重复性与 wheel smoke**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/e2e/test_phase_4_repeatability.py tests/e2e/test_phase_4_wheel_smoke.py -v
```

- [x] **Step 3：提交可重复性证据测试**

```bash
git add tests/e2e/test_phase_4_repeatability.py tests/e2e/test_phase_4_wheel_smoke.py docs/tasks/0019-eval-phase-4-acceptance.md
git commit -m "test: verify repeatable packaged evaluations"
```

---

### Task 4：运行完整质量门禁和无网络人工 Smoke

**文件：**

- Create: `docs/evals/phase-4-evals-and-internal-readiness.md`
- Modify: `README.md`

- [ ] **Step 1：运行完整自动门禁**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests scripts
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests scripts
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run python scripts/build_eval_manifest.py --check src/vera/evals/corpus
git diff --check
```

要求全部退出码 0、覆盖率至少 90%、14 case 通过、2 个既有 live 测试或实际数量明确 deselected。

- [ ] **Step 2：在仓库外执行本地 wheel smoke**

使用 `mktemp -d` 创建精确临时根，在其中创建临时 venv、HOME、state 和 output；清除所有供应商变量，只安装 `dist/` 本轮 wheel，然后运行：

```bash
vera eval validate --json
vera eval list --json
vera eval run plain-answer --json --output ./evidence
vera eval run --suite offline --json --output ./suite-evidence
```

记录退出码、14-case 数量、manifest hash、证据权限和 JSON 解析结果；不保留临时 workspace 正文。

- [ ] **Step 3：建立 14 条退出条件证据表**

`docs/evals/phase-4-evals-and-internal-readiness.md` 必须逐条映射规格退出条件到测试文件、命令和现场结果，并单列：未运行 live、未读取真实 Key、未修改 VeraTestDemo、Worker 不是 OS 沙箱、无 remote 未推送。

- [ ] **Step 4：更新 README 的评测使用说明**

README 只增加 `vera eval validate/list/run` 的最小示例、离线性质、证据路径和退出码；不得把 Fake suite 描述为真实模型质量证明。

---

### Task 5：封存阶段四并本地合并

**文件：**

- Modify: `docs/ROADMAP.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/tasks/phase-4-execution-order.md`
- Modify: `docs/tasks/0019-eval-phase-4-acceptance.md`
- Modify: `docs/PRODUCT.md`

- [ ] **Step 1：只在证据完整后更新状态**

将任务 0019 改为 `Done`、阶段四执行顺序改为 `Complete`、ROADMAP 阶段四改为 `Complete`；STATUS 记录真实测试数、覆盖率、manifest hash、wheel smoke 和下一阶段为阶段五桌面集成。PRODUCT 只把“固定离线评测集”移入已接受能力，不提前选择桌面框架。

- [ ] **Step 2：提交阶段验收**

```bash
git add README.md docs/PRODUCT.md docs/ROADMAP.md docs/STATUS.md docs/evals/phase-4-evals-and-internal-readiness.md docs/tasks/phase-4-execution-order.md docs/tasks/0019-eval-phase-4-acceptance.md
git commit -m "test: verify Vera phase four readiness"
```

- [ ] **Step 3：最终检查并本地合并**

```bash
git diff --check
git status --short --branch
git switch main
git merge --no-ff feature/eval-phase-4-acceptance -m "merge: complete Vera phase four evaluations"
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests scripts
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git branch -d feature/eval-phase-4-acceptance
```

无 remote 时不执行 push。阶段四完成后停止，不自动开始阶段五桌面框架选型。
