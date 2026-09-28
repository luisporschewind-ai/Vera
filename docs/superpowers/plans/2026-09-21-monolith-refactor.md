# Vera 大单体文件纯结构拆分 Implementation Plan

**实施状态：** 已完成（2026-09-21）。代码已提交于 `dd201e7`；本次文档提交只补齐本计划的执行状态与验证证据，不改变阶段八产品验收状态。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变 Vera Core、CLI、TUI、事件、恢复、Policy、Tool 和 Git 语义的前提下，拆分当前大单体文件，令受影响的生产代码、脚本和测试文件均不再超过 600 行，并保持现有公共导入路径兼容。

**Architecture:** 采用“公共外壳保留、内部流程按职责组合”的机械式拆分。`VeraRuntime`、`SessionController`、`TimelineProjector`、CLI app 和 smoke entrypoint 继续是对外入口；具体流程移动到职责单一的 flow/service/handler 模块。第一轮只移动现有逻辑并补齐表征测试，第二轮才做局部重复收敛，禁止在重构中修改行为、错误码或安全策略。

**Tech Stack:** Python 3.12、Pydantic、pytest、Ruff、Mypy、Typer、Textual、uv；现有 `RuntimeOutput`、`EventEnvelope`、`SessionAction`、`TimelineMutation` 和 Git/Policy contracts 保持不变。

**Spec:** `docs/specs/2026-09-17-core-tooling-and-risk-tiered-policy.md`、`docs/specs/2026-09-17-native-git-capability.md`、`docs/specs/2026-09-11-conversational-cli-and-session-status.md`、`docs/tasks/0066-phase-8-tooling-git-acceptance.md`

## Global Constraints

- 本计划只允许结构拆分、重复代码收敛、导入整理和测试组织优化；不增加新能力，不改变现有业务逻辑。
- 不改变公开构造函数、公开方法、返回类型、事件名称、事件顺序、错误码、Policy decision、Approval payload、Recovery snapshot、Journal/Receipt 格式或 CLI 参数。
- 保留既有公共导入路径：`vera.runtime.engine`、`vera.session.controller`、`vera.presentation.projector`、`vera.verification.artifacts` 和 `vera.cli` 继续可用；原模块通过 re-export 暴露已存在的公开符号。
- `VeraRuntime` 的 `_execute_prepared_tool` 等被现有测试直接调用的私有兼容入口继续存在；`SessionController` 的可继承行为继续存在；不得用会改变 MRO 或子类覆盖顺序的 mixin 替代。
- 不修改前一轮已发现的 Bash classifier、Git 全局配置读取、branch receipt recovery 问题；这些属于独立缺陷任务，重构必须保持当前行为，并在回归中锁住现状。
- 不新增第三方依赖，不移动 Provider、Policy、Workspace、Approval、Recovery、Git 的所有权。
- 受影响的 `src/vera/**/*.py`、`scripts/**/*.py` 和 `tests/**/*.py` 单文件目标上限为 600 行；优先控制在 300–500 行。文档、锁文件和阶段七既有 SVG 不纳入代码单体门禁。
- 所有任务在当前隔离工作树串行执行；不合并、不推送、不删除现有分支或工作树。本计划代码提交已获得用户明确授权。

## Review Focus

- 同一输入产生的 `EventEnvelope` / `RuntimeOutput` 类型、顺序和关键 payload 不变；测试覆盖 normalized event trace。
- Approval、Policy、ToolAction、Checkpoint、Receipt、Git operation 的生命周期不改变；测试覆盖 approve/reject/cancel/stale/replay。
- Crash/recovery、snapshot hydration、partial restore 和 terminal state 不改变；测试覆盖运行中崩溃与重复命令。
- 公共导入路径、构造函数签名、SessionController 子类覆盖、TimelineProjector 公开 mutation 类型不改变；测试覆盖 import/signature/subclass compatibility。
- wheel smoke、CLI plain/JSON、PTY 输出、workspace 外产物隔离不改变；测试覆盖安装态和现有阶段八矩阵。

