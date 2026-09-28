# 任务 0084：Core 执行沙盒 macOS 可行性验证计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**状态：** Blocked；2026-09-25 用户选择 Native 执行，本机 App Sandbox 候选已证伪通用工具链硬门槛；其他后端与独立安装机尚无证据。产品实现、提交、合并和推送仍未授权
**Goal：** 在 Intel macOS 上用可复现的临时原型判断，是否存在同时满足“整个 Core 受 OS 隔离”“项目子进程权限更窄”和“任意本机软件项目工具链可用”的后端。
**Architecture：** 先建立与语言无关的正反例矩阵，再在仓库外对签名 App Sandbox Core/Runner 候选进行验证。每个结果记录 OS 证据、失败点和用户体验；若候选不满足全部硬门槛，停止正式实现并比较替代路径，不以应用层拒绝模拟 OS 隔离。
**Tech Stack：** Intel macOS（开发机当前 15.7.9；安装机版本现场记录）、Xcode/Swift CLI、`codesign`、临时本地进程和端口、Python 3 标准库、Git、原生 Terminal.app；产品依赖保持不变。
**Spec：** [Core 执行沙盒与通用项目能力边界](../specs/2026-09-24-core-execution-sandbox.md)

## Global Constraints

- 原型、编译产物、测试工程和日志只存放在 `/private/tmp/vera-sandbox-feasibility.<随机后缀>/`；不读取真实 Provider Key、`~/.ssh`、其他私有工程或真实本机秘密。
- 不修改 Vera 产品源码、阶段八/九工作树、`/Users/admin/Desktop/VeraTestDemo` 或当前用户系统设置；不运行 `sudo`，不创建系统账号，不安装 VM 或系统扩展。
- 所有拒绝测试用临时哨兵文件、临时本地 TCP 监听端口和临时 workspace。不能把签名存在、`shell=False`、应用层路径拒绝或测试替身算作 OS 隔离通过。
- 任何需要 Developer ID、系统授权、额外安装、账户/网络规则或破坏现有配置的候选，先只记录前置条件与风险，另行审阅后才能执行。
- 本任务只形成可行性证据和后端选型建议；不接受“无沙盒自动回退”，不改变阶段八/九/十状态，不创建产品提交、合并或推送。
- 第二台 Intel Mac 是先前记录的安装验收环境，执行时先确认仍可使用；若不可用，安装态复验记为 `Blocked`，不能用开发机重复运行代替。
- 本任务仅验证优先支持的 macOS 的 Intel（x86_64）路径；Apple Silicon（arm64）真机尚未验证，不能由 Intel 结果推断 macOS 整体支持。后续两种架构均须通过共同 Core 安全矩阵。Linux 排第二且为 `Not run`；Windows 仅作为可放弃的条件性候选，当前为 `Not run`。

## Review Focus

以下输入最容易把“可以运行”误判为“受保护”，每项必须在拥有它的步骤留下 OS 正反例证据：

1. 用户自装在非预设路径的可执行文件：授予对应路径后可启动；仅授予 workspace 读写时不能假定获得执行权。
2. `xcrun`、工具链包装器、项目脚本和孙进程：实际使用的二进制与后代仍落在声明的隔离域。
3. 构建缓存和 DerivedData 等外部产物：只写本次授权根；拒绝时不留下工程根或其他目录污染。
4. Core 私有状态、假 Provider Key 和 Broker IPC：项目进程无法读取或调用；通过空环境变量但文件/IPC 仍可访问不算通过。
5. 网络、路径链接和取消：未授权连接、越界链接及取消后孤儿进程由 OS 或受管进程边界拒绝，不靠事后扫描宣称安全。
6. 真实 Vera Core 安装态：小探针通过后仍要在同一候选边界启动仓库外安装的 Core；只跑 Swift 原型不算完整 Core 可行。

## 文件与责任

| 路径 | 责任 |
|---|---|
| `/private/tmp/vera-sandbox-feasibility.<随机后缀>/` | 一次性 Swift/脚本探针、独立 workspace、哨兵、产物和原始日志；不得进入仓库。 |
| `docs/evals/core-sandbox-macos-feasibility.md` | 记录环境、命令、预期/实际、OS 证据、能力矩阵与阻断；不记录私有正文。 |
| `docs/decisions/ADR-0023-core-sandbox-backend-and-stage.md` | 仅当证据足以选择后端及阶段位置时创建 Proposed ADR；证据不足时不预选技术。 |
| `docs/STATUS.md` | 记录任务的 Verified/Blocked/Not run 结论和下一门槛。 |

