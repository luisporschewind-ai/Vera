# Vera 交互式 CLI 会话实施计划

> **供执行 Agent 使用：** 必须使用 `superpowers:executing-plans` 按任务逐项实施本计划；用户已明确要求不派发子 Agent。每个步骤使用复选框跟踪。

**状态：** Complete

**当前执行分支：** `codex/interactive-cli-session`

**目标：** 在现有 `VeraRuntime` 上实现可从任意工程目录直接启动的持续交互式 `vera` CLI，完整驱动多道审批、写入、验证和持久化手动回滚。

**架构：** 保持 `Command -> VeraRuntime -> Event` 为唯一产品边界。新增一个与终端无关的 run 驱动器处理重复审批，一个交互会话层处理提示符与斜杠命令，一个展示层渲染人类可读 Event；CLI 不复制 Runtime 状态或文件写入逻辑。

**技术栈：** Python 3.12、Typer、Pydantic 2、Rich、uv、pytest、Ruff、Mypy。

**规格：** [`docs/specs/2026-09-10-interactive-cli-session.md`](../specs/2026-09-10-interactive-cli-session.md)

## 全局约束

- 只修改 `/Users/admin/Vera`；自动测试不得修改 `/Users/admin/Desktop/VeraTestDemo`。
- 保持 Python `>=3.12,<3.13`、现有 `src/` 布局和单 Python 发行包。
- `VeraRuntime` 继续独占审批、Checkpoint、写入、验证、回滚和 Event 权威。
- CLI 只发送版本化 Command、消费 Event 和收集用户输入，不能直接写用户工程。
- 每个自然语言输入创建独立 run；同一 CLI 会话不共享完整模型消息历史。
- `vera run ... --json` 保持严格非交互，遇到审批必须取消。
- 供应商环境文件只做严格键值解析，不能 `source`、`eval` 或调用 Shell。
- 非 live 测试通过全局 fixture 清除供应商变量并把环境文件重定向到临时路径，绝不读取或使用用户真实 API Key。
- Change Set 和命令审批保持分离，不增加自动批准入口。
- 人工 iOS 验收暂缓；实施过程只运行 Fake Model 和临时工作区自动测试。
- 每项生产行为必须先观察对应测试按预期失败，再写最小实现并观察通过。
- 每个任务通过局部检查后独立提交；最终合并前执行完整非 live 验收。

## 计划文件结构

```text
src/vera/
├── bootstrap.py                 # 加载私有供应商环境并装配 Runtime
├── cli.py                       # Typer 入口和命令兼容层
├── cli_driver.py                # Command/Event 多审批驱动器
├── cli_presenter.py             # 人类 Event 展示
├── cli_session.py               # 持续提示符和斜杠命令
├── config.py                    # 严格供应商环境文件解析
├── persistence/
│   ├── journal.py               # 追加既有 run Event
│   └── run_store.py             # 会话查询复用
├── runtime/
│   ├── context.py               # 验证进度状态
│   └── engine.py                # 多审批续跑与持久化回滚
└── workspace/checkpoint.py      # 无工作区实例读取 Manifest

tests/
├── cli/
│   ├── fakes.py
│   ├── test_driver.py
│   ├── test_presenter.py
│   ├── test_session.py
│   ├── test_entrypoint.py
│   └── test_rollback.py
├── persistence/test_run_store.py
├── runtime/test_safe_editing_flow.py
└── test_config.py
```

---

### Task 1：安全加载私有供应商环境文件

**文件：**

- Modify: `src/vera/config.py`
- Modify: `src/vera/bootstrap.py`
- Modify: `tests/test_config.py`

**接口：**

- Produces: `load_provider_environment(path: Path | None = None) -> None`
- Consumes: `VERA_PROVIDER_ENV_FILE`、默认 `~/.config/vera/deepseek.env`
- Guarantee: 当前进程已有变量优先；文件内容不回显；不执行 Shell

- [x] **Step 1：编写严格解析和权限失败测试**

