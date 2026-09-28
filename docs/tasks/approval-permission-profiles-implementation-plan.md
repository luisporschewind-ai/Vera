# 三档权限与自动审核实施计划

> **For agentic workers:** 实施时按本计划逐项执行；每项只有一个主实现 Agent。本文已获用户确认，但不构成代码、提交、合并或推送授权。

**状态：** Accepted；沙盒完成后复核技术路径，实施仍需单独授权
**接受：** 2026-09-25 用户审阅规格与实施计划后回复“确认”。
**Goal：** 在已验收的 Core/Runner OS 沙盒上提供“请求批准 / 帮我批准 / 完全访问”三档真实权限，并使低风险普通编辑连续执行、自动审核仅批准合格的精确越界动作。
**Architecture：** Core 将执行边界、风险策略和审核者组成不可由模型修改的会话权限快照。`ToolExecutor` 保持唯一动作准备与执行路径；确定性 Policy 先分类，审核路由只处理 `approval_required`，独立只读 Reviewer 给出精确一次结果；Full access 通过可信启动器为当前会话启动无 Vera 沙盒的 Core/Runner，不以 `approved=True` 伪装。
**Tech Stack：** Python 3.12、Pydantic 2、现有 PolicyEngine/ToolExecutor/ApprovalGate/Receipt/Recovery、完成后的跨平台沙盒后端、Typer/Textual、pytest/PTY、Ruff、Mypy。
**Spec：** [三档权限与自动审核机制](../specs/2026-09-25-approval-permission-profiles-and-auto-review.md)。同时受已接受的 Policy v2、ADR-0021 与合入后的 Core 沙盒规格约束；冲突条款必须先修订并接受。

## 进入实施的硬门禁

1. `2026-09-24-core-execution-sandbox.md` 及其 ADR、评测材料已从独立工作树合入正式基线；目标平台的**完整 Core + Runner** OS 隔离验收已通过，不能以 Runner 优先切片代替。macOS 以沙盒规格要求的 Intel 与 Apple Silicon 证据为准；未验收平台不展示可用的三档承诺。
2. 本规格已获用户接受；实施前还须正式修订 Policy v2 中“首版不提供 full-access”、沙盒规格中“无沙盒执行逐次审批”、原生 Git 规格中通用命令不得执行 Git 写操作及相关 ADR 的冲突。新旧状态与兼容清单须有明确版本。
3. 用户另行授权本计划的产品代码实施和 Git 边界。阶段八/九的既有实施授权不自动延伸到本任务；不得在 `main` 与沙盒工作树并发改同一代码。
4. 实施前在隔离工作树执行 `git status --short --branch`，重新读取当时的 `docs/STATUS.md`、沙盒接口和阶段八已合入的代码。若后端接口、任务编号或真实工具路径变化，先修订本计划并由用户复核，再开始产品代码。

## 文件职责图

以下为本增量拟增改的稳定职责；在门禁 4 复核时用沙盒任务已落地的模块名替换路径，不能仅凭本计划臆测后端能力。

| 文件 | 职责 |
|---|---|
| `src/vera/contracts/permission_profiles.py`（新增） | 三档预设与有效边界快照的版本化公共契约 |
| `src/vera/contracts/review.py`（新增） | 自动审核请求与结果的版本化公共契约 |
| `src/vera/session/permission_profiles.py`（新增） | 当前运行会话的内存态选择、默认恢复与切换门禁 |
| `src/vera/policy/approval_router.py`（新增） | 根据 Policy 结果和资格事实确定直接执行、自动审核、人工或拒绝 |
| `src/vera/runtime/auto_review.py`（新增） | 独立审核者接口、最小上下文、结果校验、超时与拒绝熔断 |
| `src/vera/policy/engine.py`、`src/vera/policy/permissions.py` | 既有风险判定；Full access 下区分权限拒绝与工具/事实错误 |
| `src/vera/tools/executor.py`、`src/vera/runtime/loop_flow.py`、`src/vera/runtime/approval_flow.py` | 动作级路由、执行前再核对、审批/审核事件和恢复 |
| `src/vera/session/actions.py`、`src/vera/session/controller.py`、`src/vera/session/permissions.py`、`src/vera/session/models.py` | 用户切换动作、状态查询和三客户端共用事实 |
| `src/vera/persistence/session_store.py`、`src/vera/recovery/models.py` | 证明 Full access 不落盘、旧审批可读、恢复降回默认 |
| 完成后的沙盒启动器与 Runner 接口 | 启停受限或无沙盒 Core/Runner，核对后代退出与真实隔离状态 |
| `src/vera/terminal/widgets/approval.py` 和权限控件 | 显示当前档位、真实边界、审核来源和切换说明；客户端不做安全判断 |