## Task 1：准备可复现的临时探针与基线

**Files:** 临时目录中的 `workspace/`、`outside/`、`state/`、`bin/`、`logs/`；结果写入评测记录。

- [ ] **Step 1：读取环境事实。** 分别运行 `uname -m`、`sw_vers -productVersion`、`xcode-select -p`、`xcrun --find swiftc`、`command -v codesign`，记录精确输出；第二台 Intel Mac 独立重复，不从开发机结果推断安装机。**开发机完成；安装机 Blocked。**
- [x] **Step 2：创建只含假数据的临时夹具。** 用 `mktemp -d /private/tmp/vera-sandbox-feasibility.XXXXXX` 取得根目录；创建上述五个子目录。`outside/secret.txt` 写入固定标记 `VERA_PROBE_SECRET_ONLY`，`state/provider.env` 写入 `FAKE_PROVIDER_KEY=probe-only`。在 `bin/` 创建能打印固定标记的用户自装路径替身，在 `workspace/` 创建调用该替身并派生一次子进程的项目脚本。
- [x] **Step 3：先跑无沙盒基线。** 从临时 workspace 启动探针，记录它能否读取 `outside/secret.txt`、写 `outside/`、执行 `bin/` 文件、连接仅在 `127.0.0.1` 监听的临时端口。此组只验证夹具有效，预期越界动作可能成功，不得记为安全通过。
- [x] **Step 4：固定结果格式。** 每条用例记录 `case_id / backend / host / command / requested_grant / expected / observed / os_evidence / artifact_hash / conclusion`。`conclusion` 只能是 `Verified`、`Failed`、`Blocked` 或 `Not run`；不要把退出码非零自动解释为沙盒拒绝。
- [ ] **Step 5：检查临时夹具。** 确认哨兵和构建产物都在新目录下，Vera 正式仓库与三个既有工作树状态未变化；没有真实凭据进入日志。

## Task 2：签名 macOS Core 隔离候选

**Files:** 临时 `ProbeCore` 原型与 entitlements、临时日志、评测记录。

- [x] **Step 1：建立最小签名进程。** 原型只执行 `read/write/exec/connect/spawn` 五类探针，接受临时绝对路径作为参数，不加载 Vera 或真实 Provider。为 Core 候选声明 App Sandbox；在签名前保存 entitlements 原文和源码哈希。
- [ ] **Step 2：验证签名与运行时隔离。** 记录 `codesign -d --entitlements - <ProbeCore>`、Activity Monitor 的 Sandbox 状态以及实际拒绝用例。只有签名输出、没有运行时拒绝事实时记为 `Blocked`。
- [ ] **Step 3：检查用户选择工程。** 验证 Core 候选如何获得临时 workspace 的读写授权，进程重启后如何续用授权，以及未选的 `outside/` 是否仍被 OS 拒绝。若 CLI 只能通过破坏用户交互的方式获得目录授权，记录具体步骤和体验代价。
- [ ] **Step 4：检查 Provider 边界。** 在临时 `state/` 创建最小 Broker：只持有 `FAKE_PROVIDER_KEY=probe-only`，只接受一个固定本地 HTTP 目的地，通过权限受限的本地 IPC 回复探针请求。Core 候选必须能调用此通道，Runner 必须既不能读取假 Key、连接 Broker IPC，也不能直接连该 HTTP 端口。记录 IPC 路径权限和 OS 拒绝事实；只清除 Runner 环境变量不算通过。
- [ ] **Step 5：核对权限传递。** 派生子进程和孙进程，确认动态 workspace 授权、Core 私有状态和网络权限分别如何继承；用实际访问结果记录，不从 entitlements 推断。

## Task 3：通用工具链与更窄 Runner 候选

**Files:** 临时 `ProbeRunner` 原型、临时任意项目、评测记录。

