# Vera 普通对话、会话上下文与状态命令实施计划

> **供 Cursor Agent 执行：** 必须逐任务执行本计划。使用单一主实现 Agent，不派发并行编辑 Agent。每个生产行为先写失败测试，再做最小实现；每项完成后独立提交。

**状态：** Complete

**目标分支：** `feature/conversational-cli-session`

**目标：** 让 Vera 在同一个 CLI 会话中同时支持普通对话和安全编码任务，保留进程内上下文，并提供紧凑启动状态与首批核心 Slash Command。

**架构：** 保持 `Command -> VeraRuntime -> Event` 为唯一任务执行边界。新增 UI 无关的 `ConversationContext` 管理临时会话历史，`StartRun` 以向后兼容字段接收上下文并区分 `agent`、`compact`；CLI 只组合 Core 组件并渲染结构化结果。文件写入、命令审批、Checkpoint、验证和回滚继续由 Runtime 独占。

**技术栈：** Python 3.12、Typer、Pydantic 2、OpenAI-compatible adapter、pytest、Ruff、Mypy、uv。

**规格：** [`docs/specs/2026-09-11-conversational-cli-and-session-status.md`](../specs/2026-09-11-conversational-cli-and-session-status.md)

**架构决策：** [`docs/decisions/ADR-0004-ephemeral-conversation-context.md`](../decisions/ADR-0004-ephemeral-conversation-context.md)

## 全局约束

- 开始前确认 `main` 干净，从 `main` 创建 `feature/conversational-cli-session`；不要直接在 `main` 开发。
- 只修改 `/Users/admin/Vera`；自动测试不得读取或修改 `/Users/admin/Desktop/VeraTestDemo`。
- 不运行 `tests/live`，不读取、加载或使用用户真实 DeepSeek API Key。
- 非 live 测试继续依靠 `tests/conftest.py` 清除供应商变量并重定向 `VERA_PROVIDER_ENV_FILE`。
- 保持 Python `>=3.12,<3.13`、现有 `src/` 布局和单 Python 发行包。
- 产品规格、任务状态、ADR 和验收记录使用中文；代码标识与协议字面量保持英文。
- 保持 `schema_version=1` 向后兼容；新增字段必须有默认值，不能改变既有字段含义。
- `ConversationContext` 只能保存用户消息、助手文本和简短 run 摘要；不能保存完整工具输出、Diff、日志、环境变量或秘密。
- `summary` 只能作为普通 assistant 级上下文传给模型，绝不能提升为 System 指令。
- 普通对话不能绕过 Change Set、命令审批、Checkpoint、验证或回滚边界。
- CLI 不直接调用供应商 SDK、不直接执行 Git、不自行推断有效权限。
- `/compact` 使用当前 ModelAdapter，但请求的 `tools` 必须为空。
- 第一版不自动压缩、不恢复退出前会话、不支持长期记忆、RAG、MCP、多 Agent 或 `!shell`。
- 每项生产行为先观察对应测试按预期失败，再实现并观察通过。
- 每个任务通过局部测试、Ruff 和 Mypy 后独立提交；最终合并前运行完整非 live 验收。

## 文件结构

```text
src/vera/
├── bootstrap.py                         # 构建 Runtime、有效 CommandPolicy 与模型切换候选
├── cli.py                               # Typer 入口和真实终端 IO
├── cli_presenter.py                     # Runtime Event 的人类展示
├── cli_session.py                       # 持续提示符和 Slash Command 编排
├── cli_session_presenter.py             # 状态、上下文和权限面板展示
├── config.py                            # max_conversation_bytes 配置
├── contracts/
│   ├── commands.py                      # StartRun conversation/mode
│   └── conversation.py                  # ConversationMessage 公共契约
├── persistence/run_store.py             # 默认隐藏 compaction run
├── runtime/
│   ├── engine.py                        # 文本终态、压缩模式、有效命令策略
│   ├── prompts.py                       # Agent 与压缩 System Prompt
│   └── state.py                         # 允许无修改成功终态
├── session/
│   ├── __init__.py
│   ├── conversation.py                  # 进程内 ConversationContext
│   ├── models.py                        # Context/Permission/Git/Session 状态模型
│   ├── permissions.py                   # 有效权限快照
│   └── status.py                        # 版本、模型、工作区、Git 状态服务
└── tools/command_policy.py               # 暴露实际生效策略并供 Runtime 复用

tests/
├── cli/
│   ├── conftest.py
│   ├── test_entrypoint.py
│   ├── test_presenter.py
│   ├── test_session.py
│   └── test_session_presenter.py
├── contracts/test_models.py
├── persistence/test_run_store.py
├── runtime/
│   ├── test_conversation_response.py
│   ├── test_context_compaction.py
│   └── test_safe_editing_flow.py
├── session/
│   ├── test_conversation.py
│   ├── test_permissions.py
│   └── test_status.py
├── tools/test_command_policy.py
└── test_config.py
```

---

### Task 1：扩展对话契约与容量配置

**文件：**

- Create: `src/vera/contracts/conversation.py`
- Modify: `src/vera/contracts/commands.py`
- Modify: `src/vera/config.py`
- Modify: `tests/contracts/test_models.py`
- Modify: `tests/test_config.py`

**接口：**

