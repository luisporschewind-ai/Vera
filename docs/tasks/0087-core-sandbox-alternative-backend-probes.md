# 任务 0087：Core 沙盒替代后端可行性实验计划

> **最新工作方向：** 用户要求围绕工作区与越界审批收敛；已形成[首版方案 Draft](../specs/2026-09-26-workspace-permission-sandbox.md)供审阅。当前下一步为审阅方案，接受后同步任务门槛；以下后端结果仍是有效历史证据，本轮没有新增运行试验。

> **当前结论（2026-09-26 最新）：** 用户已批准并执行现成 runtime 最小试验；Shell 启动通过，严格策略下系统 Git/xcrun 工具链门槛 Blocked，已停止并清理。以下原状态段记录此前停点；以“最新评估与用户决定”节为准。

> **执行方式：** 用户已确认原实验计划；2026-09-25 又确认命令树优先的规格、ADR 与新增计划步骤，并解除测试延期。用户另行批准一次临时非管理员账户、假数据 ACL 探针及清理完整生命周期。VM、全局主机安全设置、接入产品 Core 与创建提交不在本轮授权中。

**状态：** Blocked；共同矩阵、无主机改动预检与同 UID 子进程树负例已完成。2026-09-25 的临时路径 Seatbelt 对照只验证了部分文件规则；2026-09-26 按崩溃 PID 查询统一日志，确认两次 SIGABRT 均由 `file-read-data /` 被拒绝、导致 dyld 启动失败。临时账户、home、ACL、假数据目录与 UID 502 launchd 域均已清理并核验。用户于 2026-09-26 决定不采用 `sandbox-exec` / Seatbelt 命令树方式实现 Vera；该路径退出产品实现候选，相关实验仅保留为历史证据。用户随后批准优先验证 XPC 隔离 Runner + App Sandbox。本轮构建了临时 ad-hoc 签名的宿主与 XPC 服务；LaunchServices 成功启动受沙盒宿主，但嵌入式服务查找返回 `NSCocoaErrorDomain 4099` / `launchd error 3: No such process`，未能执行 Runner 探针。该结果是测试夹具/签名路径下的 `Blocked`，不是 XPC 候选的可行或失败结论；未执行工具链、文件、网络及后代边界测试，临时夹具已清理。已有 0086 `xcrun`/系统 Git 包装器失败是此候选的未解决风险。未选择产品后端，未启动产品实现或主机改动。
**Goal：** 在当前 Intel macOS 上找出至少一个值得继续验证的 OS 隔离后端，或用可复现证据说明候选为何不能同时满足通用原生工具链与文件、网络、凭据隔离；本任务的 Intel 结论不构成 Apple Silicon 或 macOS 整体支持结论。
**Architecture：** `SandboxRequest`、`SandboxGrant` 与验收用例保持平台无关；每个候选只在仓库外的假数据环境运行。用户已排除 `sandbox-exec` / Seatbelt 命令树实现；剩余 macOS 候选为独立身份 + OS 强制策略、XPC 隔离 Runner 和 VM 执行域。Runner 优先只是实施顺序，完整 Core 与 Broker 仍是最终门槛。先做无需改变主机状态的能力检查，再按共同正反例验证，最后决定是否进入独立安装态验证及后端 ADR。
**Tech Stack：** 当前 Intel macOS、原生 Terminal.app、系统文件权限和进程工具、Swift/Xcode CLI、临时假数据工程；Apple Silicon（arm64）真机为 macOS 支持声明前的独立验证环境，当前 `Not run`；Linux 排在 macOS 后实测；Windows 为可放弃的条件性候选，仅在决定支持时于真实目标 OS 上执行。
**Spec：** [Core 执行沙盒与通用项目能力边界](../specs/2026-09-24-core-execution-sandbox.md)
**上游：** [任务 0086](0086-core-sandbox-feasibility.md)及其[实测记录](../evals/core-sandbox-macos-feasibility.md)

## 最新评估与用户决定（2026-09-26；覆盖上文历史停点）

**当前状态：** 用户明确批准最小试验；固定版本 runtime 已启动受限 Shell，但系统 Git/xcrun 的发现路径及宿主缓存访问阻断，`Blocked`。一次单变量归因后停止，剩余边界矩阵 `Not run`，临时环境已清理。见[试验记录](../evals/core-sandbox-srt-minimal-probe-2026-09-26.md)，后端未选定。上文排除 Seatbelt 和继续修复 XPC 夹具的记录保留为历史。

- 用户已选择“优先原生体验，允许重新评估现成 Seatbelt runtime”；优先候选为 `@anthropic-ai/sandbox-runtime@0.0.77` 加 Vera 适配层。源码快照、发布包完整性、默认权限差异与可执行试验范围见[选型审阅](../evals/core-sandbox-selection-review-2026-09-26.md)。此前为静态核对；本轮随后经单独授权安装并执行最小试验，实际结果见上述记录。
- 独立 UID/普通 ACL 不能覆盖 world-readable 文件与网络出口，否决作为独立完整后端；不再重复账户基线。XPC + App Sandbox 不推荐作为通用原生 Runner，依据是已有工具链证据和 Apple 约束，而不是 XPC 夹具启动失败；不继续修复该夹具。
- VM 可作为独立执行环境，运行验证仍 `Not run`；不把 Linux guest 当成宿主原生工具链，也不自动启动 Docker 或创建 VM。
- 下一步先审阅 Git/xcrun 所需工具链发现、系统元数据和缓存资源映射，准备精确的复验配置；不得扩大宿主读写范围来凑通过。最小试验通过后才扩大共同矩阵。完整 Core/Broker、arm64 与安装态仍待独立验证。