---

## 1. 当前单体盘点与目标

| 文件 | 当前行数 | 主要职责 | 目标 |
|---|---:|---|---:|
| `src/vera/runtime/engine.py` | 2531 | Runtime 构造、内容安全、工具执行、审批、验证、循环、恢复、命令分发 | 外壳 ≤350 行；各 flow ≤600 行 |
| `src/vera/session/controller.py` | 1157 | 会话状态、持久化、Run 驱动、编辑器、slash commands、状态展示 | 外壳 ≤450 行；各 flow ≤500 行 |
| `src/vera/presentation/projector.py` | 827 | Timeline state、stream、事件路由、30 余种事件 handler | 外壳 ≤300 行；state/handler ≤500 行 |
| `scripts/smoke_installed_wheel.py` | 584 | wheel 安装、Core smoke、CLI/会话/迁移/隔离检查 | entrypoint ≤250 行；payload/checks ≤500 行 |
| `src/vera/terminal/app.py` | 698 | Textual layout、输入、输出、审批、快捷键、clipboard、theme | 外壳 ≤450 行；UI helpers ≤500 行 |
| `src/vera/cli.py` | 638 | Typer app、session/run、recovery、state、config 命令 | app 外壳 ≤350 行；命令模块 ≤500 行 |
| `src/vera/verification/artifacts.py` | 587 | artifact root、planner、profile matcher、路径安全 | facade ≤220 行；三个职责模块 ≤450 行 |
| `tests/runtime/test_safe_editing_flow.py` | 819 | proposal/apply/approval/recovery 测试 | 按行为拆为 3–4 个文件 |
| `tests/session/test_controller.py` | 623 | lifecycle、slash、persistence、editor 测试 | 按行为拆为 3 个文件 |

文档 `docs/tasks/0002...`、`docs/tasks/0004...` 和阶段七 SVG 虽然体量较大，但不是本次代码拆分目标；不通过复制文档来制造“瘦身”假象。

## Task 0：建立重构前行为基线

**Files:**

- Create: `tests/refactor/test_public_imports.py`
- Create: `tests/refactor/test_runtime_trace_helpers.py`
- Modify: no production code

**Interfaces:**

- `test_public_imports.py` 固定现有模块的公开符号和 `inspect.signature` 结果。
- `test_runtime_trace_helpers.py` 提供只用于测试的 `normalize_event_trace()`，只删除 UUID、时间戳等非确定字段，不修改生产事件。

- [x] **Step 1: 记录当前文件尺寸和公共导入面**

运行：

```bash
git status --short --branch
git ls-files 'src/vera/**/*.py' 'scripts/**/*.py' 'tests/**/*.py' -z \
  | xargs -0 wc -l | sort -nr | head -30
```

Expected：工作树干净；记录上述表格中的大文件和当前分支 HEAD，不改文件。

- [x] **Step 2: 写公共导入和签名表征测试**

测试至少覆盖：

```python
from vera.runtime.engine import (
    ProposalInput,
    SnapshotPersistError,
    VeraRuntime,
    claims_unissued_changeset,
    tool_call_target,
)
from vera.session.controller import SessionController, SessionSnapshot
from vera.presentation.projector import (
    AppendBlock,
    FocusBlock,
    TimelineMutation,
    TimelineProjector,
    UpdateBlock,
    project_user_prompt,
)
```

同时断言 `VeraRuntime.__init__`、`SessionController.__init__`、`TimelineProjector.apply` 的参数名和默认值不变。

- [x] **Step 3: 写 normalized event trace helper 并增加一条端到端基线测试**

对 Fake Model、临时 workspace 和临时 state 运行一个普通回答、一个 proposal/approval、一个工具执行和一个恢复检查；比较 event type 顺序、状态终态、错误码、Diff 文件集合和公开 payload 字段。

- [x] **Step 4: 运行基线测试**

运行：