- [x] **Step 1：独立签名 Runner。** Runner 候选不含 Provider 网络和 Core 私有状态权限。使用与 Task 2 不同的 OS 边界证明它不能读取 `state/provider.env`、`outside/secret.txt` 或连接本地监听端口；只去掉环境变量不算通过。
- [ ] **Step 2：运行非预置路径工具。** 在临时 `bin/` 与另一用户可写位置各放一个简单可执行探针；逐项验证“仅 workspace 读写”“额外工具链只读”“执行权限”实际效果。记录绝对路径、签名状态、OS 拒绝原因和是否需要特殊安装。
- [ ] **Step 3：运行复杂项目链。** 在临时副本分别尝试自定义脚本→孙进程、系统 Git Hook、本机当前选中的 Xcode/Command Line Tools 包装器，以及一个用户自装工具链；检查每个后代的边界、输出位置和取消后清理。不因某一种语言成功就推断任意工程可用。
- [ ] **Step 4：验证外部产物根。** 对临时构建命令只授予指定 `artifacts/` 写入，检查 workspace、`outside/` 和其他临时目录哈希；若工具需要额外缓存目录，记录它提出的真实需求与可否精确授权。
- [ ] **Step 5：对抗链接与进程。** 使用指向 `outside/` 的符号链接、可创建时的硬链接、路径替换、继承文件描述符和二级子进程重复读写/联网负例；任一绕过记为 `Failed`，不要靠删除痕迹转为通过。
- [x] **Step 6：真实 Core 安装态启动。** 从仓库外临时虚拟环境安装当前 Vera wheel，在候选 Core 边界中运行 `vera --version`、`vera eval validate --json`，再分别运行 `vera eval run plain-answer --json --output <临时 evidence 目录>`、`vera eval run create-file --json --output <另一临时 evidence 目录>` 和 `vera eval run forbidden-command --json --output <第三个临时 evidence 目录>`。评测使用内置 Fake Model，不调用真实 Provider；选择三类用例分别覆盖普通响应、Core 文件修改路径和命令拒绝路径。记录实际进程的 OS 隔离事实、状态目录、评测临时 workspace 与子进程访问结果；若只能运行探针而不能运行 Vera，Core 可行性标记 `Failed` 或 `Blocked`。

## Task 4：候选比较、证据收口与下一决策

**Files:** `docs/evals/core-sandbox-macos-feasibility.md`；条件满足时创建后端 `ADR-0023` Proposed；更新 `docs/STATUS.md`。

- [x] **Step 1：汇总矩阵。** 对整 Core、Runner、任意路径工具链、工作区授权、产物根、Provider/秘密、网络、Hook、取消/恢复分别标记 `Verified/Failed/Blocked/Not run`；附脱敏命令、OS 证据和安装态差异。
- [x] **Step 2：判定 App Sandbox 候选。** 若 Core 与 Runner 的安全负例及通用工具链正例均通过，提出后端 ADR；若任一硬门槛失败，明确失败事实及不能靠 `sandbox-exec`、打包固定工具链或无沙盒回退掩盖的理由。
- [x] **Step 3：比较下一候选。** 对独立系统身份和虚拟化路径只做文档级成本、权限、原生 macOS 工具链、维护与发行约束对照；涉及创建账号、VM 或系统扩展的实验另立可审阅计划与授权。
- [x] **Step 4：形成后续实施边界。** 有可行后端时，后续计划按 `Broker/Provider → 受限 Core → Runner/Tool → 验收` 拆成独立任务；无可行后端时只记录阻断和下一候选，不创建假定技术已选定的产品实施任务。
- [ ] **Step 5：收口检查。** 运行 `git diff --check`，检查评测文档无秘密与私有源码，确认临时目录只包含本任务创建的文件；临时资源的删除作为单独、明确的收尾动作，不触碰其他目录。

## 退出条件

- 一台开发机和一台独立安装机都有可复现的 OS 正反例，而非仅有静态 entitlements 或自动单测；
- 对“整个 Core”“更窄 Runner”“任意工具链”三项分别给出可行、失败或阻断结论；
- 没有真实 Provider 调用、系统账户变更、远程推送或产品代码改动；
- 后端技术选择仅在证据充分时进入 Proposed ADR。用户审阅该证据和后续实施计划后，才可另行授权产品实现。

## 本轮执行结论

2026-09-25 的本机原型、命令、隔离正反例与未执行项见[评测记录](../evals/core-sandbox-macos-feasibility.md)。任务一夹具建立并通过无沙盒对照；任务二与三证明固定路径下的 Core、Runner 可分别限制文件/网络并运行部分自定义工具，且真实 wheel 的三个 Fake Model 用例可在签名沙盒内通过。但 `/usr/bin/xcrun` 和 `/usr/bin/git` 在 Runner 中明确报 App Sandbox 错误，项目原有 Xcode 调用链不能按通用工程要求工作。直接指定 Swift 编译器及 SDK 是受控对照，不能把每个任意工程改写为特制命令。

因此任务四不提出后端 ADR。动态工程与可执行授权、窄 Broker IPC、对抗链接/取消、独立安装机和其他候选仍未通过；本任务保留 Blocked，不将局部通过写成完整沙盒能力。下一步需针对独立系统身份或 VM 等候选另行形成可审阅的具体实验方案，且不得绕过本规格的两个同等优先安全目标。
