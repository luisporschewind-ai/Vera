# Core 沙盒后端共同验收矩阵

**状态：** 共同逻辑用例已冻结；迁移任务 0086 的 macOS 局部证据，并记录任务 0087 的同 UID 临时对照
**规格：** [Core 执行沙盒](../specs/2026-09-24-core-execution-sandbox.md)
**任务：** [0087 替代后端可行性](../tasks/0087-core-sandbox-alternative-backend-probes.md)
**证据来源：** [0086 Intel macOS 实测](core-sandbox-macos-feasibility.md)

## 口径

一条结果由 `platform + architecture + backend_id + host_id + case_id + variant` 唯一标识；既有 `dev-intel` / `install-intel` 行的架构均为 `x86_64`，Apple Silicon 真机新行须明确标为 `arm64`；不同后端、Core/Runner 角色、机器或安装形态不得互相继承结果。`Verified` 只说明该行的具体正例或负例有原始证据，不说明整个 case、候选后端或平台达标。`Failed` 是实际行为违背预期，`Blocked` 是环境或归因阻断，`Not run` 是未执行。应用层 Policy 拒绝不能代替 OS 拒绝。每次运行记录：请求 Grant、真实命令与解析后的可执行文件、期望/实际行为、OS 拒绝或允许依据、子进程树、退出码、产物哈希、签名/安装形态与未覆盖项；公开版本须脱敏。

阶段性结论分为 `runner_only` 与 `core_and_runner`，并在每条新证据中记录覆盖的执行入口。`runner_only` 只汇总命令树的 OS 正反例；`SBX-01` 完整 Core、`SBX-08` Core 网络、`SBX-10` Broker IPC 和内建文件工具的最终边界仍保持各自 `Not run`/`Blocked`，不能继承 Runner 结果。状态显示须分别报告 Core 和 Runner，不用单个 `OS sandbox active` 混写。

通用项目正例与安全负例是同等硬门槛。每组包含允许路径和拒绝路径；仅一侧通过，另一侧仍为 `Not run`。不以用户身份、沙盒名称、应用层路径判断或 Linux/Windows 文档推断 OS 隔离结果。实施与验收先聚焦 macOS，且 Intel（x86_64）和 Apple Silicon（arm64）分别验收；Linux 排第二，Windows 条件性评估且可放弃。Linux/Windows 的 `Not run` 不阻塞 macOS 独立结论，Apple Silicon 的 `Not run` 阻塞 macOS 整体支持声明。

## 共同逻辑用例

| case_id | 有 Grant 的正例 | 无 Grant / 越界负例 | 判定重点 |
|---|---|---|---|
| `SBX-01-core-domain` | 完整 Vera Core 在受限域运行 Agent、Tool、Policy、Recovery | Core 读写其他工程、私有文件或系统配置被 OS 拒绝 | 进程身份、隔离域和完整 Core，非单个探针 |
| `SBX-02-workspace-grant` | 用户动态选择任意工程；限定读写，重启后按授权续用 | 未选工程、过期 Grant 与工作中资源替换被拒绝 | 真实 OS 资源身份与期限 |
| `SBX-03-runner-domain` | Runner 读批准的源码、执行项目脚本并产生后代 | Runner 读 Core 私有状态、Broker 假 Key 或写未批准源码均被 OS 拒绝 | Runner 比 Core 更窄，后代不扩权 |
| `SBX-04-artifact-root` | 仅在批准的外部产物根写入构建结果 | 工作区外其他位置、源码意外写入被 OS 拒绝 | 构建缓存、临时目录和产物实路径 |
| `SBX-05-native-toolchain` | 项目原有命令运行系统 `git`、`xcrun`、编译/测试工具 | 工具链或 Hook 越权读写、联网被 OS 拒绝 | 保留项目既有命令，不改写成直调编译器 |
| `SBX-06-custom-toolchain` | 工程脚本及用户安装在任意位置的工具与其依赖可执行 | 未批准的工具真实路径或依赖资源被拒绝 | 路径解析、脚本解释器、多级构建 |
| `SBX-07-built-binary` | 构建生成的程序按原项目步骤运行 | 生成物执行不获得新的文件、网络或进程权限 | 签名、quarantine、后代继承 |
| `SBX-08-network-default` | Broker 经固定 Provider 通道完成已批准请求 | Core/Runner 直连任意站点、loopback、DNS 或代理被 OS 拒绝 | Core 与 Runner 分别验证网络边界 |
| `SBX-09-network-grant` | 单次项目联网仅到批准目的地与期限 | 改目标、改端口、经代理或后代绕开均被拒绝 | 实际强制范围不可宽于 Grant |
| `SBX-10-broker-ipc` | Core 通过窄接口请求 Provider 或资源，Broker 二次核验 | Runner 或伪造 Core 请求不能读 Key 或调用通用宿主命令 | IPC 身份、方法、参数和目的地 |
| `SBX-11-link-fd-race` | 授权路径稳定时可读写、执行 | 符号/硬链接、别名、挂载、重解析、路径替换、继承 FD 不扩权 | 平台真实资源身份，运行中竞态 |
| `SBX-12-hook-descendants` | Git Hook、安装器、测试子孙进程在批准域完成任务 | Hook/后代不可取得 Core/Broker 权限或逃离隔离 | 整棵进程树与进程组 |
| `SBX-13-lifecycle` | 正常完成后 Grant 收回，恢复只读事实可用 | 拒绝、过期、取消、超时、崩溃、重启不留孤儿或重复副作用 | 失败关闭与可恢复分类 |
| `SBX-14-delivery` | 源码运行、开发构建、独立安装及升级行为一致 | 签名/安装/升级差异不能静默降级或宣称已隔离 | 两台 Intel Mac 与 Apple Silicon 真机分别复验；后续目标 OS 各自复验 |
| `SBX-15-client-facts` | Plain/JSON/TUI 展示同一后端身份、能力与授权事实 | 无后端或能力不足时返回稳定错误，不显示 `OS sandbox active` | Core Command/Event 为单一事实源 |