```bash
uv run --offline pytest -q tests/refactor tests/runtime/test_conversation_response.py \
  tests/runtime/test_git_runtime_recovery.py tests/session/test_controller.py \
  tests/presentation/test_projector.py
```

Expected：基线通过；如果现有环境仍缺少 `openai>=2,<3`，只记录 wheel/install fixture 的环境阻塞，不修改依赖。

## Task 1：拆分 Runtime 公共基础与内容输入流程

**Files:**

- Create: `src/vera/runtime/intake.py`
- Create: `src/vera/runtime/content_flow.py`
- Create: `src/vera/runtime/flow_protocols.py`
- Modify: `src/vera/runtime/engine.py`
- Test: `tests/runtime/test_conversation_response.py`, `tests/runtime/test_project_instructions.py`, `tests/e2e/test_prompt_injection_adversarial.py`

**Interfaces:**

- `intake.py` 导出 `ProposalInput`、`SnapshotPersistError`、`claims_unissued_changeset()`、`tool_call_target()` 和原有常量；`engine.py` re-export 它们。
- `content_flow.py` 提供：

```python
def prepare_content(host: ContentFlowHost, context: RunContext, text: str, *,
                    source_kind: str | None, origin: str,
                    truncated: bool = False) -> tuple[Any, str, list[EventEnvelope]]: ...
def seed_context(host: ContentFlowHost, context: RunContext) -> Iterator[EventEnvelope]: ...
def seed_project_instructions(host: ContentFlowHost, context: RunContext) -> Iterator[EventEnvelope]: ...
def append_conversation_message(host: ContentFlowHost, context: RunContext,
                                message: ConversationMessage) -> Iterator[EventEnvelope]: ...
```

- `flow_protocols.py` 只声明各 flow 实际使用的属性和回调，例如 `_event()`、`_record_finding()`、`project_instructions`、`content_detector`；禁止通过 `Any` 把整个 Runtime 隐式暴露给所有 flow。

- [x] **Step 1: 提取 intake models/helpers，不改调用点语义**

先移动常量、`ProposalInput`、两个纯函数和 `SnapshotPersistError`；在 `engine.py` 保留兼容导入。运行 `tests/runtime/test_conversation_response.py`。

- [x] **Step 2: 提取内容安全与上下文 seed 流程**

机械移动 `_prepare_content`、`_record_finding`、`_seed_context`、`_seed_project_instructions`、`_append_conversation_message`；保留事件产生顺序、`security_context_hash` 更新时机和项目指令渲染结果。

- [x] **Step 3: 保留 Runtime 薄包装方法**

`VeraRuntime` 的同名私有方法保留为一行转发，保证现有测试和未来子类/调试调用不改变；不得把 `EventJournal`、`RunContext` 或 `ContentDetector` 的所有权移动到 flow。

- [x] **Step 4: 运行内容和安全回归**

运行：

```bash
uv run --offline pytest -q tests/runtime/test_conversation_response.py \
  tests/runtime/test_project_instructions.py tests/runtime/test_untrusted_context.py \
  tests/e2e/test_prompt_injection_adversarial.py
uv run --offline ruff check src/vera/runtime tests/runtime tests/e2e/test_prompt_injection_adversarial.py
```

## Task 2：拆分 Runtime 工具执行、验证和审批流程

**Files:**

- Create: `src/vera/runtime/tool_flow.py`
- Create: `src/vera/runtime/verification_flow.py`
- Create: `src/vera/runtime/approval_flow.py`
- Modify: `src/vera/runtime/engine.py`
- Test: `tests/runtime/test_tool_executor.py`, `tests/runtime/test_write_edit_tools.py`, `tests/runtime/test_policy_approval.py`, `tests/runtime/test_git_runtime_recovery.py`, `tests/e2e/test_phase_8_tooling_policy.py`, `tests/e2e/test_phase_8_native_git.py`

**Interfaces:**