## 统一实施约束

- 普通工作区新建/更新先复用阶段八的 `FileMutationPlan`、Checkpoint、Diff、Receipt，不新增第二套文件执行器。
- Reviewer 不拥有副作用工具、不读取 Provider Key；`approve_once` 只针对一个哈希绑定动作，不建立 Run/workspace Grant。
- Full access 必须使完整 Core、Runner、命令后代处于无 Vera OS 沙盒状态；只关闭审批卡不是完成。
- Full access 只在当前运行会话的内存中；新会话、重启与恢复回到“请求批准”。模式切换仅在空闲且无待审批时进行，并验证旧进程树退出。
- 模型、仓库指令、Skill、工具输出不能选择档位；用户目标仍约束 Agent 行为。公共 Event/Journal 不含秘密、完整私有文件正文或 reviewer 的长上下文。
- 旧 `review / balanced / autonomous` 不映射到 Full access；旧 Run/Journal/Approval 可读取。TUI、Plain、JSON 只消费 Core 事实。

## Review Focus

1. 用户切到 Full access 后立即新建会话、重启或恢复旧对话：新实例必须回到默认；任务 1 与任务 4 的测试覆盖。
2. 待审批动作准备后文件、符号链接、网络目标或 Policy 发生变化：Reviewer 的旧决定无效；任务 2 与任务 3 的测试覆盖。
3. Reviewer 超时、输出不完整或明确拒绝：不得视为允许，也不得靠等价命令重试；任务 3 的测试覆盖。
4. Full access 切回受限模式时旧子进程仍在运行：切换失败并停用会话，不显示已受沙盒保护；任务 4 的真实进程测试覆盖。
5. 旧 `autonomous` 配置和旧恢复快照：仍按旧语义读取，不静默变为 Full access；任务 1 与任务 5 的兼容测试覆盖。

## 任务 0：规格冲突与实施基线收束

**交付：** 已接受的规格、ADR 与本计划在同一 Git 基线上无冲突；实施代码仍未开始。

**文件：** `docs/specs/2026-09-17-core-tooling-and-risk-tiered-policy.md`、`docs/specs/2026-09-17-native-git-capability.md`、合入后的 `docs/specs/2026-09-24-core-execution-sandbox.md`、`docs/decisions/ADR-0021-core-tools-before-desktop.md`、沙盒实施顺序 ADR、`docs/STATUS.md`。只读核对 `src/vera/contracts/compatibility.py`；契约代码修改归任务 1 和任务 5。

- [ ] 核对阶段八/九、沙盒分支的合入、验收和后端能力；保存 `git status --short --branch` 与沙盒正反例报告路径。
- [ ] 在 Policy v2 中明确三档是“执行边界 × 审批者”的用户入口，`balanced` 等既有风险倾向的迁移规则保持可读；删除“永不提供 full-access”的现行产品限制，并标注生效版本。
- [ ] 在沙盒规格中把“无沙盒执行按动作逐次批准”的未来设想修订为用户显式选定的会话级 Full access；继续要求完整 Core/Runner 事实和真实 OS 验证。
- [ ] 在原生 Git 规格中明确 Full access 对结构化 `bash` 的影响：本地/远程 Git 命令若由用户目标授权，可按通用命令执行并记录进程级 Receipt；原生 Git 工具的精确 Commit、index 保全和恢复承诺只覆盖原生工具，不冒称通用 `bash` 等效。
- [ ] 以新 ADR 记录预设与风险倾向分离、Full access 的会话生命周期及风险后果；更新 ADR-0021 的对应后果和 `docs/STATUS.md`。文档经用户接受后才进入任务 1。