- Produces: `ConversationMessage(role: Literal["user", "assistant", "summary"], content: str)`
- Produces: `StartRun.conversation: tuple[ConversationMessage, ...] = ()`
- Produces: `StartRun.mode: Literal["agent", "compact"] = "agent"`
- Produces: `Limits.max_conversation_bytes: int = 200_000`
- Guarantee: 旧版 `StartRun` JSON 仍能按版本 1解析

- [x] **Step 1：编写契约和配置失败测试**

在 `tests/contracts/test_models.py` 增加：

```python
def test_start_run_accepts_conversation_and_round_trips() -> None:
    command = StartRun(
        goal="continue",
        workspace_root=Path("/tmp/project"),
        model_profile="fake",
        conversation=(
            ConversationMessage(role="user", content="inspect entry"),
            ConversationMessage(role="assistant", content="The entry is app.py"),
        ),
    )

    restored = StartRun.model_validate_json(command.model_dump_json())

    assert restored == command
    assert restored.mode == "agent"


def test_legacy_start_run_defaults_to_empty_agent_conversation() -> None:
    restored = StartRun.model_validate(
        {
            "schema_version": 1,
            "goal": "inspect",
            "workspace_root": "/tmp/project",
            "model_profile": "fake",
        }
    )

    assert restored.conversation == ()
    assert restored.mode == "agent"
```

在 `tests/test_config.py` 增加默认值和项目配置只能降低限制的测试：

```python
def test_conversation_limit_defaults_to_two_hundred_thousand(tmp_path: Path) -> None:
    config = load_config(tmp_path, {})
    assert config.limits.max_conversation_bytes == 200_000
```

- [x] **Step 2：运行测试并确认接口不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/contracts/test_models.py tests/test_config.py -v
```

预期：导入 `ConversationMessage` 失败，或 `StartRun`、`Limits` 缺少新字段。

- [x] **Step 3：实现最小公共契约**

`src/vera/contracts/conversation.py`：

```python
from typing import Literal

from pydantic import Field

from vera.contracts import ContractModel


class ConversationMessage(ContractModel):
    schema_version: Literal[1] = 1
    role: Literal["user", "assistant", "summary"]
    content: str = Field(min_length=1)
```

`StartRun` 增加带默认值字段：

```python
conversation: tuple[ConversationMessage, ...] = ()
mode: Literal["agent", "compact"] = "agent"
```

`Limits` 增加：

```python
max_conversation_bytes: int = Field(default=200_000, ge=1)
```

不要把 `ConversationMessage` 复用为模型内部带 tool call 的 `ModelMessage`。

- [x] **Step 4：运行契约、配置和静态检查**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/contracts/test_models.py tests/test_config.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check \
  src/vera/contracts src/vera/config.py tests/contracts tests/test_config.py
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Task 1**

```bash
git add src/vera/contracts/conversation.py src/vera/contracts/commands.py \
  src/vera/config.py tests/contracts/test_models.py tests/test_config.py \
  docs/tasks/0004-conversational-cli-and-session-status.md
git commit -m "feat: define conversational run contracts"
```

---

### Task 2：让普通文本和只读回答正常完成

**文件：**

- Create: `tests/runtime/test_conversation_response.py`
- Modify: `src/vera/runtime/engine.py`
- Modify: `src/vera/runtime/prompts.py`
- Modify: `src/vera/runtime/state.py`
- Modify: `tests/cli/test_session.py`

**接口：**

- Consumes: `StartRun(mode="agent", conversation=...)`
- Produces: `assistant.message` Event，Payload 为 `{"content": str}`
- Produces: `run.completed` Payload 包含 `state="completed"`、`outcome="responded"`
- Guarantee: 非空文本无工具调用是成功；空文本无工具调用才失败

- [x] **Step 1：编写普通文本终态失败测试**

创建 `tests/runtime/test_conversation_response.py`：

```python
def test_plain_assistant_text_completes_without_changes(tmp_path: Path) -> None:
    adapter = FakeModelAdapter(
        [ModelTurn(assistant_text="你好，我是 Vera。", finish_reason="stop")]
    )
    runtime = VeraRuntime(adapter, ToolRegistry(), tmp_path / "state")

    events = list(
        runtime.handle(
            StartRun(goal="Hello", workspace_root=tmp_path, model_profile="fake")
        )
    )

    assert [event.type for event in events][-2:] == [
        "assistant.message",
        "run.completed",
    ]
    assert events[-2].payload["content"] == "你好，我是 Vera。"
    assert events[-1].payload == {"state": "completed", "outcome": "responded"}
    assert not any(
        event.type
        in {"changeset.proposed", "approval.required", "checkpoint.created"}
        for event in events
    )


def test_empty_model_response_fails_explicitly(tmp_path: Path) -> None:
    adapter = FakeModelAdapter([ModelTurn(assistant_text="", finish_reason="stop")])
    runtime = VeraRuntime(adapter, ToolRegistry(), tmp_path / "state")

    events = list(
        runtime.handle(
            StartRun(goal="Hello", workspace_root=tmp_path, model_profile="fake")
        )
    )

    assert events[-1].type == "run.failed"
    assert events[-1].payload["reason"] == "empty_model_response"
```

再添加“调用 `read_file` 后第二轮返回文本”的测试，断言最终正常完成且没有 `changeset.proposed`、`approval.required`、`checkpoint.created`。

- [x] **Step 2：运行测试并确认当前 `no_changes_proposed` 行为失败**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/runtime/test_conversation_response.py tests/cli/test_session.py -v
```