- `ToolExecutionFlow.execute_prepared(context, call, executor, prepared, approved=False)` 保持现有 `_execute_prepared_tool` 的返回类型 `tuple[ToolResult, tuple[EventEnvelope, ...]]`。
- `ToolExecutionFlow.execute_git(...)` 保持 `git.operation.started`、`git.operation.completed/recovered/manual_required/failed` 的事件顺序。
- `VerificationFlow.verify(context)`、`VerificationFlow.plan(...)` 只移动已有验证计划/绑定逻辑，不改变 `VerificationCommand` 或 artifact profile。
- `ApprovalFlow.propose(context, call)`、`ApprovalFlow.resolve(command)`、`ApprovalFlow.expire(...)` 保持现有 approval target hash、fact hash、policy hash 和 security kwargs。

- [x] **Step 1: 提取 receipt/event 通用私有辅助**

将 `_replay_receipt`、`_file_effect_refs`、`_commit_receipt`、`_process_receipt_payload`、`_replayed_tool_result`、`_git_operation_payload`、`_with_receipt` 放入 `tool_flow.py` 的私有辅助或 `RuntimeReceiptFlow`，先不合并任何错误处理分支。

- [x] **Step 2: 提取普通工具和 Git 工具执行**

移动 `_execute_prepared_tool`、`_execute_git_tool` 的实现，保留 `VeraRuntime._execute_prepared_tool()` 兼容包装。特别保留 started event 已落盘后异常继续抛出的行为，以及 receipt 写入顺序。

- [x] **Step 3: 提取 verification flow**

移动 `_planner`、`_verification_runner`、`_plan_verification`、`_expected_artifact_root`、`_verification_binding_matches`、`_verification_event_payload`、`_verify`，不改变 artifact root、环境变量和 `VerificationResult` 序列化。

- [x] **Step 4: 提取 proposal/approval flow**

移动 `_propose`、`_approval_payload`、`_expire_approval`、`_resolve_approval` 及其直接使用的纯辅助；`VeraRuntime` 继续维护 `runs`、`ApprovalGate` 和 snapshot 生命周期。

- [x] **Step 5: 运行工具、审批、Git 回归**

运行：

```bash
uv run --offline pytest -q tests/runtime/test_tool_executor.py \
  tests/runtime/test_write_edit_tools.py tests/runtime/test_policy_approval.py \
  tests/runtime/test_git_runtime_recovery.py tests/e2e/test_phase_8_tooling_policy.py \
  tests/e2e/test_phase_8_native_git.py tests/e2e/test_phase_8_client_parity.py
```

Expected：事件 trace、结果内容和错误码与 Task 0 的 baseline 相同；不借此任务修复已有 Bash/Git/recovery 缺陷。

## Task 3：拆分 Runtime loop、command dispatch 和 recovery

**Files:**

- Create: `src/vera/runtime/loop_flow.py`
- Create: `src/vera/runtime/recovery_flow.py`
- Create: `src/vera/runtime/command_flow.py`
- Modify: `src/vera/runtime/engine.py`
- Test: `tests/runtime/test_discovery_loop.py`, `tests/runtime/test_context_compaction.py`, `tests/runtime/test_recovery_resume.py`, `tests/runtime/test_recovery_snapshots.py`, `tests/cli/test_recovery_actions.py`, `tests/e2e/test_crash_recovery.py`

**Interfaces:**

- `LoopFlow.drive(context)`、`LoopFlow.complete_with_retry(...)`、`LoopFlow.finish_at_tool_limit(...)`、`LoopFlow.compact(context)` 保持 `RuntimeOutput` 流和 retry sleep 行为。
- `RecoveryFlow.inspect_recovery(...)`、`inspect_state(...)`、`plan_state_migration(...)`、`apply_state_migration(...)`、`resume(...)`、`abandon(...)` 保持当前 `RecoveryClassification`、`RecoveryStage` 和 snapshot hydration 语义。
- `CommandFlow.dispatch(command)` 只负责现有 `CoreCommand` 分发；`VeraRuntime.handle()`、`stream()` 签名保持不变。

