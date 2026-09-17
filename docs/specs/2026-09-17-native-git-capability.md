# Vera 原生 Git 能力

**状态：** Accepted
**日期：** 2026-09-17
**接受：** 2026-09-18 用户确认规格并授权继续编写实施计划
**所属阶段：** 阶段八——Core 工具集、Policy v2 与原生 Git（尚未开始）

## 目的

让 Vera 能以结构化、可审阅、可恢复的方式理解 Git 仓库并完成本地提交等基础版本控制工作，而不是让模型通过通用命令工具自由拼接 `git add/commit/push`。Git 能力由 Core 管理，CLI 与未来桌面客户端只消费同一套结构化事实。

## 当前能力与缺口

当前 Vera 只在会话状态中以固定只读命令探测当前分支与 dirty 状态，并在验证隔离中支持少量 `git status`、`git diff --check`。Checkpoint 是 Vera 私有文件快照，不是 Git Commit；Runtime 没有 Git 状态条目、Diff 范围、历史、提交计划、分支动作或远程动作契约。

直接开放通用 `git` 命令会产生以下风险：

- `git commit` 默认提交整个 index，可能夹带用户原有 staged 内容；
- 同一路径可能同时存在 staged 与 unstaged 修改；
- branch、HEAD、index 或工作树在审批后可能变化；
- Hook、签名、身份和编辑器可能执行额外进程或阻塞；
- Commit 成功后进程崩溃可能导致恢复时重复提交；
- merge/rebase/cherry-pick、detached HEAD、unborn branch、submodule 和 linked worktree 语义不同；
- fetch/pull/push 涉及网络、凭据、远程引用与外部副作用。

## 技术决策

第一版通过系统 Git CLI 实现，不引入 GitPython 或 libgit2：

- 复用用户机器上的 Git 配置、worktree 与仓库格式兼容性；
- 所有调用使用结构化 argv、`shell=False`、最小环境、超时与有界输出；
- 机器解析只使用 Git 稳定格式，例如 `status --porcelain=v2 -z --branch`；
- 不解析本地化人类输出，不依赖颜色、Pager 或交互编辑器；
- Git 写动作经过专用 GitService、PolicyEngine、ApprovalGate、Operation Receipt 与结构化 Event，不能由通用 `bash` 绕过。

## 第一版工具集

### `git_status`

返回 `GitRepositorySnapshot`：

```text
repository_root
workspace_prefix
head_oid
branch
detached
unborn
upstream
ahead
behind
operation_state
entries[]
```

每个条目区分 staged、unstaged、untracked、ignored、renamed、deleted、conflicted 和 submodule 状态。路径以仓库根为基准解析，但只向模型返回 workspace 内允许暴露的路径。

### `git_diff`

支持：

- `working`：index 到工作树；
- `staged`：HEAD 到 index；
- `head`：HEAD 到工作树；
- 明确 Commit/Range 的只读比较。

允许有界路径过滤、stat 或 patch 输出、上下文行数与输出上限。二进制内容只返回结构化摘要，不返回完整数据。

### `git_log`

有界读取 Commit 历史，返回 OID、父提交、作者/提交者显示信息、时间和标题。默认最多 20 条，最大值由 Core 限制；支持明确 ref 和 workspace 内路径过滤。

### `git_show`

查看一个明确 Commit 的结构化元数据、文件列表和有界 Diff。ref 必须经 Git 解析为 OID 后再绑定结果，不把任意格式字符串直接当命令参数组合。

### `git_branch_list`

列出本地分支、当前分支、upstream 与 ahead/behind 摘要。首版只读，不自动访问远程。

### `git_commit`

模型提供提交消息和候选范围；Core 必须先形成 `GitCommitPlan`。默认候选范围是当前 Run 由 Vera 成功应用并通过所需验证的路径，不能用空路径隐式表示“提交整个 index”。

用户原有修改只有在用户明确选择路径并审阅 Commit Plan 后才可纳入。首版不向模型暴露独立 `git_add`，暂存只是 GitService 的内部事务步骤。

## 后续本地工具

完成第一版 Commit dogfood 后，再在同一阶段评估：