每个 case 的正反例都必须在同一后端配置下重测。macOS 额外覆盖别名、卷、TCC 与 Gatekeeper；Linux 额外覆盖挂载、`/proc` 与 namespace；Windows 额外覆盖盘符、UNC、reparse point、ACL 与大小写。这些是附加负例，不替代共同矩阵。

## 已迁移结果：macOS / `app-sandbox-static` / `dev-intel`

本候选指任务 0086 的签名 `.app` 固定临时路径授权。下表仍区分 `Core`、`Runner` 和具体配置。原始证据位于 `/private/tmp/vera-sandbox-feasibility.6iMmi7/logs/`，引用文件的 SHA-256 见[0086 记录](core-sandbox-macos-feasibility.md)。原始文件在 2026-09-25 复核时仍存在且四个哈希一致；该临时目录尚非发布夹具。

| case_id / variant | platform / backend_id / host_id | 0086 证据与实际结果 | 状态与覆盖范围 |
|---|---|---|---|
| `SBX-01 / core-outside-read-write` | macOS / `app-sandbox-static` / `dev-intel` | `core-default-outside-read`、`core-default-outside-write`；OS 报 `Operation not permitted` | `Verified`，仅探针负例；完整 Core 未证 |
| `SBX-01 / installed-fake-model` | macOS / `app-sandbox-static` / `dev-intel` | `installed-vera-core`；wheel 的三个离线 Fake Model 用例通过 | `Verified`，仅指定 Core 路径，未证明完整 Core 隔离 |
| `SBX-02 / fixed-workspace` | macOS / `app-sandbox-static` / `dev-intel` | `core-static-workspace`；签名前固定路径可读写，外部仍拒绝 | `Verified`，固定路径变体；动态 Grant `Not run` |
| `SBX-02 / no-user-selection` | macOS / `app-sandbox-static` / `dev-intel` | `core-default-workspace-read`；只声明 entitlement、未选目录时 OS 拒绝 | `Verified`，无 Grant 负例 |
| `SBX-03 / fixed-runner` | macOS / `app-sandbox-static` / `dev-intel` | `runner-static-boundary`；假 Key/秘密读取及源码写入被拒，自定义脚本和后代可运行 | `Verified`，临时固定路径，不代表任意工程 |
| `SBX-04 / artifact-write` | macOS / `app-sandbox-static` / `dev-intel` | `runner-static-boundary`；批准的 artifacts 写入成功，源码写入拒绝 | `Verified`，临时固定路径 |
| `SBX-05 / system-wrappers` | macOS / `app-sandbox-static` / `dev-intel` | `xcrun-wrapper`；`/usr/bin/xcrun` 与 `/usr/bin/git` 返回 `xcrun: error: cannot be used within an App Sandbox.` | `Failed`，通用原生命令硬门槛 |
| `SBX-05 / direct-swiftc` | macOS / `app-sandbox-static` / `dev-intel` | `swift-direct-compile`；直调 `swiftc` 且显式指定 SDK 后编译 | `Verified`，受控直调，不抵消 system-wrappers 失败 |
| `SBX-06 / fixed-custom-script` | macOS / `app-sandbox-static` / `dev-intel` | `core-static-workspace`、`runner-static-boundary`；固定脚本可运行 | `Verified`，任意安装位置与解释器链 `Not run` |
| `SBX-07 / generated-binary` | macOS / `app-sandbox-static` / `dev-intel` | `generated-binary-quarantine`；生成程序因 quarantine 无法执行 | `Failed`，编译后执行工作流 |
| `SBX-08 / no-network` | macOS / `app-sandbox-static` / `dev-intel` | `network-default`；Core 与 Runner 连临时 loopback 均 errno 1 | `Verified`，仅 loopback 拒绝；Broker Provider 通道 `Not run` |
| `SBX-08 / core-network-client` | macOS / `app-sandbox-static` / `dev-intel` | `core-network-client`；加 entitlement 后 Core 可连 loopback | `Verified`，证明联网授权过宽，非固定目的地通过 |
| `SBX-10 / broker-unix-socket` | macOS / `app-sandbox-static` / `dev-intel` | `broker-unix-socket`；两种配置均 errno 1，原因未归因 | `Blocked`，不能推断全部 IPC 不可用 |

