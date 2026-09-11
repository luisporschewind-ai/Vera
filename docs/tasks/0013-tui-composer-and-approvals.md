# Vera TUI Composer、审批与任务控制实施计划

> **供 Agent 执行（For agentic workers）：** REQUIRED SUB-SKILL: 使用 `superpowers:executing-plans` 按 Task 顺序实施；只使用一个主实现 Agent。

**状态：** Complete

**目标分支：** `cursor/tui-composer-approvals-b138`

**目标：** 为富交互界面增加多行输入、Slash Command 补全、Core 驱动审批、取消语义、状态词和可禁用动画。

**架构：** Composer 和 Approval Widget 只产生 SessionAction；SessionController 和阶段二 Runtime 才能改变任务状态。`ActivityPresenter` 从权威 Event 映射状态词，`AnimationClock` 只改变视觉帧，不创造业务进度。

**技术栈：** Python 3.12、Textual 8、Rich 14、Pydantic 2、pytest、Textual Pilot、Ruff、Mypy。

**规格：** [阶段三富交互 Terminal UI](../specs/2026-09-11-rich-terminal-ui.md)

## 全局约束

- 依赖任务 0010–0012 已合并。
- Approve 不得绑定单字母快捷键，审批卡初始焦点固定为 Cancel。
- Ctrl+C 只发送取消意图，不直接终止 Runtime thread 或宣称任务失败。
- Slash Command 必须复用现有目录和 Controller 语义，不维护第二份处理逻辑。
- 不运行 live 测试，不读取真实 Key，不修改 `VeraTestDemo`。

---

### Task 1：建立 Composer、输入历史和 Slash Command 目录

**文件：**

- Create: `src/vera/session/command_catalog.py`
- Modify: `src/vera/terminal/widgets/composer.py`
- Create: `src/vera/terminal/widgets/completions.py`
- Create: `tests/session/test_command_catalog.py`
- Create: `tests/terminal/test_composer.py`
- Create: `tests/terminal/test_completions.py`

**接口：**

- Produces: `CommandDescriptor(name, usage, description, enabled_when)`
- Produces: `CommandCatalog.list(prefix, snapshot) -> tuple[CommandDescriptor, ...]`
- Produces: `PromptSubmitted(text: str)` Textual Message
- Produces: `PromptComposer.submit()`、`insert_newline()`、`clear()`

- [ ] **Step 1：编写提交、多行和补全测试**

```python
@pytest.mark.asyncio
async def test_enter_submits_and_ctrl_j_inserts_newline(app_factory) -> None:
    app = app_factory.empty()
    async with app.run_test() as pilot:
        await pilot.press("h", "i", "ctrl+j", "x")
        assert app.composer.text == "hi\nx"
        await pilot.press("ctrl+enter")
        assert app.submitted == ["hi\nx"]
        assert app.composer.text == ""


def test_slash_completion_comes_from_shared_catalog(catalog, snapshot) -> None:
    names = [item.name for item in catalog.list("/rec", snapshot)]
    assert names == ["/recover"]
```

另测 Enter 提交单行、空白不提交、历史只驻留当前进程、上下文满时补全仍显示 `/compact` 和 `/new`。

- [ ] **Step 2：运行失败测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/session/test_command_catalog.py tests/terminal/test_composer.py tests/terminal/test_completions.py -v
```

- [ ] **Step 3：实现 TextArea Composer 和共享命令元数据**

Composer 使用 Textual `TextArea`，单行时 Enter 提交，多行通过 Ctrl+Enter 提交，Ctrl+J 始终插入换行。提交后向 App 发送 `PromptSubmitted`，App 再构造 `SubmitPrompt` 或 `ExecuteSlashCommand`。命令说明由 Session 层提供。

- [ ] **Step 4：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/session tests/terminal/test_composer.py tests/terminal/test_completions.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/session src/vera/terminal tests/session tests/terminal
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/session src/vera/terminal tests/session tests/terminal docs/tasks/0013-tui-composer-and-approvals.md
git commit -m "feat: add terminal composer and command completion"
```

---

### Task 2：实现审批卡焦点和结构化决定

**文件：**

- Create: `src/vera/terminal/widgets/approval.py`
- Modify: `src/vera/terminal/widgets/blocks.py`
- Modify: `src/vera/terminal/app.py`
- Create: `tests/terminal/test_approval.py`
- Modify: `tests/runtime/test_approval.py`

**接口：**

- Produces: `ApprovalSelected(approval_id, decision)` Textual Message
- Produces: `ApprovalBlockWidget`
- Consumes: `ResolveSessionApproval(approval_id, decision)`

- [ ] **Step 1：编写默认 Cancel 和审批链测试**

```python
@pytest.mark.asyncio
async def test_approval_focus_defaults_to_cancel_and_never_implicit_approve(app_factory) -> None:
    app = app_factory.awaiting_approval(kind="changeset", risk="low")
    async with app.run_test() as pilot:
        assert app.approval.focused_decision == "cancel"
        await pilot.press("enter")
        assert app.controller.actions[-1] == ResolveSessionApproval(
            approval_id="approval_1", decision="cancel"
        )
```

参数化覆盖 Change Set、命令、恢复计划；再测试 stale ID、policy_hash/workspace 失效、Tab 顺序、Reject 和批准后卡片锁定，确保 Widget 不直接调用写入器。