- `git_branch_create`；
- `git_branch_switch`；
- `git_branch_delete`；
- `git_revert`。

`amend`、`rebase`、`reset`、`clean`、`stash` 与强制历史改写不属于第一版。

阶段八退出前必须实现并验证 `git_branch_create` 与 `git_branch_switch`；`git_branch_delete` 和 `git_revert` 保持后续同阶段增量，不阻塞第一版退出。

## GitCommitPlan

Commit Plan 至少包含：

```text
plan_id
run_id
changeset_or_action_ids
workspace_identity
repository_root
workspace_prefix
head_oid
branch
index_fingerprint
operation_state
paths
before_hashes
after_hashes
staged_diff_hash
commit_message_hash
verification_status
hook_policy
signing_policy
policy_hash
```

公开 Event 和 Journal 不记录完整文件内容、秘密、完整私有提交正文或凭据；提交标题可显示，完整 message 按既有私有数据规则处理。

## Commit 流程

```text
collect repository facts
  -> reject unsupported repository state
  -> select exact paths
  -> build bounded staged/working diff preview
  -> build GitCommitPlan and risk decision
  -> optional approval
  -> revalidate HEAD/index/paths/message/policy
  -> execute path-scoped commit transaction
  -> verify resulting commit tree and preserved index
  -> persist receipt and emit result
```

### 前置条件

- workspace 位于 Git 工作树内，repository root 与 workspace prefix 可确定；
- 当前分支不是 detached，除非未来规格显式支持；
- 不处于 merge、rebase、cherry-pick、revert、bisect 或未解决冲突状态；
- Git 用户身份已经由现有配置提供；Vera 不自动写入 `user.name` 或 `user.email`；
- HEAD、index 和目标路径与 Plan 绑定事实一致；
- 目标路径位于 workspace 且符合 Policy；
- 必需验证已完成且结果符合当前任务策略。

### index 隔离

第一版必须满足：

1. 不使用无 pathspec 的 `git add .`、`git add -A` 或 `git commit`；
2. Commit 只包含 Plan 中的路径；
3. 用户在其他路径上的 staged 内容在 Commit 前后保持不变；
4. 目标路径在 Run 开始前已有 staged 内容时，默认拒绝自动 Commit并要求用户重新选择；
5. 新文件、删除和重命名使用专门测试证明不会污染无关 index；
6. 路径通过 `--`、literal pathspec 或 NUL pathspec 输入，不能被解释为 Git 选项或 glob；
7. Commit 后以新 Commit tree、路径集合、blob hash 和剩余 staged Diff 反向验证实际结果。

系统 Git 的 pathspec Commit 可以忽略其他路径已 staged 的内容，但 Vera 仍必须用混合 staged/unstaged、新文件和特殊文件名矩阵验证目标平台行为；不能只依赖单一 happy path。

### 提交消息

- 消息有字节与行数上限，拒绝 NUL 和不允许的控制字符；
- 先经过秘密检测和脱敏检查，不能把 Token、私钥或 `.env` 值写入历史；
- 通过 Vera 私有 `0600` 临时文件或等价的有界 stdin 交给 Git，不经 Shell；
- Vera 不在未告知用户时添加营销尾注、共同作者或工具签名。

### 身份、Hooks 与签名

- 使用仓库、工作树或用户现有 Git 身份；缺失时返回 `git_identity_missing`；
- 检测 `core.hooksPath` 与相关 Commit Hooks；不静默使用 `--no-verify`；
- `untrusted` workspace 的 Hook 不执行；`trusted` workspace 第一次运行某组 Commit Hooks 时请求 workspace 级授权，授权绑定 Hook 路径、内容哈希、Git 配置事实与 Policy 主版本；任一事实变化后重新审批；
- Hook 产生额外工作区/index 变化时必须可见，并在超出 Plan 时使 Commit 失败或进入人工处理；
- 检测 GPG/SSH 签名配置；首版不能完成非交互签名时返回稳定错误，不修改用户配置，也不静默降级为未签名提交。

## Policy 与审批

