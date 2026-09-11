# Vera Terminal 模式兼容与阶段三验收实施计划

> **供 Agent 执行（For agentic workers）：** REQUIRED SUB-SKILL: 使用 `superpowers:executing-plans` 按 Task 顺序实施；只使用一个主实现 Agent。

**状态：** Complete

**目标分支：** `cursor/terminal-modes-acceptance-b138`

**目标：** 完成 `vera --plain`、`vera --json`、旧一次性 JSON 的兼容边界，并通过真实 PTY、尺寸、颜色、性能和安全矩阵收口阶段三。

**架构：** PlainSessionDriver 和 JsonSessionDriver 复用 SessionController。JSON Session 使用版本化 NDJSON SessionAction/SessionRecord；PTY Harness 只验证终端生命周期，不调用真实模型。阶段三最终验收把 15 条规格逐项映射到自动或人工证据。

**技术栈：** Python 3.12、Typer、Textual 8、Rich 14、Pydantic 2、pty/subprocess、pytest、Ruff、Mypy、uv。

**规格：** [阶段三富交互 Terminal UI](../specs/2026-09-11-rich-terminal-ui.md)

## 全局约束

- 依赖任务 0010–0013 已合并。
- stdout 的 JSON Session 只能包含 NDJSON；启动错误之外不得混入人类文本、提示符或 ANSI。
- `vera run ... --json` 字节级结构保持阶段二兼容，不增加包装层或瞬时帧。
- PTY、性能和端到端测试只使用 Fake Model、临时状态目录和临时工作区。
- 不运行 live 测试，不读取真实 Key，不修改 `VeraTestDemo`。

---

### Task 1：固定 JSON Session Codec 与驱动

**文件：**

- Create: `src/vera/session/protocol.py`
- Create: `src/vera/cli_json_session.py`
- Modify: `src/vera/cli.py`
- Create: `tests/session/test_protocol.py`
- Create: `tests/cli/test_json_session.py`

**接口：**

- Produces: `SessionActionCodec.decode(line: str) -> SessionAction`
- Produces: `SessionRecord(record_type, event=None, stream=None)`
- Produces: `SessionRecordCodec.encode(record) -> str`
- Produces: `JsonSessionDriver.run(input: TextIO, output: TextIO) -> int`

- [ ] **Step 1：编写 NDJSON round-trip 和错误隔离测试**

```python
def test_json_session_round_trips_prompt_and_outputs_records(driver_factory) -> None:
    source = StringIO('{"schema_version":1,"type":"prompt.submit","text":"你好"}\n')
    target = StringIO()

    assert driver_factory().run(source, target) == 0

    records = [json.loads(line) for line in target.getvalue().splitlines()]
    assert records[0]["record_type"] == "event"
    assert records[-1]["event"]["type"] == "run.completed"
    assert "\u001b" not in target.getvalue()


def test_invalid_line_emits_structured_error_and_continues(driver_factory) -> None:
    source = StringIO("not-json\n" + valid_status_action_json() + "\n")
    target = StringIO()
    assert driver_factory().run(source, target) == 0
    records = [json.loads(line) for line in target.getvalue().splitlines()]
    assert records[0]["event"]["type"] == "session.input_failed"
    assert records[1]["event"]["type"] == "session.status"
```

参数化输入 `prompt.submit`、`session.command`、`approval.resolve`、`run.cancel`、`session.close`；覆盖未知 schema、额外字段、stale approval、Stream Frame 包装和 EOF。

- [ ] **Step 2：运行失败测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/session/test_protocol.py tests/cli/test_json_session.py -v
```

- [ ] **Step 3：实现版本化 Codec 和逐行驱动**

`SessionActionCodec` 显式按 `type` 分派 Pydantic model；不得用任意 import 或动态类名。`SessionRecord` 恰好包含 event 或 stream。Driver 每读一行 dispatch 一次，逐条 flush 输出；异常只发脱敏 `session.input_failed`。

- [ ] **Step 4：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/session tests/cli/test_json_session.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/session src/vera/cli_json_session.py tests/session tests/cli
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/session src/vera/cli_json_session.py src/vera/cli.py tests/session tests/cli docs/tasks/0014-terminal-modes-and-acceptance.md
git commit -m "feat: add Vera JSON terminal session"
```