- [ ] **Step 2：运行失败测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/terminal/test_approval.py tests/runtime/test_approval.py -v
```

- [ ] **Step 3：实现审批 Widget 和 App 消息处理**

审批卡显示 kind、risk、reason、目标摘要和三个完整按钮。按钮顺序为 Cancel、Reject、Approve，初始 focus 为 Cancel。选择后立即禁用全部按钮并提交 action；最终状态只由 `approval.resolved` 或 `approval.invalidated` Event 更新。

- [ ] **Step 4：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/terminal/test_approval.py tests/runtime tests/recovery -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/terminal tests/terminal
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/terminal tests/terminal tests/runtime docs/tasks/0013-tui-composer-and-approvals.md
git commit -m "feat: route terminal approvals through Vera Core"
```

---

### Task 3：实现活动状态映射和可禁用动画

**文件：**

- Create: `src/vera/presentation/activity.py`
- Create: `src/vera/terminal/animation.py`
- Modify: `src/vera/terminal/widgets/status_line.py`
- Modify: `src/vera/config.py`
- Create: `tests/presentation/test_activity.py`
- Create: `tests/terminal/test_animation.py`
- Modify: `tests/test_config.py`

**接口：**

- Produces: `ActivityState(label, phase, active, severity)`
- Produces: `ActivityPresenter.apply(event) -> ActivityState`
- Produces: `AnimationClock(enabled, fps=10)`
- Produces: `UiConfig.animations: bool = True`

- [ ] **Step 1：编写状态词和动画边界测试**

```python
@pytest.mark.parametrize(
    ("event_type", "label"),
    [
        ("model.requested", "正在思考"),
        ("tool.started", "正在读取"),
        ("approval.required", "等待审批"),
        ("changeset.applied", "正在验证"),
        ("recovery.detected", "正在恢复"),
        ("run.failed", "失败"),
    ],
)
def test_activity_labels_are_derived_from_events(event_type, label) -> None:
    assert ActivityPresenter().apply(event(event_type)).label == label


def test_disabled_animation_is_static(fake_clock) -> None:
    clock = AnimationClock(enabled=False, clock=fake_clock)
    assert clock.frame() == clock.frame()
```

另测刷新率不超过 10 FPS、`VERA_NO_ANIMATIONS=1` 覆盖配置、所有颜色状态同时包含文字。

- [ ] **Step 2：运行失败测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/presentation/test_activity.py tests/terminal/test_animation.py tests/test_config.py -v
```

- [ ] **Step 3：实现纯 Event 映射和视觉时钟**

ActivityPresenter 不读取 wall clock 或 Runtime 内部状态；未知事件保持上一状态。AnimationClock 只返回 spinner 字符，不能产生百分比。环境变量只关闭动画，不能扩大任何策略。

- [ ] **Step 4：验证并提交**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/presentation tests/terminal tests/test_config.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests/presentation tests/terminal
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git add src/vera/presentation src/vera/terminal src/vera/config.py tests docs/tasks/0013-tui-composer-and-approvals.md
git commit -m "feat: present terminal activity and animation state"
```

---

### Task 4：固定 Ctrl+C、Ctrl+D、退出与 Resize 焦点语义

**文件：**

- Modify: `src/vera/terminal/app.py`
- Modify: `src/vera/terminal/widgets/composer.py`
- Create: `tests/terminal/test_keybindings.py`
- Create: `tests/terminal/test_exit_semantics.py`
- Create: `docs/evals/tui-composer-and-approvals.md`

**接口：**

- Produces: App actions `cancel_or_clear`、`exit_if_idle`、`return_to_tail`
- Consumes: `CancelActiveRun`、`CloseSession`

- [ ] **Step 1：编写上下文相关按键测试**

```python
@pytest.mark.asyncio
async def test_ctrl_c_cancels_active_run_but_does_not_exit(app_factory) -> None:
    app = app_factory.active_run("run_1")
    async with app.run_test() as pilot:
        await pilot.press("ctrl+c")
        assert app.controller.actions[-1] == CancelActiveRun(run_id="run_1")
        assert app.is_running


@pytest.mark.asyncio
async def test_ctrl_d_exits_only_when_idle_and_empty(app_factory) -> None:
    app = app_factory.empty()
    async with app.run_test() as pilot:
        await pilot.press("ctrl+d")
    assert app.return_value == 0
```

另测空闲非空 Ctrl+C 清空、空闲空输入 Ctrl+C 只提示、未决审批退出先 cancel、Resize 后保持 Composer 文本和审批焦点、End 回到底部。

- [ ] **Step 2：运行失败测试**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/terminal/test_keybindings.py tests/terminal/test_exit_semantics.py -v
```

- [ ] **Step 3：实现显式 action 和有序关闭**

关闭顺序固定为：提交未决 cancel → 等待 Controller 接受 → 停止 Worker → 恢复 Textual App。超时只结束 UI，不伪造 Core 终态；下次启动由阶段二 RecoveryClassifier 判定。

- [ ] **Step 4：完整验证、记录证据、提交并合并**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
git add src tests docs/evals/tui-composer-and-approvals.md docs/STATUS.md docs/tasks/0013-tui-composer-and-approvals.md
git commit -m "test: verify terminal input and approvals"
git switch main
git merge --no-ff feature/tui-composer-approvals -m "merge: add Vera terminal input and approvals"
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" -q
git branch -d feature/tui-composer-approvals
```

创建 `docs/evals/tui-composer-and-approvals.md`，记录审批类型、取消、动画关闭、按键和未执行 live。确认 `main` 干净后才开始任务 0014。