| Git 动作 | `balanced` 默认 |
|---|---|
| status/diff/log/show/branch-list | 自动允许 |
| 用户明确要求、只含当前 Run 路径且验证通过的 Commit | 可信 workspace 自动允许 |
| 模型自行建议 Commit | 审批 |
| 纳入用户既有 staged/unstaged 修改 | 审批并展示精确路径/Diff |
| branch create | 用户明确要求且事实稳定时允许，否则审批 |
| branch switch/delete | 审批；活动 Run 或不安全工作树时拒绝 |
| fetch | 后续独立增量，按 remote/host 授权 |
| push | 后续独立增量，始终审批精确 remote/ref |
| force push、reset --hard、clean、宽泛历史改写 | 第一版拒绝 |

通用 `bash` 遇到 Git 写子命令时返回 `use_native_git_tool`，不能通过命令前缀授权绕过 GitCommitPlan。

## Event、Journal 与客户端事实

新增候选事件：

```text
git.snapshot
git.commit.proposed
git.commit.started
git.commit.completed
git.commit.failed
git.commit.stale
git.branch.changed
```

事件 Payload 使用结构化 OID、路径摘要、计数、Policy/Plan hash、结果和稳定错误码。TUI、Plain、JSON 与未来桌面端消费相同事实，不解析 Git stdout/stderr。

## 恢复与幂等

每个 Git 写动作持久化 Operation Receipt。Commit 恢复分类：

- HEAD 仍是 Plan 的旧 OID，且 index/路径事实未变：尚未提交，可安全重试；
- HEAD 是 Receipt 记录的预期新 OID，Commit tree 与 Plan 一致：补记完成，不重复提交；
- HEAD、index、branch 或目标路径出现其他变化：`manual_required`；
- 无法证明 Commit 是否成功：`manual_required`，绝不猜测重试。

Vera 不自动 `reset --hard` 或重写历史。Commit 后执行 Vera Rollback 可以把文件恢复成反向工作树 Diff，但不会删除 Commit；用户可审阅后另行 Commit。原生 `git_revert` 后续单独实现。

## 仓库边界

- 使用 Git 命令发现真实 repository root 和 git-dir，不假设 `.git` 必须是目录；
- 支持 workspace 是仓库子目录，所有模型可见和可写路径仍受 workspace 限制；
- linked worktree 使用 Git 提供的路径事实，不直接拼接共享 `.git` 内部路径；
- submodule、嵌套仓库、bare repository、sparse checkout 和 unborn branch 必须有明确分类；未支持状态失败关闭；
- 不读取其他 worktree 的文件，不把 repository root 自动扩张为 Vera workspace。

## 远程能力边界

`git_fetch`、`git_pull`、`git_push` 不进入第一版：

- remote URL 与 ref 必须来自仓库结构化事实，不能由模型提供任意 URL 绕过网络策略；
- fetch 会修改远程跟踪引用，pull 会改变工作树，push 会产生外部副作用；
- 凭据不得进入模型、Event、Journal 或命令输出；
- push 必须绑定 remote、local OID、remote ref、预期 remote OID 和 Policy hash；
- force push 默认拒绝，未来只有独立规格、精确 `--force-with-lease` 事实和显式用户授权后才可讨论。

## 错误码

至少冻结：

```text
git_not_repository
git_repository_outside_workspace
git_unsupported_state
git_detached_head
git_unborn_head
git_conflict_present
git_identity_missing
git_target_already_staged
git_plan_stale
git_index_changed
git_head_changed
git_hook_requires_approval
git_hook_changed_scope
git_signing_unavailable
git_commit_failed
git_commit_result_mismatch
git_manual_required
use_native_git_tool
```

错误正文不得依赖本地化 Git 输出；原始 stderr 只作为有界、脱敏诊断，不作为客户端状态判断依据。

## 非目标

- 构建完整 Git GUI；
- 自动解决 merge/rebase 冲突；
- 自动提交整个 index；
- 自动修改 Git 身份、签名、Hooks 或 remote；
- 第一版支持 pull/push/force、历史改写、stash 和多 worktree 编排；
- 使用 Git Commit 取代 Vera Checkpoint、Rollback 或 Recovery；
- 让客户端直接运行 Git 命令。

## 计划增量

本规格接受后再建立连续编号任务：

