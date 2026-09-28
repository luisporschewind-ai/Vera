# 任务 0090：Core 受控 Git 仓库初始化验收计划

**状态：** Planned（仅规划；不得据此实施）  
**所属阶段：** 阶段八——Core 工具集、Policy v2 与原生 Git  
**上游规格：** [Core 受控 Git 仓库初始化](../specs/2026-09-27-core-owned-git-repository-initialization.md)（Accepted，2026-09-27 用户确认）  
**前置：** 所需沙盒/原生 Git 文档 Accepted，且用户单独授权实现与受控原型。

## 目标

以一个 Core-owned `git_repository_init` 契约，安全支持空项目目录和已有非仓库源码目录初始化本地 Git；初始化后无缝进入 Core-owned 的本地基础 Git 闭环（状态、Diff、历史/查看、分支和精确提交），并在真实 Intel macOS 受限后端中同时证明可用路径与不可越权路径。

## 当前边界

- 这是实施与验收分解，不是实现授权，也不改变 `0089-workspace-permission-sandbox` 的所有权或结论。
- 不修改产品代码、不做真实沙盒试验、不提交、合并或推送，直至用户接受规格并另行授权。
- `0089` 已用于独立沙盒工作树；本任务编号为后续连续 `0090`，不复用或覆盖 `0089`。
- 当前 SRT 对空工作区 `git init` 的 EPERM 仅说明后端缺口；已有假仓库的提交/分支验收不能替代本任务的初始化证据。

## 预期文件边界（实施时复核）

实现前先以 Accepted 规格和实际代码布局复核以下路径，避免在未合入的阶段八分支与 `main` 间误写：

- 新增：Core Git 初始化 Contract、`GitRepositoryInitializer`/受控适配器、Plan/Receipt/事件类型及对应测试；
- 修改：现有 GitService、ToolDefinition/Policy/Approval 入口、Runner/Sandbox capability adapter、CLI/TUI/JSON 投影、兼容清单与任务状态；
- 不修改：通用 `bash` 的任意 Git 放行规则、项目文件中的权限配置、用户 Git 配置、真实项目仓库、远程配置和 Hook；
- 验证产物：仅 `/private/tmp` 下的唯一临时目录或既有验证产物隔离机制，绝不写入用户项目或正式仓库。

## 分阶段实施与验收

### A. 接口与 Policy 闭环

**交付物：** 版本化 Request、Plan、Result、错误码与 Receipt；`git_repository_init` 只能绑定已选 workspace 根；`main` 默认分支、严格分支验证、已有仓库幂等发现和不安全/嵌套目标拒绝。

**自动化验收：**

- Contract codec round-trip、旧 Journal/事件兼容、公开投影不泄露目录清单/配置内容；
- 空目录与含普通文件目录分别形成 Plan；目标外、符号链接、祖先仓库、`.git` 文件/损坏目录、非法分支在启动前失败；
- 已验证仓库返回 `already_initialized`，不产生 Approval、子进程或写入；
- Plan 中 `target_identity`、目录摘要、Git executable、Policy/Grant 绑定任一变化均使批准失效；
- Policy 只允许精确 `git_repository_initialize` 走一次人工批准；通用 `bash`、自动审核和 project instruction 无法获取该 Grant。
- 成功 Result 明确列出可继续使用的 Core Git 工具；没有 Git 身份时只阻止 `git_commit` 并返回 `git_identity_missing`，不影响状态、Diff、历史与本地分支能力。

### B. 受控初始化适配器与后端能力

**交付物：** 无 Shell、固定 Git、隔离环境、经验证空模板的初始化适配器；后端只给该子进程一次性、精确的 `.git` 初始化写能力。

**自动化验收：**

- argv、cwd、环境、超时、取消及 stderr 上限；无法从输入注入 `GIT_*`、配置 include、模板、Hook、可执行文件或额外参数；
- 普通 Runner/项目命令不能复用或继承 init Grant，且对 `.git/config`、`.git/hooks` 和工作区外写入仍拒绝；
- 后端拒绝精确 Grant 时返回 `git_init_backend_unsupported` 或 `git_init_sandbox_denied`，不退回无沙盒；
- 退出非零、取消、验证失败及 Receipt 写入失败都保留现场，后续请求报告部分元数据而不删除/覆盖 `.git`。

### C. Core 结果、恢复与客户端一致性

