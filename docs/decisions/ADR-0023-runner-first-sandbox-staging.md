> 当前实施以 [工作区权限沙盒 Accepted 规格](../specs/2026-09-26-workspace-permission-sandbox.md) 和任务 0089 为准；本文件保留历史决策。

# ADR-0023：先隔离 Agent 命令树，再完成整个 Core 沙盒

> **2026-09-26 最新方向：** 用户要求围绕工作区权限与越界审批收敛。[新方案 Draft](../specs/2026-09-26-workspace-permission-sandbox.md)拟将首版定义为可信 Core 统一授权与命令树 OS 隔离，不再要求本 ADR 中完整 Core 多层 OS 隔离作为首版前置门槛。待新方案审阅后正式修订决策；本条不将 Draft 标为 Accepted。

**状态：** Superseded
**接受：** 2026-09-25 用户确认 Runner 优先规格、ADR 与实施方向
**日期：** 2026-09-25
**来源：** 用户要求借鉴 Claude Code 对命令及后代施加 OS 沙盒的思路，向此方向规划与实施
**范围：** 实施顺序和阶段性能力声明；不选定 macOS 后端、不修改阶段编号

## 背景

已接受的 Vera 安全目标要求完整 Core 受 OS 隔离，项目 Runner 的权限更窄，Broker 独立核验 Grant。现有 `ProcessSupervisor` 管理命令、超时和进程组，却不构成 OS 沙盒。Intel macOS 的固定路径 App Sandbox 原型通过若干文件/网络负例，但系统 `xcrun`/Git 工具链和动态工程授权仍有阻断；同 UID `sandbox-exec` 子进程树对照也只是局部证据。

