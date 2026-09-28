# 任务 0090：Core 受控 Git 仓库初始化

**状态：** In progress
**所属阶段：** 阶段八——Core 工具集、Policy v2 与原生 Git
**上游规格：** [Core 受控 Git 仓库初始化](../specs/2026-09-27-core-owned-git-repository-initialization.md)（Accepted，2026-09-27）
**授权：** 用户于 2026-09-27 明确要求开始实施并验收。

## 目标

在空目录或已有普通源码的非仓库目录中，由 Core 经结构化、高风险审批的 `git_repository_init` 初始化本地仓库；成功后进入既有 Core-owned 基础 Git 工具闭环。安全边界与退出条件以上游 Accepted 规格为准。

## 工作边界

- 在隔离分支 `codex/git-repository-init` 实施；基线为阶段八 `5b6d789`。不改主工作区既有未提交更改。
- `0089-workspace-permission-sandbox` 的工作树与代码由其他任务持有；本任务不修改、不合并该工作树，也不改变其状态。
- 不关闭沙盒，不扩展 `.git/config`/`.git/hooks` 全局写权限，不回退到通用 Shell 或宿主无约束执行。
- 不执行 commit、merge、push、远程操作或真实用户项目写入。
- 真实 Intel macOS 沙盒试验尚无本分支可用的后端 Grant，且不在本任务擅自启动/改配沙盒的范围内；在授权协调接入 0089 后端前保持未验收状态。

## 实施与验收记录

### 已完成的 Core 切片

- 新增版本化初始化 Plan/Result、目标/分支检查、目录与 Git executable 身份/摘要绑定、稳定 Plan ID + 授权摘要绑定、计划过期重验证及幂等仓库发现。
- 新增 `git_repository_init` Tool 与 Policy 高风险审批、执行器计划绑定及 Operation Receipt 类型。
- 初始化无论 workspace 是否可信、是否存在 workspace 级授权，都要求本次明确审批；已有仓库只读幂等发现不要求初始化审批。
- 审批预览显示物理 workspace、`.git` 目标、初始分支，以及不创建提交/远程/身份/Hook 的说明。
- 只接受注入的单次精确初始化 Runner；未配置后端时返回 `git_init_backend_unsupported`，不产生 `.git`。
- 成功结果核对 unborn 初始分支、空 index、无 Commit/remote，并比较业务目录项；无 Git 身份时不把 `git_commit` 列入可用能力。
- Receipt 持久化失败映射为 `git_init_receipt_failed` 并保留仓库现场。

### 自动化验证

执行环境：独立 Codex Python 3.12 runtime（仓库共享 `.venv` 指向损坏的零字节系统 Python，未修复/覆盖它）。使用隔离 `uv --no-project` 环境加载测试依赖。

- 最新定向回归：`tests/git`、`tests/tools/test_git_init_tool.py`、`tests/tools/test_git.py`、`tests/policy`、`tests/runtime/test_tool_executor.py`、`tests/runtime/test_write_edit_tools.py` 共 **130 passed**。
- Ruff 对本任务全部改动的 Python 文件通过；严格 Mypy 对 `src/vera` 共 224 个源码文件通过。
- 全量 `tests`：**1299 passed、2 skipped、36 failed、1 error**。失败集中在既有 Eval/隔离执行路径（worker 报 `worker_exit_error` / CLI 返回 5）；wheel smoke 子流程强制 offline，缓存缺少 `openai`。这些阻断并非本次 Git 定向测试；全量结果不是通过。
- `git diff --check` 通过（最后变更后需再复核）。
- 测试 Runner 会在临时目录调用宿主 Git，只证明 Core 验证逻辑，不构成沙盒安全证据。

### 尚未验收 / 阻断

- 沙盒后端未在本分支提供初始化的一次性精确 `.git` Grant；真实初始化仍 fail closed。
- Intel macOS 真实 OS-deny 矩阵、TUI/Plain/JSON 人工一致性、Terminal.app 成功与拒绝验收未完成。
- 初始化后 status/diff/log/show/branch/commit 完整同 workspace 集成矩阵与更广回归、Ruff、类型检查尚未完成。
- Apple Silicon 未验证；不声明支持。

## 关闭条件

任务保持 `In progress`，直至 Core 自动化回归和代码质量检查通过，并在获得适当授权后接入由 0089 提供的精确后端能力、完成 Intel 真实沙盒矩阵和客户端人工验收。不得以宿主测试代替 OS 沙盒证据。关闭前更新本记录、`docs/STATUS.md` 及相关索引；当前不提交、合并或推送。