**交付物：** 成功后的受控发现与 Result/Receipt；TUI、Plain、JSON 共用 Core 事实。

**自动化验收：**

- 成功结果验证 unborn `main`（及已验证自定义分支）、无 Commit/index/remote/身份/Hook、原业务文件目录摘要不变；
- 在同一已初始化工作区用 Core 契约执行 `git_status`、`git_diff`、空历史/查看、分支列举、分支创建和切换；具备受控 Git 身份、精确 Commit Plan 和独立批准时再执行一次精确提交，证明没有回退到通用 Shell 或继承 init Grant；
- 拒绝、过期、目录替换、Git 不可用、后端不支持、部分元数据和成功后重试映射至稳定错误码/幂等状态；
- 取消/崩溃恢复不自动再次运行初始化；公开日志和 Journal 脱敏；
- 三个客户端的批准预览、成功、`already_initialized`、失败原因一致，且不解析人类 Git 输出。

### D. 真实 Intel macOS 沙盒验收

**执行条件：** 用户单独批准在隔离临时目录做该矩阵；只使用虚构 Git 身份（原则上不需身份）、无 remote/网络、无真实项目、无系统配置改写。

| 场景 | 预期证据 |
| --- | --- |
| 新建空工作区，经批准初始化 | 仅生成预期 `.git`；HEAD 为 unborn `main`；无 Commit、remote、Hook、业务文件变化。 |
| 已有非仓库源码目录，经批准初始化 | 与上行相同，且创建前后业务文件哈希/目录摘要相同。 |
| 用户拒绝或 Grant 过期 | Git 子进程未启动，目标目录不变。 |
| 既有仓库再次请求 | `already_initialized`，无批准、无写入。 |
| 工作区外路径、嵌套仓库、链接逃逸、目录替换 | Core/OS 任一层阻止；目标外没有 `.git`。 |
| 尝试以普通项目命令写 `.git/config`、创建 `.git/hooks`、使用模板/环境注入 | 仍被拒绝；不把成功初始化误写成普遍 Git 元数据写权限。 |
| 后端不能建立精确 Grant | 明确失败、不启动无约束重试、不建议关闭沙盒。 |
| 初始化成功后的基础 Git 闭环 | `status/diff/log/show/branch` 均经 Core 成功；有受控身份时精确 commit 成功，且无关 index/路径未受影响。 |

验收同时保存脱敏的结构化 Result、Receipt、最小 OS-deny 证据、版本/架构、测试命令和退出状态。只运行单元测试、在宿主无沙盒运行 `git init`、或复制已有 `.git` 夹具，均不得勾选本节。

### E. 回归与人工门禁

- 运行受影响 Contract、Policy、Git、Sandbox、Recovery、CLI 三投影测试及项目规定的完整非 live 套件；记录实际通过、环境阻断与未运行项，不以历史分支结果代替。
- 运行 Ruff、format、Mypy、打包/安装 smoke（可运行时）和 `git diff --check`；检查最终 Diff 仅包含本任务文件。
- 在 Terminal.app 完成成功、拒绝/过期、已有仓库幂等三个可见流程；用户确认前保持 `Ready for manual acceptance` 或更早状态。
- Apple Silicon 没有真实设备前在结果中明确 `未验证`；不得从 Intel 或模拟器外推支持。

## 退出条件

只有在所有以下条件满足后，任务才可转为 `Ready for manual acceptance`：规格/关联决策已 Accepted、用户已授权实现、A–C 自动化门禁通过、D 在 Intel macOS 真实受限后端通过、E 的回归与证据已记录、无 Critical/High 安全或正确性缺口。最终状态仍需要用户人工确认；本任务不改变阶段八整体状态，也不授权 Phase 10/11 工作。

## 待决与风险

1. 目标沙盒后端能否表达一次性、物理目标绑定的 `.git` 创建 Grant；若不能，停在能力缺口而非降低边界。
2. 系统 Git 的最低支持版本与隔离配置/空模板兼容性，需在不读取或改变用户配置的条件下验证。
3. 失败留下的部分元数据只能保留现场；自动修复/删除需后续独立规格和审批。
4. 无 Git 身份的新用户如何经单独 Core-owned 能力完成首次提交；不得由 init 暗写 `.git/config`。
5. `main` 与未合入的阶段八/沙盒工作树可能有代码布局差异；实施前必须重新核对基线、所有权与任务编号。