```python
def test_provider_environment_loads_known_values_without_overwriting_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "deepseek.env"
    source.write_text(
        "export DEEPSEEK_API_KEY=file-secret\n"
        "VERA_DEEPSEEK_BASE_URL=https://api.deepseek.com\n"
        "VERA_DEEPSEEK_MODEL=deepseek-flash\n",
        encoding="utf-8",
    )
    source.chmod(0o600)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "process-secret")
    load_provider_environment(source)
    assert os.environ["DEEPSEEK_API_KEY"] == "process-secret"
    assert os.environ["VERA_DEEPSEEK_MODEL"] == "deepseek-flash"


def test_provider_environment_rejects_public_permissions(tmp_path: Path) -> None:
    source = tmp_path / "deepseek.env"
    source.write_text("DEEPSEEK_API_KEY=secret\n", encoding="utf-8")
    source.chmod(0o644)
    with pytest.raises(UnsafeProviderEnvironment):
        load_provider_environment(source)


def test_provider_environment_rejects_shell_syntax(tmp_path: Path) -> None:
    source = tmp_path / "deepseek.env"
    source.write_text("DEEPSEEK_API_KEY=$(whoami)\n", encoding="utf-8")
    source.chmod(0o600)
    with pytest.raises(UnsafeProviderEnvironment):
        load_provider_environment(source)
```

- [x] **Step 2：运行测试并确认因接口不存在而失败**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/test_config.py -v
```

预期：FAIL，导入 `load_provider_environment` 或 `UnsafeProviderEnvironment` 失败。

- [x] **Step 3：实现无 Shell 的已知键解析器**

在 `config.py` 中定义允许键集合：

```python
_PROVIDER_ENV_KEYS = frozenset(
    {
        "DEEPSEEK_API_KEY",
        "VERA_DEEPSEEK_BASE_URL",
        "VERA_DEEPSEEK_MODEL",
        "GLM_API_KEY",
        "VERA_GLM_BASE_URL",
        "VERA_GLM_MODEL",
    }
)


class UnsafeProviderEnvironment(ValueError):
    """Raised when a private provider environment file is unsafe or malformed."""


def load_provider_environment(path: Path | None = None) -> None:
    source = path or Path(
        os.environ.get(
            "VERA_PROVIDER_ENV_FILE",
            str(Path.home() / ".config" / "vera" / "deepseek.env"),
        )
    )
    if not source.exists():
        return
    if os.name == "posix" and source.stat().st_mode & 0o077:
        raise UnsafeProviderEnvironment("provider environment file must use mode 0600")
    for line_number, raw in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        name, separator, value = line.partition("=")
        if not separator or name not in _PROVIDER_ENV_KEYS:
            raise UnsafeProviderEnvironment(f"invalid provider setting at line {line_number}")
        if any(token in value for token in ("`", "$(", "${")):
            raise UnsafeProviderEnvironment(f"shell syntax is forbidden at line {line_number}")
        os.environ.setdefault(name, value.strip().strip("'\""))
```

`bootstrap.build_runtime` 在 `load_config` 前调用此函数。解析器不得支持变量展开、命令替换、多行值或未知变量。

- [x] **Step 4：运行测试、Ruff 和 Mypy**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/test_config.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/config.py src/vera/bootstrap.py tests/test_config.py
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Task 1**

```bash
git add src/vera/config.py src/vera/bootstrap.py tests/test_config.py docs/tasks/0003-interactive-cli-session.md
git commit -m "feat: load private provider environment"
```

---

### Task 2：修复 Runtime 的多道验证审批续跑

**文件：**

- Modify: `src/vera/runtime/context.py`
- Modify: `src/vera/runtime/engine.py`
- Modify: `tests/runtime/test_safe_editing_flow.py`

**接口：**

- Produces: `RunContext.verification_index: int`
- Produces: `RunContext.verification_failed: bool`
- Guarantee: 每条验证命令只执行或拒绝一次，审批后从下一条继续

- [x] **Step 1：编写批准验证命令后正常终止的失败测试**

创建包含一项需要审批的 `VerificationCommand` 的 Change Set。批准 Change Set 后取得第二个 `approval.required`，再批准命令：

```python
command_events = list(runtime.handle(resolve(command_approval, "approve")))
assert [event.type for event in command_events] == [
    "approval.resolved",
    "verification.completed",
    "run.completed",
]
assert not any(event.type == "approval.required" for event in command_events)
```

另写拒绝命令测试，断言命令未执行、文件保持已应用状态、最后为 `run.completed` 且状态是 `verification_failed`。

- [x] **Step 2：运行目标测试并确认重复审批或非法状态失败**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/runtime/test_safe_editing_flow.py -v
```

