# Core 受控 Git 仓库初始化

**状态：** Accepted  
**日期：** 2026-09-27  
**接受：** 2026-09-27 用户确认方案  
**所属阶段：** 阶段八——Core 工具集、Policy v2 与原生 Git  
**关联：** [Vera 原生 Git 能力](2026-09-17-native-git-capability.md)、`2026-09-24-core-execution-sandbox.md`（独立工作树中的 Accepted 规格）、[任务 0090](../tasks/0090-core-owned-git-repository-initialization.md)

## 目标

让用户在 Vera 已选择的本地工作区中，经过一次可理解、可拒绝、精确绑定的批准后，初始化一个新的本地 Git 仓库。能力由 Core 提供结构化契约，CLI 与未来桌面客户端只展示并调用该契约；模型、项目脚本和通用 `bash` 都不能自行拼接或绕过它。

这项能力服务于两类同等常见的通用软件项目：

1. Vera 或用户刚创建的、尚为空的项目目录；
2. 已有源码、但尚未被 Git 管理的目录。

它不因当前 macOS 沙盒后端对 `.git/config`、`.git/hooks` 和其祖先创建的限制而从产品目标中删除。当前限制是待解决的后端能力缺口，不是“用户必须先在终端手工 `git init`”的产品结论。

初始化也不是孤立按钮。成功结果必须使该工作区进入既有 Core 原生 Git 的本地基础闭环：`git_status`、`git_diff`、`git_log`、`git_show`、`git_branch_list`、精确范围 `git_commit`、`git_branch_create` 和 `git_branch_switch` 都继续通过同一 Core 契约、Policy、Approval、Receipt 与沙盒边界工作。客户端不得要求用户另开终端或用通用 Shell 把一个“刚初始化”的项目变成可管理仓库。

## 范围与非目标

本增量只初始化本地、非 bare 仓库；初始化不会创建 Commit、暂存文件、创建远程、联网、设置身份、安装软件、执行项目脚本、执行 Hook、签名，或修改工作区中已有的业务文件。

以下均不属于本规格：

- `clone`、`fetch`、`pull`、`push`、远程和凭据；
- `git init --bare`、submodule、linked worktree、嵌套仓库、迁移已有仓库；
- 导入用户的 Git 模板、Hook、全局/系统配置、配置 include、attributes、fsmonitor 或自定义扩展；
- 自动设置 `user.name`、`user.email`、默认 remote、提交签名或初始 Commit；
- 删除或修复不完整的 `.git`；这需要以后单独、可恢复的恢复能力；
- 用复制已有 `.git` 元数据作为产品实现或验收替代。

初始化后首次 `git_commit` 仍要求 Git 身份已由受控来源提供。若用户没有现有可用身份，Core 必须以 `git_identity_missing` 明确说明前置条件；不得静默把账户资料写入 `.git/config`。是否新增一个同样需要精确批准、只写 `user.name`/`user.email` 的 Core-owned 身份设置能力，列为本规格的待决增量，必须单独定义和验收，不能由 init Grant 顺带获得。

## Core 公共契约

Core 新增版本化的 `git_repository_init` 工具。客户端传入用户已选择的 `workspace_identity`，不能传任意绝对路径，也不能要求工具在工作区外创建目录。

```text
GitRepositoryInitRequest
  schema_version: 1
  workspace_identity: string
  initial_branch: string | null       # null 时为 "main"

GitRepositoryInitPlan
  plan_id: string
  action_id: string
  workspace_identity: string
  repository_root: absolute physical path
  target_identity: device + inode + canonical path
  initial_branch: string
  target_kind: "empty_directory" | "existing_non_repository_directory"
  target_listing_hash: string          # 仅目录条目名、类型与必要元数据的有界哈希
  git_executable_identity: path + file identity + digest
  environment_profile_hash: string
  policy_hash: string
  sandbox_grant_hash: string
  expected_effects: ["workspace_write", "process_execute"]

GitRepositoryInitResult
  status: "initialized" | "already_initialized" | "rejected" | "failed"
  repository_snapshot: GitRepositorySnapshot | null
  available_followup_tools: tuple[GitToolName, ...]
  reason_code: string | null
  receipt_id: string | null
```

