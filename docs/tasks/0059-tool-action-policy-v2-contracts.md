# 任务 0059：ToolAction、Policy v2 与 workspace trust 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**状态：** Done；用户于 2026-09-18 授权 Inline Execution
**Goal：** 冻结后续工具、文件、命令和 Git 共用的 v2 契约、风险模型、使用档位、workspace trust 与受限授权存储。
**Architecture：** 公共 Contract 只表达结构化 ToolAction 与 Policy 结果；私有 Store 保存 trust/grant，不允许仓库内容写入。PolicyEngine 继续是唯一决策入口，现有 v1 Action 和旧策略快照保持可解码。
**Tech Stack：** Python 3.12、Pydantic 2、现有 PolicyEngine/PrivateWriter/Codec、pytest。
**Spec：** `docs/specs/2026-09-17-core-tooling-and-risk-tiered-policy.md`

## Global Constraints

- `balanced` 是默认模式；`review`/`autonomous` 只能来自用户私有配置。
- workspace trust 绑定 `workspace_identity`、Policy 主版本和受保护根；仓库文件不能建立或续期。
- 授权规则必须包含 tool、effect、参数约束和作用域，禁止仅按可执行文件名永久放行。
- 新字段按 ADR-0014 分类；旧 `PolicyAction`、快照和 Journal 必须继续读取。

## Files

- Create: `src/vera/contracts/tool_actions.py`
- Create: `src/vera/policy/permissions.py`
- Create: `src/vera/persistence/workspace_permissions.py`
- Modify: `src/vera/tools/definitions.py`
- Modify: `src/vera/policy/models.py`
- Modify: `src/vera/policy/snapshot.py`
- Modify: `src/vera/policy/rules.py`
- Modify: `src/vera/contracts/compatibility.py`
- Test: `tests/contracts/test_tool_actions.py`
- Test: `tests/policy/test_policy_v2.py`
- Test: `tests/persistence/test_workspace_permissions.py`

## Interfaces

```python
class ToolEffect(StrEnum):
    WORKSPACE_READ = "workspace_read"
    WORKSPACE_WRITE = "workspace_write"
    PROCESS_EXECUTE = "process_execute"
    NETWORK_ACCESS = "network_access"
    EXTERNAL_SERVICE = "external_service"
    SECRET_ACCESS = "secret_access"

class PolicyMode(StrEnum):
    REVIEW = "review"
    BALANCED = "balanced"
    AUTONOMOUS = "autonomous"

class RiskLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    FORBIDDEN = "forbidden"

class ToolAction(ContractModel):
    schema_version: Literal[1] = 1
    action_id: str
    run_id: str
    tool_name: str
    tool_version: int
    effects: tuple[ToolEffect, ...]
    workspace_identity: str
    normalized_arguments: dict[str, JsonValue]
    input_hash: str

class ToolDefinitionV2(ContractModel):
    schema_version: Literal[2] = 2
    name: str
    description: str
    input_schema: dict[str, JsonValue]
    effects: tuple[ToolEffect, ...]
    supports_cancellation: bool
    supports_recovery: bool
    max_output_bytes: int

class PermissionGrant(ContractModel):
    grant_id: str
    scope: Literal["once", "run", "workspace"]
    tool_name: str
    effects: tuple[ToolEffect, ...]
    argument_constraints: dict[str, JsonValue]
    run_id: str | None
    expires_at: datetime | None

class WorkspacePermissionSnapshot(ContractModel):
    schema_version: Literal[1] = 1
    workspace_identity: str
    policy_major_version: int
    trusted: bool
    protected_roots_hash: str
    grants: tuple[PermissionGrant, ...]

class RiskAssessment(ContractModel):
    level: RiskLevel
    reason_codes: tuple[str, ...]

class WorkspacePermissionStore:
    def load(self, workspace_identity: str) -> WorkspacePermissionSnapshot: ...
    def save(self, snapshot: WorkspacePermissionSnapshot) -> None: ...
    def revoke(self, workspace_identity: str) -> None: ...
```

## Steps

- [x] **Step 1: 写契约失败测试** — 覆盖 ToolDefinition v2、ToolAction JSON round-trip、未知字段、稳定 `input_hash`、深层不可变参数和严格 JSON。
- [x] **Step 2: 运行 Red** — v2 模块缺失时，契约、Policy 和 store 三组测试均按预期失败。
- [x] **Step 3: 实现最小契约** — 新增带 `tool_version` 的 v2 定义、可判别 codec、ToolAction、风险事实和 canonical hash；v1 请求仍可解码。
- [x] **Step 4: 写 Policy v2 矩阵失败测试** — 覆盖三档、四级风险、六类 effect、trusted/untrusted、目标匹配、精确授权、路径/策略绑定和 grant 重放。
- [x] **Step 5: 实现 Policy v2 纯函数** — `classify_risk`/`decide_v2` 与 `PolicyEngine.decide_tool_action` 失败关闭绑定；投毒检测继续只能收紧。
- [x] **Step 6: 写 Store 原子性测试** — 覆盖 `0600/0700`、唯一临时文件替换、损坏/失效隔离、future version 保留、binding 变化、revoke、临时 grant 拒绝和仓库同名文件无效。
- [x] **Step 7: 实现私有 permission store** — 仅持久化 workspace grant；正文不进入公开契约，公开面为 mode/trust/规则摘要/hash。
- [x] **Step 8: 更新兼容清单** — ToolDefinition v2、ToolAction 和 `WorkspacePermissionSummary` 为 additive；旧 PolicyAction/ChangeSet 继续列入支持清单。
- [x] **Step 9: 运行局部门禁** — 聚焦 `59 passed`；共同门禁 `1176 passed, 2 deselected`；Ruff、格式、Mypy、wheel/sdist 和 diff 检查通过。
- [x] **Step 10: 提交（用户已授权）** — 本提交仅包含 0059 契约、Policy、私有存储、兼容契约、测试和状态记录。

## Done

- v2 契约和权限存储可独立测试；默认 `balanced` 不依赖 UI。
- trust/grant 不能由工程内容建立，损坏或版本变化失败关闭。
- 旧 v1 Policy/Tool/Journal fixture 仍可读取。

## 验证记录

- 双轮只读代码审查：第一轮关闭深层可变参数、Engine binding、grant 生命周期/作用域、Store 原子性与私有边界、v2 codec 和公开投影问题；第二轮关闭不完整 read 自动允许和错误消费 once grant 问题，最终结论 Ready。
- 2026-09-18：`UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/contracts/test_tool_actions.py tests/policy/test_policy_v2.py tests/persistence/test_workspace_permissions.py tests/contracts/test_compatibility_manifest.py tests/models/test_adapter_conformance.py -q` → `59 passed`。
- 2026-09-18：完整非 live → `1176 passed, 2 deselected, 6 warnings`；warnings 为既有 PTY `forkpty` deprecation。
- 2026-09-18：`ruff check`、`ruff format --check`、`mypy src`、`uv build --out-dir /private/tmp/vera-phase8-dist` 和 `git diff --check` 均通过。