预期：当前 Runtime 产生 `run.failed(reason=no_changes_proposed)`；既有 CLI 失败测试也需要更新语义。

- [x] **Step 3：实现文本成功终态**

把 Agent System Prompt 调整为：允许对普通问题直接给出文本；项目事实不足时先使用只读工具；只有需要修改文件时才调用 `propose_changeset`；不得声称未执行操作成功。

在 `RunState.DISCOVERING` 的允许目标中加入 `RunState.COMPLETED`。Runtime 收到无 tool call 的 turn 时执行：

```python
text = (turn.assistant_text or "").strip()
if not text:
    yield from self._fail(context, "empty_model_response")
    return
context.machine.transition(RunState.COMPLETED)
yield self._event(context, "assistant.message", {"content": text})
yield self._event(
    context,
    "run.completed",
    {"state": RunState.COMPLETED.value, "outcome": "responded"},
)
return
```

模型同时返回文本与 tool calls 时，本任务不把前导文本当作最终回答；继续执行工具，直到出现无 tool call 的最终文本或 Change Set。

更新 `tests/cli/test_session.py` 中原来把非空文本视为失败的用例：改为断言显示助手文本、返回提示符且 run 完成。

- [x] **Step 4：运行 Runtime、CLI 与静态检查**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/runtime/test_conversation_response.py tests/runtime tests/cli/test_session.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check \
  src/vera/runtime tests/runtime tests/cli/test_session.py
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Task 2**

```bash
git add src/vera/runtime/engine.py src/vera/runtime/prompts.py \
  src/vera/runtime/state.py tests/runtime/test_conversation_response.py \
  tests/cli/test_session.py docs/tasks/0004-conversational-cli-and-session-status.md
git commit -m "feat: complete conversational responses"
```

---

### Task 3：实现 UI 无关的进程内 ConversationContext

**文件：**

- Create: `src/vera/session/__init__.py`
- Create: `src/vera/session/models.py`
- Create: `src/vera/session/conversation.py`
- Create: `tests/session/__init__.py`
- Create: `tests/session/test_conversation.py`

**接口：**

- Produces: `ConversationStats(session_id, message_count, context_bytes, max_bytes, warning, compaction_count)`
- Produces: `ConversationContext(max_bytes: int, session_id_factory: Callable[[], str] | None = None)`
- Produces: `snapshot() -> tuple[ConversationMessage, ...]`
- Produces: `can_accept(content: str) -> bool`
- Produces: `record_response(user_text: str, assistant_text: str) -> None`
- Produces: `record_run(user_text: str, events: Sequence[EventEnvelope]) -> None`
- Produces: `replace_with_summary(summary: str) -> None`
- Produces: `reset() -> str`

- [x] **Step 1：编写会话上下文失败测试**

`tests/session/test_conversation.py` 至少覆盖：

```python
def test_context_records_conversation_in_order() -> None:
    context = ConversationContext(200_000, session_id_factory=lambda: "session-1")

    context.record_response("Hello", "你好")

    assert context.snapshot() == (
        ConversationMessage(role="user", content="Hello"),
        ConversationMessage(role="assistant", content="你好"),
    )
    assert context.stats().message_count == 2


def test_code_run_stores_summary_without_diff_or_tool_output() -> None:
    context = ConversationContext(200_000, session_id_factory=lambda: "session-1")
    events = (
        event("tool.completed", {"name": "read_file", "content": "secret body"}),
        event("changeset.proposed", {"unified_diff": "must-not-be-stored"}, sequence=2),
        event("changeset.applied", {"status": "applied"}, sequence=3),
        event(
            "run.completed",
            {"state": "completed", "outcome": "changed"},
            sequence=4,
        ),
    )

    context.record_run("change color", events)

    serialized = "\n".join(message.content for message in context.snapshot())
    assert "change color" in serialized
    assert "已应用" in serialized
    assert "secret body" not in serialized
    assert "must-not-be-stored" not in serialized
```

再覆盖：70% 警戒线、超过上限拒绝、`reset()` 更换 session ID、`replace_with_summary()` 原子替换、空摘要拒绝、失败/取消 run 的确定性简短摘要。

- [x] **Step 2：运行测试并确认 session 模块不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/session/test_conversation.py -v
```

预期：导入 `vera.session.conversation` 或接口失败。

- [x] **Step 3：实现 ConversationContext**

使用私有 `list[ConversationMessage]`，所有写入先构造候选列表并计算 UTF-8 字节，确认不超过 `max_bytes` 后再整体替换。`summary` 映射保持普通上下文角色，不能成为 System Prompt。

核心容量计算使用实际序列化内容，不使用 Python 字符数：

```python
def _content_bytes(messages: Sequence[ConversationMessage]) -> int:
    return sum(len(message.content.encode("utf-8")) for message in messages)
```

`record_run` 只从 Event 类型和有限字段生成确定性摘要，不复制任意 Payload。结果示例：

```text
run run_123 已应用 Change Set，验证通过。
run run_456 已取消，工作区未应用该 Change Set。
run run_789 失败：model_error。
```

`reset()` 清空消息和压缩次数，并通过注入的 factory 生成新 session ID，保证测试可重复。

- [x] **Step 4：运行会话模型和静态检查**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/session/test_conversation.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/session tests/session
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Task 3**

```bash
git add src/vera/session tests/session \
  docs/tasks/0004-conversational-cli-and-session-status.md