---

### Task 2：完成 Plain 模式和旧 JSON 兼容矩阵

**文件：**

- Create: `src/vera/cli_plain_session.py`
- Modify: `src/vera/cli_session.py`
- Modify: `src/vera/cli_presenter.py`
- Modify: `src/vera/cli.py`
- Create: `tests/cli/test_plain_session.py`
- Create: `tests/cli/test_mode_compatibility.py`
- Modify: `tests/cli/test_run.py`

**接口：**

- Produces: `PlainSessionDriver.run() -> int`
- Guarantee: Plain 不使用 alternate screen、光标回写或动画
- Guarantee: `vera run <goal> --json` 只输出原始 EventEnvelope

- [ ] **Step 1：编写三种模式互斥和兼容测试**

```python
def test_plain_mode_has_no_dynamic_terminal_sequences(cli_runner) -> None:
    result = cli_runner.invoke(app, ["--plain"], input="/status\n/exit\n")
    assert result.exit_code == 0
    assert "\x1b[?1049h" not in result.stdout
    assert "\x1b[2K" not in result.stdout


def test_legacy_run_json_remains_raw_event_envelopes(cli_runner, fake_model) -> None:
    result = cli_runner.invoke(app, ["run", "hello", "--json"])
    records = [json.loads(line) for line in result.stdout.splitlines()]
    assert all("record_type" not in record for record in records)
    assert records[-1]["type"] == "run.completed"
```

再覆盖所有阶段二子命令、Plain 审批文字、TUI 不可用提示、`--plain --json` 退出 2、非 TTY 默认模式不静默降级。

- [ ] **Step 2：运行失败测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/cli/test_plain_session.py tests/cli/test_mode_compatibility.py tests/cli/test_run.py -v
```

- [ ] **Step 3：让 Plain 和 TUI 复用 SessionController**

Plain driver 负责 `read/write` 和 Human Presenter，所有 Slash Command 与审批仍由 Controller dispatch。它过滤 Stream Frame，收到最终 `assistant.message` 后一次输出，不进行动态重绘。旧 `InteractiveSession` 保留为兼容 facade 或迁移调用方后删除，不能留下第二份行为实现。

- [ ] **Step 4：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/cli tests/session tests/runtime -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/cli.py src/vera/cli_plain_session.py src/vera/cli_presenter.py tests/cli
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/cli.py src/vera/cli_plain_session.py src/vera/cli_session.py src/vera/cli_presenter.py tests/cli docs/tasks/0014-terminal-modes-and-acceptance.md
git commit -m "refactor: preserve Vera plain and JSON modes"
```

---

### Task 3：建立真实 PTY 生命周期和终端能力测试

**文件：**

- Create: `tests/pty/__init__.py`
- Create: `tests/pty/harness.py`
- Create: `tests/pty/test_tui_lifecycle.py`
- Create: `tests/pty/test_terminal_capabilities.py`
- Modify: `src/vera/terminal/app.py`
- Modify: `src/vera/terminal/mode.py`
- Modify: `src/vera/terminal/theme.tcss`

**接口：**

- Produces: `PtyHarness.spawn(argv, env, size) -> PtyProcess`
- Guarantee: 正常、异常、SIGTERM 后恢复 alternate screen 和光标
- Guarantee: 60×16、80×24、120×40 可操作

- [ ] **Step 1：编写终端进入与恢复字节测试**

