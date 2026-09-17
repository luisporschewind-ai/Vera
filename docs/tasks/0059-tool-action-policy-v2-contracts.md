# 任务 0059：ToolAction、Policy v2 与 workspace trust 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**状态：** In progress；用户于 2026-09-18 授权 Inline Execution
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

- [ ] **Step 1: 写契约失败测试** — 在 `tests/contracts/test_tool_actions.py` 固定 `ToolDefinitionV2(schema_version=2, effects=(...), supports_cancellation=True, supports_recovery=True, max_output_bytes=100_000)`、`ToolAction` JSON round-trip、未知字段拒绝和稳定 `input_hash`。
- [ ] **Step 2: 运行 Red** — `UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/contracts/test_tool_actions.py -q`；预期因 v2 类型不存在失败。
- [ ] **Step 3: 实现最小契约** — 新增上述枚举/模型；`ToolDefinitionV2` 与现有 v1 使用可判别 Codec，不改变旧 fixture 的读取结果。
- [ ] **Step 4: 写 Policy v2 矩阵失败测试** — 参数化覆盖三档模式、四级风险、六类 effect、trusted/untrusted、用户目标匹配/不匹配，断言 forbidden 永不因模式降低。
- [ ] **Step 5: 实现 Policy v2 纯函数** — `classify_risk(action, permission_snapshot) -> RiskAssessment` 与 `decide_v2(...) -> PolicyDecision`；现有投毒 `tighten_policy_decision` 在基础决策后执行且只能收紧。
- [ ] **Step 6: 写 Store 原子性测试** — 覆盖 `0600`、临时文件替换、损坏隔离、future version 拒绝、identity/Policy 版本变化失效、revoke 幂等和仓库内同名文件无效。
- [ ] **Step 7: 实现私有 permission store** — 复用 `PrivateStateWriter`/安全 run-id 风格校验；正文不进入 Event，公开投影只含模式、trust、规则摘要和 hash。
- [ ] **Step 8: 更新兼容清单** — 将 ToolDefinition v2、ToolAction 和 permission facts 标为 additive；旧 PolicyAction/ChangeSet 仍在受支持清单。
- [ ] **Step 9: 运行局部门禁** — `uv run pytest tests/contracts/test_tool_actions.py tests/policy/test_policy_v2.py tests/persistence/test_workspace_permissions.py tests/contracts/test_compatibility_manifest.py -q`，再运行阶段八共同门禁。
- [ ] **Step 10: 提交（仅用户授权后）** — `git add` 仅限本任务文件并执行 `git commit -m "feat: define tool action and policy v2 contracts"`。

## Done

- v2 契约和权限存储可独立测试；默认 `balanced` 不依赖 UI。
- trust/grant 不能由工程内容建立，损坏或版本变化失败关闭。
- 旧 v1 Policy/Tool/Journal fixture 仍可读取。