## 任务 1：版本化权限快照与会话生命周期

**交付：** 三档预设契约及内存生命周期可独立验证；Full access 在任务 4 验证真实边界前不得对用户启用，且不能因会话保存或恢复而留存。

**文件：** 新增 `src/vera/contracts/permission_profiles.py`、`src/vera/session/permission_profiles.py`；修改 `src/vera/session/actions.py`、`src/vera/session/controller.py`、`src/vera/persistence/session_store.py`、`src/vera/recovery/models.py`、兼容清单；新增 `tests/contracts/test_permission_profiles.py`、`tests/session/test_permission_profile_lifecycle.py`、`tests/recovery/test_permission_profile_resume.py`。

**接口草案：**

```python
class PermissionPreset(StrEnum):
    ASK_FOR_APPROVAL = "ask_for_approval"
    APPROVE_FOR_ME = "approve_for_me"
    FULL_ACCESS = "full_access"

class PermissionSession:
    def select(self, preset: PermissionPreset, *, idle: bool, pending: bool) -> None: ...
    def snapshot_for_run(self, run_id: str) -> PermissionProfileSnapshot: ...
    @classmethod
    def new_or_resumed(cls, session_id: str) -> PermissionSession: ...
```

- [ ] 先写失败测试：新建/恢复默认 `ask_for_approval`；仅在 Fake 边界控制器证明确认切换时，Full access 才能在同会话下一 Run 保持；无控制器、活动 Run 或待审批时拒绝切换；新会话、重启恢复旧对话均复位；模型/Skill/项目文件不能构造 `select`。
- [ ] 运行 `UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/contracts/test_permission_profiles.py tests/session/test_permission_profile_lifecycle.py tests/recovery/test_permission_profile_resume.py -q`，确认新行为测试先失败。
- [ ] 实现 `SelectPermissionPreset` 会话动作、内存态 `PermissionSession` 与版本化只读快照；未接入经验证的边界控制器时，Full access 选择返回 `permission_mode_unavailable`。持久化只记录非授权性的“曾显示何档”审计事实，不序列化可恢复的 Full access 授权。
- [ ] 在旧 Codec 兼容测试中固定：`review / balanced / autonomous` 仍按原风险倾向读取，迁移后的用户入口为有沙盒的请求批准；未知新版本拒绝执行而可只读检查。
- [ ] 重跑聚焦测试、`mypy` 和契约兼容测试，检查公开 Event 不包含可重放的 Full access 令牌。

## 任务 2：确定性动作分类和自动审核资格门

**交付：** 普通可信编辑直接执行；越界申请分流为自动审核资格、人工或拒绝，且理由可解释。

**文件：** 新增 `src/vera/policy/approval_router.py`；修改 `src/vera/policy/engine.py`、`src/vera/policy/permissions.py`、`src/vera/tools/executor.py`；新增 `tests/policy/test_approval_routing.py`、`tests/tools/test_permission_profile_actions.py`。

**接口草案：**

```python
class ApprovalRoute(StrEnum):
    EXECUTE = "execute"
    AUTO_REVIEW = "auto_review"
    HUMAN = "human"
    DENY = "deny"

@dataclass(frozen=True)
class SandboxReviewFacts:
    exact_grant_enforceable: bool
    core_isolated: bool
    runner_isolated: bool

def route_action(
    prepared: PreparedToolAction,
    profile: PermissionProfileSnapshot,
    sandbox_facts: SandboxReviewFacts,
) -> ApprovalRoute: ...
```

