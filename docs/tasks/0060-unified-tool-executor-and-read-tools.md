# 任务 0060：统一 ToolExecutor 与只读工具迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**状态：** Planned；已授权串行实施，依赖 0059 完成
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

- [ ] **Step 1: 写 Executor 失败测试** — 固定 unknown tool、schema error、workspace escape、allow/approval/deny、参数或事实变化 stale，断言 deny/approval 不调用工具实现。
- [ ] **Step 2: 运行 Red** — `uv run pytest tests/tools/test_executor.py -q`，预期模块不存在。
- [ ] **Step 3: 实现 Registry/Executor 最小边界** — Registry 提供 `definitions() -> tuple[ToolDefinitionV2, ...]` 和内部 `implementation(name)`；删除业务层直接 `execute` 的新调用路径。
- [ ] **Step 4: 写 canonical read 工具测试** — `read` 有界 UTF-8 范围，`grep` 返回相对路径/行号，`find` 发现文件，`ls` 稳定排序；覆盖 symlink、二进制、过大输出和特殊路径。
- [ ] **Step 5: 实现 `read/grep/find/ls`** — 复用 `WorkspacePaths` 与现有 filesystem 函数；定义 v2 effects/max output，不通过 `bash` 实现发现。
- [ ] **Step 6: 写 Runtime 旁路回归** — monkeypatch `ToolRegistry.execute` 抛错，正常只读 Run 仍成功；PolicyAction、ToolAction、ToolResult Event 顺序固定。
- [ ] **Step 7: 接入 Runtime** — `_execute_tool_call()` 只调用 `ToolExecutor.prepare/execute_allowed`；approval plan 保存 `action_id/input_hash/target_facts_hash/policy_hash`，恢复前重验。
- [ ] **Step 8: 迁移模型工具名** — System Prompt 与 adapter definitions 只暴露 canonical 名称；`read_file/list_directory/search_text` 仅保留旧 Journal/fixture decoder 映射，不注册给新模型请求。
- [ ] **Step 9: 客户端契约对照** — TUI/Plain/JSON 对同一 ToolAction/Result 的名称、状态、截断和错误码一致，不解析 content 判断成功。
- [ ] **Step 10: 运行局部与共同门禁** — `uv run pytest tests/tools tests/runtime/test_tool_executor.py tests/e2e/test_core_client_contract_parity.py -q` 后运行阶段八共同门禁。
- [ ] **Step 11: 提交（仅用户授权后）** — 提交信息 `feat: add unified tool execution pipeline`。

## Done

- Runtime 中不存在普通工具绕过 Policy 的执行路径。
- 新模型只看到 canonical 工具，旧记录仍可恢复。
- 四个只读工具的边界、截断和错误码稳定。