- [x] **Step 3：用显式验证游标实现续跑**

`_verify` 从 `context.verification_index` 开始。自动允许、禁止、批准或拒绝一条命令后都把游标推进一次；失败状态累计到 `verification_failed`。命令审批拒绝不能进入通用 Change Set 取消分支：

```python
if request.kind == ApprovalKind.COMMAND.value:
    if decision == "reject":
        context.verification_failed = True
        context.pending_command = None
        context.verification_index += 1
        yield self._event(context, "verification.completed", {"status": "rejected"})
    else:
        yield from self._run_pending_verification(context)
    yield from self._verify(context)
    return
```

`run.started` Payload 同时记录 `workspace_root` 和 `model_profile`，使 run 摘要与持久化诊断准确。

- [x] **Step 4：运行 Runtime 测试和静态检查**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/runtime -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/runtime tests/runtime
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Task 2**

```bash
git add src/vera/runtime/context.py src/vera/runtime/engine.py tests/runtime/test_safe_editing_flow.py docs/tasks/0003-interactive-cli-session.md
git commit -m "fix: continue runs across verification approvals"
```

---

### Task 3：提取可复用的 Command/Event run 驱动器

**文件：**

- Create: `src/vera/cli_driver.py`
- Create: `tests/cli/fakes.py`
- Create: `tests/cli/test_driver.py`
- Modify: `src/vera/cli.py`

**接口：**

- Produces: `drive_run(runtime, start, decide, on_events) -> tuple[EventEnvelope, ...]`
- Produces: `ApprovalDecision = Literal["approve", "reject", "cancel"]`
- Consumes: `Callable[[EventEnvelope], ApprovalDecision]`
- Consumes: `Callable[[tuple[EventEnvelope, ...]], None]`，每个 Event batch 产生后立即调用

- [x] **Step 1：编写连续两道审批的驱动器失败测试**

使用真实 `VeraRuntime`、Fake Model 和临时工作区，脚本化决定为 `approve, approve`：

```python
events = drive_run(runtime, start, lambda _event: decisions.pop(0), batches.append)
assert [event.type for event in events].count("approval.required") == 2
assert events[-1].type == "run.completed"
assert target.read_text(encoding="utf-8") == "new\n"
```

再测试 `cancel` 映射为 `CancelRun`，目标文件保持不变。

- [x] **Step 2：运行测试并确认模块不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/cli/test_driver.py -v
```

- [x] **Step 3：实现无终端依赖的驱动循环**

```python
def drive_run(
    runtime: VeraRuntime,
    start: StartRun,
    decide: Callable[[EventEnvelope], ApprovalDecision],
    on_events: Callable[[tuple[EventEnvelope, ...]], None],
) -> tuple[EventEnvelope, ...]:
    events: list[EventEnvelope] = []
    command: CoreCommand = start
    while True:
        batch = tuple(runtime.handle(command))
        events.extend(batch)
        on_events(batch)
        approval = next((event for event in reversed(batch) if event.type == "approval.required"), None)
        if approval is None:
            return tuple(events)
        decision = decide(approval)
        if decision == "cancel":
            command = CancelRun(run_id=approval.run_id)
        else:
            command = ResolveApproval(
                run_id=approval.run_id,
                approval_id=str(approval.payload["approval_id"]),
                target_hash=str(approval.payload["target_hash"]),
                decision=decision,
            )