```python
def test_tui_restores_terminal_after_normal_exit(pty_harness, fake_env) -> None:
    process = pty_harness.spawn(["vera"], fake_env, size=(80, 24))
    process.wait_for("Vera")
    process.send("/exit\r")
    output = process.read_to_exit()
    assert "\x1b[?1049h" in output
    assert "\x1b[?1049l" in output
    assert output.rfind("\x1b[?1049l") > output.rfind("\x1b[?1049h")
```

另测 Controller exception、SIGTERM、`TERM=dumb`、非 TTY、窗口从 59×15 恢复到 80×24、`VERA_NO_ANIMATIONS=1` 和 256 色。测试结束必须清理子进程，禁止访问网络。

- [ ] **Step 2：运行失败测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/pty -v
```

- [ ] **Step 3：实现有序终端生命周期和兼容主题**

使用 Textual App 生命周期恢复终端；信号处理只请求 App 退出并让阶段二 Recovery 处理未终止 run。最小尺寸 Screen 保留 Controller、Composer 文本和 pending approval。主题不依赖 true color，所有状态包含文字。

- [ ] **Step 4：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/pty tests/terminal -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/terminal tests/pty tests/terminal
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/terminal tests/pty tests/terminal docs/tasks/0014-terminal-modes-and-acceptance.md
git commit -m "test: verify Vera terminal lifecycle"
```

---

### Task 4：阶段三安全、性能和全链路验收

**文件：**

- Create: `tests/e2e/test_phase_3_terminal_ui.py`
- Create: `docs/evals/phase-3-rich-terminal-ui.md`
- Modify: `README.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/tasks/phase-3-execution-order.md`
- Modify: `docs/tasks/0014-terminal-modes-and-acceptance.md`

**接口：**

- Evidence: 阶段三规格 15 条验收标准逐项映射

- [ ] **Step 1：编写代表性 Fake Agent E2E**

```python
@pytest.mark.asyncio
async def test_safe_editing_tui_story(phase3_app_factory) -> None:
    app = phase3_app_factory.safe_editing_story()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press(*list("change color"), "enter")
        await app.wait_for_approval()
        assert app.latest_diff.collapsed is False
        assert app.latest_approval.focused_decision == "cancel"
        await app.choose_approval(pilot, "approve")
        await app.wait_for_completion()
        assert app.latest_tool.collapsed is True
        assert app.status.label == "已完成"
```

另含普通对话流式结果、工具失败自动展开、恢复审批、向上滚动时持续输出、Plain 故事、JSON Session round-trip、旧 run JSON、控制字符注入和 500 block 性能。

- [ ] **Step 2：运行完整质量门禁**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

要求全部退出码为 0、覆盖率至少 90%、live 明确排除。

- [ ] **Step 3：执行仓库外无网络人工验收**

在临时工作区、临时 `VERA_STATE_DIR` 和 Fake Provider 下安装构建产物，分别验证 `vera`、`vera --plain`、`vera --json` 和 `vera run ... --json`。使用 macOS Terminal.app 完成一次键盘/滚轮/Resize/复制观察；不得加载用户 Provider 环境文件。

- [ ] **Step 4：更新阶段文档并记录限制**

`docs/evals/phase-3-rich-terminal-ui.md` 逐条列出 15 条标准、证据命令、测试数、覆盖率、SVG/PTY 结果和人工环境。将阶段三标记 Complete，阶段四评测与内部就绪成为下一阶段；桌面仍为阶段五。

- [ ] **Step 5：提交、合并并最终复核**

```bash
git add tests/e2e/test_phase_3_terminal_ui.py README.md docs/ROADMAP.md docs/STATUS.md docs/evals/phase-3-rich-terminal-ui.md docs/tasks/phase-3-execution-order.md docs/tasks/0014-terminal-modes-and-acceptance.md
git commit -m "test: verify Vera phase three terminal UI"
git switch main
git merge --no-ff feature/terminal-modes-acceptance -m "merge: complete Vera phase three terminal UI"
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git branch -d feature/terminal-modes-acceptance
```

无 remote 时只记录本地合并，不宣称 push。真实供应商测试仍由用户后续明确执行。
