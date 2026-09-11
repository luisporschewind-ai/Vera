# Vera 统一 PolicyEngine 与审批指纹实施计划

> **供 Cursor Agent 执行：** 由单一主实现 Agent 顺序执行。先写失败测试，最小迁移已有规则，逐任务提交；不得并行重写安全组件。

**状态：** Planned

**目标分支：** `feature/unified-policy-engine`

**目标：** 用一个 UI 无关 PolicyEngine 统一解释路径、工具、验证命令、Change Set 和恢复动作，将审批绑定工作区及策略指纹，同时保持阶段一所有硬性限制和纵深复核。

**架构：** PolicyEngine 只做纯判定并返回结构化 `PolicyDecision`；执行仍由 WorkspacePaths、ToolRegistry、ChangeApplier 和 VerificationRunner 负责。现有 CommandPolicy 先成为兼容适配器，再逐步把规则迁入 Engine；任何行为迁移都由决策矩阵证明不放宽。

**技术栈：** Python 3.12、Pydantic 2、pytest、Ruff、Mypy、uv；不新增第三方依赖。

**规格：** [阶段二总规格](../specs/2026-09-11-phase-2-recovery-compatibility-policy.md)

**架构决策：** [ADR-0007](../decisions/ADR-0007-unified-policy-engine.md)

**依赖：** 任务 0005–0007 已合并到 `main`。

## 全局约束

- 固定优先级：硬性禁止 → 工作区/敏感资源 → 用户授权 → 内置安全 → 本次审批。
- 项目配置只能收紧，不可授权。
- 用户授权不能覆盖工作区逃逸、凭据文件、提权、Shell 或宽泛破坏命令。
- PolicyEngine 不执行文件、命令、工具、恢复或迁移。
- WorkspacePaths、VerificationRunner 和 CheckpointStore 保留执行前复核。
- `policy_hash` 不包含 Key、Base URL、自然语言 reason 或不影响决定的显示字段。
- 恢复与 ResolveApproval 前重新计算策略；不同 hash 使旧审批失效。
- 第一版不支持自动批准、通配命令或临时关闭规则。
- 不运行 live 测试，不使用真实 Key。

## 文件结构

```text
src/vera/
├── policy/
│   ├── __init__.py
│   ├── models.py
│   ├── rules.py
│   ├── engine.py
│   └── snapshot.py
├── tools/{command_policy,filesystem,registry}.py
├── runtime/{approval,engine}.py
├── recovery/{coordinator,resume}.py
├── session/{models,permissions}.py
└── bootstrap.py

tests/
├── policy/{test_models,test_matrix,test_hash}.py
├── runtime/test_policy_approval.py
├── recovery/test_policy_resume.py
├── session/test_permissions.py
└── tools/{test_command_policy,test_filesystem}.py
```

---

### Task 1：固定 PolicyAction、Decision 与规范化哈希

**文件：**

- Create: `src/vera/policy/__init__.py`
- Create: `src/vera/policy/models.py`
- Create: `src/vera/policy/snapshot.py`
- Create: `tests/policy/__init__.py`
- Create: `tests/policy/test_models.py`
- Create: `tests/policy/test_hash.py`

**接口：**

- Produces: `PolicyDecisionKind.ALLOW | APPROVAL_REQUIRED | DENY`
- Produces: `PolicyActionKind`
- Produces: `PolicyAction(kind, workspace_identity, resource, argv=(), metadata={})`
- Produces: `PolicyDecision(decision, reason_code, reason, matched_rule, policy_hash)`
- Produces: `EffectivePolicySnapshot`
- Produces: `policy_hash(snapshot) -> str`

- [ ] **Step 1：编写模型和哈希稳定性测试**