`initial_branch` 的默认值固定为 `main`。非空值必须是 Core 用 Git refname 规则验证过的本地分支名；NUL、控制字符、`..`、`@{`、空段、以 `.` 开头或结尾、以 `.lock` 结尾及会被解释为选项的值均在形成 Plan 前拒绝。Core 把已验证的值作为单独 argv 传递，永不经 Shell、配置文件或环境变量拼接。

创建计划时，Core 以打开目录的真实对象建立 `target_identity`，逐段拒绝符号链接、非目录、权限不可确认的祖先和目录替换。批准前与启动子进程前都重新比较设备号、inode、canonical path、目录项摘要、工作区 identity、Git 可执行文件 identity、Policy 与沙盒 Grant；任一不一致即失效并要求重新准备，绝不沿用旧批准。

公开 Event、Journal 和 Receipt 只能记录上述有界事实、分支名、结果状态及脱敏错误码；不得记录用户 Git 配置、完整目录清单、密钥、提交正文或任意 `.git/config` 内容。

## 目标资格与幂等语义

计划只可把已选工作区根目录本身作为 `repository_root`。该目录必须存在、可安全解析且位于当前 Workspace Grant 内；Vera 不会为了初始化而新建父目录或把工作区根切换到别处。

| 发现状态 | 行为 |
| --- | --- |
| 工作区根是普通空目录 | 可创建 Plan，`target_kind=empty_directory`。 |
| 工作区根有普通项目文件、但自身及祖先均非 Git worktree | 可创建 Plan，`target_kind=existing_non_repository_directory`；业务文件保持不变。 |
| 工作区根已是可验证 Git worktree | 返回 `already_initialized` 与只读仓库快照；不启动 Git、不要新的批准、不要改写配置。 |
| 工作区根是另一个仓库的子目录，或其祖先是 Git worktree | 拒绝 `git_init_nested_repository`。 |
| 根目录含 `.git` 文件、损坏的 `.git` 目录、未能安全验证的 gitdir 指针，或发现符号链接/替换 | 拒绝 `git_init_target_unsafe`；不自动删除、重命名或修复产物。 |
| 目录在准备后已变为仓库 | 执行前返回 `already_initialized`（仅当身份和仓库可验证），否则使 Plan 失效。 |

`already_initialized` 是幂等的发现结果，而不是成功重跑初始化。一次进程崩溃后若留下完整、可验证的仓库，重试同样返回该结果；若只留下不完整元数据，保持失败现场并报告 `git_init_partial_metadata`，不得以删除 `.git` 或覆盖配置来“自动恢复”。

## Policy、审批与可信执行边界

`git_repository_init` 是结构化 `ToolAction`，其 effect 为 `workspace_write + process_execute`。在受限权限档，默认风险分类为需要用户明确批准的 `git_repository_initialize`；不进入普通文件编辑的自动允许，也不交给自动审核者。批准页至少显示：物理目标、目录类型、初始分支、将创建的唯一 Git 元数据根 `.git`、不创建 Commit/远程/身份/Hook 的承诺、拒绝与失败后不清理部分产物的结果。

一次性 Grant 必须绑定 `session_id + run_id + action_id + plan_id + target_identity + target_listing_hash + initial_branch + git_executable_identity + environment_profile_hash + policy_hash + sandbox_grant_hash`，并有短时有效期。批准、拒绝、过期、取消、后端不可用或任何重验证失败都不得启动子进程。未来 Full access 档仍使用相同输入验证、结构化工具、Receipt、路径安全与恢复语义；它不能把项目指令变成授权，也不能使通用 `bash` 获得本工具的特权。