- [x] **Step 1: 提取 model request/loop**

移动 `_model_request`、`_definitions`、`_complete_with_retry`、`_drive`、`_finish_at_tool_limit`、`_compact`；保持空回复提示、tool limit 提示、model retry 和 stream frame 顺序。

- [x] **Step 2: 提取 recovery flow**

移动 `_report_payload`、`_ephemeral_event`、`_inspect_recovery`、`_inspect_state`、migration 两个方法、`_reject_resume`、`_resume`、`_propose_partial_restore`、`_apply_recovery_plan`、`_context_from_snapshot`、`_abandon`。

- [x] **Step 3: 保留 command facade**

`VeraRuntime.handle()` 和 `stream()` 继续是唯一入口；`command_flow.py` 不直接暴露新的公共协议，不改变未知 command 的静默行为。

- [x] **Step 4: 运行完整 Runtime/recovery 回归**

运行：

```bash
uv run --offline pytest -q tests/runtime tests/e2e/test_crash_recovery.py \
  tests/cli/test_recovery_actions.py tests/cli/test_recovery_inspection.py \
  tests/cli/test_state_migration.py
```

## Task 4：拆分 SessionController，保留可继承 façade

**Files:**

- Create: `src/vera/session/persistence_flow.py`
- Create: `src/vera/session/run_flow.py`
- Create: `src/vera/session/command_flow.py`
- Create: `src/vera/session/editor_flow.py`
- Modify: `src/vera/session/controller.py`
- Test: `tests/session/test_controller_lifecycle.py`, `tests/session/test_controller_commands.py`, `tests/session/test_controller_persistence.py`, `tests/session/test_controller.py`

**Interfaces:**

- `SessionController` 继续拥有 mutable session state 和公开属性；flow 只接收显式 `SessionControllerHost` protocol 和参数，不直接重新创建 Controller。
- `PersistenceFlow.persist_turn(user_text, events)`、`persist_compaction(summary)`、`open_new_session()` 保持 unsaved 状态、错误码和建议文本。
- `RunFlow.submit(text)`、`queue_prompt(text)`、`clear_queued_prompt()`、`resolve_approval(...)`、`cancel(run_id)`、`close()` 保持 `_active_run_id`、`_pending_approval`、`queued_prompt` 和 `_drive_epoch` 的时机。
- `CommandFlow.execute(raw)` 保持所有 slash command 名称、参数错误行为、帮助文本和事件类型。
- `EditorFlow.open(text)`、`confirm(accept)` 保持 external editor preview、draft cleanup 和拒绝错误码。

- [x] **Step 1: 先移动纯持久化段落**

提取 `_persistence_code`、`_mark_unsaved`、`_persist_turn`、`_persist_compaction`、`_open_new_persistent_session`；保留 Controller 包装方法，先跑 session persistence tests。

- [x] **Step 2: 移动 editor/queue/run lifecycle**

提取 editor、queue、submit、approval、cancel、close 的实现；显式保留 `RecordingController`、`BlockingController`、`FailingController` 等现有子类的覆盖点。

- [x] **Step 3: 移动 slash command handlers**

按命令类别分到 `command_flow.py`：session/status/context、permissions/instructions、sessions/new/clear、diff/review/doctor/config/usage/theme、recovery/rollback。`controller.py` 只保留 dispatch 和薄包装。

- [x] **Step 4: 运行 Session/CLI/TUI 回归**

运行：

```bash
uv run --offline pytest -q tests/session tests/cli/test_session.py \
  tests/cli/test_plain_session.py tests/cli/test_json_session.py \
  tests/terminal/test_bridge.py tests/terminal/test_keyboard_flows.py \
  tests/e2e/test_phase_7_product_matrix.py
```

## Task 5：拆分 TimelineProjector，维持 mutation re-export

**Files:**