```python
def test_display_reason_does_not_change_policy_hash() -> None:
    snapshot = policy_snapshot(user_allowed_prefixes=(("pytest",),))
    first = decision(snapshot, reason="中文说明")
    second = decision(snapshot, reason="different display text")
    assert first.policy_hash == second.policy_hash


def test_policy_hash_changes_when_effective_prefix_changes() -> None:
    first = policy_snapshot(user_allowed_prefixes=(("pytest",),))
    second = policy_snapshot(user_allowed_prefixes=(("ruff",),))
    assert policy_hash(first) != policy_hash(second)
```

再断言序列化内容不包含测试 Key/Base URL，规则顺序规范化后 hash 相同，workspace identity 改变后 hash 改变。

- [ ] **Step 2：运行测试并确认 policy 包不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/policy/test_models.py tests/policy/test_hash.py -v
```

- [ ] **Step 3：实现精确动作枚举**

`PolicyActionKind` 固定为 `path_read`、`path_write`、`tool_execute`、`command_execute`、`changeset_apply`、`checkpoint_restore`、`recovery_resume`、`state_migrate`。Snapshot 只包含内置策略版本、工作区身份、受保护模式、规范化用户命令前缀和项目收紧规则。

哈希使用以下规范化字节计算 SHA-256；`EffectivePolicySnapshot` 本身不包含展示 reason 和秘密配置：

```python
encoded = json.dumps(
    snapshot.model_dump(mode="json"),
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
```

- [ ] **Step 4：运行模型与静态检查**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/policy -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/policy tests/policy
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [ ] **Step 5：提交 Policy 模型**

```bash
git add src/vera/policy tests/policy docs/tasks/0008-unified-policy-engine.md
git commit -m "feat: define effective policy decisions"
```

---

### Task 2：实现规则优先级和命令兼容适配

**文件：**

- Create: `src/vera/policy/rules.py`
- Create: `src/vera/policy/engine.py`
- Modify: `src/vera/tools/command_policy.py`
- Create: `tests/policy/test_matrix.py`
- Modify: `tests/tools/test_command_policy.py`

**接口：**

- Produces: `PolicyEngine(snapshot: EffectivePolicySnapshot)`
- Produces: `decide(action: PolicyAction) -> PolicyDecision`
- Preserves: `CommandPolicy.classify(VerificationCommand) -> CommandDecision`

- [ ] **Step 1：编写决策矩阵**

```python
@pytest.mark.parametrize(
    ("argv", "prefixes", "expected", "reason_code"),
    [
        (("sudo", "pytest"), (("sudo",),), "deny", "privilege_forbidden"),
        (("zsh", "-lc", "pytest"), (("zsh",),), "deny", "shell_forbidden"),
        (("rm", "-rf", "build"), (("rm",),), "deny", "deletion_forbidden"),
        (("pytest", "-q"), (("pytest",),), "allow", "user_prefix_allowed"),
        (("git", "diff", "--check"), (), "allow", "builtin_safe_command"),
        (("xcodebuild", "test"), (), "approval_required", "command_not_preapproved"),
    ],
)
def test_command_policy_precedence(argv, prefixes, expected, reason_code) -> None:
    engine = engine_with_prefixes(prefixes)
    decision = engine.decide(command_action(argv))
    assert decision.decision.value == expected
    assert decision.reason_code == reason_code
```

再覆盖 NUL、空 argv、绝对可执行路径按 basename 判断、Git destructive 子命令、项目规则只能 deny、用户短前缀不能误匹配其他可执行文件。

- [ ] **Step 2：运行矩阵并确认 Engine 不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/policy/test_matrix.py tests/tools/test_command_policy.py -v
```

- [ ] **Step 3：实现纯规则链**

每条规则返回 match 或 None；Engine 按固定优先级执行并为最终决定附同一个 policy_hash。CommandPolicy 构造函数改为接收 PolicyEngine，保留旧 `user_allowed_prefixes` 构造作为兼容入口并内部创建 Engine。现有 `CommandDecisionKind` 映射到新决定，保证任务 0004 行为不变。

- [ ] **Step 4：运行工具和策略回归**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/policy tests/tools -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/policy src/vera/tools tests/policy tests/tools
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [ ] **Step 5：提交规则引擎**

```bash
git add src/vera/policy src/vera/tools/command_policy.py \
  tests/policy tests/tools/test_command_policy.py \
  docs/tasks/0008-unified-policy-engine.md
git commit -m "feat: centralize command policy decisions"
```

---

### Task 3：统一路径、工具和写入判定

**文件：**

- Modify: `src/vera/tools/filesystem.py`
- Modify: `src/vera/tools/registry.py`
- Modify: `src/vera/workspace/paths.py`
- Modify: `src/vera/runtime/engine.py`
- Create: `tests/policy/test_workspace_actions.py`
- Modify: `tests/tools/test_filesystem.py`
- Modify: `tests/workspace/test_paths.py`

**接口：**

- Consumes: `PolicyActionKind.PATH_READ/PATH_WRITE/TOOL_EXECUTE/CHANGESET_APPLY`
- Guarantee: 执行层继续独立校验 WorkspacePaths

- [ ] **Step 1：编写不放宽安全边界测试**

```python
def test_user_rule_cannot_allow_sensitive_file(tmp_path: Path) -> None:
    engine = engine_with_user_allow(".env")
    decision = engine.decide(path_read_action(tmp_path, ".env"))
    assert decision.decision is PolicyDecisionKind.DENY
    assert decision.reason_code == "sensitive_path_forbidden"


def test_policy_allow_still_cannot_escape_workspace(tmp_path: Path) -> None:
    paths = WorkspacePaths(tmp_path, policy_engine=allowing_engine())
    with pytest.raises(WorkspaceBoundaryError):
        paths.resolve_read("../secret.txt")
```

覆盖绝对路径、符号链接逃逸、`.env`、私钥模式、未知工具、只读工具、propose_changeset 和删除操作。

- [ ] **Step 2：运行测试并确认现有组件未消费统一决定**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/policy/test_workspace_actions.py tests/tools/test_filesystem.py \
  tests/workspace/test_paths.py -v
```

- [ ] **Step 3：接入 Engine 并保留纵深复核**

ToolRegistry 执行前请求 TOOL_EXECUTE；文件工具请求 PATH_READ；ChangeSet 应用前请求 CHANGESET_APPLY。DENY 返回稳定 error_code，APPROVAL_REQUIRED 只能由 Runtime 转为审批，工具不能自行批准。

WorkspacePaths 继续规范化、resolve 和 symlink 检查，即使 Engine 返回 allow 也不能跳过。

- [ ] **Step 4：运行安全工具全回归**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/policy tests/tools tests/workspace tests/runtime -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests/policy tests/tools tests/workspace
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [ ] **Step 5：提交 Workspace 策略集成**

```bash
git add src/vera/tools src/vera/workspace/paths.py src/vera/runtime/engine.py \
  tests/policy/test_workspace_actions.py tests/tools tests/workspace/test_paths.py \
  docs/tasks/0008-unified-policy-engine.md
git commit -m "feat: enforce unified workspace policy"
```

---

### Task 4：把审批绑定 workspace_identity 与 policy_hash

**文件：**

- Modify: `src/vera/contracts/approvals.py`
- Modify: `src/vera/runtime/approval.py`
- Modify: `src/vera/runtime/engine.py`
- Modify: `src/vera/recovery/models.py`
- Create: `tests/runtime/test_policy_approval.py`

**接口：**

- Produces: `ApprovalRequest.workspace_identity: str | None = None`
- Produces: `ApprovalRequest.policy_hash: str | None = None`
- Produces: `approval.invalidated`

- [ ] **Step 1：编写策略漂移审批测试**

```python
def test_changed_policy_invalidates_pending_approval(runtime_factory) -> None:
    first = runtime_factory(prefixes=(("pytest",),))
    request = pending_changeset_approval(first)
    second = runtime_factory(prefixes=(("ruff",),))

    events = tuple(second.handle(resolve(request, "approve")))

    assert events[-1].type == "approval.invalidated"
    assert events[-1].payload["reason_code"] == "policy_changed"
    assert workspace_is_unchanged()
```

再覆盖工作区身份变化、目标 hash 错误、相同规范化策略继续有效、legacy ApprovalRequest 缺少新字段时恢复必须重新审批。

- [ ] **Step 2：运行测试并确认审批未绑定策略**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/runtime/test_policy_approval.py tests/runtime/test_approval.py -v
```

- [ ] **Step 3：实现兼容字段与 Resolve 前重判定**

新字段使用可空默认值以保持 schema v1 旧 JSON 可读；所有新审批必须填充非空值。ApprovalGate 继续验证 ID/target hash；Runtime 在 resolve 前通过当前 Engine 验证 workspace identity 和 policy hash。失效只发 approval.invalidated 并保持工作区不变，不转为普通模型失败。

- [ ] **Step 4：运行审批、恢复与契约回归**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/contracts tests/runtime tests/recovery -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests/runtime
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [ ] **Step 5：提交审批指纹**

```bash
git add src/vera/contracts/approvals.py src/vera/runtime \
  src/vera/recovery/models.py tests/runtime/test_policy_approval.py \
  docs/tasks/0008-unified-policy-engine.md
git commit -m "feat: bind approvals to effective policy"
```

---

### Task 5：恢复重判定、权限展示与完整验收

**文件：**

- Modify: `src/vera/recovery/coordinator.py`
- Modify: `src/vera/recovery/resume.py`
- Modify: `src/vera/bootstrap.py`
- Modify: `src/vera/session/models.py`
- Modify: `src/vera/session/permissions.py`
- Modify: `src/vera/cli_session_presenter.py`
- Modify: `tests/recovery/test_policy_resume.py`
- Modify: `tests/session/test_permissions.py`
- Create: `docs/evals/unified-policy-engine.md`
- Modify: `docs/STATUS.md`

- [ ] **Step 1：编写恢复重判定和展示测试**

```python
def test_resume_reclassifies_command_with_current_policy(recovery_fixture) -> None:
    recovery_fixture.persist_pending_command(policy_with_prefix(("pytest",)))
    runtime = recovery_fixture.runtime(policy_with_prefix(()))
    events = tuple(runtime.handle(ResumeRun(run_id="run_1")))

    assert events[-1].type == "approval.invalidated"
    assert not recovery_fixture.command_runner.calls
```

权限展示断言包含策略版本、policy hash 短前缀、硬性禁止摘要和真实用户前缀，不含 Key/Base URL。项目试图增加 allow 规则必须被配置加载拒绝。

- [ ] **Step 2：运行测试并确认恢复仍沿用旧决定**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/recovery/test_policy_resume.py tests/session/test_permissions.py -v
```

- [ ] **Step 3：装配唯一 Engine 实例**

Bootstrap 从有效配置和 installation/workspace identity 构造一个 Engine，同时注入 Runtime、ToolRegistry、RecoveryCoordinator 和 permissions snapshot。任何组件不得从配置副本另算权限。

- [ ] **Step 4：运行完整离线验收**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

覆盖率不低于 90%，现有安全测试全部保持。

- [ ] **Step 5：记录、提交和合并**

验收记录包含完整决策矩阵、策略哈希稳定性、路径纵深防御、审批失效、恢复重判定、权限展示和未运行 live。任务改 Complete，STATUS 指向 0009。

```bash
git add src/vera/recovery src/vera/bootstrap.py src/vera/session \
  src/vera/cli_session_presenter.py tests/recovery/test_policy_resume.py \
  tests/session/test_permissions.py docs/STATUS.md \
  docs/evals/unified-policy-engine.md docs/tasks/0008-unified-policy-engine.md
git commit -m "test: verify unified Vera policy"
git switch main
git merge --no-ff feature/unified-policy-engine \
  -m "merge: integrate unified policy engine"
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" -q
git branch -d feature/unified-policy-engine
```