执行必须经由可信的、仅服务此 ToolAction 的初始化适配器：固定 `git` 可执行文件、固定 cwd、结构化 argv、最小环境、无 Shell、超时、取消和有界 stderr。项目命令、模型输出和仓库文件不能选择可执行文件、追加 argv、设置环境变量或替换模板。适配器必须显式隔离全局/系统配置、配置 include、环境中的 `GIT_*` 注入和用户模板；使用由 Core 创建并验证为空的临时模板源，且只写 Git 所需的仓库元数据。它不得导入或执行任何 Hook，亦不得写 `user.name`、`user.email`、remote、签名或其他用户配置。

沙盒后端必须向这一**单次、精确、已验证目标**授予创建 `target/.git` 及其初始化必需子项的能力，并同时继续拒绝：其他工作区、目标外路径、用户配置位置、任意 `.git/config`/`.git/hooks` 写入、任意 Hook 执行和后续项目命令对 Git 元数据的自由写入。不能以关闭 Vera 沙盒、将 `.git/config` 或 `.git/hooks` 加进全局白名单、扩大祖先目录可写范围，或让通用 Shell 继承该能力达成支持。

这里规定安全契约和验收结果，不预先指定后端通过复制模板、放宽 SRT 规则、替换 Git 实现或其他技巧实现。实施前须用最小原型证明所选 macOS 后端能提供上述一次性精确 Grant；若不能，报告 `git_init_backend_unsupported`，不伪造成功也不降级为宿主无约束执行。

## 执行、验证与失败

批准后执行顺序固定如下：

```text
安全发现与 Plan -> 用户批准 -> 身份/Policy/Grant 重验证
-> 受控初始化适配器 -> 受控仓库发现 -> Receipt/事件
```

适配器只可运行等价于 `git init --quiet --initial-branch <validated-branch> --template <verified-empty-template> -- <validated-target>` 的结构化调用；具体 Git 版本兼容参数必须保持等价的无模板导入、无交互和无配置注入语义。不得以通用 `git init` 文字命令作为客户端或模型 API。

成功后 Core 必须在同一物理目录重新发现并确认：非 bare worktree、仓库根恰为目标、HEAD 指向所选初始分支的 unborn 状态、没有 Commit、没有 index 中的条目、工作区业务文件的条目摘要与 Plan 时一致、没有 remote、没有用户身份写入、没有从模板导入的 Hook。验证失败、退出非零、超时、取消或 Receipt 写入失败都返回结构化失败，保留已经存在的 `.git` 供用户检查；后续请求按“部分元数据”规则拒绝。

验证成功后，Core 在同一结果中以能力事实列出可立即使用的只读工具和本地分支工具。`git_commit` 仅在当前仓库状态、精确 Commit Plan、用户批准和身份前置条件均满足时列为可执行；没有身份时仍可读取、查看 Diff 和管理本地分支，且客户端应显示“提交需要设置 Git 身份”，而非把失败伪装成初始化失败。

最低错误分类为：`git_init_approval_required`、`git_init_plan_stale`、`git_init_target_outside_workspace`、`git_init_target_unsafe`、`git_init_nested_repository`、`git_init_invalid_branch`、`git_init_git_unavailable`、`git_init_backend_unsupported`、`git_init_sandbox_denied`、`git_init_process_failed`、`git_init_verification_failed`、`git_init_partial_metadata`。错误信息可说明下一步，但不得建议用户用 `sudo`、关闭安全限制、安装工具、全局改写 Git 配置或手工删除 `.git` 来绕过失败。

## 最小可执行路线比较

