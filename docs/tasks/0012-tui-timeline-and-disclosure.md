# Vera TUI 对话时间线与披露策略实施计划

> **供 Agent 执行（For agentic workers）：** REQUIRED SUB-SKILL: 使用 `superpowers:executing-plans` 按 Task 顺序实施；只使用一个主实现 Agent。

**状态：** Planned

**目标分支：** `feature/tui-conversation-timeline`

**目标：** 实现可滚动的结构化对话时间线，固定工具/日志折叠、Diff/审批展开、失败自动展开规则，并让流式 Markdown 稳定刷新。

**架构：** UI 无关 `TimelineProjector` 把 RuntimeOutput 转为不可变 TimelineBlock 和 TimelineMutation；`DisclosurePolicy` 决定初始展开状态。Textual Widget 只应用 mutation，不读取 Workspace 或 Journal。

**技术栈：** Python 3.12、Pydantic 2、Textual 8、Rich 14、pytest、Textual Pilot/SVG、Ruff、Mypy。

**规格：** [阶段三富交互 Terminal UI](../specs/2026-09-11-rich-terminal-ui.md)

## 全局约束

- 依赖任务 0010 和 0011 已合并。
- View Model 与 Projector 不导入 Textual；每个工具输出使用一个 block，不能为每行创建 Widget。
- 模型、工具、Diff 和日志一律视为不可信文本，先脱敏并清理控制字符。
- 手动披露状态优先；失败只在第一次转为失败时强制展开。
- 不运行 live 测试，不读取真实 Key，不修改 `VeraTestDemo`。

---

### Task 1：固定 TimelineBlock、披露矩阵和控制字符清理

**文件：**

- Create: `src/vera/presentation/timeline.py`
- Create: `src/vera/presentation/disclosure.py`
- Create: `src/vera/presentation/sanitize.py`
- Create: `src/vera/presentation/__init__.py`
- Create: `tests/presentation/test_timeline.py`
- Create: `tests/presentation/test_disclosure.py`
- Create: `tests/presentation/test_sanitize.py`

**接口：**

- Produces: `BlockKind.USER|ASSISTANT|TOOL|LOG|DIFF|APPROVAL|VERIFICATION|ERROR|STATUS`
- Produces: `BlockStatus.PENDING|RUNNING|SUCCEEDED|FAILED|CANCELLED`
- Produces: `TimelineBlock(block_id, run_id, kind, title, body, status, expanded, user_overridden)`
- Produces: `DisclosurePolicy.initial_state()`、`on_status_change()`
- Produces: `sanitize_terminal_text(value: str) -> str`

- [ ] **Step 1：编写失败测试**

```python
@pytest.mark.parametrize(
    ("kind", "expanded"),
    [
        (BlockKind.TOOL, False),
        (BlockKind.LOG, False),
        (BlockKind.DIFF, True),
        (BlockKind.APPROVAL, True),
        (BlockKind.ERROR, True),
    ],
)
def test_initial_disclosure(kind, expanded) -> None:
    assert DisclosurePolicy().initial_state(kind, BlockStatus.PENDING) is expanded


def test_untrusted_osc_and_ansi_are_removed() -> None:
    value = "safe\x1b]52;c;secret\x07\x1b[31mred\x1b[0m"
    assert sanitize_terminal_text(value) == "safered"
```

另测成功验证折叠、失败验证展开、失败首次强制展开，以及用户之后手动折叠不会被再次打开。

- [ ] **Step 2：运行测试并观察模块缺失**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/presentation -v
```

- [ ] **Step 3：实现冻结 View Model、纯规则和 ANSI/OSC 清理**

`TimelineBlock.body` 只保存已脱敏纯文本或结构化 `BlockContent`，不保存 Rich/Textual 对象。规则使用 `BlockKind` 和 `BlockStatus` 显式 match，不通过标题推断。

- [ ] **Step 4：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/presentation -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/presentation tests/presentation
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/presentation tests/presentation docs/tasks/0012-tui-timeline-and-disclosure.md
git commit -m "feat: define terminal timeline view models"
```

---

### Task 2：实现 RuntimeOutput 到 TimelineMutation 的纯投影

**文件：**

- Create: `src/vera/presentation/projector.py`
- Create: `tests/presentation/test_projector.py`

**接口：**

- Produces: `AppendBlock`、`UpdateBlock`、`FocusBlock`
- Produces: `TimelineMutation` discriminated union
- Produces: `TimelineProjector.apply(output: RuntimeOutput) -> tuple[TimelineMutation, ...]`

- [ ] **Step 1：编写 Event 映射和流去重测试**

```python
def test_changeset_and_approval_are_expanded(projector, events) -> None:
    diff = only_appended_block(projector.apply(events.changeset_proposed("--- a/a.py")))
    approval_mutations = projector.apply(events.approval_required("approval_1"))
    approval = only_appended_block(approval_mutations)
    assert diff.kind is BlockKind.DIFF and diff.expanded is True
    assert approval.kind is BlockKind.APPROVAL and approval.expanded is True
    assert isinstance(approval_mutations[-1], FocusBlock)


def test_duplicate_delta_is_ignored(projector) -> None:
    frame = assistant_delta(stream_id="s1", index=0, text="你")
    first = projector.apply(frame)
    second = projector.apply(frame)
    assert first
    assert second == ()
```

参数化覆盖 user、assistant、tool、verification、recovery、migration 和 run 终态；失败更新既有 block 并展开。

