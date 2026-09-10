# Vera Core 安全编辑垂直切片实施计划

> **供执行 Agent 使用：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按任务逐项实施本计划。每个步骤使用复选框跟踪；未经用户明确选择，不得自行派发子 Agent。

**状态：** In progress

**当前执行分支：** `codex/core-safe-editing`

**目标：** 实现一个可安装的 Python `vera` CLI，由 `VeraRuntime` 完成一次“上下文收集 → Change Set 审批 → Checkpoint → 写入 → 验证 → 手动回滚”的安全编辑闭环。

**架构：** `VeraRuntime` 是唯一产品权威，统一接收版本化 Command 并输出有序 Event。模型、工具、工作区、验证、持久化和 CLI 通过小接口组合；供应商 SDK 类型和终端格式不能进入 Core 契约。

**技术栈：** Python 3.12、uv、Hatchling、Pydantic 2、Typer、Rich、platformdirs、OpenAI Python Client、pytest、pytest-cov、Ruff、Mypy。

**规格：** [`docs/specs/2026-09-10-core-safe-editing-vertical-slice.md`](../specs/2026-09-10-core-safe-editing-vertical-slice.md)

## 全局约束

- 只在 `/Users/admin/Vera` 实施；`/Users/admin/Coding-harness` 只读且不得复制代码。
- 运行环境锁定为 Python `>=3.12,<3.13`；当前已验证本机为 Python `3.12.2`。
- 使用 `src/` 布局和一个 Python 发行包，不提前拆分服务。
- `VeraRuntime` 独占状态转换、审批、Checkpoint、写入、验证和回滚权威。
- 公共边界只使用 `schema_version: 1` 的 Pydantic Model，并且可序列化为 JSON。
- 模型没有直接写文件的工具；Runtime 根据模型意图生成哈希和统一 Diff。
- 所有命令通过 `subprocess` 参数数组并设置 `shell=False`；禁止 Shell 解释。
- 命令进程不是操作系统沙箱；需要审批的命令必须明确提示其以当前用户权限运行，不能把受限 cwd 描述成完整文件系统隔离。
- 目标文件写入前必须完成 Checkpoint；应用失败时尝试恢复；验证失败时保留现场供手动回滚。
- 默认限制严格采用规格值：20 个模型轮次、50 次工具调用、单文件 1,000,000 字节、单工具输出 100,000 字节、总上下文 2,000,000 字节、单验证命令 120 秒。
- 默认测试不联网、不使用真实 API Key；在线测试必须显式选择并控制成本。
- 每个任务只有一个主实现 Agent；高风险策略、写入与回滚任务使用 Sol 高。
- 每个任务遵循 Red → Green → Refactor，并在独立检查通过后提交。
- 文档使用中文；代码标识、命令、协议字段和 Event 名保持规范英文。

## 当前环境与执行前置

- Git 分支：`main`；计划编写前工作区干净。
- 当前没有 Agent 源码、Python 依赖清单或远程仓库。
- 本机为 Intel macOS；Homebrew 会回退到 Rust 源码构建。执行 Task 1 前，使用 uv 官方独立安装器安装 `0.12.10`，再运行 `uv --version`；后续机器若有可用 bottle，可使用 Homebrew。
- uv 使用 `pyproject.toml` 管理依赖并提交跨平台 `uv.lock`；每次验证使用 `uv run`。
- OpenAI-compatible Adapter 使用 OpenAI Python Client 的 Chat Completions 形状，因为 DeepSeek 和 GLM 官方接口均支持该兼容形式；供应商 Base URL 和模型名保留为本地配置。

参考资料：