`SBX-02` 动态资源、`SBX-06` 任意自装工具、`SBX-09`、`SBX-11` 至 `SBX-15` 均未完成；部分 `SBX-01`、`SBX-03`、`SBX-05`、`SBX-08` 和 `SBX-10` 仍缺正反例。第二台 Intel Mac 安装态 `Blocked`。上述固定路径候选的 `Failed` 不自动否定独立身份、VM 或其他后端。

## 临时对照：macOS / `seatbelt-same-uid-control` / `dev-intel`

[0087 预检](core-sandbox-alternative-preflight.md)在同一 UID 上运行了两种 `sandbox-exec` 配置，仅用于比较 OS 行为。`research.sb` 默认允许其他文件，不能当沙盒通过；`runner-v5.sb` 采用固定路径拒绝默认策略，但 `sandbox-exec` 本机手册已标为 deprecated，且未覆盖完整 Core、独立身份或安装态。

| case_id / variant | 平台 / 后端 / 机器 | 实际结果 | 状态 |
|---|---|---|---|
| `SBX-01 / world-readable-fake-secret` | macOS / `seatbelt-same-uid-control` / `dev-intel` | `runner-v5.sb` 下 `/bin/cat` 被 OS 拒绝 | `Verified`，单文件负例 |
| `SBX-04 / fixed-artifact-root` | macOS / `seatbelt-same-uid-control` / `dev-intel` | 临时 artifacts 写入成功，workspace 新文件被 OS 拒绝 | `Verified`，固定路径变体 |
| `SBX-05 / system-wrappers` | macOS / `seatbelt-same-uid-control` / `dev-intel` | `xcrun --find swiftc`、系统 `git --version` 均返回 0，但都报 `xcrun_db-*` 缓存创建拒绝 | `Blocked`，真实工具链成功条件未达到 |
| `SBX-05 / no-cache-option` | macOS / `seatbelt-same-uid-control` / `dev-intel` | `xcrun_nocache=1`/`--no-cache` 下转调 `xcodebuild -find`，SDK 初始化及 Git 工具定位失败 | `Failed`，该绕行不满足原生命令通过 |
| `SBX-08 / loopback-deny` | macOS / `seatbelt-same-uid-control` / `dev-intel` | `nc` 退出 1，OS 日志为 `network-outbound remote:*:9` 拒绝 | `Verified`，仅 loopback 负例 |
| `SBX-12 / project-script-descendants` | macOS / `seatbelt-same-uid-control` / `dev-intel` | 假项目脚本启动 `cat`/`bash`/`nc` 后代；OS 分别拒绝假秘密读取、workspace 写入与出站网络，artifact 写入允许 | `Verified`，固定路径同 UID 子进程负例；不代表独立身份或完整 Core |
| `SBX-03 / dynamic-temp-path-file-boundary` | macOS / `seatbelt-same-uid-control` / `dev-intel` | 新临时路径 profile 下，后代 `cat` 读取假秘密和 `bash` 写 workspace 均收到 `Operation not permitted`；artifact 写入成功 | `Verified`，仅研究 profile；不是产品动态 Grant |
| `SBX-08 / dynamic-temp-path-loopback` | macOS / `seatbelt-same-uid-control` / `dev-intel` | `nc` 退出 1；本次未取得匹配的 OS 拒绝日志 | `Not run`，不能排除端口未监听 |
| `SBX-05 / separate-identity-native-baseline` | macOS / `separate-identity-plus-os-policy` / `dev-intel` | 非管理员 UID 502 可读 world-readable 假秘密；`git --version` 与 `xcrun --find swiftc` 成功，环境为假 `HOME`/`TMPDIR` | `Verified`，仅基线，不代表隔离策略通过 |
| `SBX-03+08 / separate-identity-seatbelt-startup` | macOS / `separate-identity-plus-os-policy` / `dev-intel` | profile 启动对目标脚本与 `/usr/bin/true` 两次以 SIGABRT（134）退出；移除冗余网络拒绝规则后仍复现 | `Blocked`，profile 崩溃根因未知；文件与网络用例 `Not run` |