| 路线 | 结论 | 原因 |
| --- | --- | --- |
| 受控初始化适配器 + 后端提供的一次性精确 `.git` 创建 Grant | 首选，进入实现前原型验证 | 保持系统 Git 兼容与 Core-owned 契约，同时把元数据写权限制为一个已批准动作。 |
| 在普通 SRT profile 中放开 `.git/config`、`.git/hooks` 或其祖先 | 拒绝 | 会让后续项目命令或未知路径共享敏感写权，违背最小授权。 |
| 对初始化命令或整个会话关闭沙盒 | 拒绝 | 把后端局限转化为无边界宿主权限，不能证明产品安全边界。 |
| 复制预置 `.git` 或现有仓库元数据 | 不作为路线 | 可用于受控测试夹具准备，但不能证明用户项目初始化，也会带入配置/Hook/身份风险。 |
| 由通用 `bash` 拼接 `git init` | 拒绝 | 失去 argv、路径、审批绑定、环境和恢复控制。 |
| Core 直接手写 Git 元数据 | 仅在独立规格修订后再评估 | 会偏离既有系统 Git CLI 决策并增加格式兼容、原子性与安全维护面。 |

## 验收门禁

1. 本规格、相关沙盒规格及若需调整的既有原生 Git 规格/ADR 均已 Accepted，且用户另行授权实现；Draft 不授权代码变更或敏感实验。
2. Intel macOS 的真实受限后端中，空目录和含普通源码的非仓库目录各完成一次经批准的初始化；两者均仅产生预期 `.git`，没有 Commit、remote、身份、Hook 或业务文件变化。
3. 同一真实后端中，工作区外写入、目标外写入、`.git/config` 与 `.git/hooks` 的非本 ToolAction 写入、链接逃逸、目录替换、模板/环境配置注入均被拒绝；不能只以单元测试或宿主无沙盒结果替代。
4. 已有仓库、父仓库子目录、损坏/部分 `.git`、批准后目标替换、分支非法、拒绝/过期/取消、Git 或后端不可用分别得到上文定义的无副作用结果；已存在仓库的幂等发现不产生新批准或新写入。
5. 初始化成功后的同一 workspace 立即通过 Core 调用 `git_status`、`git_diff`、空历史 `git_log`/`git_show`、`git_branch_list`、创建/切换本地分支；在具备受控身份与精确 Commit Plan 时完成一次精确 `git_commit`。这些操作不得退回通用 Shell，也不得借 init Grant 扩大 `.git` 写权限。
6. TUI、Plain、JSON 对同一 Core Plan、批准状态、结果、后续工具可用性和错误码一致；客户端不解析 Git 人类输出，也不自行计算路径/风险。
7. 自动化测试、结构化 Event/Receipt/Journaling、恢复与完整回归通过；最终 `git diff --check` 通过。真实 Terminal.app 验收至少展示一次批准预览、一次成功、一次后续基本 Git 操作和一次拒绝/失败。
8. 首轮发布声明只覆盖已验收的 Intel macOS。Apple Silicon 因无设备暂记为未验证，不得宣称支持；后续取得独立真实设备证据后才可补充。

## 待决事项

1. 目标后端是否能以文件对象/物理身份为基础，向单个受控子进程提供上述精确 `.git` 创建 Grant；这需要批准后的最小、无敏感项目数据原型验证。
2. 支持的 Git 最低版本及该版本对空模板、初始分支和隔离配置的兼容矩阵；不能以当前机器版本替代产品承诺。
3. 初始化后发现 `.git` 部分产物时，未来恢复功能的用户体验与可恢复操作；本规格明确当前只能停止并保留现场。
4. 用户没有可用 Git 身份时，独立 `git_identity_configure` 增量的安全契约、存储位置和审批体验；该增量不随本规格暗中实施。

## 需要另行用户批准的动作

- 接受本 Draft 并授权实现；
- 在隔离临时目录执行真实 macOS 沙盒后端的初始化/拒绝矩阵原型；
- 改变既有 Accepted 沙盒或原生 Git 规格、ADR，或引入/更新沙盒后端；
- 对任何真实用户项目、真实仓库、真实 Git 配置、身份、Hook、远程或网络进行操作。