- [ ] 写参数化失败矩阵：普通可信 `write/edit` 在前两档直接执行；受保护路径、删除、脚本、远程发布、秘密、越权与事实缺失分别路由；同一个 `ToolAction` 的效果和目标变化必须改变绑定哈希。
- [ ] 运行 `UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/policy/test_approval_routing.py tests/tools/test_permission_profile_actions.py -q`，确认新增断言失败。
- [ ] 实现纯函数资格门，先尊重 `PolicyDecisionKind.DENY`，再对 `APPROVAL_REQUIRED` 检查风险 `low/moderate`、用户目标、可恢复性、秘密/外部目的地和后端可强制 Grant；资格不满足进入人工或拒绝。Full access 只有在任务 4 的边界状态证明确认为 `disabled_by_user` 后才能返回 `EXECUTE`。
- [ ] 为明确公开文档读取与已规划临时产物根编写正例；对混入私有正文的网络请求、路径替换、Policy 变化编写负例。执行前通过既有 ToolExecutor 再核对事实。
- [ ] 重跑聚焦矩阵和阶段八已有 `tests/policy`、`tests/tools`，确认普通编辑仍留下 Checkpoint、Diff 与 Receipt。

## 任务 3：独立自动审核者与审批生命周期

**交付：** “帮我批准”能对合格精确申请给出一次性审核结果，失败转人工，拒绝不可绕过。

**文件：** 新增 `src/vera/runtime/auto_review.py`、`src/vera/contracts/review.py`；修改 `src/vera/runtime/loop_flow.py`、`src/vera/runtime/approval_flow.py`、`src/vera/runtime/approval.py`、`src/vera/recovery/models.py`；新增 `tests/runtime/test_auto_review.py`、`tests/runtime/test_auto_review_recovery.py`、`tests/contracts/test_review_codec.py`。

**接口草案：**

```python
class ReviewVerdict(StrEnum):
    APPROVE_ONCE = "approve_once"
    DENY = "deny"
    NEEDS_USER = "needs_user"

class AutoReviewer(Protocol):
    def review(self, request: ReviewRequest) -> ReviewDecision: ...
```

- [ ] 用 Fake Reviewer 写失败测试：批准只覆盖同一 `session_id/run_id/action_id/input_hash/target_facts_hash/policy_hash/grant_hash`；任一事实变化后必须重新申请；Reviewer 不能生成 workspace Grant 或使用副作用工具。
- [ ] 写拒绝、格式错误、超时、服务不可用和重复等价申请的失败测试；明确拒绝不得由主 Agent 改换包装器重试，超时/不可用转人工。
- [ ] 运行 `UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/runtime/test_auto_review.py tests/runtime/test_auto_review_recovery.py tests/contracts/test_review_codec.py -q`，确认 Red。
- [ ] 实现脱敏 `ReviewRequest`、独立 `AutoReviewer` 接口和受控调用；返回 `ReviewDecision` 时校验精确绑定，交给原有 ApprovalGate/沙盒 Broker 的一次性路径执行，记录来源 `auto_reviewer` 而非 `user`。
- [ ] 实现会话内拒绝熔断和重启恢复：未决审核不自动重放；已批准但未证明副作用的动作按原 Receipt/Recovery 进入人工处理。
- [ ] 重跑聚焦、恢复和提示词投毒测试；检查公共 Event/Journal 只含脱敏摘要、审核者没有隐藏的工具执行能力。

## 任务 4：真实 Full access 启停与无审批执行

**交付：** 用户选定后仅当前会话的完整 Core/Runner/后代无 Vera 沙盒、无 Vera 审批；退出或恢复回默认。

**文件：** 任务 1 的 `src/vera/session/permission_profiles.py`、`src/vera/policy/approval_router.py`、`src/vera/tools/executor.py`、`src/vera/session/controller.py`；接入已完成的沙盒启动器、Runner 和 Broker；新增 `tests/integration/test_full_access_boundary.py`、`tests/integration/test_permission_switch_process_tree.py`、`tests/recovery/test_full_access_reset.py`。

**接口草案：**