git commit -m "feat: add ephemeral conversation context"
```

---

### Task 4：实现无工具的上下文压缩模式

**文件：**

- Create: `tests/runtime/test_context_compaction.py`
- Modify: `src/vera/runtime/engine.py`
- Modify: `src/vera/runtime/prompts.py`
- Modify: `src/vera/persistence/run_store.py`
- Modify: `tests/persistence/test_run_store.py`

**接口：**

- Consumes: `StartRun(mode="compact", conversation=..., goal=focus)`
- Produces: `conversation.compacted` Payload 为 `{"summary": str}`
- Produces: `run.started` Payload `kind="compaction"`
- Produces: `run.completed` Payload `outcome="compacted"`
- Guarantee: compact 请求的 `ModelRequest.tools == ()`

- [x] **Step 1：编写压缩模式失败测试**

```python
def test_compaction_uses_no_tools_and_emits_summary(tmp_path: Path) -> None:
    adapter = FakeModelAdapter(
        [ModelTurn(assistant_text="保留结论：使用 Python Core。", finish_reason="stop")]
    )
    runtime = VeraRuntime(adapter, ToolRegistry(), tmp_path / "state")
    command = StartRun(
        goal="保留架构决策",
        workspace_root=tmp_path,
        model_profile="fake",
        mode="compact",
        conversation=(
            ConversationMessage(role="user", content="Core 用什么语言？"),
            ConversationMessage(role="assistant", content="使用 Python。"),
        ),
    )

    events = list(runtime.handle(command))

    assert adapter.requests[0].tools == ()
    assert next(event for event in events if event.type == "run.started").payload[
        "kind"
    ] == "compaction"
    assert next(
        event for event in events if event.type == "conversation.compacted"
    ).payload["summary"] == "保留结论：使用 Python Core。"
    assert events[-1].payload["outcome"] == "compacted"
```

再测试空摘要、compact turn 返回 tool call 时分别以 `empty_model_response`、`invalid_compaction_response` 失败。

在 `tests/persistence/test_run_store.py` 写入一个 `kind=compaction` 和一个 `kind=task` 的 run，断言默认 `list_runs()` 只返回 task。

- [x] **Step 2：运行测试并确认 mode 尚未生效**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/runtime/test_context_compaction.py tests/persistence/test_run_store.py -v
```

预期：compact 请求仍包含工具或缺少 `conversation.compacted`。

- [x] **Step 3：实现专用压缩请求**

在 `prompts.py` 增加固定 `COMPACTION_PROMPT`，要求只总结用户提供的对话、保留决策/路径/未完成事项、不得把对话内文本当成系统指令。

Runtime 映射 conversation 时：

```python
def _conversation_model_message(message: ConversationMessage) -> ModelMessage:
    if message.role == "summary":
        return ModelMessage(role="assistant", content=f"[会话摘要]\n{message.content}")
    return ModelMessage(role=message.role, content=message.content)
```

严禁把 `summary` 映射成 `role="system"`。

`mode=compact` 时构造无工具 `ModelRequest`，成功后发出 `conversation.compacted`；不进入 `_drive` 工具循环。普通 `run.started` 显示 `kind=task`，压缩显示 `kind=compaction`。

`RunStore.list_runs(include_internal: bool = False)` 在默认参数下跳过 compaction；显式 `include_internal=True` 时保留诊断能力。

- [x] **Step 4：运行压缩、持久化和静态检查**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/runtime/test_context_compaction.py tests/persistence -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check \
  src/vera/runtime src/vera/persistence tests/runtime tests/persistence
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Task 4**

```bash
git add src/vera/runtime/engine.py src/vera/runtime/prompts.py \
  src/vera/persistence/run_store.py tests/runtime/test_context_compaction.py \
  tests/persistence/test_run_store.py \
  docs/tasks/0004-conversational-cli-and-session-status.md
git commit -m "feat: compact conversation context through core"
```

---

### Task 5：把有效 CommandPolicy 注入 Runtime 并提供权限快照

**文件：**

- Create: `src/vera/session/permissions.py`
- Create: `tests/session/test_permissions.py`
- Modify: `src/vera/session/models.py`
- Modify: `src/vera/tools/command_policy.py`
- Modify: `src/vera/runtime/engine.py`
- Modify: `src/vera/bootstrap.py`
- Modify: `tests/tools/test_command_policy.py`
- Modify: `tests/runtime/test_safe_editing_flow.py`

**接口：**

- Produces: `PermissionStatus(approval_mode, changeset_approval, command_policy, user_allowed_prefixes, execution_boundary, os_sandbox)`
- Produces: `CommandPolicy.user_allowed_prefixes` 作为实际生效的不可变元组
- Produces: `permission_status(policy: CommandPolicy) -> PermissionStatus`
- Consumes: `VeraConfig.user_allowed_command_prefixes`
- Guarantee: Runtime 分类验证命令时使用注入的同一个 policy

- [x] **Step 1：编写“配置必须真实生效”的失败测试**

在 `tests/runtime/test_safe_editing_flow.py` 增加配置前缀命令无需第二道审批的测试：