```

实现必须把每个 batch 立即交给可选的 `on_events` 回调，保证用户在输入审批前已经看到 Diff；不能等整个 run 结束才统一渲染。`cli.execute_run` 改为复用该驱动器，JSON 模式的决定函数固定返回 `cancel`。

- [x] **Step 4：运行驱动器和既有 CLI 测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/cli -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/cli.py src/vera/cli_driver.py tests/cli
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Task 3**

```bash
git add src/vera/cli.py src/vera/cli_driver.py tests/cli docs/tasks/0003-interactive-cli-session.md
git commit -m "feat: drive runs through repeated approvals"
```

---

### Task 4：实现跨进程的持久化手动回滚

**文件：**

- Modify: `src/vera/workspace/checkpoint.py`
- Modify: `src/vera/runtime/engine.py`
- Modify: `src/vera/cli.py`
- Modify: `tests/conftest.py`
- Modify: `tests/runtime/test_safe_editing_flow.py`
- Modify: `tests/cli/test_rollback.py`

**接口：**

- Produces: `CheckpointStore.load_manifest(state_dir: Path, run_id: str) -> CheckpointManifest`
- Consumes: `RollbackRun(run_id=...)` on a newly created `VeraRuntime`
- Guarantee: 回滚冲突不覆盖用户后续修改

- [x] **Step 1：编写新 Runtime 实例回滚的失败测试**

```python
first_runtime = make_runtime(state_dir, scripted_change)
run_id = apply_change(first_runtime, workspace)
second_runtime = make_runtime(state_dir, no_model_calls)
events = list(second_runtime.handle(RollbackRun(run_id=run_id)))
assert events[-1].type == "rollback.completed"
assert target.read_text(encoding="utf-8") == "old\n"
```

另测修改后的目标已被用户再次编辑时，返回 `rollback.conflicted` 且保留用户字节；不存在 run 时 CLI 明确输出“未找到可回滚的 Checkpoint”并返回非零，不创建伪造的 run 目录。

- [x] **Step 2：运行目标测试并确认新 Runtime 找不到内存 context**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/runtime/test_safe_editing_flow.py tests/cli/test_rollback.py -v
```

- [x] **Step 3：从 Manifest 重建回滚所需边界**

当 `self.runs` 没有 context 时，`VeraRuntime._rollback` 直接读取 Manifest：

```python
manifest = CheckpointStore.load_manifest(self.state_dir, run_id)
paths = WorkspacePaths(manifest.workspace_root)
store = CheckpointStore(self.state_dir, paths)
result = ChangeApplier(paths, store).rollback(manifest)
journal = EventJournal(self.state_dir, run_id, Redactor([]))
yield journal.append(event_type, payload)
```

只恢复文件和追加回滚 Event，不重建模型消息、待审批或状态机。Manifest 缺失时 Runtime 不创建新 Journal，CLI 将空结果映射为“未找到可回滚的 Checkpoint”和退出码 `5`；Manifest 损坏或工作区不存在时，在既有 Journal 追加 `rollback.conflicted`，Payload 状态为 `recovery_required`。

- [x] **Step 4：运行回滚、Journal 和 Workspace 测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/runtime/test_safe_editing_flow.py tests/cli/test_rollback.py tests/persistence tests/workspace -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/runtime src/vera/persistence src/vera/workspace tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Task 4**

```bash
git add src/vera/cli.py src/vera/runtime/engine.py src/vera/workspace/checkpoint.py tests/conftest.py tests/runtime/test_safe_editing_flow.py tests/cli/test_rollback.py docs/tasks/0003-interactive-cli-session.md
git commit -m "feat: rollback persisted runs after restart"
```

---

### Task 5：实现人类可审阅的 Event 展示层

**文件：**

- Create: `src/vera/cli_presenter.py`
- Create: `tests/cli/test_presenter.py`
- Modify: `src/vera/cli.py`

**接口：**

- Produces: `HumanPresenter.write_events(events: Sequence[EventEnvelope]) -> None`
- Produces: `HumanPresenter.approval_prompt(event: EventEnvelope) -> str`
- Consumes: 注入的 `write: Callable[[str], None]`