```python
class BoundaryStatus(BaseModel):
    core_isolation: Literal["active", "disabled_by_user"]
    runner_isolation: Literal["active", "disabled_by_user"]
    descendants_stopped: bool

class ExecutionBoundaryController(Protocol):
    def transition(self, session_id: str, preset: PermissionPreset) -> BoundaryStatus: ...
    def stop_descendants(self, session_id: str) -> bool: ...
```

- [ ] 写失败测试：Full access 下使用假工程与假敏感文件证明工作区外读写、受控本地网络与普通命令不触发 Vera 审批；同样动作在前两档仍受真实 OS 边界限制。
- [ ] 写切换负例：活动 Run/待审批拒绝切换；旧子进程不退出、新进程未按目标边界启动、后端状态不可证明时停用会话；新会话和崩溃恢复重置到请求批准。
- [ ] 运行上述聚焦测试，确认在受限沙盒实现中 Red；使用假数据和本地受控端点，不使用真实凭据或远程发布。
- [ ] 接入可信启动器：先停止旧 Core/Runner/后代，再按 `full_access` 启动未施加 Vera 沙盒的新进程；切回时重建受限进程。实际 `BoundaryStatus` 由后端返回，Core 不得自行宣称成功。
- [ ] 将 Full access 的权限分类从 `ToolExecutor` 的审批/拒绝分支中显式隔离；继续执行输入校验、用户目标检查、事实重验、Checkpoint、Receipt、Diff、取消和恢复。针对 `bash` 的权限性工作区/网络/Git 拒绝作真实 argv 负例，避免“Full access”只有名义权限。
- [ ] 在 macOS Intel 与 Apple Silicon 的沙盒共同矩阵上加入无沙盒正例和切回受限负例；未验证架构不得标为支持。

## 任务 5：CLI/结构化客户端与验收

**交付：** 用户看得懂当前真实边界、自动审核来源和切换结果；全量自动门禁与人工 dogfood 记录齐全。

**文件：** 修改 `src/vera/session/permissions.py`、`src/vera/session/models.py`、`src/vera/session/command_catalog.py`、`src/vera/presentation/projector.py`、`src/vera/terminal/widgets/approval.py`、`src/vera/contracts/compatibility.py`；新增 `tests/session/test_permission_profiles_ui.py`、`tests/pty/test_permission_profiles.py`、`docs/evals/approval-permission-profiles-acceptance.md`。

- [ ] 写失败测试：`/permissions` 可选择三档并显示真实 Core/Runner 沙盒状态、审核者可用性、会话范围；Full access 有明确边界说明；TUI/Plain/JSON 对同一快照一致；自动审核批准不能显示为用户批准。
- [ ] 运行 `UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/session/test_permission_profiles_ui.py tests/pty/test_permission_profiles.py -q`，确认 Red。
- [ ] 接入 Core 会话动作和状态投影；60×16 终端中仍能查看当前档位、越界目标与拒绝理由。新增字段按兼容清单标注 additive/deprecated/breaking，旧客户端不能把未知模式当成 Full access。
- [ ] 跑聚焦测试、三客户端契约、恢复/安全负例、OS 沙盒正反例、Python/Node/Swift 真实工程 Terminal.app dogfood。记录 `Verified / Failed / Blocked / Not run`，区分模拟 Policy 结果与 OS 证据。
- [ ] 在隔离构建目录运行完整非 live `pytest`、`ruff check`、`ruff format --check`、`mypy src`、wheel/安装态 smoke、`git diff --check`；检查最终 diff 与 `docs/STATUS.md`，经用户人工确认后才把任务标为完成。

## 建议的独立审阅与提交边界

任务 0 是文档门禁；任务 1–5 各自形成可独立审阅的增量。实施授权若包含本地提交，可按“契约与会话 → 路由资格 → 自动审核 → Full access 边界 → 客户端与验收”分批提交；不含授权时保持工作树改动供用户审阅。任何阶段的绿测都不自动授权合并、推送、发布或启用真实 Full access。