```python
def test_runtime_uses_injected_user_allowed_command_prefix(tmp_path: Path) -> None:
    policy = CommandPolicy(user_allowed_prefixes=((sys.executable, "-c"),))
    runtime = runtime_with_verification_command(
        tmp_path,
        (sys.executable, "-c", "print('verified')"),
        command_policy=policy,
    )

    start_events = list(runtime.handle(start(tmp_path)))
    approval = next(event for event in start_events if event.type == "approval.required")
    final_events = list(runtime.handle(resolve(approval, "approve")))

    assert not any(event.type == "approval.required" for event in final_events)
    assert final_events[-1].type == "run.completed"
```

在 `tests/session/test_permissions.py` 断言快照只包含实际 policy 的前缀，并显示 `manual`、`current user`、`False` OS sandbox；不得包含供应商配置。

- [x] **Step 2：运行测试并确认 Runtime 当前新建默认 policy**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/runtime/test_safe_editing_flow.py tests/session/test_permissions.py -v
```

预期：`VeraRuntime` 不接受 `command_policy`，或命令仍产生审批。

- [x] **Step 3：注入并复用有效策略**

Runtime 构造函数增加：

```python
command_policy: CommandPolicy | None = None
```

并保存：

```python
self.command_policy = command_policy or CommandPolicy()
```

`_verify` 只能使用 `self.command_policy`，不能每次创建 `CommandPolicy()`。`build_runtime` 使用：

```python
policy = CommandPolicy(config.user_allowed_command_prefixes)
runtime = VeraRuntime(
    adapter,
    registry,
    config.state_dir,
    config.limits,
    command_policy=policy,
)
```

`permission_status()` 从传入 policy 生成冻结状态对象。不得把“配置存在但未注入”的前缀显示为有效。

- [x] **Step 4：运行策略、Runtime 和静态检查**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/tools/test_command_policy.py tests/session/test_permissions.py \
  tests/runtime/test_safe_editing_flow.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check \
  src/vera/tools src/vera/session src/vera/runtime src/vera/bootstrap.py \
  tests/tools tests/session tests/runtime
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Task 5**

```bash
git add src/vera/tools/command_policy.py src/vera/session/models.py \
  src/vera/session/permissions.py src/vera/runtime/engine.py src/vera/bootstrap.py \
  tests/tools/test_command_policy.py tests/session/test_permissions.py \
  tests/runtime/test_safe_editing_flow.py \
  docs/tasks/0004-conversational-cli-and-session-status.md
git commit -m "fix: expose effective runtime permissions"
```

---

### Task 6：实现 UI 无关的会话状态服务

**文件：**

- Create: `src/vera/session/status.py`
- Create: `tests/session/test_status.py`
- Modify: `src/vera/session/models.py`
- Modify: `src/vera/bootstrap.py`

**接口：**

- Produces: `GitStatus(available: bool, branch: str | None, dirty: bool | None)`
- Produces: `SessionStatus(version, model_profile, model_name, workspace, git, context, permissions)`
- Produces: `WorkspaceStatusProbe.inspect(workspace: Path) -> GitStatus`
- Produces: `SessionStatusService.snapshot(...) -> SessionStatus`
- Guarantee: Git 只通过固定 argv、无 Shell、只读、3 秒超时执行

- [x] **Step 1：编写状态服务失败测试**

使用注入 runner，不能让单元测试依赖本机 Git 状态：

```python
def test_status_contains_safe_session_fields(tmp_path: Path) -> None:
    runner = FakeGitRunner(
        branch=CompletedProcess([], 0, "main\n", ""),
        status=CompletedProcess([], 0, " M README.md\n", ""),
    )
    service = SessionStatusService(version_reader=lambda: "0.1.0", git_runner=runner)

    status = service.snapshot(
        workspace=tmp_path,
        model_profile="deepseek",
        model_name="deepseek-flash",
        conversation=ConversationStats(
            session_id="session-1",
            message_count=2,
            context_bytes=20,
            max_bytes=200_000,
            warning=False,
            compaction_count=0,
        ),
        permissions=manual_permissions(),
    )

    assert status.workspace == tmp_path.resolve()
    assert status.git.branch == "main"
    assert status.git.dirty is True
    assert "api" not in status.model_dump_json().lower()
```

再测试：非 Git 返回 `available=False`；branch 查询失败、status 查询超时或版本读取失败分别降级为 `unavailable`，且 `snapshot()` 不抛异常。

- [x] **Step 2：运行测试并确认状态服务不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/session/test_status.py -v
```

预期：导入 `SessionStatusService` 失败。

- [x] **Step 3：实现固定 argv 状态探测**

实际 Git runner 只允许：

```python
("git", "-C", str(workspace), "symbolic-ref", "--short", "HEAD")
("git", "-C", str(workspace), "status", "--porcelain=v1")
```

使用 `subprocess.run(..., shell=False, capture_output=True, text=True, timeout=3, check=False)`。不接受用户输入的 Git 参数，不调用 shell。版本通过 `importlib.metadata.version("vera-agent")` 获取；异常时返回 `unavailable`。

`SessionStatusService` 只组合显式传入的模型名、ConversationStats 和 PermissionStatus，不读取环境变量，不接收 API Key 或 Base URL。