- Create: `src/vera/presentation/mutations.py`
- Create: `src/vera/presentation/timeline_state.py`
- Create: `src/vera/presentation/stream_projector.py`
- Create: `src/vera/presentation/event_projector.py`
- Create: `src/vera/presentation/prompt_block.py`
- Modify: `src/vera/presentation/projector.py`
- Test: `tests/presentation/test_projector.py`, `tests/presentation/test_projector_extra.py`, `tests/presentation/test_event_copy.py`, `tests/performance/test_terminal_timeline.py`, `tests/e2e/test_phase_8_client_parity.py`

**Interfaces:**

- `mutations.py` 定义并导出 `AppendBlock`、`UpdateBlock`、`FocusBlock`、`TimelineMutation`；`projector.py` 继续 re-export。
- `TimelineState` 管理 blocks、streams、tool mappings、side-effect runs、model failures 和 tool start times；保留 `_blocks`、`_max_blocks` 等现有测试可见属性的兼容访问。
- `StreamProjector.apply(state, frame, disclosure, max_body_bytes)` 只处理 assistant stream。
- `EventProjector.apply(state, event, disclosure, max_body_bytes)` 只处理 event handler 和 handler map；handler 的 block id、title、body、status 和 mutation 顺序不变。
- `TimelineProjector.apply(output)` 继续先 redaction，再按 Stream/Event 分派；`blocks()`、`reset()` 和 `project_user_prompt()` 的公共行为不变。

- [x] **Step 1: 提取 mutation models 和 prompt helper**

只移动 Pydantic model 和 `project_user_prompt()`，添加旧路径 import test。

- [x] **Step 2: 提取 state/common operations**

移动 truncate、evict、append、relabel、side-effect/diff tracking；保持 insertion order 和 max block eviction 顺序。

- [x] **Step 3: 提取 stream/event handlers**

按现有分支机械移动，不改变 unknown event、silent event、redaction、occurred_at stamping 行为。

- [x] **Step 4: 运行 Presentation/PTY/performance 回归**

运行：

```bash
uv run --offline pytest -q tests/presentation tests/performance/test_terminal_timeline.py \
  tests/pty/test_permissions_v2.py tests/e2e/test_phase_8_client_parity.py
```

## Task 6：拆分 Verification artifact 与 installed-wheel smoke

**Files:**

- Create: `src/vera/verification/artifact_paths.py`
- Create: `src/vera/verification/artifact_root.py`
- Create: `src/vera/verification/artifact_planner.py`
- Modify: `src/vera/verification/artifacts.py`
- Create: `scripts/smoke_support/core_payload.py`
- Create: `scripts/smoke_support/cli_checks.py`
- Create: `scripts/smoke_support/session_checks.py`
- Modify: `scripts/smoke_installed_wheel.py`
- Test: `tests/verification/test_artifacts.py`, `tests/verification/test_runner.py`, `tests/e2e/test_verification_artifact_isolation.py`, `tests/e2e/test_phase_5_install_upgrade.py`

**Interfaces:**

- `artifacts.py` 继续 re-export `CleanupResult`、`VerificationArtifactRoot`、`VerificationArtifactPlanner`、`artifact_root()`、`environment_for_plan()` 和已有 path helpers。
- `smoke_installed_wheel.py` 只负责参数解析、临时环境、子进程编排、退出码；Core payload 和 CLI/session assertions 移入 `smoke_support`。
- `_CORE_SMOKE` 的安装态执行方式保持 `python -c <payload> <workspace>`，不能改成源码 import，以继续验证 wheel 而不是仓库源码。

- [x] **Step 1: 拆 artifact path/root/planner**

按现有边界拆分，不改变 artifact profile 名称、输出路径、ownership 校验、cleanup 状态或错误码；所有旧 import 从 facade 继续可用。

- [x] **Step 2: 拆 smoke payload 和 CLI/session checks**

把嵌入式 Core smoke 作为独立 source string provider，把 CLI/version/eval/session/recovery/instruction 检查按职责拆出；保持测试中 `SMOKE_SCRIPT` 路径不变。