1. 冻结 Git contracts、状态解析、错误码和仓库 fixture；
2. 实现 repository discovery、`git_status/diff/log/show/branch-list`；
3. 实现只读 `GitCommitPlan`、精确路径与 Policy 决策，不产生 Commit；
4. 实现 path-scoped index 事务、Commit、结果反向验证和已有 staged 内容保全；
5. 接入 Hooks、签名、身份、Receipt、崩溃恢复与旧 Run 兼容；
6. 接入 ToolExecutor、四客户端展示与本地 Git dogfood；
7. 实现并验证 branch create/switch；
8. 远程 Git 另立规格与 ADR，不自动进入本阶段。

## 测试矩阵

至少覆盖：

- 非 Git、普通仓库、仓库子目录、linked worktree、detached HEAD、unborn branch；
- clean、仅 staged、仅 unstaged、同一路径 staged+unstaged、untracked、delete、rename、conflict；
- 用户无关 staged 内容在 Commit 前后保持；
- 新文件、空文件、可执行位、Unicode、空格、换行和前导 `-` 路径；
- branch/HEAD/index 在计划后变化；
- 缺失身份、Hook 成功/失败/越界修改、签名不可用；
- Commit 成功前崩溃、成功后 Receipt 前崩溃、恢复重复调用；
- 工作区子目录不能提交父目录变化；
- 通用 `bash` 不能绕过原生 Git Policy；
- Event/Journal/Plain/JSON/TUI 不泄漏秘密或依赖本地化 Git 文本。

## 验收标准

1. 只读 Git 工具返回稳定结构化事实，不受颜色、Pager、语言和普通用户配置影响。
2. Vera 能提交当前 Run 的精确已验证路径，不夹带用户其他 staged/unstaged 内容。
3. HEAD、index、branch、路径或 Policy 变化会使旧 Commit Plan 失效。
4. Commit 崩溃恢复不会重复提交；无法证明时进入 `manual_required`。
5. Git 身份、Hooks、签名和特殊仓库状态不会被静默绕过或修改。
6. `balanced` 下用户明确要求的普通本地 Commit 不产生重复审批，其他来源 Commit 有清楚边界。
7. 第一版无 fetch/pull/push、force、reset --hard、clean 或自动历史改写入口。
8. 临时仓库离线矩阵、完整产品门禁与至少两个真实 Git 工程 Terminal.app dogfood 通过。

## 已收束的第一版决策

1. 第一版不支持 unborn branch 的首个 Commit；先稳定已有 HEAD 的普通仓库，并返回 `git_unborn_head`。
2. trusted workspace 中检测到 Commit Hooks 时仍请求一次 workspace 级授权，且授权绑定 Hook 内容与配置事实。
3. 用户原有目标路径已 staged 时第一版拒绝自动 Commit，不提供“审批后混合提交”的旁路。
4. Commit 完成后可以在普通回答中建议下一步，但不得自动创建分支、访问远程或发起 push。
5. `git_branch_create` 与 `git_branch_switch` 进入阶段八退出条件；branch delete/revert 后置，远程操作另立规格。

## 关联

- [产品定义](../PRODUCT.md)
- [路线图](../ROADMAP.md)
- [Core 工具集与风险分级 Policy v2](2026-09-17-core-tooling-and-risk-tiered-policy.md)
- [Core 安全编辑垂直切片](2026-09-10-core-safe-editing-vertical-slice.md)
- [验证产物隔离与工作区无污染](2026-09-14-verification-artifact-isolation.md)
- [ADR-0003：私有状态与 Checkpoint](../decisions/ADR-0003-private-state-and-checkpoints.md)
- [ADR-0005：确定性 Run 恢复边界](../decisions/ADR-0005-deterministic-run-recovery.md)
- [ADR-0007：统一 PolicyEngine 与策略指纹](../decisions/ADR-0007-unified-policy-engine.md)
- [ADR-0014：Core 客户端兼容契约](../decisions/ADR-0014-core-client-compatibility-contract.md)
- [ADR-0021：桌面前插入 Core 工具集与 Git 能力阶段](../decisions/ADR-0021-core-tools-before-desktop.md)