- [x] **Step 4：运行状态、配置和静态检查**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/session/test_status.py tests/test_config.py tests/cli/test_entrypoint.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check \
  src/vera/session src/vera/bootstrap.py tests/session
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Task 6**

```bash
git add src/vera/session/models.py src/vera/session/status.py \
  src/vera/bootstrap.py tests/session/test_status.py \
  docs/tasks/0004-conversational-cli-and-session-status.md
git commit -m "feat: report structured Vera session status"
```

---

### Task 7：展示助手文本与会话状态面板

**文件：**

- Create: `src/vera/cli_session_presenter.py`
- Create: `tests/cli/test_session_presenter.py`
- Modify: `src/vera/cli_presenter.py`
- Modify: `tests/cli/test_presenter.py`

**接口：**

- Produces: `HumanPresenter` 对 `assistant.message`、`conversation.compacted` 的稳定展示
- Produces: `SessionPresenter.write_status(status: SessionStatus) -> None`
- Produces: `SessionPresenter.write_context(stats: ConversationStats) -> None`
- Produces: `SessionPresenter.write_permissions(status: PermissionStatus) -> None`
- Consumes: 注入的 `write: Callable[[str], None]`

- [x] **Step 1：编写人类展示失败测试**

```python
def test_presenter_displays_plain_assistant_message() -> None:
    output: list[str] = []
    presenter = HumanPresenter(output.append)

    presenter.write_events((event("assistant.message", {"content": "你好"}),))

    assert output == ["Vera：你好"]
```

状态面板测试断言包含版本、`deepseek / deepseek-flash`、绝对工作区、`main · dirty`、消息数量、`manual`、`no OS sandbox`；断言不包含测试 Key 和 Base URL。

上下文展示只允许统计字段：测试消息正文使用 `must-not-render`，确认输出中不存在该字符串。权限展示必须逐项显示 Change Set 审批、命令策略、有效前缀和执行边界。

- [x] **Step 2：运行测试并确认新增 Event 回退为事件名**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/cli/test_presenter.py tests/cli/test_session_presenter.py -v
```

预期：`assistant.message` 只显示事件名，且 `SessionPresenter` 不存在。

- [x] **Step 3：实现稳定的纯展示层**

`HumanPresenter` 对 `assistant.message` 只读取 `payload["content"]`；对 `conversation.compacted` 显示“上下文已压缩”和摘要字节数，不重复打印整份摘要。

`SessionPresenter` 使用固定字段顺序：

```text
Vera <version>

Model       <profile> / <model>
Workspace   <absolute-path>
Git         <branch> · <clean|dirty>
Session     <session-id> · <message-count> messages
Context     <bytes>/<max-bytes> bytes · compacted <count>
Approval    manual
Execution   current user · no OS sandbox
```

非 Git 显示 `not a repository`，失败字段显示 `unavailable`。展示类不读取文件、环境或 Git。

- [x] **Step 4：运行展示与静态检查**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/cli/test_presenter.py tests/cli/test_session_presenter.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check \
  src/vera/cli_presenter.py src/vera/cli_session_presenter.py tests/cli
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Task 7**

```bash
git add src/vera/cli_presenter.py src/vera/cli_session_presenter.py \
  tests/cli/test_presenter.py tests/cli/test_session_presenter.py \
  docs/tasks/0004-conversational-cli-and-session-status.md
git commit -m "feat: render conversational session status"
```

---

### Task 8：把会话上下文与核心只读命令接入 InteractiveSession

**文件：**

- Modify: `src/vera/cli_session.py`
- Modify: `src/vera/cli.py`
- Modify: `tests/cli/conftest.py`
- Modify: `tests/cli/test_session.py`
- Modify: `tests/cli/test_entrypoint.py`

**接口：**

- Consumes: `ConversationContext`、`SessionStatusService`、`SessionPresenter`
- Produces: `/new`、`/clear`、`/context`、`/status`、`/permissions`
- Produces: `SessionIO.clear() -> None`
- Guarantee: 每个普通输入把 `conversation.snapshot()` 传给 `StartRun`

- [x] **Step 1：编写连续对话和命令失败测试**

测试两个普通输入，FakeModelAdapter 准备两个文本 turn：

```python
def test_second_goal_receives_first_conversation_pair(session_fixture) -> None:
    session, adapter, io = session_fixture(
        inputs=["Hello", "刚才说了什么？", "/exit"],
        turns=[
            ModelTurn(assistant_text="你好", finish_reason="stop"),
            ModelTurn(assistant_text="我刚才说你好", finish_reason="stop"),
        ],
    )

    assert session.run() == 0

    second_messages = adapter.requests[1].messages
    assert [(message.role, message.content) for message in second_messages[-3:]] == [
        ("user", "Hello"),
        ("assistant", "你好"),
        ("user", "刚才说了什么？"),
    ]
```

再测试：

- `/new` 后下一请求不包含旧消息且 session ID 改变；
- `/clear` 调用 `SessionIO.clear()` 并完成 `/new` 语义；
- `/context`、`/status`、`/permissions` 不调用模型；
- 上下文达到 70% 后提示 `/compact`；超过上限时拒绝自然语言输入但 `/new` 可恢复；
- 启动首先显示状态面板，再出现 `Vera >`；
- `/help` 列出所有本增量命令。

- [x] **Step 2：运行测试并确认当前会话不传历史**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/cli/test_session.py tests/cli/test_entrypoint.py -v
```

