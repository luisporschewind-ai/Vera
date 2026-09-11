# Vera Textual TUI 外壳与模式路由实施计划

> **供 Agent 执行（For agentic workers）：** REQUIRED SUB-SKILL: 使用 `superpowers:executing-plans` 按 Task 顺序实施；只使用一个主实现 Agent，每个生产增量独立提交。

**状态：** Planned

**目标分支：** `feature/textual-tui-shell`

**目标：** 让 `vera` 在受支持 TTY 中默认进入可测试的 Textual 全屏外壳，并建立 TUI、Plain、JSON 共用的 SessionController 边界。

**架构：** Typer 的顶层 callback 只选择 `PresentationMode` 并装配依赖。UI 无关的 SessionController 接收 SessionAction，TerminalBridge 在 Textual Worker 中消费 RuntimeOutput 并把消息安全投递给主 UI 线程。

**技术栈：** Python 3.12、Typer、Textual `>=8.2,<9`、Rich `>=14,<15`、pytest-asyncio、Textual Pilot、Ruff、Mypy、uv。

**规格：** [阶段三富交互 Terminal UI](../specs/2026-09-11-rich-terminal-ui.md)

## 全局约束

- 依赖任务 0010 已合并到 `main`。
- Textual 类型只能存在于 `vera.terminal` 和 CLI 装配层，不能进入 Core Contract、Runtime、Policy 或 Workspace。
- `vera run`、现有子命令和 `VeraRuntime.handle()` 保持兼容。
- TUI Worker 不得更新 Widget；只能通过 Textual message 或 `call_from_thread()` 回到 UI 线程。
- 不运行 live 测试，不读取真实 Key，不修改 `VeraTestDemo`。

---

### Task 1：加入依赖并固定模式与终端能力路由

**文件：**

- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/vera/terminal/__init__.py`
- Create: `src/vera/terminal/mode.py`
- Create: `tests/terminal/__init__.py`
- Create: `tests/terminal/test_mode.py`
- Modify: `tests/cli/test_entrypoint.py`

**接口：**

- Produces: `PresentationMode.TUI|PLAIN|JSON`
- Produces: `TerminalCapabilities(stdin_tty, stdout_tty, term, columns, rows)`
- Produces: `select_mode(plain, json_output, capabilities) -> PresentationMode`
- Produces: `TerminalModeError(reason_code, message, exit_code=2)`

- [ ] **Step 1：编写互斥、TTY 和 dumb terminal 测试**

```python
def test_default_mode_is_tui_for_supported_terminal() -> None:
    capabilities = TerminalCapabilities(
        stdin_tty=True, stdout_tty=True, term="xterm-256color", columns=80, rows=24
    )
    assert select_mode(False, False, capabilities) is PresentationMode.TUI


def test_default_mode_requires_explicit_fallback_without_tty() -> None:
    capabilities = TerminalCapabilities(
        stdin_tty=False, stdout_tty=False, term="", columns=80, rows=24
    )
    with pytest.raises(TerminalModeError, match="--plain.*--json"):
        select_mode(False, False, capabilities)
```

再覆盖 `--plain`/`--json` 互斥、`TERM=dumb`、只有 stdin 或 stdout 为 TTY、显式 Plain/JSON 不依赖 TTY。

- [ ] **Step 2：运行测试并观察接口缺失**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/terminal/test_mode.py tests/cli/test_entrypoint.py -v
```

- [ ] **Step 3：增加依赖与纯模式选择器**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv add "textual>=8.2,<9"
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv add --dev "pytest-asyncio>=1,<2"
```

`select_mode()` 不导入 Textual。显式模式优先，冲突立即抛错；默认模式只在受支持 TTY 返回 TUI。

- [ ] **Step 4：运行依赖和模式检查**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv sync --extra dev
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/terminal/test_mode.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/terminal tests/terminal
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [ ] **Step 5：提交模式基础**

```bash
git add pyproject.toml uv.lock src/vera/terminal tests/terminal \
  tests/cli/test_entrypoint.py docs/tasks/0011-textual-tui-shell.md
git commit -m "feat: define Vera terminal modes"
```

---

### Task 2：建立 UI 无关 SessionAction 与 SessionController

**文件：**

- Create: `src/vera/session/actions.py`
- Create: `src/vera/session/controller.py`
- Modify: `src/vera/session/__init__.py`
- Create: `tests/session/test_actions.py`
- Create: `tests/session/test_controller.py`
- Modify: `src/vera/cli_session.py`
- Modify: `tests/cli/test_session.py`

**接口：**

- Produces: `SubmitPrompt(text: str)`
- Produces: `ExecuteSlashCommand(raw: str)`
- Produces: `ResolveSessionApproval(approval_id, decision)`
- Produces: `CancelActiveRun(run_id: str)`
- Produces: `CloseSession()`
- Produces: `SessionAction` discriminated union
- Produces: `SessionController.dispatch(action) -> Iterator[RuntimeOutput]`
- Produces: `SessionSnapshot(session_id, active_run_id, pending_approval_id, model_profile)`

- [ ] **Step 1：编写跨前端统一行为测试**

```python
def test_controller_submits_prompt_through_runtime(controller, runtime) -> None:
    outputs = tuple(controller.dispatch(SubmitPrompt(text="解释这个项目")))

    assert runtime.received[0].goal == "解释这个项目"
    assert any(
        isinstance(item, EventEnvelope) and item.type == "run.completed" for item in outputs
    )