- [x] **Step 3: 运行 artifact 和 smoke 回归**

运行：

```bash
uv run --offline pytest -q tests/verification tests/e2e/test_verification_artifact_isolation.py
uv build --offline --wheel --sdist
```

安装依赖缓存可用时再运行仓库外 wheel smoke；缓存不可用时保留明确的环境阻塞，不伪造通过。

## Task 7：拆分 CLI 与 Terminal app 的剩余生产单体

**Files:**

- Create: `src/vera/cli_commands.py`
- Create: `src/vera/cli_recovery.py`
- Create: `src/vera/cli_inspection.py`
- Create: `src/vera/terminal/layout_flow.py`
- Create: `src/vera/terminal/input_actions.py`
- Create: `src/vera/terminal/output_flow.py`
- Modify: `src/vera/cli.py`
- Modify: `src/vera/terminal/app.py`
- Test: `tests/cli`, `tests/terminal`, `tests/pty`, `tests/e2e/test_phase_7_product_matrix.py`

**Interfaces:**

- `cli.py` 保留 Typer `app`、入口函数、command registration 和旧命令 help/exit code；具体 run/session/recovery/state/config 实现移入命令模块。
- `VeraTerminalApp` 保留 Textual lifecycle、公开构造函数和 message handler；layout resize/chrome、input/keyboard/approval、runtime output 分别移入 helper flow。
- 不改变 ANSI/plain/JSON 规则，不改变 Terminal widget 查找、focus、scroll、approval selection 和 clipboard 行为。

- [x] **Step 1: 拆 CLI command groups**

先拆 recovery/state/inspection，再拆 run/session；每一步运行对应 CLI tests，保证 Typer command name、option、help 和 exit code 稳定。

- [x] **Step 2: 拆 Terminal layout/input/output**

使用显式 `VeraTerminalAppHost` protocol 或纯 helper，不使用 mixin；保持 Textual callback 的 owner 仍是 `VeraTerminalApp`。

- [x] **Step 3: 运行 Terminal/PTY 回归**

运行：

```bash
uv run --offline pytest -q tests/cli tests/terminal tests/pty \
  tests/e2e/test_phase_7_product_matrix.py
```

## Task 8：拆分大测试文件并增加尺寸门禁

**Files:**

- Create: `tests/runtime/test_safe_editing_proposal.py`
- Create: `tests/runtime/test_safe_editing_apply.py`
- Create: `tests/runtime/test_safe_editing_recovery.py`
- Create: `tests/session/test_controller_lifecycle.py`
- Create: `tests/session/test_controller_commands.py`
- Create: `tests/session/test_controller_persistence.py`
- Create: `scripts/check_source_sizes.py`
- Test: existing moved test modules

**Interfaces:**

- 测试拆分只移动测试函数和 fixtures，不改变 fixture 名称的语义、临时目录生命周期、Fake Model sequence 或断言。
- `scripts/check_source_sizes.py` 接受仓库根目录参数，默认扫描 `src/vera`、`scripts`、`tests`，打印超过 600 行的相对路径并以非零退出；不扫描 `docs`、`.venv`、`dist` 和缓存。

- [x] **Step 1: 按行为拆分 safe editing tests**

proposal/approval 放入 `test_safe_editing_proposal.py`，apply/checkpoint/diff 放入 `test_safe_editing_apply.py`，rollback/recovery/crash 放入 `test_safe_editing_recovery.py`；先运行原文件测试，再运行三个新文件。

- [x] **Step 2: 按行为拆分 controller tests**

lifecycle/queue/editor 放入 `test_controller_lifecycle.py`，slash/status/permissions 放入 `test_controller_commands.py`，persistence/reload/unsaved 放入 `test_controller_persistence.py`。

- [x] **Step 3: 加入尺寸检查**

运行：

```bash
uv run --offline python scripts/check_source_sizes.py /Users/admin/Vera/tmp/vera-phase8-tooling-policy-git
```