Claude Code 的[官方文档](https://code.claude.com/docs/en/sandboxing)说明，其内置沙盒约束 Bash 等命令及其后代，macOS 使用 Seatbelt；内建文件工具不在该命令沙盒内。这个设计证明了“先明确命令树边界”是一种值得验证的分层方式，不能证明 Vera 可以直接复用其后端、放弃完整 Core 隔离，或把现有同 UID 探针视为产品安全保证。

## 候选方案

1. 先验证并接入 Agent 命令树的 OS 隔离，再接入完整 Core 与 Broker。能以命令、后代和原生工具链形成较小的可观察切片；阶段性状态必须说明 Core 尚未受 OS 隔离。
2. 先隔离完整 Core，再处理命令树。维持原规格实施顺序，但 Core 与工具链兼容性、Broker IPC 和动态资源授权同时阻断时，难以独立归因。
3. 仅隔离命令树并把它作为最终产品沙盒。内建文件工具、模型调用、Provider 凭据和恢复仍在 Core 宿主域，不能满足已接受的完整 Core 安全目标。

## 决策

采用方案 1 作为实施顺序，保持完整 Core 与更窄 Runner 的最终目标：

1. 盘点全部 Agent 发起的 OS 命令入口。结构化 Bash、原生 Git、验证、构建、安装器、项目脚本、Hook 及后代必须通过统一受限执行入口；不能按工具名称、是否使用 Shell 或调用方客户端决定豁免。
2. 首个实施切片验证 Runner 的 OS 文件、网络、凭据和后代进程边界，同时证明通用原生工程命令可运行。每个动作绑定 `SandboxRequest`/`SandboxGrant`；Policy、Approval、Receipt、恢复不因命令入沙盒而放宽。
3. 阶段性状态分别报告 Core 与 Runner 的实际隔离情况。Runner 通过不能宣称整个 Core 已受隔离，也不能通过无沙盒自动重试维持表面成功。
4. 后续接入受限 Core、最小 Broker 与 Provider 通道，Runner 继续比 Core 权限更窄；最终按共同矩阵和 Intel/Apple Silicon 真机证据验收。
5. macOS 的按命令 Seatbelt 只列为优先研究候选。其公开调用方式、签名发行、动态 Grant、工具链兼容、网络/凭据隔离和后代边界都须实测。已弃用的 `sandbox-exec` 不因 Claude Code 使用 Seatbelt 就自动成为 Vera 产品后端。
6. 本 ADR 的接受不授权创建账户、安装 VM、主机安全设置变更、提交或发布；用户于 2026-09-25 另行解除 0087 的测试延期，但产品代码仍须满足后端证据、阶段门禁和 0088 实施计划。后端与阶段位置待证据充分后由后续 ADR 决定。

## 后果与验收

- 命令树隔离可作为独立工程里程碑，但完整 Core 门禁在 Core、Broker、Runner 全部达标前保持未完成。
- Core 内建 Read/Edit/Write 与直接文件操作不会被“Bash 沙盒”自动覆盖；阶段性发布若存在，必须明确告知此事实及适用范围。
- 不允许模型通过另一项命令工具、Git 包装器、诊断进程、Shell 功能或子进程链绕开 Runner。外部编辑器和用户自己输入的命令需与 Agent 发起命令分开定义。
- Intel 的正反例不能继承为 Apple Silicon 通过；Linux 后续，Windows 条件性评估。
- 若候选无法兼顾任意项目原生工具链与 OS 负例，保持 `Blocked` 并复审，不通过无沙盒执行满足验收。

## 重新评审触发器

- 命令树候选无法提供受支持且可发行的 macOS 约束机制；
- 真实项目需要长期宽泛的文件、网络、IPC 或 Apple Events 权限，使安全负例不成立；
- Agent 发起的执行路径无法可靠收敛到统一入口；
- 完整 Core 与 Broker 的后续隔离不能维持同一安全语义或可接受的产品体验。

## 后续用户决定（2026-09-26，历史；评估范围被下节修订）

用户决定不采用基于 `sandbox-exec` / Seatbelt 命令树的方式实现 Vera。该路径从产品实现候选中排除；既有同 UID 试验与崩溃诊断仅作为历史证据保留，不再据此继续产品候选验证。原有“Runner 优先、随后完成 Core 与 Broker”的架构顺序和完整 Core 安全目标不变。

后续仅比较以下三条 macOS 候选，不预先认定其可行或选定其中任何一条：

1. **独立系统身份 + OS 强制策略：** Runner 使用单独的非管理员身份，再组合可维护的 OS 文件与网络限制。UID 分离本身不算沙盒；需证明任意项目工具可运行，同时越界读写和网络由 OS 拒绝。
2. **XPC 隔离 Runner：** 将不可信命令置于独立 XPC Service / App Sandbox，通过动态 security-scoped bookmark 和窄 Broker IPC 授予当前工程所需资源。原生工具链、书签传递范围和后代继承仍待验证。
3. **VM 执行域：** 在虚拟机中运行项目命令，以虚拟化边界隔离宿主数据。当前 Intel Mac 上，Apple Virtualization 的 Linux guest 只能验证 Linux 项目，不能覆盖原生 macOS/Xcode 工程；可运行的通用项目范围、共享目录与网络边界仍须评估。

本决定只排除一种实现路径，不取消沙盒目标，也不授权创建账户、VM、安装软件或更改主机设置。候选顺序与实验范围待后续用户选择和具体审阅。

## 最新用户决定：重新评估现成 runtime（2026-09-26）

在比较独立身份、VM 与主流 macOS 本地产品后，用户选择“优先原生体验，允许重新评估现成 Seatbelt runtime”。该决定覆盖上节对 Seatbelt 的评估排除，允许优先审阅固定版本 Anthropic Sandbox Runtime；不代表已选定产品后端或授权新的安装、敏感试验及产品实现。

本轮[选型审阅](../evals/core-sandbox-selection-review-2026-09-26.md)不推荐独立 UID/ACL 作为完整后端，也不推荐 XPC + App Sandbox 作为通用原生 Runner；VM 保留为独立执行环境，未实测。XPC 可继续作为 IPC 机制。Runner 优先、完整 Core/Broker 目标和阶段门禁保持有效。下一步是审阅所列最小试验并取得其生命周期授权；不再优先排查原 XPC 手工夹具。

## 关联

- [Core 执行沙盒规格](../specs/2026-09-24-core-execution-sandbox.md)
- [任务 0087：替代后端可行性](../tasks/0087-core-sandbox-alternative-backend-probes.md)
- [共同验收矩阵](../evals/core-sandbox-backend-matrix.md)
- [ADR-0021：桌面前插入 Core 工具集与 Git](ADR-0021-core-tools-before-desktop.md)