- [uv 项目与锁文件](https://docs.astral.sh/uv/guides/projects/)
- [OpenAI Python Client](https://github.com/openai/openai-python)
- [DeepSeek API 官方文档](https://api-docs.deepseek.com/)
- [GLM OpenAI API 兼容文档](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction)
- [GLM 工具调用文档](https://docs.bigmodel.cn/cn/guide/capabilities/function-calling)

## 计划文件结构

```text
pyproject.toml
.python-version
uv.lock
src/vera/
├── __init__.py
├── cli.py
├── bootstrap.py
├── config.py
├── redaction.py
├── contracts/
│   ├── __init__.py
│   ├── commands.py
│   ├── events.py
│   ├── changes.py
│   ├── approvals.py
│   ├── checkpoints.py
│   └── verification.py
├── runtime/
│   ├── __init__.py
│   ├── approval.py
│   ├── engine.py
│   ├── context.py
│   ├── prompts.py
│   └── state.py
├── models/
│   ├── __init__.py
│   ├── base.py
│   └── openai_compatible.py
├── tools/
│   ├── __init__.py
│   ├── definitions.py
│   ├── registry.py
│   ├── filesystem.py
│   └── command_policy.py
├── workspace/
│   ├── __init__.py
│   ├── paths.py
│   ├── changeset.py
│   ├── checkpoint.py
│   └── apply.py
├── persistence/
│   ├── __init__.py
│   ├── journal.py
│   └── run_store.py
└── verification/
    ├── __init__.py
    └── runner.py
tests/
├── conftest.py
├── fakes.py
├── contracts/
├── runtime/
├── tools/
├── workspace/
├── persistence/
├── verification/
├── cli/
├── e2e/
└── live/
```

测试片段中的简化辅助对象不是生产接口：全局的 `state_dir` 等临时状态 fixture 放在 `tests/conftest.py`；`RuntimeFixture` 放在 `tests/runtime/conftest.py`；CLI 的 `test_dependencies` 放在 `tests/cli/conftest.py`；`GitFixture` 和端到端运行辅助函数放在 `tests/e2e/conftest.py`。只在单个测试模块使用的 `update`、`create`、`pytest_command`、`seed_two_files` 等 helper 就地定义在该模块，不暴露给生产代码。

---

### Task 1：治理同步与可安装 Python 骨架

**主执行档位：** Sol 高

**文件：**

- Create: `docs/decisions/ADR-0001-python-core-runtime.md`
- Create: `docs/decisions/ADR-0002-command-event-contract.md`
- Create: `docs/decisions/ADR-0003-private-state-and-checkpoints.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/STATUS.md`
- Modify: `.gitignore`
- Create: `.python-version`
- Create: `pyproject.toml`
- Create: `uv.lock`（由 uv 生成）
- Create: `src/vera/__init__.py`
- Create: `tests/test_package.py`

**接口：**

- Produces: `vera.__version__: str`
- Produces: `vera` Console Script，入口暂指向 `vera.cli:app`
- Produces: 三份 Accepted ADR，后续任务以其为技术约束

- [x] **Step 1：安装并验证 uv**

先取得用户对本机工具安装的授权，然后运行官方独立安装器：

```bash
curl -LsSf https://astral.sh/uv/0.12.10/install.sh | sh
exec zsh -l
uv --version
```

预期：`uv --version` 退出码为 `0`。

- [x] **Step 2：编写包版本失败测试**

先创建 `src/vera/__init__.py`：

```python
"""Vera Core public package."""
```

再创建 `tests/test_package.py`：

```python
import vera


def test_package_exposes_version() -> None:
    assert vera.__version__ == "0.1.0"
```

- [x] **Step 3：建立项目清单并确认测试先失败**

创建 `.python-version`，内容为 `3.12`。创建 `pyproject.toml`：

```toml
[build-system]
requires = ["hatchling>=1.27,<2"]
build-backend = "hatchling.build"

[project]
name = "vera-agent"
version = "0.1.0"
description = "Local, inspectable, and recoverable coding agent core"
requires-python = ">=3.12,<3.13"
dependencies = [
  "openai>=2,<3",
  "platformdirs>=4,<5",
  "pydantic>=2,<3",
  "rich>=14,<15",
  "typer>=0.16,<1",
]

[project.optional-dependencies]
dev = [
  "mypy>=1,<2",
  "pytest>=8,<10",
  "pytest-cov>=6,<8",
  "ruff>=0.12,<1",
]

[project.scripts]
vera = "vera.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["src/vera"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["live: requires an explicitly selected real provider and API key"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.12"
strict = true
packages = ["vera"]
```

运行：

```bash
uv sync --extra dev
uv run pytest tests/test_package.py -v
```

预期：FAIL，错误包含 `AttributeError: module 'vera' has no attribute '__version__'`。

- [x] **Step 4：实现最小包并通过测试**

修改 `src/vera/__init__.py`：

```python
"""Vera Core public package."""

__version__ = "0.1.0"
```

运行：

```bash
uv lock
uv run pytest tests/test_package.py -v
uv run ruff check src tests
uv run mypy src
```

预期：测试 PASS，Ruff 和 Mypy 退出码均为 `0`，`uv.lock` 已生成。

- [x] **Step 5：同步治理文档**

三份 ADR 均使用中文，状态为 `Accepted`：

- ADR-0001：选择 Python 3.12、薄自研 `VeraRuntime`、uv、Pydantic、Typer/Rich、OpenAI Python Client；明确不采用 Vercel AI SDK、OpenAI Agents SDK 或 LangGraph 作为 Runtime。
- ADR-0002：公共边界是 `Command -> VeraRuntime -> Event`，使用 `schema_version: 1`，CLI 和未来 Wails 不共享展示文本。
- ADR-0003：Checkpoint 与 Event Journal 存在 Vera 私有状态目录；项目内不落状态；先校验哈希再应用或回滚。

把 `docs/ROADMAP.md` 的 Phase 1 调整为本规格的最小安全循环，把 Phase 2 描述为恢复、兼容性和策略扩展。把 `docs/STATUS.md` 的活动任务改为本文件，并记录 Python/Runtime/协议/私有存储决定已经接受。

在 `.gitignore` 的缓存区加入：

```gitignore
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.egg-info/
__pycache__/
*.py[cod]
```

- [x] **Step 6：检查并提交 Task 1**

运行：

```bash
uv run pytest tests/test_package.py -v
uv run ruff check src tests
uv run mypy src
git diff --check
```

预期：全部退出码为 `0`。

提交：

```bash
git add .gitignore .python-version pyproject.toml uv.lock src/vera/__init__.py tests/test_package.py docs/decisions docs/ROADMAP.md docs/STATUS.md docs/tasks/0002-core-safe-editing-vertical-slice.md
git commit -m "chore: establish Vera Python Core foundation"
```

---

### Task 2：版本化 Core 契约与状态机

**主执行档位：** Sol 高

**文件：**

- Create: `src/vera/contracts/__init__.py`
- Create: `src/vera/contracts/commands.py`
- Create: `src/vera/contracts/events.py`
- Create: `src/vera/contracts/changes.py`
- Create: `src/vera/contracts/approvals.py`
- Create: `src/vera/contracts/checkpoints.py`
- Create: `src/vera/contracts/verification.py`
- Create: `src/vera/runtime/__init__.py`
- Create: `src/vera/runtime/state.py`
- Create: `tests/contracts/test_models.py`
- Create: `tests/runtime/test_state.py`

**接口：**

- Produces: `CoreCommand = StartRun | ResolveApproval | CancelRun | RollbackRun`
- Produces: `EventEnvelope`, `ChangeSet`, `FileChange`, `ApprovalRequest`, `VerificationCommand`, `VerificationResult`
- Produces: `RunState` 与 `RunStateMachine.transition(target: RunState) -> None`

- [x] **Step 1：编写契约序列化失败测试**

```python
from pathlib import Path

from vera.contracts.commands import StartRun


def test_start_run_serializes_schema_version_and_workspace(tmp_path: Path) -> None:
    command = StartRun(goal="修复问候语", workspace_root=tmp_path, model_profile="test")
    payload = command.model_dump(mode="json")
    assert payload["schema_version"] == 1
    assert payload["workspace_root"] == str(tmp_path)
```

运行：`uv run pytest tests/contracts/test_models.py -v`

预期：FAIL，原因是 `vera.contracts` 尚不存在。

- [x] **Step 2：实现 Command、Change Set、Approval 和 Verification Model**

使用 `ConfigDict(frozen=True, extra="forbid")`。核心签名必须为：

```python
class StartRun(BaseModel):
    schema_version: Literal[1] = 1
    goal: str
    workspace_root: Path
    model_profile: str
    verification_overrides: dict[str, JsonValue] = Field(default_factory=dict)


class ResolveApproval(BaseModel):
    schema_version: Literal[1] = 1
    run_id: str
    approval_id: str
    target_hash: str
    decision: Literal["approve", "reject"]


class FileChange(BaseModel):
    operation: Literal["create", "update", "delete"]
    path: str
    before_hash: str
    after_hash: str
    unified_diff: str


class ChangeSet(BaseModel):
    changeset_id: str
    run_id: str
    summary: str
    files: tuple[FileChange, ...]
    verification: tuple[VerificationCommand, ...]
    content_hash: str


class VerificationCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    argv: tuple[str, ...]
    cwd: str = "."
    timeout_seconds: int = Field(default=120, ge=1)
    required: bool = True


class VerificationResult(BaseModel):
    argv: tuple[str, ...]
    cwd: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float = Field(ge=0)
    exit_code: int | None
    stdout: str
    stderr: str
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    status: Literal["passed", "failed", "timed_out", "rejected", "error"]
```

`ApprovalRequest` 包含 `approval_id`、`run_id`、`kind`、`target_id`、`target_hash`、`description` 和 `risk`。`CheckpointManifest` 包含 `checkpoint_id`、`run_id`、工作区根目录、路径到修改前状态的映射，以及路径到应用后哈希的映射。`CancelRun` 只含 `run_id`；`RollbackRun` 接受且只能接受 `run_id` 或 `checkpoint_id` 其中之一。为所有非法额外字段添加拒绝测试。

- [x] **Step 3：实现 Event Model 并验证顺序字段**

```python
class EventEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    event_id: str
    run_id: str
    sequence: int = Field(ge=1)
    timestamp: datetime
    type: str
    payload: dict[str, JsonValue]
```

测试 JSON round-trip 后对象相等，并测试 `sequence=0` 被拒绝。

- [x] **Step 4：编写并实现状态转换测试**

```python
def test_runtime_rejects_apply_before_checkpoint() -> None:
    machine = RunStateMachine()
    machine.transition(RunState.DISCOVERING)
    with pytest.raises(IllegalTransition):
        machine.transition(RunState.APPLYING)
```

`RunState` 必须包含规格中的全部十四个状态。使用显式邻接表定义合法转换，不使用自由字符串：

```python
ALLOWED_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.CREATED: frozenset({RunState.DISCOVERING, RunState.CANCELLED}),
    RunState.DISCOVERING: frozenset({RunState.GENERATING, RunState.FAILED, RunState.CANCELLED}),
    RunState.GENERATING: frozenset({RunState.DISCOVERING, RunState.CHANGESET_PROPOSED, RunState.FAILED, RunState.CANCELLED}),
    RunState.CHANGESET_PROPOSED: frozenset({RunState.AWAITING_APPROVAL, RunState.FAILED}),
    RunState.AWAITING_APPROVAL: frozenset({RunState.CHECKPOINTING, RunState.CANCELLED, RunState.STALE}),
    RunState.CHECKPOINTING: frozenset({RunState.APPLYING, RunState.STALE, RunState.FAILED}),
    RunState.APPLYING: frozenset({RunState.VERIFYING, RunState.FAILED, RunState.RECOVERY_REQUIRED}),
    RunState.VERIFYING: frozenset({RunState.COMPLETED, RunState.VERIFICATION_FAILED, RunState.RECOVERY_REQUIRED}),
}
```

终止状态的目标集合为空。

- [ ] **Step 5：运行检查并提交 Task 2**

```bash
uv run pytest tests/contracts tests/runtime/test_state.py -v
uv run ruff check src tests
uv run mypy src
git diff --check
git add src/vera/contracts src/vera/runtime tests/contracts tests/runtime/test_state.py
git commit -m "feat: define versioned Vera Core contracts"
```

预期：全部检查通过。

---

### Task 3：配置、脱敏和有序 Event Journal

**主执行档位：** Luna 高

**文件：**

- Create: `src/vera/config.py`
- Create: `src/vera/redaction.py`
- Create: `src/vera/persistence/__init__.py`
- Create: `src/vera/persistence/journal.py`
- Create: `src/vera/persistence/run_store.py`
- Create: `tests/test_config.py`
- Create: `tests/test_redaction.py`
- Create: `tests/conftest.py`
- Create: `tests/persistence/test_journal.py`

**接口：**

- Produces: `load_config(workspace: Path, cli_overrides: Mapping[str, object]) -> VeraConfig`
- Produces: `Redactor(secret_values: Iterable[str]).redact(value: JsonValue) -> JsonValue`
- Produces: `EventJournal.append(event_type: str, payload: dict[str, JsonValue]) -> EventEnvelope`
- Produces: `RunStore.list_runs() -> tuple[RunSummary, ...]`
- Produces: `RunStore.read_events(run_id: str) -> tuple[EventEnvelope, ...]`

- [x] **Step 1：编写配置优先级和安全限制失败测试**

```python
def test_project_config_can_lower_but_not_raise_limits(tmp_path: Path) -> None:
    write_project_config(tmp_path, {"limits": {"max_model_turns": 10}})
    assert load_config(tmp_path, {}).limits.max_model_turns == 10

    write_project_config(tmp_path, {"limits": {"max_model_turns": 21}})
    with pytest.raises(UnsafeProjectConfig):
        load_config(tmp_path, {})
```

同时测试 CLI > 环境变量 > 项目 > 用户 > 内置默认值，以及项目配置包含 `api_key` 或安全命令声明时被拒绝。

- [x] **Step 2：实现不可变配置 Model 和 TOML 合并**

```python
class Limits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    max_model_turns: int = 20
    max_tool_calls: int = 50
    max_file_bytes: int = 1_000_000
    max_tool_output_bytes: int = 100_000
    max_context_bytes: int = 2_000_000
    command_timeout_seconds: int = 120


class ProviderConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    base_url: AnyHttpUrl
    model: str
    api_key_env: str


class VeraConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    state_dir: Path
    limits: Limits
    providers: dict[str, ProviderConfig]
    user_allowed_command_prefixes: tuple[tuple[str, ...], ...] = ()


class RunSummary(BaseModel):
    run_id: str
    workspace_root: Path
    goal_summary: str
    last_event_at: datetime
    terminal_state: str | None
```

用户配置路径由 `platformdirs.user_config_path("Vera")` 生成；状态目录由 `platformdirs.user_state_path("Vera")` 生成；测试通过环境注入临时路径，不访问真实用户目录。

- [x] **Step 3：编写并实现递归脱敏测试**

```python
def test_redactor_removes_secret_from_nested_payload() -> None:
    redactor = Redactor(["sk-live-secret"])
    value = {"error": "Bearer sk-live-secret", "nested": ["sk-live-secret"]}
    assert redactor.redact(value) == {"error": "Bearer [REDACTED]", "nested": ["[REDACTED]"]}
```

同时覆盖键名 `api_key`、`authorization`、`token`、`password`；这些键的值整体替换为 `[REDACTED]`。

- [x] **Step 4：编写 Event Journal 失败测试并实现追加语义**

```python
def test_journal_assigns_monotonic_sequence_and_persists_jsonl(tmp_path: Path) -> None:
    journal = EventJournal(tmp_path, run_id="run_1", redactor=Redactor([]))
    first = journal.append("run.started", {"goal": "test"})
    second = journal.append("tool.started", {"name": "read_file"})
    assert (first.sequence, second.sequence) == (1, 2)
    assert [event.type for event in journal.read_all()] == ["run.started", "tool.started"]
```

`append` 必须先以 UTF-8 JSON Lines 写入并 `flush`，再返回 Event。文件创建权限在 POSIX 上断言为 `0o600`，运行目录断言为 `0o700`。
重新打开同一 run 的 Journal 时，必须从现有最后一条合法 Event 恢复 sequence；损坏或不连续的 JSON Lines 记录必须明确报错，不能从 `1` 静默覆盖顺序。

- [ ] **Step 5：运行检查并提交 Task 3**

```bash
uv run pytest tests/test_config.py tests/test_redaction.py tests/persistence -v
uv run ruff check src tests
uv run mypy src
git diff --check
git add src/vera/config.py src/vera/redaction.py src/vera/persistence tests/conftest.py tests/test_config.py tests/test_redaction.py tests/persistence
git commit -m "feat: add private run configuration and event journal"
```

---

### Task 4：Workspace 边界与只读工具

**主执行档位：** Luna 高

**文件：**

- Create: `src/vera/workspace/__init__.py`
- Create: `src/vera/workspace/paths.py`
- Create: `src/vera/tools/__init__.py`
- Create: `src/vera/tools/definitions.py`
- Create: `src/vera/tools/registry.py`
- Create: `src/vera/tools/filesystem.py`
- Create: `tests/workspace/test_paths.py`
- Create: `tests/tools/test_filesystem.py`
- Create: `tests/tools/test_registry.py`

**接口：**

- Produces: `WorkspacePaths.resolve_read(path: str) -> Path`
- Produces: `WorkspacePaths.resolve_mutation(path: str) -> Path`
- Produces: `ToolRegistry.execute(name: str, arguments: dict[str, JsonValue]) -> ToolResult`
- Produces: `list_directory`, `search_text`, `read_file` 工具

- [x] **Step 1：编写路径越界和符号链接失败测试**

```python
def test_read_rejects_symlink_that_escapes_workspace(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("secret", encoding="utf-8")
    (tmp_path / "escape").symlink_to(outside)
    paths = WorkspacePaths(tmp_path)
    with pytest.raises(WorkspaceBoundaryError):
        paths.resolve_read("escape")


def test_mutation_rejects_all_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("ok", encoding="utf-8")
    (tmp_path / "link").symlink_to(target)
    with pytest.raises(WorkspaceBoundaryError):
        WorkspacePaths(tmp_path).resolve_mutation("link")
```

同时覆盖绝对路径、`..`、不存在父目录中的符号链接，以及 `.env`、私钥和真实凭据文件。

- [x] **Step 2：实现路径规范化和敏感文件策略**

```python
BUILT_IN_PROTECTED_NAMES = frozenset({".env", ".npmrc", ".pypirc", "credentials"})
BUILT_IN_PROTECTED_SUFFIXES = (".pem", ".key", ".p12")
SAFE_ENV_TEMPLATES = frozenset({".env.example", ".env.sample", ".env.template"})
```

`WorkspacePaths` 的公开签名固定为 `__init__(root: Path, protected: ProtectedPathPolicy | None = None)`、`resolve_read(relative_path: str) -> Path` 和 `resolve_mutation(relative_path: str) -> Path`。先规范化分隔符并拒绝空路径、绝对路径和 `..`，再解析真实路径并使用 `Path.is_relative_to(root)` 校验。任何修改路径只要路径本身或已存在父目录包含符号链接就拒绝。

- [x] **Step 3：编写只读工具限制测试**

```python
def test_read_file_marks_truncation(tmp_path: Path) -> None:
    (tmp_path / "large.txt").write_text("abcdef", encoding="utf-8")
    result = read_file(WorkspacePaths(tmp_path), "large.txt", max_bytes=4)
    assert result.content == "abcd"
    assert result.truncated is True
```

测试目录排序稳定、搜索结果按路径和行号排序、二进制文件拒绝、默认忽略 `.git`、`.venv`、`node_modules`、`dist`、`build`、`.vera`。

- [x] **Step 4：实现 Tool Registry 和只读工具**

```python
class ToolDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    description: str
    input_schema: dict[str, JsonValue]


class ToolResult(BaseModel):
    ok: bool
    content: JsonValue
    truncated: bool = False
    error_code: str | None = None


class Tool(Protocol):
    name: str
    input_model: type[BaseModel]

    def execute(self, arguments: BaseModel) -> ToolResult:
        raise NotImplementedError


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise DuplicateToolError(tool.name)
        self._tools[tool.name] = tool

    def execute(self, name: str, arguments: dict[str, JsonValue]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, content=None, error_code="unknown_tool")
        parsed = tool.input_model.model_validate(arguments)
        return tool.execute(parsed)
```

Registry 拒绝未知工具和不符合 Pydantic 输入 Model 的参数。文件读取使用严格 UTF-8；无法解码时返回 `binary_or_non_utf8`，不猜测编码。

- [x] **Step 5：运行检查并提交 Task 4**

```bash
uv run pytest tests/workspace/test_paths.py tests/tools -v
uv run ruff check src tests
uv run mypy src
git diff --check
git add src/vera/workspace src/vera/tools tests/workspace tests/tools
git commit -m "feat: enforce workspace boundaries for read tools"
```

---

### Task 5：Change Set 生成与审批完整性

**主执行档位：** Sol 高

**文件：**

- Create: `src/vera/workspace/changeset.py`
- Create: `src/vera/runtime/approval.py`
- Create: `tests/workspace/test_changeset.py`
- Create: `tests/runtime/test_approval.py`

**接口：**

- Consumes: `WorkspacePaths`, `ChangeSet`, `FileChange`, `VerificationCommand`
- Produces: `ChangeProposal`
- Produces: `ChangeSetBuilder.build(run_id, summary, proposals, verification) -> BuiltChangeSet`
- Produces: `ApprovalGate.require(kind, target_id, target_hash, description, risk) -> ApprovalRequest`
- Produces: `ApprovalGate.resolve(command: ResolveApproval) -> Literal["approve", "reject"]`

- [x] **Step 1：编写 Runtime 生成 Diff 和哈希失败测试**

```python
def test_changeset_hash_covers_files_and_verification(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    builder = ChangeSetBuilder(WorkspacePaths(tmp_path))
    first = builder.build("run_1", "更新问候", [update("hello.txt", "new\n")], [pytest_command()])
    second = builder.build("run_1", "更新问候", [update("hello.txt", "new\n")], [ruff_command()])
    assert first.change_set.files[0].unified_diff.startswith("--- a/hello.txt")
    assert first.change_set.content_hash != second.change_set.content_hash
```

增加 create、update、delete、多文件排序和相同输入产生相同哈希的测试。

- [x] **Step 2：实现权威 Change Set Builder**

```python
class ChangeProposal(BaseModel):
    operation: Literal["create", "update", "delete"]
    path: str
    after_content: str | None = None


class BuiltChangeSet(BaseModel):
    change_set: ChangeSet
    intended_bytes: dict[str, bytes]
```

实现 `ChangeSetBuilder.build(self, run_id: str, summary: str, proposals: Sequence[ChangeProposal], verification: Sequence[VerificationCommand]) -> BuiltChangeSet`。`create` 要求目标不存在且提供内容；`update` 要求目标是普通文本文件且提供内容；`delete` 要求目标存在且 `after_content is None`。哈希只覆盖文件操作、路径、前后哈希和验证计划，不覆盖随机 ID 或展示摘要；使用排序键固定的 UTF-8 JSON 和 SHA-256。统一 Diff 使用 `difflib.unified_diff`，路径固定为 `a/<path>` 与 `b/<path>`，同时把精确写入字节保存在 `BuiltChangeSet.intended_bytes`。

- [x] **Step 3：编写审批重放和篡改失败测试**

```python
def test_approval_rejects_changed_target_hash() -> None:
    gate = ApprovalGate(run_id="run_1")
    request = gate.require(ApprovalKind.CHANGESET, "cs_1", "hash_a", "diff", "medium")
    command = ResolveApproval(
        run_id="run_1",
        approval_id=request.approval_id,
        target_hash="hash_b",
        decision="approve",
    )
    with pytest.raises(ApprovalMismatch):
        gate.resolve(command)
```

同时测试旧审批 ID 重放、错误 run ID、拒绝决定和已解决审批二次提交。

- [x] **Step 4：实现一次性审批门**

`ApprovalGate` 保存唯一 `pending_approval`。`require` 计算并返回 `ApprovalRequest`；`resolve` 先比较 run、approval、target hash，再以原子状态变化清除请求并返回决定。拒绝决定不能被解释为工具错误或隐式批准。

- [x] **Step 5：运行检查并提交 Task 5**

```bash
uv run pytest tests/workspace/test_changeset.py tests/runtime/test_approval.py -v
uv run ruff check src tests
uv run mypy src
git diff --check
git add src/vera/workspace/changeset.py src/vera/runtime/approval.py tests/workspace/test_changeset.py tests/runtime/test_approval.py
git commit -m "feat: build tamper-evident change sets"
```

---

### Task 6：Checkpoint、原子应用与冲突安全回滚

**主执行档位：** Sol 高

**文件：**

- Create: `src/vera/workspace/checkpoint.py`
- Create: `src/vera/workspace/apply.py`
- Create: `tests/workspace/test_checkpoint.py`
- Create: `tests/workspace/test_apply.py`
- Create: `tests/workspace/test_rollback.py`

**接口：**

- Consumes: `BuiltChangeSet`, `WorkspacePaths`, 私有 `state_dir`
- Produces: `CheckpointStore.create(change_set: ChangeSet) -> CheckpointManifest`
- Produces: `CheckpointStore.load_for_run(run_id: str) -> CheckpointManifest`
- Produces: `ChangeApplier.apply(built: BuiltChangeSet, manifest: CheckpointManifest) -> ApplyResult`
- Produces: `ChangeApplier.rollback(manifest: CheckpointManifest) -> RollbackResult`

- [x] **Step 1：编写 Checkpoint 字节与权限失败测试**

```python
def test_checkpoint_records_original_bytes_and_absent_files(tmp_path: Path, state_dir: Path) -> None:
    (tmp_path / "old.txt").write_bytes(b"old\n")
    built = build_changes(tmp_path, update("old.txt", "new\n"), create("new.txt", "created\n"))
    manifest = CheckpointStore(state_dir, WorkspacePaths(tmp_path)).create(built.change_set)
    assert manifest.files["old.txt"].before_hash == sha256_bytes(b"old\n")
    assert manifest.files["new.txt"].existed_before is False
```

测试 Checkpoint 目录位于 `state_dir/runs/<run-id>/checkpoint/`，不在工作区内，并检查 POSIX 权限。

- [x] **Step 2：实现 Checkpoint Store**

实现 `CheckpointStore.create(change_set: ChangeSet) -> CheckpointManifest` 和 `CheckpointStore.load_for_run(run_id: str) -> CheckpointManifest`。清单写入 `manifest.json`；原始字节按路径哈希命名存储，避免状态目录路径穿越。先写临时文件并 `os.replace`，完成后才返回清单。

- [x] **Step 3：编写应用失败恢复测试**

```python
def test_apply_failure_restores_every_touched_file(tmp_path: Path, checkpoint_store: CheckpointStore) -> None:
    original = seed_two_files(tmp_path)
    built = build_two_file_changes(tmp_path)
    manifest = checkpoint_store.create(built.change_set)
    writer = FailingFileWriter(fail_after=1)
    applier = ChangeApplier(WorkspacePaths(tmp_path), checkpoint_store, writer=writer)
    result = applier.apply(built, manifest)
    assert result.status == ApplyStatus.RESTORED_AFTER_FAILURE
    assert snapshot_bytes(tmp_path) == original
```

同时测试审批后文件哈希变化时在 Checkpoint 前和 apply 前均拒绝、create/update/delete 成功、多文件预检失败时零写入。

- [x] **Step 4：实现预检、同目录原子替换和失败恢复**

定义 `FileWriter` Protocol，包含 `replace(path: Path, content: bytes, mode: int | None) -> None` 和 `delete(path: Path) -> None`；生产实现使用同目录临时文件与 `os.replace`，测试使用 `FailingFileWriter` 注入失败，不在生产类中增加测试开关。`apply` 不创建 Checkpoint，只接受并核对 Runtime 已创建的 `CheckpointManifest`。顺序必须固定：验证清单与 Change Set 对应 → 验证全部 before hash → 验证所有目标路径 → 对 create/update 原子替换 → 执行 delete。捕获任一应用异常后使用传入清单恢复全部已触及路径并返回明确状态；恢复本身失败时返回 `RECOVERY_REQUIRED` 和路径列表。

- [x] **Step 5：编写并实现回滚冲突保护**

```python
def test_rollback_refuses_to_overwrite_user_edit(tmp_path: Path, applied_run: AppliedRun) -> None:
    (tmp_path / "hello.txt").write_text("user edit\n", encoding="utf-8")
    result = applied_run.applier.rollback(applied_run.manifest)
    assert result.status == RollbackStatus.CONFLICTED
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "user edit\n"
```

回滚先检查全部当前哈希；任一冲突时所有文件保持不变。没有冲突时恢复原始字节、存在性和平台支持的权限位。

- [x] **Step 6：运行检查并提交 Task 6**

```bash
uv run pytest tests/workspace/test_checkpoint.py tests/workspace/test_apply.py tests/workspace/test_rollback.py -v
uv run ruff check src tests
uv run mypy src
git diff --check
git add src/vera/workspace/checkpoint.py src/vera/workspace/apply.py tests/workspace
git commit -m "feat: checkpoint and safely roll back file changes"
```

---

### Task 7：命令策略与验证证据

**主执行档位：** Sol 高

**文件：**

- Create: `src/vera/tools/command_policy.py`
- Create: `src/vera/verification/__init__.py`
- Create: `src/vera/verification/runner.py`
- Create: `tests/tools/test_command_policy.py`
- Create: `tests/verification/test_runner.py`

**接口：**

- Produces: `CommandPolicy.classify(command: VerificationCommand) -> CommandDecision`
- Produces: `VerificationRunner.run(command: VerificationCommand) -> VerificationResult`

- [x] **Step 1：编写命令分类失败测试**

```python
@pytest.mark.parametrize("argv", [("sh", "-c", "echo x"), ("sudo", "true"), ("rm", "-rf", ".")])
def test_forbidden_commands_never_request_approval(argv: tuple[str, ...]) -> None:
    decision = CommandPolicy().classify(VerificationCommand(argv=argv, cwd="."))
    assert decision.kind is CommandDecisionKind.FORBIDDEN


def test_exact_user_prefix_is_policy_allowed() -> None:
    policy = CommandPolicy(user_allowed_prefixes=(("python", "-m", "pytest"),))
    command = VerificationCommand(argv=("python", "-m", "pytest", "-q"), cwd=".")
    assert policy.classify(command).kind is CommandDecisionKind.ALLOWED
```

内置安全命令仅包含 `git status --short` 和 `git diff --check`。其他命令默认为 `APPROVAL_REQUIRED`。Shell 可执行文件、提权命令、直接删除工具、`git clean`、`git reset --hard`、`git checkout` 和 `git restore` 永久禁止。

- [x] **Step 2：实现命令策略**

策略先验证非空 argv、工作目录和每个参数不含 NUL，再按“永久禁止 → 精确内置允许 → 用户级前缀允许 → 需要审批”顺序判定。项目配置不进入允许前缀输入。

- [x] **Step 3：编写验证执行和截断失败测试**

```python
def test_runner_captures_exit_code_and_truncates_output(tmp_path: Path) -> None:
    command = VerificationCommand(
        argv=(sys.executable, "-c", "print('abcdef')"),
        cwd=".",
        timeout_seconds=5,
    )
    result = VerificationRunner(tmp_path, max_output_bytes=4).run(command)
    assert result.exit_code == 0
    assert result.stdout == "abcd"
    assert result.stdout_truncated is True
```

同时测试非零退出码、默认 120 秒策略限制、测试注入的短超时、stderr、无法启动和工作目录越界。

- [x] **Step 4：实现无 Shell 的 VerificationRunner**

使用：

```python
completed = subprocess.run(
    list(command.argv),
    cwd=resolved_cwd,
    shell=False,
    capture_output=True,
    timeout=effective_timeout,
    check=False,
)
```

环境变量只保留 `PATH`、`LANG`、`LC_ALL`、`TMPDIR` 以及用户配置明确允许的名称，不把 Vera 供应商密钥传给子进程。`APPROVAL_REQUIRED` 的风险说明必须包含“该进程以当前系统用户权限运行，Vera 第一版不提供 OS 沙箱”。结果统一解码为 UTF-8 并使用替换字符处理无效字节；记录开始时间、结束时间和单调时钟时长。

- [x] **Step 5：运行检查并提交 Task 7**

```bash
uv run pytest tests/tools/test_command_policy.py tests/verification -v
uv run ruff check src tests
uv run mypy src
git diff --check
git add src/vera/tools/command_policy.py src/vera/verification tests/tools/test_command_policy.py tests/verification
git commit -m "feat: classify commands and capture verification evidence"
```

---

### Task 8：可替换 ModelAdapter 与供应商协议转换

**主执行档位：** Luna 高

**文件：**

- Create: `src/vera/models/__init__.py`
- Create: `src/vera/models/base.py`
- Create: `src/vera/models/openai_compatible.py`
- Create: `tests/fakes.py`
- Create: `tests/models/test_openai_compatible.py`
- Create: `tests/live/test_providers.py`

**接口：**

- Produces: `ModelAdapter.complete(request: ModelRequest) -> ModelTurn`
- Produces: `OpenAICompatibleAdapter`
- Produces: `FakeModelAdapter`，供后续 Runtime 测试使用

- [x] **Step 1：编写标准化 Tool Call 转换失败测试**

```python
def test_adapter_normalizes_provider_tool_call(fake_openai_client: FakeOpenAIClient) -> None:
    fake_openai_client.respond_with_tool("read_file", '{"path":"README.md"}', call_id="call_1")
    adapter = OpenAICompatibleAdapter(test_provider(), client=fake_openai_client)
    turn = adapter.complete(sample_request())
    assert turn.tool_calls == (
        ModelToolCall(call_id="call_1", name="read_file", arguments={"path": "README.md"}),
    )
```

同时测试纯文本、无效 JSON 参数、未知 finish reason、usage 缺失和供应商异常转换为 Vera 错误。

- [x] **Step 2：定义稳定 ModelAdapter 协议**

```python
class ModelMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None


class ModelRequest(BaseModel):
    messages: tuple[ModelMessage, ...]
    tools: tuple[ToolDefinition, ...]
    max_output_tokens: int


class ModelToolCall(BaseModel):
    call_id: str
    name: str
    arguments: dict[str, JsonValue]


class ModelUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class ModelTurn(BaseModel):
    assistant_text: str | None = None
    tool_calls: tuple[ModelToolCall, ...] = ()
    finish_reason: str
    usage: ModelUsage | None = None
    provider_metadata: dict[str, JsonValue] = Field(default_factory=dict)


class ModelAdapter(Protocol):
    def complete(self, request: ModelRequest) -> ModelTurn:
        raise NotImplementedError
```

`ModelTurn` 包含 `assistant_text`、标准化 `tool_calls`、`finish_reason`、可选 `usage` 和经过脱敏的 `provider_metadata`。

- [x] **Step 3：实现 OpenAI-compatible Adapter**

构造客户端时显式传入 `api_key`、`base_url`、`timeout=120.0`、`max_retries=0`，避免 SDK 隐式重试造成不可见成本。调用 `client.chat.completions.create`，只在 `models/` 内访问供应商对象；Tool Call 参数使用 `json.loads` 后再通过本地模型校验。

- [x] **Step 4：实现可脚本化 FakeModelAdapter**

```python
class FakeModelAdapter:
    def __init__(self, turns: Sequence[ModelTurn]) -> None:
        self._turns = deque(turns)
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelTurn:
        self.requests.append(request)
        if not self._turns:
            raise AssertionError("FakeModelAdapter has no scripted turn")
        return self._turns.popleft()
```

- [x] **Step 5：添加显式在线冒烟测试入口**

`tests/live/test_providers.py` 只在同时存在 `VERA_LIVE_PROVIDER`、对应 API Key 环境变量、Base URL 和模型名时运行；否则使用 `pytest.skip`。DeepSeek 使用 `DEEPSEEK_API_KEY`、`VERA_DEEPSEEK_BASE_URL`、`VERA_DEEPSEEK_MODEL`；GLM 使用 `GLM_API_KEY`、`VERA_GLM_BASE_URL`、`VERA_GLM_MODEL`。测试断言一次文本响应和一次 Tool Call 均能标准化，并且任何失败输出都通过 Redactor。

运行默认测试确认不会联网：

```bash
uv run pytest tests/models tests/live -m "not live" -v
```

- [x] **Step 6：运行检查并提交 Task 8**

```bash
uv run pytest tests/models tests/live -m "not live" -v
uv run ruff check src tests
uv run mypy src
git diff --check
git add src/vera/models tests/fakes.py tests/models tests/live
git commit -m "feat: add replaceable OpenAI-compatible model adapter"
```

---

### Task 9：VeraRuntime 发现循环与 Change Set 暂停点

**主执行档位：** Sol 高

**文件：**

- Create: `src/vera/runtime/prompts.py`
- Create: `src/vera/runtime/context.py`
- Create: `src/vera/runtime/engine.py`
- Create: `tests/runtime/test_discovery_loop.py`
- Create: `tests/runtime/test_limits.py`
- Create: `tests/runtime/conftest.py`

**接口：**

- Consumes: `ModelAdapter`, `ToolRegistry`, `ChangeSetBuilder`, `CommandPolicy`, `VerificationRunner`, `EventJournal`, `RunContext`
- Produces: `VeraRuntime.handle(command: CoreCommand) -> Iterator[EventEnvelope]`
- Produces: `VeraRuntime` 在 Change Set 审批点保持内存态，等待 `ResolveApproval`

- [x] **Step 1：编写读取、搜索、提案流程失败测试**

```python
def test_runtime_reaches_changeset_approval_without_writing(runtime_fixture: RuntimeFixture) -> None:
    runtime_fixture.adapter.script(
        tool_turn("read_file", {"path": "hello.txt"}),
        tool_turn("propose_changeset", update_hello_arguments()),
    )
    events = list(runtime_fixture.runtime.handle(runtime_fixture.start_command))
    assert [event.type for event in events][-2:] == ["changeset.proposed", "approval.required"]
    assert runtime_fixture.read("hello.txt") == "old\n"
```

断言 Event 顺序包含 `run.started`、`model.requested/completed`、`tool.started/completed`，并验证供应商原生对象没有进入 Payload。

- [x] **Step 2：实现固定系统策略和模型工具 Schema**

`prompts.py` 的系统策略明确：只能使用注册工具；不得声称执行成功；读取足够上下文后调用一次 `propose_changeset`；不得输出秘密；无法形成安全修改时返回原因。Runtime 收到无 Tool Call 的终止响应后以 `run.failed` 和 `reason=no_changes_proposed` 结束。工具 Schema 从 Pydantic 输入 Model 生成，不维护第二份手写参数定义。

模型工具中包含特殊工具 `run_command` 和 `propose_changeset`。它们的参数分别复用 `VerificationCommand` 和 Change Set 提案 Model，但由 Runtime 直接协调，不能绕过 CommandPolicy 或进入普通 Tool Registry 的自由执行路径。

- [x] **Step 3：实现 StartRun 到审批点的 Runtime 驱动**

```python
@dataclass
class RunContext:
    run_id: str
    command: StartRun
    machine: RunStateMachine
    journal: EventJournal
    messages: list[ModelMessage]
    approval_gate: ApprovalGate
    model_turns: int = 0
    tool_calls: int = 0
    context_bytes: int = 0
    built_change_set: BuiltChangeSet | None = None
    pending_command: VerificationCommand | None = None
    verification_index: int = 0
```

实现 `VeraRuntime.handle(self, command: CoreCommand) -> Iterator[EventEnvelope]`、`_drive_until_interrupt(self, context: RunContext) -> Iterator[EventEnvelope]` 和 `_execute_model_tool(self, context: RunContext, call: ModelToolCall) -> ToolResult`。`StartRun` 创建 `RunContext`、状态机和 Journal，并把它保存在 Runtime 的内存运行表中。每次模型调用前后写 Event；每次工具调用执行 Registry 校验并写 Event。`propose_changeset` 不进入普通文件工具，而是交给 `ChangeSetBuilder`，随后输出 Diff、创建一次性审批请求并返回控制权。

发现阶段的 `run_command` 先经过 CommandPolicy：`ALLOWED` 才直接交给 VerificationRunner；`APPROVAL_REQUIRED` 输出包含 argv、cwd、哈希和非沙箱风险的 `approval.required` 后暂停；`FORBIDDEN` 直接向模型返回拒绝结果。匹配的 `ResolveApproval` 到达后，Runtime 执行原哈希绑定命令、输出 `tool.completed`，再继续模型循环。

- [x] **Step 4：编写并实现上下文和循环限制**

```python
def test_three_identical_tool_calls_fail_without_writes(runtime_fixture: RuntimeFixture) -> None:
    runtime_fixture.adapter.repeat(tool_turn("read_file", {"path": "hello.txt"}), times=3)
    events = list(runtime_fixture.runtime.handle(runtime_fixture.start_command))
    assert events[-1].type == "run.failed"
    assert events[-1].payload["reason"] == "repeated_tool_call"
    assert runtime_fixture.read("hello.txt") == "old\n"
```

分别测试 20 轮、50 次工具、单文件、单输出和总上下文字节限制。截断结果必须有 `truncated=true`；达到上限时在审批和写入前终止。

- [x] **Step 5：运行检查并提交 Task 9**

```bash
uv run pytest tests/runtime/test_discovery_loop.py tests/runtime/test_limits.py -v
uv run ruff check src tests
uv run mypy src
git diff --check
git add src/vera/runtime tests/runtime/conftest.py tests/runtime/test_discovery_loop.py tests/runtime/test_limits.py
git commit -m "feat: drive bounded VeraRuntime discovery loop"
```

---

### Task 10：Runtime 审批、应用、验证与回滚编排

**主执行档位：** Sol 高

**文件：**

- Modify: `src/vera/runtime/engine.py`
- Modify: `src/vera/runtime/context.py`
- Modify: `src/vera/persistence/run_store.py`
- Create: `tests/runtime/test_safe_editing_flow.py`
- Create: `tests/runtime/test_runtime_failures.py`

**接口：**

- Consumes: `ResolveApproval`, `CheckpointStore`, `ChangeApplier`, `CommandPolicy`, `VerificationRunner`
- Produces: 完整终态 `COMPLETED | VERIFICATION_FAILED | CANCELLED | STALE | FAILED | RECOVERY_REQUIRED`
- Produces: `VeraRuntime.rollback(command: RollbackRun) -> Iterator[EventEnvelope]`

- [x] **Step 1：编写批准后的完整流程失败测试**

```python
def test_approved_changeset_checkpoints_applies_and_verifies(runtime_fixture: RuntimeFixture) -> None:
    approval = runtime_fixture.drive_to_changeset_approval()
    events = list(runtime_fixture.runtime.handle(approve(approval)))
    assert runtime_fixture.read("hello.txt") == "new\n"
    assert ordered_types(events) == [
        "approval.resolved",
        "checkpoint.created",
        "changeset.applied",
        "verification.started",
        "verification.completed",
        "run.completed",
    ]
```

- [x] **Step 2：实现 Change Set 审批后的编排**

批准后严格执行：再次校验 `target_hash` → 状态进入 CHECKPOINTING → `CheckpointStore.create` → 输出 `checkpoint.created` → `ChangeApplier.apply(built, manifest)` → 输出 `changeset.applied` → 逐条验证 → 输出结果 → 生成终态 Event。拒绝时输出 `approval.resolved` 和 `run.cancelled`，不创建 Checkpoint。

- [x] **Step 3：实现验证命令审批中断**

验证阶段复用 Task 9 的命令路径：`ALLOWED` 直接执行；`APPROVAL_REQUIRED` 创建 command 审批并返回控制权；`FORBIDDEN` 生成拒绝证据且不提供批准入口。再次收到匹配的 `ResolveApproval` 后，只执行哈希绑定的 argv 和 cwd。

- [x] **Step 4：覆盖全部失败终态**

测试并实现：

- 审批后文件变化 → `changeset.stale`，零写入；
- Checkpoint 失败 → `run.failed`，零目标写入；
- apply 失败且恢复成功 → `checkpoint.restored` + `run.failed`；
- apply 恢复失败 → `checkpoint.restore_failed` + `run.failed`，Payload 状态为 `RECOVERY_REQUIRED`；
- verification 非零或超时 → `verification.completed` + `run.completed`，Payload 状态为 `VERIFICATION_FAILED`；
- 所有持久化 Payload 经过 Redactor。

- [x] **Step 5：编写并实现 Runtime 回滚**

```python
def test_runtime_rollback_emits_completed_and_restores_bytes(applied_runtime: RuntimeFixture) -> None:
    events = list(applied_runtime.runtime.handle(RollbackRun(run_id=applied_runtime.run_id)))
    assert events[-1].type == "rollback.completed"
    assert applied_runtime.read("hello.txt") == "old\n"
```

冲突时输出 `rollback.conflicted`，任何目标文件都不改变。

- [x] **Step 6：运行检查并提交 Task 10**

```bash
uv run pytest tests/runtime -v
uv run ruff check src tests
uv run mypy src
git diff --check
git add src/vera/runtime src/vera/persistence/run_store.py tests/runtime
git commit -m "feat: orchestrate approved edits verification and rollback"
```

---

### Task 11：CLI 人类模式与 JSON Event 模式

**主执行档位：** Luna 高

**文件：**

- Create: `src/vera/bootstrap.py`
- Create: `src/vera/cli.py`
- Create: `tests/cli/test_run.py`
- Create: `tests/cli/test_runs.py`
- Create: `tests/cli/test_rollback.py`
- Create: `tests/cli/test_config.py`
- Create: `tests/cli/conftest.py`

**接口：**

- Consumes: `VeraConfig`, `VeraRuntime`, `RunStore`, Core Command/Event
- Produces: `vera run`, `vera runs list`, `vera runs show`, `vera rollback`, `vera config show`
- Produces: 退出状态码 `0/2/3/4/5`

- [x] **Step 1：编写 CLI 帮助和配置脱敏失败测试**

```python
def test_config_show_never_prints_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-do-not-print")
    result = runner.invoke(app, ["config", "show"], obj=test_dependencies())
    assert result.exit_code == 0
    assert "sk-do-not-print" not in result.stdout
    assert "DEEPSEEK_API_KEY" in result.stdout
```

测试 `vera --help` 包含五个正式命令。

- [x] **Step 2：实现依赖组装和 Typer 命令树**

```python
app = typer.Typer(no_args_is_help=True)
runs_app = typer.Typer()
config_app = typer.Typer()
app.add_typer(runs_app, name="runs")
app.add_typer(config_app, name="config")


@app.command()
def run(
    goal: str,
    workspace: Path = typer.Option(Path(".")),
    model: str | None = typer.Option(None),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    exit_code = execute_run(
        goal=goal,
        workspace=workspace.resolve(),
        model_profile=model,
        json_output=json_output,
    )
    raise typer.Exit(exit_code)
```

`bootstrap.py` 是唯一组装点：加载配置、读取指定 API Key 环境变量、创建 Redactor、Adapter、Workspace、Journal、CheckpointStore、Verifier 和 Runtime。`execute_run(goal: str, workspace: Path, model_profile: str | None, json_output: bool) -> int` 负责驱动 Runtime 和渲染器，并返回规格定义的退出码。

- [x] **Step 3：编写并实现交互审批和渲染**

人类模式用 Rich 展示状态、文件列表、完整统一 Diff、验证命令、风险和 run ID。收到 `approval.required` 时只接受明确的 `approve` 或 `reject`；将 Event 中的 `approval_id` 和 `target_hash` 原样放入 `ResolveApproval`。

```python
decision = typer.prompt("输入 approve 批准，或 reject 拒绝")
if decision not in {"approve", "reject"}:
    raise typer.BadParameter("必须明确输入 approve 或 reject")
```

- [x] **Step 4：实现 JSON 和非交互行为**

JSON 模式每行只输出 `event.model_dump_json()`，不输出 ANSI 或提示文字。`json_output is True` 或 `not sys.stdin.isatty()` 时不发起文本提示；遇到审批后向 Runtime 发送 `CancelRun`，输出 `run.cancelled`，状态码为 `2`，并证明目标文件未变化。

- [x] **Step 5：实现 runs、rollback 和退出码映射**

`runs list` 按最近事件时间倒序显示 run ID、工作区、目标摘要和终态；`runs show` 输出已脱敏 Event；`rollback` 调用 `RollbackRun` 并展示成功或冲突。终态到退出码使用一个只读映射，不在命令函数中分散判断。

- [x] **Step 6：运行检查并提交 Task 11**

```bash
uv run pytest tests/cli -v
uv run vera --help
uv run ruff check src tests
uv run mypy src
git diff --check
git add src/vera/bootstrap.py src/vera/cli.py tests/cli
git commit -m "feat: expose VeraRuntime through the CLI"
```

---

### Task 12：完整链路、真实供应商与阶段验收

**主执行档位：** Sol 高

**文件：**

- Create: `tests/e2e/test_git_fixture.py`
- Create: `tests/e2e/test_rejection.py`
- Create: `tests/e2e/conftest.py`
- Create: `tests/live/test_runtime_provider.py`
- Create: `docs/evals/phase-1-safe-editing.md`
- Modify: `README.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/tasks/0002-core-safe-editing-vertical-slice.md`

**接口：**

- Consumes: 已安装的 `vera` CLI 和完整 Core
- Produces: 确定性 Git Fixture 证据、真实供应商证据、人工验收记录
- Produces: Phase 1 垂直切片完成或明确未完成的状态

- [ ] **Step 1：编写临时 Git 仓库端到端失败测试**

```python
def test_full_safe_editing_and_rollback_in_git_fixture(tmp_path: Path) -> None:
    repo = GitFixture.create(tmp_path, {"hello.txt": "old\n", "test_hello.py": PASSING_TEST})
    result = run_scripted_vera(repo, goal="把 hello 改为 new", decision="approve")
    assert result.exit_code == 0
    assert repo.read("hello.txt") == "new\n"
    assert repo.git("diff", "--", "hello.txt") != ""
    rollback = run_vera_rollback(repo, result.run_id)
    assert rollback.exit_code == 0
    assert repo.read("hello.txt") == "old\n"
    assert repo.git("status", "--short") == ""
```

测试通过测试专用依赖注入选择 `FakeModelAdapter`，不能通过生产 CLI 参数暴露任意 Fake Adapter。

- [ ] **Step 2：增加拒绝和冲突端到端测试**

拒绝分支断言字节快照与 `git status --short` 完全不变。冲突分支在 apply 后人工写入新内容，再运行 rollback，断言退出非零、输出 `rollback.conflicted` 且用户内容保留。

- [ ] **Step 3：运行完整离线验收**

```bash
uv run pytest -m "not live" --cov=vera --cov-report=term-missing
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv build
git diff --check
```

预期：所有命令退出码为 `0`；没有跳过的非 live 测试；构建生成 wheel 和 source distribution。覆盖率仅作为定位未测试分支的证据，本切片不以单一百分比代替规格验收。

- [ ] **Step 4：执行低成本真实供应商验证**

先由用户选择 DeepSeek 或 GLM 并授权一次真实 API 调用，再只在当前终端设置对应环境变量。运行：

```bash
VERA_LIVE_PROVIDER=deepseek uv run pytest tests/live/test_providers.py tests/live/test_runtime_provider.py -m live -v
VERA_LIVE_PROVIDER=glm uv run pytest tests/live/test_providers.py tests/live/test_runtime_provider.py -m live -v
```

只运行用户明确选择并授权的其中一条命令，不得自动尝试另一家供应商。`test_runtime_provider.py` 在临时 Git 项目中使用真实 Adapter 完成读取、Tool Call、Change Set、测试用显式审批、Checkpoint、应用和验证，并在最后回滚。记录模型名、时间、通过/失败、Tool Call 转换和 Usage；绝不记录 API Key。失败时保留为未完成证据，不把旧原型结果替代本次验证。

- [ ] **Step 5：执行真实项目副本人工验收**

取得用户指定且可恢复的项目副本路径，先记录其 Git 状态和字节快照，再运行一次 `vera run`。用户亲自检查并批准 Diff；验证完成后运行 `vera rollback <run-id>`，再次比较字节和 Git 状态。原始有价值工作副本不作为首次目标。

- [ ] **Step 6：记录证据并关闭或保留任务**

创建 `docs/evals/phase-1-safe-editing.md`，逐项记录规格十条验收标准的命令、日期和结果。只有十条全部满足时，才把本任务状态改为 `Done`，把 `docs/STATUS.md` 的 Phase 1 垂直切片标记为完成，并在 README 增加已验证 CLI 用法。任何真实供应商或人工验收缺失时，任务保持 `In progress` 并准确列出缺口。

- [ ] **Step 7：最终检查并提交 Task 12**

```bash
uv run pytest -m "not live" --cov=vera --cov-report=term-missing
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv build
git diff --check
git status --short --branch
```

在用户明确授权提交后：

```bash
git add tests/e2e docs/evals/phase-1-safe-editing.md README.md docs/STATUS.md docs/tasks/0002-core-safe-editing-vertical-slice.md
git commit -m "test: verify Vera Core safe editing vertical slice"
```

## 规格覆盖索引

| 规格要求 | 实施任务 |
|---|---|
| Python Core、包和 CLI | Task 1、Task 11 |
| Runtime 权威状态机 | Task 2、Task 9、Task 10 |
| Command/Event 契约与日志 | Task 2、Task 3 |
| ModelAdapter、DeepSeek、GLM | Task 8、Task 12 |
| 读取、搜索、上下文限制 | Task 4、Task 9 |
| Change Set、Diff、哈希审批 | Task 5、Task 10 |
| Workspace 和敏感路径边界 | Task 4、Task 6 |
| Checkpoint、应用失败恢复、回滚 | Task 6、Task 10、Task 12 |
| 命令权限与验证证据 | Task 7、Task 10 |
| CLI 人类/JSON 模式与退出码 | Task 11 |
| 确定性、Git Fixture、真实链路验收 | Task 12 |

## 执行边界

- 每个 Task 开始前重新读取本计划、规格、`AGENTS.md` 和 `docs/STATUS.md`。
- 每个 Task 完成后由独立审查步骤核对规格一致性，再进入下一个 Task。
- 不在同一工作树中并行修改；如果用户选择子 Agent 驱动，必须逐 Task 交接所有权。
- 任何权限、安全、Checkpoint、回滚或恢复语义变化都必须停下并重新取得用户批准。
- 计划中的提交命令只是建议检查点；执行时仍须遵守 `AGENTS.md`，逐次取得当前用户请求的提交授权。