预期：第二个 ModelRequest 不含第一轮消息，Slash Command 未识别。

- [x] **Step 3：接入上下文与只读命令**

`InteractiveSession` 构造函数显式接收或创建：

```python
conversation: ConversationContext
status_service: SessionStatusService
```

`_run_goal` 使用当前快照：

```python
events = drive_run(
    self.dependencies.runtime,
    StartRun(
        goal=goal,
        workspace_root=self.workspace,
        model_profile=self.model_profile,
        conversation=self.conversation.snapshot(),
    ),
    self._decide,
    self.presenter.write_events,
)
self.conversation.record_run(goal, events)
```

若 events 含 `assistant.message`，`record_run` 保存该准确文本；代码、失败或取消 run 只保存确定性摘要。

扩展 `SessionIO` 为 `clear()`。真实 `_ConsoleSessionIO.clear()` 仅在 TTY 输出清屏控制符；测试 IO 记录调用。`/clear` 即使清屏失败也先完成 context reset，并打印确认。

`/status` 每次从服务重新组合状态；`/permissions` 传入 Runtime 的实际 `command_policy`；不得读取配置副本冒充有效策略。

- [x] **Step 4：运行全部会话测试和静态检查**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/cli/test_session.py tests/cli/test_entrypoint.py \
  tests/cli/test_session_presenter.py tests/session -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check \
  src/vera/cli.py src/vera/cli_session.py src/vera/cli_session_presenter.py \
  tests/cli tests/session
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Task 8**

```bash
git add src/vera/cli.py src/vera/cli_session.py \
  tests/cli/conftest.py tests/cli/test_session.py tests/cli/test_entrypoint.py \
  docs/tasks/0004-conversational-cli-and-session-status.md
git commit -m "feat: retain in-process Vera conversation"
```

---

### Task 9：接入 `/compact` 与安全 `/model` 切换

**文件：**

- Modify: `src/vera/bootstrap.py`
- Modify: `src/vera/cli_session.py`
- Modify: `src/vera/cli.py`
- Modify: `tests/cli/conftest.py`
- Modify: `tests/cli/test_session.py`
- Modify: `tests/cli/test_entrypoint.py`

**接口：**

- Produces: `RuntimeBuilder = Callable[[Path, str | None], RuntimeDependencies]`
- Produces: `/compact [focus]`
- Produces: `/model [profile]`
- Guarantee: 压缩与模型切换都是事务式，失败保留原上下文和 Runtime

- [x] **Step 1：编写压缩和模型切换失败测试**

压缩成功测试：

```python
def test_compact_replaces_context_only_after_success(session_fixture) -> None:
    session, adapter, io = session_fixture(
        inputs=["Hello", "/compact 保留问候", "/context", "/exit"],
        turns=[
            ModelTurn(assistant_text="你好", finish_reason="stop"),
            ModelTurn(assistant_text="摘要：用户与 Vera 互相问候。", finish_reason="stop"),
        ],
    )

    assert session.run() == 0

    assert adapter.requests[1].tools == ()
    assert session.conversation.snapshot() == (
        ConversationMessage(role="summary", content="摘要：用户与 Vera 互相问候。"),
    )
    assert session.conversation.stats().compaction_count == 1
```

再测试：空上下文 `/compact` 不调用模型；压缩失败后 snapshot 完全相等；`/model` 显示当前 profile/model；有效 profile 候选构建成功后才替换 Runtime；未知 profile 或 builder 抛错时保留原 Runtime、profile、ConversationContext。

- [x] **Step 2：运行测试并确认命令未知**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/cli/test_session.py -v
```

预期：`/compact`、`/model` 被报告为未知或不改变状态。

- [x] **Step 3：实现事务式压缩和模型切换**

`InteractiveSession` 接收 `runtime_builder`，默认使用 `build_runtime`。`/model <profile>` 先构建局部候选：

```python
candidate = self.runtime_builder(self.workspace, requested_profile)
self.dependencies = candidate
self.model_profile = requested_profile
self.store = RunStore(candidate.config.state_dir)
```

只有 `candidate` 完全构建成功后执行后三行赋值。失败时捕获异常并显示脱敏错误，不修改现有字段。

`/compact` 先保存 `before = conversation.snapshot()`，运行 `StartRun(mode="compact", conversation=before, goal=focus)`。只有拿到一个非空 `conversation.compacted` Event 且最终为 `run.completed/outcome=compacted` 时调用 `replace_with_summary()`；否则保留 `before`。

压缩 run 使用当前 profile，不能走审批，不能包含任何工具定义。空上下文直接显示“当前上下文为空”，不创建 run。

- [x] **Step 4：运行全部 CLI、压缩和静态检查**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/cli tests/runtime/test_context_compaction.py tests/session -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests/cli tests/session
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Task 9**

```bash
git add src/vera/bootstrap.py src/vera/cli.py src/vera/cli_session.py \
  tests/cli/conftest.py tests/cli/test_session.py tests/cli/test_entrypoint.py \
  docs/tasks/0004-conversational-cli-and-session-status.md