def test_controller_rejects_second_prompt_while_run_active(controller) -> None:
    controller.mark_active("run_1")
    outputs = tuple(controller.dispatch(SubmitPrompt(text="second")))
    assert outputs[-1].type == "session.action_rejected"
    assert outputs[-1].payload["reason_code"] == "run_active"
```

覆盖 Slash Command 继续复用既有解析、审批 ID 不匹配、取消幂等、Close 时未决审批转 cancel、ConversationContext 只记录最终持久结果。

- [ ] **Step 2：运行测试并确认 Controller 不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/session/test_actions.py tests/session/test_controller.py tests/cli/test_session.py -v
```

- [ ] **Step 3：把 InteractiveSession 编排迁移到 Controller**

```python
class SessionController:
    def dispatch(self, action: SessionAction) -> Iterator[RuntimeOutput]:
        match action:
            case SubmitPrompt(text=text):
                yield from self._submit(text)
            case ExecuteSlashCommand(raw=raw):
                yield from self._slash_commands.dispatch(raw)
            case ResolveSessionApproval(approval_id=approval_id, decision=decision):
                yield from self._resolve_approval(approval_id, decision)
            case CancelActiveRun(run_id=run_id):
                yield from self._cancel(run_id)
            case CloseSession():
                yield from self._close()
```

Controller 不返回人类字符串。会话状态和 Slash Command 结果使用结构化 Session Event；Plain Presenter 在下一步适配，现有用户行为必须由回归测试保持。

- [ ] **Step 4：运行 Session、CLI 与 Runtime 回归**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/session tests/cli tests/runtime -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/session src/vera/cli_session.py tests/session tests/cli
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [ ] **Step 5：提交 Controller**

```bash
git add src/vera/session src/vera/cli_session.py tests/session tests/cli \
  docs/tasks/0011-textual-tui-shell.md
git commit -m "refactor: centralize Vera session control"
```

---

### Task 3：建立 Textual App 骨架和稳定布局

**文件：**

- Create: `src/vera/terminal/app.py`
- Create: `src/vera/terminal/theme.tcss`
- Create: `src/vera/terminal/widgets/__init__.py`
- Create: `src/vera/terminal/widgets/header.py`
- Create: `src/vera/terminal/widgets/timeline.py`
- Create: `src/vera/terminal/widgets/composer.py`
- Create: `src/vera/terminal/widgets/status_line.py`
- Create: `tests/terminal/test_app.py`
- Create: `tests/terminal/test_layout.py`

**接口：**

- Produces: `VeraTerminalApp(controller, workspace, model_profile, animations=True)`
- Produces: Widget IDs `#header`, `#timeline`, `#composer`, `#status-line`
- Guarantee: 最小尺寸 60×16，小尺寸 Screen 可恢复

- [ ] **Step 1：编写 Pilot 布局和 Resize 测试**

```python
@pytest.mark.asyncio
async def test_app_mounts_stable_regions(controller) -> None:
    app = VeraTerminalApp(controller, Path("/workspace"), "fake")
    async with app.run_test(size=(80, 24)) as pilot:
        assert app.query_one("#timeline")
        assert app.query_one("#composer").has_focus
        await pilot.resize_terminal(59, 15)
        assert app.query_one("#terminal-too-small").display is True
        await pilot.resize_terminal(80, 24)
        assert app.query_one("#composer").has_focus
```

再覆盖 60×16、120×40、宽度小于 80 隐藏次要 Header 字段、Resize 前输入文本保留。

- [ ] **Step 2：运行测试并观察 App 缺失**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/terminal/test_app.py tests/terminal/test_layout.py -v
```

- [ ] **Step 3：实现最小可运行 App**

```python
class VeraTerminalApp(App[int]):
    CSS_PATH = "theme.tcss"
    MINIMUM_SIZE = Size(60, 16)

    def compose(self) -> ComposeResult:
        yield VeraHeader(id="header")
        yield ConversationTimeline(id="timeline")
        yield PromptComposer(id="composer")
        yield VeraStatusLine(id="status-line")

    def on_mount(self) -> None:
        self.query_one(PromptComposer).focus()