## 全局约束与评审重点

- 最终产品门槛仍要求完整 Core 在 OS 隔离域、项目命令和所有后代在更窄 Runner 域，Broker 独立核验授权。本任务可先单独判定命令树 Runner 候选；Runner 通过不能算 Core 已受隔离。
- 任意项目既有命令与用户安装在任意位置的工具需要能运行；不能用预置语言或改写构建命令代替。
- 工作区外文件、Provider Key、Core 私有状态与未授权网络出口必须由 OS 边界拒绝。macOS 先行且包含 Intel（x86_64）与 Apple Silicon（arm64）；Linux 后续、Windows 条件性评估。两个 macOS 架构及每个声明支持的平台共享同一授权、默认拒绝与失败关闭语义；Linux/Windows 的 `Not run` 不阻塞 macOS 验收，Apple Silicon 的 `Not run` 则阻塞 macOS 整体支持声明。
- Agent 发起的 Bash、原生 Git、验证、构建、安装器、项目脚本与 Hook 均须进入同一受限执行入口；阶段八实现中任何直接 `subprocess` 路径须逐项分类，不能形成旁路。内建文件工具不因命令树隔离而获得 OS 防护；Policy 与审批不因沙盒存在而放宽。
- 最容易误判的五类输入：`/usr/bin/xcrun`/`git` 包装命令、用户自装工具的真实路径、跨根符号链接或硬链接、继承的 FD 与孙进程、可联网的项目脚本。每类均须给出运行命令、预期、实际 OS 证据及 `Verified`/`Failed`/`Blocked`/`Not run`；缺一不可。
- 所有哨兵、脚本、凭据与端口都用仓库外假数据。只记录必要路径和哈希，不采集真实秘密。未通过的候选停止扩展实验，不靠宿主无沙盒执行绕过。

## 当前只读预检