- [x] **Step 1：编写 Diff、命令风险和终态展示失败测试**

```python
presenter.write_events([changeset_event])
text = "\n".join(output)
assert "VeraTestDemo/ViewController.swift" in text
assert "-        view.backgroundColor = .blue" in text
assert "+        view.backgroundColor = .green" in text
assert changeset_hash in text
```

命令审批测试断言完整 argv、cwd、风险和“当前系统用户权限”提示存在；普通 `tool.completed` 不输出读取到的文件正文。

- [x] **Step 2：运行测试并确认 presenter 尚不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/cli/test_presenter.py -v
```

- [x] **Step 3：按 Event 类型实现稳定的人类展示**

只读取 Event Payload，不重新读取项目文件或生成 Diff。未知 Event 使用简短 `event.type` 回退；JSON 模式继续使用原始 `model_dump_json()`，不经过 Presenter。

- [x] **Step 4：运行展示与 CLI 测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/cli/test_presenter.py tests/cli/test_run.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/cli_presenter.py src/vera/cli.py tests/cli
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Task 5**

```bash
git add src/vera/cli.py src/vera/cli_presenter.py tests/cli/test_presenter.py tests/cli/test_run.py docs/tasks/0003-interactive-cli-session.md
git commit -m "feat: render reviewable CLI events"
```

---

### Task 6：实现持续交互会话和斜杠命令

**文件：**

- Create: `src/vera/cli_session.py`
- Create: `tests/cli/test_session.py`
- Modify: `src/vera/cli.py`

**接口：**

- Produces: `InteractiveSession.run() -> int`
- Consumes: 一个 `RuntimeDependencies`、规范化工作区、模型名称、`SessionIO`
- Produces: `/help`、`/runs`、`/show`、`/rollback`、`/exit`、`/quit`

- [x] **Step 1：编写两个连续 run 和斜杠命令的失败测试**

使用内存 `SessionIO` 输入：空行、第一条任务、审批、第二条任务、拒绝、`/runs`、未知命令、`/exit`。断言：

```python
assert started_goals == ["first task", "second task"]
assert output.count("Vera >") >= 3
assert "未知命令" in output
assert session.run() == 0
```

另测 EOF 正常退出、任务失败后重新出现提示符，以及 `/show`、`/rollback` 不调用模型。

- [x] **Step 2：运行测试并确认会话模块不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/cli/test_session.py -v
```

- [x] **Step 3：实现可注入 IO 的会话循环**

```python
class SessionIO(Protocol):
    def read(self, prompt: str) -> str: ...
    def write(self, text: str) -> None: ...


class InteractiveSession:
    def run(self) -> int:
        self._write_banner()
        while True:
            try:
                value = self.io.read("Vera > ").strip()
            except EOFError:
                return 0
            if not value:
                continue
            if value in {"/exit", "/quit"}:
                return 0
            if value.startswith("/"):
                self._handle_command(value)
                continue
            self._run_goal(value)
```

审批读取只接受 `approve`、`reject`、`cancel`；无效输入重复提示，不发送 Command。`KeyboardInterrupt` 按规格区分提示符和审批边界。

- [x] **Step 4：运行全部会话测试和静态检查**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/cli/test_session.py tests/cli/test_driver.py tests/cli/test_presenter.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/cli_session.py tests/cli
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Task 6**

```bash
git add src/vera/cli_session.py src/vera/cli.py tests/cli/test_session.py docs/tasks/0003-interactive-cli-session.md
git commit -m "feat: add persistent interactive CLI session"
```

---

### Task 7：把 `vera` 空命令接入交互会话

**文件：**

- Modify: `src/vera/cli.py`
- Create: `tests/cli/test_entrypoint.py`
- Modify: `tests/cli/test_run.py`
- Modify: `README.md`

**接口：**

- Produces: `vera [--workspace PATH] [--model PROFILE]`
- Preserves: `vera run`、`vera runs`、`vera rollback`、`vera config`

- [x] **Step 1：编写根命令启动和子命令兼容失败测试**