这些行不能与 `app-sandbox-static` 合并计算。`separate-identity-plus-os-policy` 只有无沙盒工具/ACL 基线通过，OS 策略验证因启动崩溃而 `Blocked`。子进程原始结果哈希见[预检记录](core-sandbox-alternative-preflight.md#固定路径子进程树对照)。

## 其他后端和平台

| platform | backend_id | host_id | 状态 | 下一证据门槛 |
|---|---|---|---|---|
| macOS | `command-tree-seatbelt-candidate` | `dev-intel` | `Blocked`（现成 runtime） | 用户已授权首轮试验；Shell 启动通过，系统 Git/xcrun 发现路径与宿主缓存访问失败。编译、文件/网络与后代矩阵 `Not run`；已停止清理，见[试验记录](core-sandbox-srt-minimal-probe-2026-09-26.md) |
| macOS | `separate-identity-plus-os-policy` | `dev-intel` | 账户基线 `Verified`；组合策略 `Blocked` | UID 502 可读 world-readable 假秘密；UID/ACL 单独不具备完整边界，架构选型否决。附加 Seatbelt 策略启动崩溃，不把未验证组合标为通过 |
| macOS | `xpc-sandboxed-runner-service` | `dev-intel` | 夹具 `Blocked` | ad-hoc 宿主启动，嵌入服务查找 error 3；Runner 边界未运行。架构审阅结合 Apple 约束和 0086 工具链失败，不推荐 App Sandbox 为通用原生 Runner，停止继续修复此夹具；XPC 仍可作 IPC |
| macOS | `seatbelt-same-uid-control` | `dev-intel` | `Verified` / `Blocked`，仅临时对照 | 缓存、任意工程、完整 Core、受支持发行机制均未通过 |
| macOS | `vm-native-project` | `dev-intel` | `Not run` | Intel host 上原生 macOS 项目可运行及 host 文件/网络拒绝 |
| macOS | `app-sandbox-static` | `install-intel` | `Blocked` | 第二台 Intel Mac 独立安装环境 |
| macOS | 待选后端 | `install-apple-silicon`（arm64） | `Not run` | Apple Silicon 真机的共同正反例、原生工具链、签名、独立安装与升级；Intel 结果不可继承 |
| Linux | `landlock-runner` | `unavailable` | `Not run` | ABI 协商、继承 FD、文件/网络语义与目标发行版完整矩阵 |
| Windows | `appcontainer-runner` | `unavailable` | `Not run` | 支持的系统构建、Broker 启动、路径/网络 Grant 和后代工具链 |
| Windows | `experimental-createprocessinsandbox` | `unavailable` | `Not run` | Windows 11 实验 API 可用性、外部 Broker 派生与兼容性；不得作为默认后端

任何平台在全部共同用例与本平台附加负例通过前均不得声明 `OS sandbox active` 或 `Supported`。文档候选不等于已选产品后端。矩阵中的 `unavailable` 表示当前没有可确认的对应目标测试机。