- [ ] **Step 2：运行失败测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/presentation/test_projector.py -v
```

- [ ] **Step 3：实现稳定 block ID 和穷尽映射**

持久 Event ID 使用 `run_id:event-sequence:kind`，流式助手 ID 使用 `run_id:stream_id:assistant`。遇到 frame index 缺口就标记 incomplete，停止接收该 stream 的后续 delta，等待最终 `assistant.message` 替换正文。未知持久 Event 映射为折叠 STATUS block；未知 Stream Frame 忽略并记脱敏诊断。

- [ ] **Step 4：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/presentation tests/contracts tests/test_redaction.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/presentation tests/presentation
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/presentation tests/presentation docs/tasks/0012-tui-timeline-and-disclosure.md
git commit -m "feat: project Vera events into terminal blocks"
```

---

### Task 3：实现 Textual 卡片与增量 DOM 更新

**文件：**

- Create: `src/vera/terminal/widgets/blocks.py`
- Create: `src/vera/terminal/widgets/diff.py`
- Modify: `src/vera/terminal/widgets/timeline.py`
- Modify: `src/vera/terminal/theme.tcss`
- Create: `tests/terminal/test_blocks.py`
- Create: `tests/terminal/test_timeline.py`

**接口：**

- Produces: `TimelineBlockWidget.from_model(block)`
- Produces: `DiffBlockWidget`
- Produces: `ConversationTimeline.apply(mutations) -> None`

- [ ] **Step 1：编写卡片状态和交互测试**

```python
@pytest.mark.asyncio
async def test_disclosure_defaults_and_failure(app_factory) -> None:
    app = app_factory.with_blocks(tool_block(), diff_block(), failed_tool_block())
    async with app.run_test() as pilot:
        assert app.block("tool_1").collapsed is True
        assert app.block("diff_1").collapsed is False
        assert app.block("tool_failed").collapsed is False
        await pilot.click(app.block("tool_1").title)
        assert app.block("tool_1").collapsed is False
```

另测审批、Markdown code fence、长路径、中文宽字符、空工具结果和不可信 Rich markup。

- [ ] **Step 2：运行失败测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/terminal/test_blocks.py tests/terminal/test_timeline.py -v
```

- [ ] **Step 3：实现每个 block 一个 Widget**

工具和日志正文保存在单个 `Static`/`RichLog`，首次展开时才生成 renderable。Diff 使用专用只读 Widget，保留 `+/-/@@` 语义色但不执行外部 markup。`ConversationTimeline.apply()` 按 ID 更新现有 Widget，不能清空重建 DOM。

- [ ] **Step 4：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/terminal tests/presentation -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/terminal src/vera/presentation tests/terminal
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/terminal tests/terminal docs/tasks/0012-tui-timeline-and-disclosure.md
git commit -m "feat: render structured terminal timeline blocks"
```

---

### Task 4：实现滚动锚点、流式节流和长时间线验收

**文件：**

- Create: `src/vera/terminal/render_scheduler.py`
- Modify: `src/vera/terminal/widgets/timeline.py`
- Modify: `src/vera/terminal/widgets/status_line.py`
- Create: `tests/terminal/test_scrolling.py`
- Create: `tests/terminal/test_render_scheduler.py`
- Create: `tests/terminal/test_timeline_performance.py`
- Create: `tests/terminal/test_snapshots.py`
- Create: `docs/evals/tui-timeline-and-disclosure.md`
- Modify: `docs/STATUS.md`

**接口：**

- Produces: `RenderScheduler(interval_seconds=0.05)`
- Produces: `ConversationTimeline.follow_tail`、`pending_update_count`、`return_to_tail()`

- [ ] **Step 1：编写滚动与批处理测试**

```python
@pytest.mark.asyncio
async def test_new_output_does_not_steal_scroll_position(app_factory) -> None:
    app = app_factory.with_many_blocks(80)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("pageup")
        before = app.timeline.scroll_y
        app.append_output(tool_completed_event())
        await pilot.pause()
        assert app.timeline.scroll_y == before
        assert app.timeline.pending_update_count == 1
        await pilot.press("end")
        assert app.timeline.follow_tail is True
```

Fake clock 测试 50 ms 内 delta 合并；性能测试投影 500 block 和一个含 10,000 行的折叠工具正文，断言 Widget 数量与 block 数量同阶。

- [ ] **Step 2：运行失败测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/terminal/test_scrolling.py tests/terminal/test_render_scheduler.py tests/terminal/test_timeline_performance.py -v
```

- [ ] **Step 3：实现 tail-follow 状态机和 50 ms flush**

只有当前在底部且没有用户滚动意图时自动跟随。PageUp、鼠标向上和选择历史 block 关闭 follow_tail；新 mutation 增加计数；End 清零并恢复。Scheduler 在 UI 线程合并 delta，一次只更新对应 Assistant Widget。

- [ ] **Step 4：生成 80×24/120×40 确定性 SVG 并运行完整门禁**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

- [ ] **Step 5：记录证据、提交并合并**

```bash
git add src/vera/terminal tests/terminal docs/evals/tui-timeline-and-disclosure.md docs/STATUS.md docs/tasks/0012-tui-timeline-and-disclosure.md
git commit -m "test: verify terminal conversation timeline"
git switch main
git merge --no-ff feature/tui-conversation-timeline -m "merge: add Vera terminal conversation timeline"
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" -q
git branch -d feature/tui-conversation-timeline
```

无 remote 时不执行 push。确认 `main` 干净后才开始任务 0013。
