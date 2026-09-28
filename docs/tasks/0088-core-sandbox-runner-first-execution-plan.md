> 当前实施以 [工作区权限沙盒 Accepted 规格](../specs/2026-09-26-workspace-permission-sandbox.md) 和任务 0089 为准；本文件保留历史决策。

# Core 沙盒：命令树优先实施计划

> **2026-09-26 待修订：** 用户要求按工作区边界、越界审批与基础运行权限收敛，见[首版方案 Draft](../specs/2026-09-26-workspace-permission-sandbox.md)。该方案接受后再同步本计划；当前不按旧多层隔离要求追加实现。

**状态：** Superseded（实施拆分；后端实测、阶段门禁及敏感操作审批仍未满足）
**范围：** macOS 先行，Intel（x86_64）与 Apple Silicon（arm64）都在最终支持范围；Linux 后续，Windows 条件性评估
**编号：** 0088（基于主线已提交到 0083 的任务记录分配；后端评估为 0087）
**规格：** [Core 执行沙盒](../specs/2026-09-24-core-execution-sandbox.md)
**决策：** [ADR-0023（Accepted）](../decisions/ADR-0023-runner-first-sandbox-staging.md)
**证据：** [共同验收矩阵](../evals/core-sandbox-backend-matrix.md)、[0086 Intel 原型](../evals/core-sandbox-macos-feasibility.md)、[0087 替代后端计划](0087-core-sandbox-alternative-backend-probes.md)

## 进入条件

1. **已满足：** 用户已接受 Runner 优先规格与 ADR-0023；阶段八/九原有人工门禁保持有效，不因本计划跳过。
2. 0087 用假数据证明至少一个 macOS 命令树候选同时满足通用原生命令正例和 OS 文件、网络、凭据负例，并明确受支持的签名、打包及安装方式；证据足够时再接受后端 ADR-0023。
3. 从包含阶段八最终 ToolExecutor、Bash、Git、验证能力的干净基线创建独立实施工作树。当前沙盒文档工作树不直接承载未接受规格的产品代码。
4. 若实施步骤涉及新账户、VM、系统安全设置、真实凭据或真实工程，先给出具体影响和回退清单并取得用户对该动作的批准；当前不运行此类操作。测试延期解除前不运行新探针。

## 切片 1：冻结执行契约与入口清单

- 定义 `SandboxRequest`、`SandboxGrant`、后端能力与结果类别；绑定 workspace、动作、真实可执行文件、目录、可写产物根、网络目的地、期限和取消标识。未经实测的字段不声称 OS 可强制。
- 盘点 Agent 能触发的所有 OS 进程入口，至少检查阶段八分支的 `src/vera/tools/bash.py`、`src/vera/git/service.py`、`src/vera/git/discovery.py`、`src/vera/verification/runner.py` 和 `src/vera/process/supervisor.py`，以及验证中的 `git_porcelain` 直接 `subprocess.run`。逐项标记“必须进 Runner”“仅用户显式启动”“产品内部诊断”；后两类不得被模型借道执行项目命令。
- 把现有 Workspace、Policy、Approval、Receipt、Checkpoint、Recovery 的事实映射到请求；不在客户端复制授权判断。

**只读初盘（阶段八隔离分支当前代码；实施时须从最终基线复核）：**

| 入口 | 当前启动方式 | 初步归类与待处理 |
|---|---|---|
| `tools/bash.py` | `ProcessSupervisor.run(ProcessRequest)` | Agent 命令；必须进入 Runner |
| `git/discovery.py`、`git/service.py` | 共用 `ProcessSupervisor`；Commit/Branch 等操作经 Git 服务派生 | Agent 原生 Git；含 Hook 后代，必须进入 Runner |
| `verification/runner.py` | 验证命令经 `ProcessSupervisor`；`git_porcelain` 另用直接 `subprocess.run` | 两条路径均须受限；直接调用不能旁路 |
| `session/status.py`、`version.py` | 固定 Git 参数的直接 `subprocess.run` | 产品诊断；项目 Git 配置或 helper 可能触发后代，须证明安全或纳入受限入口，不能仅因参数只读就豁免 |
| `evals/process_runner.py` | `ProcessSupervisor` 启动 Eval Worker | 评测客户端进程；Worker 内部的 Agent 命令仍须走 Runner，评测进程自身的边界单独审阅 |
| `session/external_editor.py`、`terminal/app.py` 的 `pbcopy` | 用户显式操作触发的直接 `subprocess.run` | 独立用户操作；不得开放给模型借道执行项目命令 |

