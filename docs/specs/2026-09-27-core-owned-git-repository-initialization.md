# Core 受控 Git 仓库初始化

**状态：** Accepted（2026-09-27）
**所属阶段：** 阶段八——Core 工具集、Policy v2 与原生 Git
**实施任务：** [任务 0090](../tasks/0090-core-owned-git-repository-initialization.md)

## 目标与范围

Core 提供结构化 `git_repository_init` 能力，在当前已选 Workspace 根目录初始化本地 Git，并在成功后继续使用现有 Core Git 工具：`git_status`、`git_diff`、`git_log`、`git_show`、`git_branch_list`、`git_branch_create`、`git_branch_switch` 与满足身份/精确计划/独立批准条件的 `git_commit`。覆盖空目录和已有普通源码的非仓库目录。默认分支为 `main`。

客户端只消费 Core 的 Plan、审批、Result、能力列表与稳定错误码，不解析 Git 人类输出，不通过 `bash` 执行初始化。

## 安全边界

- 只允许当前 Workspace 根本身；拒绝符号链接/目录替换、损坏 `.git`、工作区位于另一仓库内及不能安全验证的目标。
- Plan 绑定 run/action/workspace identity、目标设备号/inode/canonical path、目录项摘要、初始分支、Git 可执行文件身份和摘要、隔离环境摘要、Policy 与一次性沙盒 Grant。审批及执行前都重验证；变化即失效。
- 初始化是 `workspace_write + process_execute` 高风险动作，始终要求用户明确批准。拒绝、过期、取消、后端不可用或重验证失败不得启动初始化进程。
- 执行只允许固定 Git、固定 cwd、结构化 argv、Core 创建并确认为空的模板、最小环境和有界执行。禁止 Shell、配置注入、用户模板/Hook、remote、身份、签名或用户 Git 配置写入。
- OS 后端只为该次初始化提供精确 `.git` 创建 Grant。不得全局放开 `.git/config`/`.git/hooks`、扩大祖先目录写权限、关闭沙盒或让通用命令继承 Grant。没有可证明的精确 Grant 时 fail closed，返回 `git_init_backend_unsupported` 或 `git_init_sandbox_denied`。
- 初始化后验证仓库根、非 bare、目标 unborn 分支、无 Commit、空 index、无 remote、无导入 Hook、业务目录项未变。失败、Receipt 写入失败或部分元数据均保留现场，不自动删除/修复。
- 输出和持久化只记录有界结构化事实、分支和脱敏错误码；不记录完整目录清单、配置内容、身份、密钥或提交正文。

## 目标发现与幂等

| 目标 | 行为 |
| --- | --- |
| 空的安全目录 | 可建立 Plan，初始分支默认为 `main`。 |
| 含普通文件且自身/祖先均非仓库 | 可建立 Plan，业务文件保持不变。 |
| 已验证仓库根 | 返回 `already_initialized` 与只读快照；不再审批、不写入。 |
| 另一个仓库内的子目录 | 返回 `git_init_nested_repository`。 |
| 损坏/不安全 `.git`、链接或无法验证的替换 | 拒绝并保留现场，不自动修复。 |
| 执行后留下部分 `.git` | 返回 `git_init_partial_metadata`；后续重试不覆盖/删除。 |

分支名通过 Git refname 校验并作为独立 argv 传递。拒绝选项前缀、控制字符、`..`、`@{`、空段、点开头/结尾和 `.lock` 结尾。

## 成功结果与失败

成功结果必须报告结构化仓库快照及后续可用工具。没有可用 Git 身份时，仍开放读取与本地分支能力，但不列出 `git_commit`，并以 `git_identity_missing` 说明提交前置条件；初始化不得写入身份。

稳定错误至少包括 `git_init_approval_required`、`git_init_plan_stale`、`git_init_target_outside_workspace`、`git_init_target_unsafe`、`git_init_nested_repository`、`git_init_invalid_branch`、`git_init_git_unavailable`、`git_init_backend_unsupported`、`git_init_sandbox_denied`、`git_init_process_failed`、`git_init_verification_failed`、`git_init_partial_metadata` 与 `git_init_receipt_failed`。不得建议通过 sudo、关闭安全限制、全局改配置或删除 `.git` 绕过失败。

## 验收门禁

1. 相关沙盒与 Git 规格 Accepted，且用户单独授权实施及受控原型。
2. Intel macOS 真实受限后端完成空目录和源码目录初始化；仅产生预期 `.git`，没有 Commit、remote、身份、Hook 或业务文件变化。
3. 同一后端拒绝越界写入、`.git/config`/`.git/hooks` 的普通写入、链接/替换逃逸、模板与环境注入；单元测试或宿主无沙盒测试不能替代该证据。
4. 已有/嵌套/损坏仓库、非法分支、拒绝/过期/取消、Git/后端不可用、替换和部分产物均有稳定无越权结果。
5. 同一 workspace 通过 Core 工具完成状态、Diff、历史/查看、分支操作；身份就绪时通过精确 Commit Plan 与独立批准完成提交，且不复用初始化 Grant。
6. TUI、Plain、JSON 投影一致；回归、Receipt/恢复、Ruff、类型检查与 `git diff --check` 通过。
7. Terminal.app 完成可见批准、成功、后续 Git 操作及拒绝/失败流程。仅声明已验收架构；Apple Silicon 无设备则记为未验证。

## 明确不在本任务内

通用 Shell 放宽、关闭沙盒、全局 Git 配置/身份/Hook/remote 修改、真实用户仓库操作、Apple Silicon 支持声明，以及任何 commit、merge、push 或远端变更。