```

主题只使用语义 class 和 16/256 色安全值。Widget 只展示空壳，不在本 Task 实现卡片细节。

- [ ] **Step 4：运行 Textual 布局检查**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/terminal/test_app.py tests/terminal/test_layout.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/terminal tests/terminal
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [ ] **Step 5：提交 App 骨架**

```bash
git add src/vera/terminal tests/terminal docs/tasks/0011-textual-tui-shell.md
git commit -m "feat: add Textual terminal shell"
```

---

### Task 4：用 TerminalBridge 安全驱动 Runtime Worker

**文件：**

- Create: `src/vera/terminal/bridge.py`
- Modify: `src/vera/terminal/app.py`
- Create: `tests/terminal/test_bridge.py`
- Modify: `tests/terminal/test_app.py`

**接口：**

- Produces: `RuntimeOutputReceived(output: RuntimeOutput)` Textual Message
- Produces: `WorkerStopped(run_id, reason_code)` Textual Message
- Produces: `TerminalBridge.submit(action: SessionAction) -> None`
- Guarantee: Controller 在单一 thread Worker 执行，Widget 更新只在 UI thread

- [ ] **Step 1：编写非阻塞、顺序和关闭测试**

```python
@pytest.mark.asyncio
async def test_slow_runtime_does_not_block_composer(app_factory) -> None:
    app, controller = app_factory.blocking_controller()
    async with app.run_test() as pilot:
        await pilot.press("h", "i", "enter")
        await controller.wait_until_started()
        assert app.query_one("#composer").disabled is False
        controller.release()
        await pilot.pause()
        assert app.received_sequences == sorted(app.received_sequences)
```

再测试 Worker exception 不直接写 Widget、App exit 取消 Worker、Stream Frame 顺序保持、重复 submit 在 active run 时由 Controller 拒绝。

- [ ] **Step 2：运行测试并确认 Bridge 缺失**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/terminal/test_bridge.py -v
```

- [ ] **Step 3：实现 thread Worker 与消息投递**

```python
class TerminalBridge:
    def submit(self, action: SessionAction) -> None:
        self.app.run_worker(
            lambda: self._dispatch(action),
            thread=True,
            exclusive=False,
            exit_on_error=False,
        )

    def _dispatch(self, action: SessionAction) -> None:
        try:
            for output in self.controller.dispatch(action):
                self.app.post_message(RuntimeOutputReceived(output))
        except Exception:
            self.app.post_message(WorkerStopped(self.controller.active_run_id, "worker_failed"))
```

日志记录异常时继续使用现有脱敏器。`post_message()` 传递不可变 Contract，不从 thread 调用 `query_one()` 或 Widget 方法。

- [ ] **Step 4：运行终端、Session 与 Runtime 回归**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/terminal tests/session tests/runtime -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests/terminal tests/session
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [ ] **Step 5：提交 Bridge**

```bash
git add src/vera/terminal tests/terminal docs/tasks/0011-textual-tui-shell.md
git commit -m "feat: bridge Terminal UI to Vera runtime"
```

---

### Task 5：接入 `vera` 默认入口并完成任务验收

**文件：**

- Modify: `src/vera/cli.py`
- Modify: `tests/cli/test_entrypoint.py`
- Create: `docs/evals/textual-tui-shell.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/tasks/0011-textual-tui-shell.md`

**接口：**

- Produces: root option `--plain`
- Produces: `launch_tui(dependencies, workspace, model_profile) -> int`

- [ ] **Step 1：编写入口路由测试**

```python
def test_vera_defaults_to_tui_in_tty(cli_runner, fake_tty, app_launcher) -> None:
    result = cli_runner.invoke(app, [])
    assert result.exit_code == 0
    assert app_launcher.calls == 1


def test_vera_plain_keeps_existing_session(cli_runner, fake_tty, plain_session) -> None:
    result = cli_runner.invoke(app, ["--plain"], input="/exit\n")
    assert result.exit_code == 0
    assert plain_session.started is True
```

再覆盖非 TTY 默认失败、Textual import/启动失败提示 `--plain` 或后续 `--json`、所有既有子命令不启动 TUI。

- [ ] **Step 2：运行测试并确认默认仍是旧 REPL**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/cli/test_entrypoint.py -v
```

- [ ] **Step 3：实现惰性 Textual 装配**

`cli.py` 在选择 TUI 后才导入 `vera.terminal.app`。子命令优先于 root mode，`vera run` 和 `runs/config/recover/state` 等阶段二命令不受 root TUI 影响。本任务只接入 `--plain`；任务 0014 在 JSON Session 驱动可用时再公开 root `--json`，不能提前暴露不可用入口。

- [ ] **Step 4：运行完整离线质量门禁**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

- [ ] **Step 5：记录证据、提交并本地合并**

```bash
git add src/vera/cli.py tests/cli/test_entrypoint.py docs/evals/textual-tui-shell.md \
  docs/STATUS.md docs/tasks/0011-textual-tui-shell.md
git commit -m "test: verify Textual TUI shell"
git switch main
git merge --no-ff feature/textual-tui-shell -m "merge: add Vera Textual TUI shell"
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" -q
git branch -d feature/textual-tui-shell
```

无 remote 时不执行 push。确认 `main` 干净后才开始任务 0012。