git commit -m "feat: manage Vera context and model commands"
```

---

### Task 10：完成兼容性、离线验收和文档收口

**文件：**

- Create: `docs/evals/conversational-cli-and-session-status.md`
- Modify: `README.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/tasks/0004-conversational-cli-and-session-status.md`
- Modify: `tests/cli/test_run.py`
- Modify: `tests/cli/test_entrypoint.py`

**接口：**

- Preserves: `vera run`、`vera runs`、`vera rollback`、`vera config`
- Preserves: `vera run ... --json` 无提示符、无 ANSI、审批时安全取消
- Produces: 可复核的完整非 live 验收记录

- [x] **Step 1：补充回归与秘密边界测试**

新增测试断言：

```python
def test_json_plain_response_contains_events_without_human_output(
    tmp_path: Path, monkeypatch
) -> None:
    deps = dependencies_with_text_turn(tmp_path, "hello")
    monkeypatch.setattr("vera.cli.build_runtime", lambda *_args, **_kwargs: deps)

    result = CliRunner().invoke(
        app,
        ["run", "Hello", "--workspace", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    assert '"type":"assistant.message"' in result.stdout
    assert '"outcome":"responded"' in result.stdout
    assert "Vera：" not in result.stdout
    assert "Vera >" not in result.stdout
    assert "\x1b" not in result.stdout
```

状态和命令输出测试设置假的 `DEEPSEEK_API_KEY=must-not-render`、假的 Base URL，断言完整 CLI 输出不包含二者。现有 JSON 审批取消、回滚和历史命令测试必须继续通过。

- [x] **Step 2：运行完整非 live 验收**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

全部命令必须退出码为 0。若 `uv build` 只因沙箱 DNS 无法解析 PyPI 失败，应记录该环境证据并由用户在本机重跑；不能把网络失败伪装成构建通过。

- [x] **Step 3：仓库外离线启动验收**

```bash
uv tool install --editable /Users/admin/Vera
command -v vera
mkdir -p /private/tmp/vera-conversation-acceptance
cd /private/tmp/vera-conversation-acceptance
```

使用测试专用假的供应商环境启动，只输入 `/status`、`/context`、`/permissions`、`/new`、`/clear`、`/exit`。不得输入自然语言任务，确保不发起真实模型请求；不得加载用户私有环境文件。

```bash
DEEPSEEK_API_KEY=offline-test-not-used \
VERA_DEEPSEEK_BASE_URL=https://127.0.0.1:9 \
VERA_DEEPSEEK_MODEL=offline-test \
VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file \
VERA_STATE_DIR=/private/tmp/vera-conversation-state \
vera
```

`VERA_PROVIDER_ENV_FILE` 指向不存在的测试路径，且进程环境先注入假的完整 Provider 配置，因此不会读取用户私有配置。由于本验收只执行本地 Slash Command，任何网络请求都属于失败。

验证启动状态包含工作区、模型、会话和安全边界，输出中没有测试 Key 或 Base URL。真实 DeepSeek 普通对话与 iOS 工程回归留给用户后续明确执行。

- [x] **Step 4：更新中文文档与验收记录**

`README.md` 增加普通对话、会话内上下文和 Slash Command 示例。`docs/evals/conversational-cli-and-session-status.md` 逐项记录规格 16 条验收标准、测试数量、覆盖率、静态检查、构建、仓库外启动、未执行 live 测试和已知限制。

`docs/STATUS.md` 更新当前分支、已完成能力、验证证据和下一检查点。任务状态改为 `Complete`，但只有所有检查成功后才能勾选本任务。

- [x] **Step 5：检查文档一致性和工作树**

```bash
rg -n "Draf[t]|TB[D]|TOD[O]|no_changes_proposed|普通对话.*未实现|会话上下文.*未实现" \
  docs README.md
git diff --check
git status --short --branch
```

允许 `no_changes_proposed` 只出现在历史验收记录中，并必须标明它是已修复前的历史现象。不要删除历史证据。

- [x] **Step 6：提交 Task 10**

```bash
git add README.md docs/STATUS.md \
  docs/evals/conversational-cli-and-session-status.md \
  docs/tasks/0004-conversational-cli-and-session-status.md \
  tests/cli/test_run.py tests/cli/test_entrypoint.py
git commit -m "test: verify conversational Vera CLI"
```

- [x] **Step 7：合并回 main**

在功能分支工作区干净且完整验证通过后：

```bash
git switch main
git merge --no-ff feature/conversational-cli-session \
  -m "merge: integrate conversational Vera CLI"
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git branch -d feature/conversational-cli-session
```

仓库没有 remote 时准确记录“已本地合并、未推送”，不能宣称 push 成功。

## 规格覆盖索引

| 规格能力 | 实施任务 |
|---|---|
| 普通文本与只读回答正常完成 | Task 2、Task 7 |
| 会话内连续上下文 | Task 1、Task 3、Task 8 |
| 代码任务安全边界保持 | Task 2、Task 5、Task 8、Task 10 |
| `/new`、`/clear`、`/context` | Task 3、Task 8 |
| `/compact` 无工具且事务式 | Task 4、Task 9 |
| `/status` 与启动状态 | Task 6、Task 7、Task 8 |
| `/permissions` 显示有效策略 | Task 5、Task 7、Task 8 |
| `/model` 安全切换 | Task 6、Task 9 |
| 历史命令和 JSON 兼容 | Task 4、Task 10 |
| 凭据、工作区和测试隔离 | 全局约束、Task 6、Task 10 |
| 文档、构建与最终证据 | Task 10 |
