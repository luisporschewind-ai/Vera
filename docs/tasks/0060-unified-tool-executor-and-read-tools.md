# 任务 0060：统一 ToolExecutor 与只读工具迁移实施计划

> 2026-09-26 文档对齐：本记录来自 `codex/phase-8-tooling-policy-git`（核对时 HEAD `5b6d789`）。实现及验证属于该隔离分支，尚未合入 `main`；同步文档不代表代码集成或本轮重新测试。下文提交/推送表述保留各任务完成时的历史边界，当前分支状态见阶段八执行计划。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**状态：** Done；已授权串行实施，依赖 0059 完成
**Goal：** 让所有普通工具先形成 ToolAction、收集事实并经过 Policy，再执行 canonical `read/grep/find/ls`，消除 Runtime 直接调用 registry 的旁路。
**Architecture：** ToolRegistry 只负责定义与实现发现；ToolExecutor 分为 `prepare()` 和 `execute_allowed()`，Runtime 负责暂停审批并把已批准的精确 plan 交回 Executor。只读工具复用现有安全 filesystem 函数，旧名称仅由恢复兼容层识别。
**Tech Stack：** Python 3.12、Pydantic 2、现有 WorkspacePaths/ToolRegistry/VeraRuntime、pytest。
**Spec：** `docs/specs/2026-09-17-core-tooling-and-risk-tiered-policy.md`

## Files

- Create: `src/vera/tools/executor.py`
- Modify: `src/vera/tools/registry.py`
- Modify: `src/vera/tools/builtin.py`
- Modify: `src/vera/tools/filesystem.py`
- Modify: `src/vera/runtime/engine.py`
- Modify: `src/vera/runtime/prompts.py`
- Modify: `src/vera/bootstrap.py`
- Modify: `src/vera/contracts/compatibility.py`
- Test: `tests/tools/test_executor.py`
- Modify: `tests/tools/test_builtin.py`
- Modify: `tests/tools/test_registry.py`
- Test: `tests/runtime/test_tool_executor.py`
- Modify: `tests/e2e/test_core_client_contract_parity.py`

## Interfaces

```python
@dataclass(frozen=True)
class PreparedToolAction:
    action: ToolAction
    definition: ToolDefinitionV2
    parsed_arguments: BaseModel
    policy_decision: PolicyDecision
    target_facts_hash: str

class ToolExecutor:
    def prepare(self, *, run_id: str, name: str, arguments: dict[str, Any]) -> PreparedToolAction: ...
    def execute_allowed(self, prepared: PreparedToolAction) -> ToolResult: ...
```

## Steps

- [x] **Step 1: 写 Executor 失败测试** — 固定 unknown tool、schema error、workspace escape、allow/deny、参数或事实变化 stale；deny 不调用工具实现；高风险动作覆盖审批前不执行。
- [x] **Step 2: 运行 Red** — `UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/tools/test_executor.py -q`，确认初始 `ModuleNotFoundError: vera.tools.executor`。
- [x] **Step 3: 实现 Registry/Executor 最小边界** — Registry 提供 `definitions() -> tuple[ToolDefinitionV2, ...]` 和内部 `implementation(name)`；Runtime 的普通工具路径不调用 `execute`。
- [x] **Step 4: 写 canonical read 工具测试** — `read` 有界 UTF-8 范围，`grep` 返回相对路径/行号，`find` 发现文件，`ls` 稳定排序；已有 filesystem 回归覆盖 symlink、二进制、特殊路径，Executor 覆盖过大输出。
- [x] **Step 5: 实现 `read/grep/find/ls`** — 复用 `WorkspacePaths` 与现有 filesystem 函数；声明 v2 effects/max output，不通过 `bash` 实现发现。
- [x] **Step 6: 写 Runtime 旁路回归** — monkeypatch `ToolRegistry.execute` 抛错，normal `read` Run 仍成功；固定 `tool.started → tool.policy_decided → tool.action_prepared → tool.completed`。
- [x] **Step 7: 接入 Runtime** — 普通调用只经过 `ToolExecutor.prepare/execute_allowed`；高风险 approval plan 保存 `action_id/input_hash/target_facts_hash/policy_hash`，快照恢复后重新校验 facts/policy 再执行。
- [x] **Step 8: 迁移模型工具名** — System Prompt 与 adapter definitions 只暴露 canonical 名称；`read_file/list_directory/search_text` 仅保留旧 fixture/decoder 类，不注册给新 bootstrap。
- [x] **Step 9: 客户端契约对照** — 事件仍由 Core 统一产生；presentation/activity 识别 canonical 名称，现有 TUI/Plain/JSON Core parity 回归保持通过。
- [x] **Step 10: 运行局部与共同门禁** — 局部、分组回归、Ruff、格式、Mypy、diff 和 wheel/sdist 已通过；共同 non-live 合并命令通过。
- [x] **Step 11: 提交（仅用户授权后）** — 提交信息 `feat: add unified tool execution pipeline`。

## Done

- Runtime 中不存在普通工具绕过 Policy 的执行路径。
- 新模型只看到 canonical 工具，旧记录仍可恢复。
- 四个只读工具的边界、截断和错误码稳定。

## 本任务完成时的证据与边界

- 2026-09-19：Executor 红测已确认；审批暂停、快照恢复、批准后复验及 action resolved 持久化已接入；最新审查修复覆盖 `find` glob 越界、`grep/find` 外部 symlink、执行阶段 definition/input binding stale、显式 V2 policy 不被重绑定，以及 `approved=True` 不得绕过 `DENY`，并补充对应回归。工具/Runtime/Recovery/Contract/Policy/Persistence/Workspace 分组 `386 passed`，CLI/Presentation 分组 `213 passed`；共同 non-live `1208 passed, 2 deselected, 6 warnings`，Ruff、格式、Mypy、`git diff --check` 与 wheel/sdist 构建全部通过。
- canonical `read/grep/find/ls` 已由 bootstrap 注册；旧 `read_file/list_directory/search_text` 仅保留历史 fixture/decoder 类，不进入新 bootstrap。
- 0060 完成时要求后续任务另获授权；0062 后来已实施完成，当前阶段八剩余事项见执行计划。