这个盘点只依据当前阶段八分支源码，不证明运行时覆盖完整。实施时还需搜索其它进程 API、运行时注入入口和依赖升级引入的执行路径，并用负例验证旁路失败。

**退出证据：** 一张覆盖全部 Agent 命令入口和旁路的清单、稳定的版本化契约、失败关闭语义；测试只证明契约和路由，不宣称 OS 沙盒已生效。

## 切片 2：单一 Runner 执行入口

- 在工具执行层建立单一受限进程入口，把 Bash、原生 Git、验证、构建、安装脚本、Hook 的首次进程及后代接入。任一路径无法附加受限后端时拒绝执行，并保留原 Policy/Approval 门禁。
- 默认不给 Runner Provider Key、Core 私有状态、Broker IPC、非必要环境变量或继承文件描述符。仅当次动作授予 workspace 读取、计划产物根写入及明确批准的网络范围。
- 取消、超时、崩溃、恢复和 Git Commit 后的 Hook 必须处理整棵进程树及重复副作用；新增状态记录后端身份、实际能力和覆盖的入口。

**退出证据：** 每个 Agent 命令入口能在独立夹具中证明“进入同一 Runner 或失败关闭”；正反例覆盖子进程和孙进程。只运行 mock 后端或 `ProcessSupervisor` 的测试不能证明 OS 隔离。

## 切片 3：macOS 受限后端与可用性

- 用户于 2026-09-26 先排除 Seatbelt，后在选型复核中明确选择“优先原生体验，允许重新评估现成 Seatbelt runtime”。0087 已静态审阅固定版本 Anthropic Sandbox Runtime；用户随后批准首轮最小试验；Shell 启动通过，系统 Git/xcrun 工具链门槛阻断，已停止清理；须先完成工具链资源映射并复验，文件/网络及后代矩阵尚未运行。XPC + App Sandbox 不推荐作为通用原生 Runner，不再优先修复原 ad-hoc 夹具。详见[选型审阅](../evals/core-sandbox-selection-review-2026-09-26.md)。
- 用仓库外假数据检查系统 `git`、`xcrun`、自装工具、解释器、包管理器、构建产物运行、Hook 与多级后代；同时检查其他工程和假秘密读写、网络/loopback、Unix socket、链接、FD、缓存目录、取消与孤儿进程。
- 独立安装、签名与升级在 Intel 和 Apple Silicon 真机分别复验。Intel 开发机结果不能代替 arm64 原生验证；无 Apple Silicon 设备时保持 `Not run`，不声明 macOS 整体支持。

**退出证据：** 共同矩阵中 Runner 正反例及发行路径均有原始 OS 证据；存在一个可维护候选后，才进入产品后端选择。

## 切片 4：阶段性状态与完整 Core

- Runner 优先切片完成时，结构化状态分别显示 Core 未隔离和 Runner 已隔离及其覆盖范围；Plain/JSON/TUI 使用同一 Core 事实。沙盒不可用、拒绝和缺能力有稳定错误，不进行无沙盒自动重试。内建 Read/Edit/Write 继续由现有 Policy 管控，但不得被宣称受 Runner OS 沙盒保护。
- 后续按原规格把完整 Core、Provider Broker、资源 IPC 与内建文件访问纳入 OS 边界；Runner 始终更窄。两层均达标前，桌面前完整 Core 安全门禁保持未完成。

**最终验收：** `SBX-01` 至 `SBX-15` 的共同正反例、Intel 与 Apple Silicon 的原生安装态、真实任意工程和失败恢复均通过；文档与产品状态明确区分每个已验证事实和未运行项。

## 当前停点

本计划的实施顺序已接受；沙盒任务编号维持 0086（Intel 可行性）、0087（替代后端评估）与 0088（实施拆分）。用户已重新开放现成 Seatbelt runtime 的评估，首选验证候选为固定版本 Anthropic Sandbox Runtime 加 Vera 适配层。首轮试验已获授权并执行；受限 Shell 启动通过，工具链发现及宿主缓存访问阻断，其余矩阵未运行；独立 UID/ACL 不作完整后端，XPC 保留 IPC 用途，VM 保留可选环境。下一步在 0087 内明确工具链最小资源映射并准备复验，通过后再扩矩阵和后端 ADR；当前不开始产品实现。产品代码须使用独立工作树并满足阶段门禁，Intel 结果不得推广为 arm64 支持。