- 2026-09-25 当前开发机 `sw_vers -productVersion` 为 `15.7.9`，`sysctl -n kern.hv_support` 为 `1`。这只说明硬件虚拟化接口可用，未证明某种 guest、文件共享、原生 macOS 构建链或安全边界可用。
- Apple [Virtualization 文档](https://developer.apple.com/documentation/virtualization)覆盖 Intel Mac 的 Linux guest；其 [`VZMacPlatformConfiguration`](https://developer.apple.com/documentation/virtualization/vzmacplatformconfiguration)明确面向 Apple silicon 上的 macOS guest。因此 Apple Virtualization 的 Intel Linux guest 不能充当 Xcode/Simulator 项目的通用原生执行验证。
- 独立 UID 只能提供系统身份与权限分离的候选基础，不能凭 UID 名称推定对世界可读文件、网络出口或继承 FD 的拒绝。须实测附加 OS 限制，并保持 Core 与 Runner 两级边界。

## Task 1：冻结共同逻辑矩阵与证据格式

**Files:** 创建 `docs/evals/core-sandbox-backend-matrix.md`；更新本任务的步骤状态。
**Produces:** 稳定 `case_id`、请求的能力、预期 OS 行为、证据字段与逐候选、逐平台状态；后续所有候选复用。

- [x] 把任务 0086 的已测场景映射为共同 case：默认外部读写拒绝、工作区读写、项目脚本及后代、Runner 假 Key/私有状态拒绝、网络默认拒绝、产物根可写、系统 Git 与 Swift 工具链。
- [x] 补全尚未测的硬门槛：动态选择任意工程、用户自装工具、Git Hook、链接/路径替换/继承 FD、Provider Broker 窄 IPC、Grant 过期、取消与孤儿进程、崩溃恢复、源码运行及安装/升级。
- [x] 每条结果都标明 `platform`、`backend_id`、`host_id`、`case_id` 和证据引用；初始只迁移有原始证据的 macOS App Sandbox 行。独立身份、VM、Linux 与 Windows 均标 `Not run`，不将一个候选的通过归给整个平台，也不以文档阅读冒充实测。
- [x] 检查每个 case 同时有正例和相关负例，并能区分 OS 拒绝、应用层拒绝和测试环境阻断。

## Task 2：macOS 候选的最小杀手实验

**Files:** 仓库外临时原型与原始日志；在矩阵中补证据链接和结论。
**Consumes:** Task 1 的共同 `case_id` 与 0086 的基线；不复用未脱敏的真实状态。

- [x] 先只读检查独立身份、虚拟化和原生工具链所需前提，写明候选运行方式、权限边界与主机改动清单。实际创建账户、VM 或修改系统设置之前，提交这份清单供用户审阅。见[预检和改动清单](../evals/core-sandbox-alternative-preflight.md)。
- [x] 在临时固定路径策略下验证假项目脚本的 `cat`、`bash`、`nc` 子进程仍继承 OS 文件与网络拒绝，允许写入单独 artifacts；证据见[子进程树对照](../evals/core-sandbox-alternative-preflight.md#固定路径子进程树对照)。此项是同 UID 控制，不替代下项独立身份试验。
- [x] 只读核对按命令启动的 macOS Seatbelt 公开实现：[Claude Code 文档](https://code.claude.com/docs/en/sandboxing)说明命令及后代边界，[Anthropic Sandbox Runtime](https://github.com/anthropics/sandbox-runtime/blob/main/README.md)明确通过 `sandbox-exec` 启动动态 profile，且自身为研究预览。源码使用宿主代理约束网络；默认读取策略和本机 `sandbox-exec` deprecated 状态均不能直接满足 Vera 产品保证。见[预检补充](../evals/core-sandbox-alternative-preflight.md#命令树-seatbelt-候选官方源码只读核对2026-09-25)。
- [x] 保留用户先排除 Seatbelt、后明确重新开放现成 runtime 评估的决定链；根因及历史证据见[预检记录](../evals/core-sandbox-alternative-preflight.md#临时非管理员账户执行记录2026-09-26)。新方向不继承旧探针的通过结果。
- [x] 评估独立 UID/ACL：既有假秘密可读和缺少网络边界已足以否决其独立完整后端资格；未指明实现的“附加 OS 策略”不作为可交付方案。
- [x] 评估 XPC + App Sandbox：结合 0086 原生工具链失败与 Apple 平台约束，不推荐作为通用原生 Runner。原 XPC 夹具仍是 `Blocked`，不伪记为边界实测失败；停止继续调试此夹具。
- [x] 审阅固定版本 Anthropic runtime 的许可、依赖、macOS profile、网络与退出路径，识别默认读写、无约束模式和进程取消适配点。
- [x] 经用户单独授权执行[首轮最小 runtime 试验](../evals/core-sandbox-srt-minimal-probe-2026-09-26.md)，核对固定发布包、依赖锁与关键代码；工具链门槛失败后停止并清理。此勾选仅表示试验已执行，不代表通过。
- [ ] 解决最小资源映射后，经具体审阅复验原生工具链，再验证 OS 文件/网络拒绝及后代清理。
- [ ] 评估 VM 方案能覆盖的项目类型和隔离边界。Intel Mac 上 Linux guest 的成功只可证明 Linux 项目，不可替代原生 macOS/Xcode 验证；VM 镜像、下载、磁盘与网络配置必须在运行前逐项审阅。
- [ ] 对任何初步通过的候选，再试动态工程/工具路径、最小 Broker IPC、Grant 撤销、链接/FD/后代绕过、取消和恢复；记录具体 OS 拒绝依据、进程树、退出码、日志哈希与未覆盖面。

## Task 3：逐平台映射与后端决策门

**Files:** 更新矩阵、本任务和 `docs/STATUS.md`；仅证据充分时另写 Proposed ADR。
**Produces:** 一份可以区分“macOS 候选可继续”“候选失败”“缺设备阻断”的结论。

- [x] 用 Linux 官方 Landlock/进程隔离文档与 Windows 官方 AppContainer/受限进程文档标注候选机制及版本前提；文档研究只标 `Not run`，不宣称两个平台已满足共同语义。见[预检映射](../evals/core-sandbox-alternative-preflight.md)。
- [ ] 对 macOS 候选逐条核对共同矩阵。只有原生工具链正例和文件、网络、凭据负例都通过，才安排第二台 Intel Mac 的独立安装态、签名、升级与性能复验。
- [ ] 有完整证据时提出后端与阶段位置的 `ADR-0023` Proposed；`ADR-0023` 仅记录 Runner 优先的实施顺序，不选后端。没有证据则保留 Blocked，并明确是能力缺口、设备缺失还是实验尚未运行。不得据此启动产品实现或更改阶段八/九/十状态。

## 完成条件

本任务作为 Intel 可行性调查，须先给按命令启动的 Runner 候选及其替代路径分别记录 `Verified`/`Failed`/`Blocked`，不能凭 Claude Code 文档或旧同 UID 探针推定通过。可以在一个候选通过共同硬门槛且完成两台 Intel Mac 的安装态复验后标 `Done`；也可以在所有经计划审阅的候选均有可复现的硬门槛失败证据后，以“Intel 路径没有可选后端”的明确结论标 `Done`。无论本任务状态如何，Apple Silicon 真机的同矩阵、原生 arm64、签名与安装态验证另立后续任务，完成前不得选定覆盖整个 macOS 的后端或声明 macOS 受支持。缺少设备、主机改动授权或关键实验时保持 `Blocked`/`Planned`，不能将尚未测的候选算作失败。最终执行 `git diff --check`、检查文档链接、逐项核对原始证据与结论；提交、合并、推送另按用户授权处理。