Expected：`src/vera`、`scripts`、`tests` 中没有超过 600 行的文件；文档和生成资产不参与该门禁。

## Task 9：最终等价性和工程门禁

**Files:**

- Modify: `tests/refactor/test_runtime_trace_helpers.py` only if a missing nondeterministic field needs normalization
- Modify: no status/roadmap/phase-completion document

- [x] **Step 1: 运行所有受影响专项测试**

```bash
uv run --offline pytest -q tests/refactor tests/runtime tests/session tests/presentation \
  tests/verification tests/cli tests/terminal tests/pty \
  tests/e2e/test_phase_8_tooling_policy.py \
  tests/e2e/test_phase_8_native_git.py \
  tests/e2e/test_phase_8_client_parity.py
```

- [x] **Step 2: 运行静态和格式门禁**

```bash
uv run --offline ruff check src tests scripts
uv run --offline ruff format --check src tests scripts
uv run --offline mypy src
git diff --check
uv run --offline python scripts/check_source_sizes.py .
```

- [x] **Step 3: 运行全量 non-live 和构建检查**

```bash
uv run --offline pytest -q -m 'not live'
uv build --offline --wheel --sdist
```

若 `openai>=2,<3` 仍不在离线缓存中，记录具体的 failed/error 测试为环境阻塞；不得把历史验收结果覆盖成“本轮全绿”。

- [x] **Step 4: 做公共导入、安装态和工作树检查**

```bash
uv run --offline pytest -q tests/refactor
git status --short --branch
git diff --stat
git diff --check
```

确认没有生产行为 diff、没有公共导入断裂、没有超大代码文件、没有 workspace 外污染；不更新 Phase 8 Complete 状态。

## Completion Criteria

- `VeraRuntime`、`SessionController`、`TimelineProjector`、CLI 和 wheel smoke 的公共入口保持兼容。
- normalized event trace、Tool/Approval/Recovery/Git 状态和 CLI/TUI/JSON 输出与基线一致。
- `src/vera`、`scripts`、`tests` 没有超过 600 行的单文件；新模块保持单一职责。
- Ruff、format、Mypy、受影响测试、尺寸门禁、`git diff --check` 通过；构建和安装态结果明确区分通过与环境阻塞。
- 本次不修复 Bash/Git/recovery 已知缺陷，不改变 Phase 8 `Ready for manual acceptance` 状态，也不启动 Phase 9 或桌面工作。

## 实施结果与验证证据

- **代码范围：** Runtime、SessionController、Presentation projector、Verification artifacts、installed-wheel smoke、CLI、Terminal app 和两组大测试文件均已按职责拆分；旧公共导入路径与兼容 façade 保留。
- **文件尺寸：** `src/vera`、`scripts`、`tests` 尺寸门禁通过，没有超过 600 行的文件；最终最大源文件为 571 行。文档不参与该代码门禁。
- **专项验证：** 受影响最终矩阵 `642 passed`，仅有 8 个 PTY deprecation warnings；`tests/refactor` 为 `10 passed`。
- **工程门禁：** Ruff、Ruff format、Mypy（223 个源文件）、wheel/sdist 构建和 `git diff --check` 均通过。
- **全量 non-live：** `1315 passed, 2 deselected, 8 warnings`，另有 1 个失败和 1 个错误，均来自离线 wheel 安装缺少缓存的 `openai>=2,<3`，属于环境阻塞，未伪造为全绿。
- **提交边界：** 代码提交为 `dd201e7 refactor: split phase eight monoliths`；本计划文档随后单独提交。`docs/STATUS.md`、`docs/ROADMAP.md`、阶段八验收状态和阶段九工作树不在本次文档同步范围内。

## Handoff

本计划描述的纯代码拆分和优化已完成并形成代码提交 `dd201e7`；本次文档同步后，代码、验证证据和计划状态一致。未执行合并、推送或删除分支/工作树；Phase 8 仍保持 `Ready for manual acceptance`，Phase 9 不因本任务自动启动。