通过 Typer `CliRunner` 注入测试依赖，输入 `/exit`：

```python
result = runner.invoke(app, ["--workspace", str(tmp_path)], input="/exit\n")
assert result.exit_code == 0
assert str(tmp_path.resolve()) in result.stdout
assert "Vera >" in result.stdout
```

同时断言 `vera --help` 仍列出四个原有子命令，`vera run ... --json` 不出现 `Vera >` 或审批提示。

- [x] **Step 2：运行测试并确认根命令仍只显示帮助**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/cli/test_entrypoint.py tests/cli/test_run.py -v
```

- [x] **Step 3：使用 Typer callback 装配会话**

把根应用设置为 `invoke_without_command=True`。Callback 只在 `ctx.invoked_subcommand is None` 时构建 Runtime 和启动 `InteractiveSession`；任何子命令路径都不重复启动会话。工作区在传给 Core 前调用 `resolve()` 并验证为目录。

- [x] **Step 4：运行全部 CLI 测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/cli -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests/cli
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Task 7**

```bash
git add src/vera/cli.py tests/cli/test_entrypoint.py tests/cli/test_run.py README.md docs/tasks/0003-interactive-cli-session.md
git commit -m "feat: enter interactive mode with vera"
```

---

### Task 8：完成自动验收、安装与文档收口

**文件：**

- Create: `docs/evals/interactive-cli-session.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/tasks/0003-interactive-cli-session.md`
- Modify: `README.md`

**接口：**

- Consumes: 完成交互 CLI 的 Python 包
- Produces: 可从仓库外执行的 `vera` 命令和可复核验收证据

- [x] **Step 1：运行完整非 live 验收**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

预期：全部命令退出码为 `0`；live 测试以明确 deselected 或 skip 形式保留；`VeraTestDemo` 未被自动测试触碰。

- [x] **Step 2：安装 editable tool 并从临时工程验证启动**

```bash
uv tool install --editable /Users/admin/Vera
command -v vera
cd /private/tmp/vera-cli-acceptance
vera --help
```

创建 `/private/tmp/vera-cli-acceptance` 只能使用临时目录。启动交互会话后输入 `/help`、`/runs`、`/exit`，不得调用真实模型或修改真实工程。真实 DeepSeek 和 iOS 人工验收留给用户后续明确开始测试时执行。

- [x] **Step 3：记录证据并更新状态**

`docs/evals/interactive-cli-session.md` 记录：测试数量、静态检查、构建、安装路径、仓库外启动结果、未执行的 live/iOS 人工验收，以及当前已知限制。规格 13 条验收标准逐项标记通过或未完成。

- [x] **Step 4：检查文档一致性**

```bash
rg -n "Draf[t]|TB[D]|TOD[O]|一次性 CL[I].*已完成|交互式 CL[I].*未实现" docs README.md
git diff --check
git status --short --branch
```

修正所有与实际行为矛盾的状态；不要删除历史验收记录。

- [x] **Step 5：最终提交 Task 8**

```bash
git add README.md docs/STATUS.md docs/evals/interactive-cli-session.md docs/tasks/0003-interactive-cli-session.md
git commit -m "test: verify interactive Vera CLI session"
```

- [ ] **Step 6：合并回 main**

完整验证通过后切换 `main`，使用 `--no-ff` 合并 `codex/interactive-cli-session`。仓库没有 remote 时准确记录“未推送”，不能宣称已经 push。

## 规格覆盖索引

| 规格能力 | 实施任务 |
|---|---|
| 私有供应商环境自动加载 | Task 1 |
| Runtime 多审批连续执行 | Task 2、Task 3 |
| JSON 非交互取消语义 | Task 3、Task 7 |
| 跨进程手动回滚 | Task 4 |
| Diff、风险和验证证据展示 | Task 5 |
| 持续提示符与多个独立 run | Task 6 |
| `/help`、`/runs`、`/show`、`/rollback`、退出 | Task 6 |
| `vera` 空命令与原有命令兼容 | Task 7 |
| 仓库外安装和最终证据 | Task 8 |
