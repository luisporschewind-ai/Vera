# 0089 Apple 工具链修复与实测结果

**日期：** 2026-09-28
**状态：** 根因修复与 Intel 假工程最终生产 backend 验收已通过；0089 其余跨语言、CLI 和生命周期项目仍在 In progress。
**边界：** 本记录属于任务 0089，采用 Accepted 工作区权限规格，不新增任务编号。

**2026-09-28 用户新决定：** [Apple iOS 构建系统服务规格](../specs/2026-09-28-apple-ios-build-service-boundary.md)已接受，允许经单次构建审批开放 Core 维护的精确服务集合；不要求先证明完整独立 device set，但必须披露可能访问当前用户模拟器状态。最终生产 SRT backend 假工程构建与审批聚焦回归已通过；整体 0089 尚未完成。

## 2026-09-28 根因收口与当前交付（覆盖此前未验证假设）

**规格已接受；Core 单次授权与产物卷已接通。最终生产 SRT backend 假工程 build、审批展示与拒绝路径、卷清理及外部读取拒绝均已聚焦验收通过；0089 其余门槛仍 In progress。**

三个独立阻塞已由定向证据区分：

1. **simctl 崩溃：缺少 ICU 数据读取。** `/usr/share/icu/icudt76l.dat` 被拒时，最小 Foundation 程序日期格式器返回 NULL；只增加此文件只读后恢复。`simctl` 随后 exit 0。崩溃位于日期格式器，与继续增加 Mach 名称无关。
2. **Xcode 原子写入：已签名工具忽略临时目录后缀。** 内核明确拒绝宿主共享 `T/TemporaryItems/NSIRD_xcodebuild_*` 的创建；不是工作区不可写，也不是私有符号链接缺少写权限。此前猜测的链接写规则已撤回。将 DerivedData 放入独立 APFS 产物卷后，EPERM 降为 0：Foundation 的替换目录改为目标卷内，不必开放宿主共享 T。
3. **运行时发现：目录枚举与 Intel 启动服务分别不足。** 两个获批 bundle 内容可读，但祖先目录不能列出条目。只给这些祖先目录节点 `file-read-data + DIRECTORY + literal` 后，iOS 26 运行时可见但不可用；日志指向 `com.apple.CoreSimulator.SimLaunchHost-x86`。只加入这个精确第六服务后，运行时变为 available。

组合修复的真实 SRT 假 `VeraTestDemo` 构建耗时 29.57 秒，**BUILD SUCCEEDED / exit 0**，Main 和 LaunchScreen Storyboard 均编译通过，`cleanup_error=null`，产物卷正常卸载、假工程夹具删除。`supported platforms ... empty` 仍作为警告出现，因此不能再把该句单独当作失败根因。未授权的其他 device type 仍有 Malformed bundle 警告，不为消除警告扩大读取。

### 已接入代码与产品行为

- 六个服务通过固定 SRT 0.0.77 正式 `allowMachLookup` 接口，仅对获批的单次 unsigned generic iOS scheme build 生效。第六项限 Intel；Apple Silicon 实机继续延期封存，不声称已支持其完整服务链。
- Core 在批准后创建临时 APFS 稀疏镜像（逻辑容量上限 8 GiB，随使用增长），追加受审的 `-derivedDataPath`；审批展示该转换及产物销毁策略，绑定固定存储方案。结果区分原始 argv 与实际执行 argv。
- 此路径不接受用户指定的 DerivedData/result bundle/主要输出覆盖项，也不接受 target/test/archive 等其他动作；不偷偷覆盖用户输出路径。构建产物会销毁、无跨构建增量缓存。超出容量或挂载失败明确失败，不退回无沙盒。
- 镜像文件在子进程授权范围外，仅挂载卷授权。退出后精确卸载再删除，卸载失败保留现场并报告清理失败；不用强制卸载或扫描删除旧残留。
- `directory_listable` / `--list-directory` 是显式用户配置的目录节点列举权限，不读取子文件内容。ICU、两个 bundle 与工具链的递归只读仍独立审批，没有随服务能力自动授予。普通配置未改。

### 2026-09-28 最终接入聚焦验收

用户随后明确要求由 Codex 承担测试，故完成以下与本问题直接相关的最小验收：

| 验收 | 结果 |
|---|---|
| 最终 `SrtBackend` + 真实 SRT + 临时假工程 | `BUILD SUCCEEDED`，exit 0；Main/LaunchScreen Storyboard 构建通过；`cleanup_error=null` |
| 执行及产物清理 | Core 生成的 effective argv 含独立 APFS 卷下的 `-derivedDataPath`；执行后卷卸载并删除，夹具无 `vera-apple-build-*` 残留 |
| 文件边界 | 构建后在同一 SRT 会话中读取工作区外 `/private/etc/passwd`，exit 1、拒绝 |
| 审批展示回归 | `tests/sandbox/test_approval_presentation.py`：7 passed；覆盖 once、Intel 六服务、卷容量/销毁披露、后代继承及模拟器风险、HumanPresenter 渲染、批准后能力传递 |
| 拒绝审批 | FakeModel 产生审批后选择 `reject`；执行器调用数 0，范围 `once`、服务数 6 |

构建直接走最终生产 backend；审批链用 FakeModel/RecordingSupervisor 验证，HumanPresenter 用真实结构化审批事件渲染。未运行模型 API、全量套件、CLI 人工交互、取消/超时卷卸载测试。Ruff 与 `git diff --check` 通过。证据与后端复现入口保存在 `docs/evals/artifacts/0089-apple-toolchain-2026-09-28/ios-root-cause/`。

**判定：** 当前 Intel 假工程构建问题已在最终产品后端路径复现通过；用户最初的阻塞已解决。0089 整体仍为 In progress：取消/超时期间卷清理、实时 CLI Apple 构建、C Xcode 清理复验及其余代表语言矩阵尚未收口。常规 VerificationRunner Ruff 成功/失败/越界拒绝闭环已通过，但 Apple 服务能力未接入该入口。Apple Silicon 按用户决定延期。普通配置、主线、原始工程及宿主安全设置未改；未安装软件、合并或推送。本任务代码与文档已提交至 `codex/0089-sandbox-apple-build`。旧 TemporaryItems 残留仍单独登记。

## 以下为历史阶段记录（最新结论以上节为准）

## 授权与执行范围

用户要求直接完成修复并批准后续必要操作。本轮在隔离工作树实现；仅使用临时假工程、已有测试副本和既有工具链。工具链临时读取范围包含 `/Applications/Xcode.app`、`/usr/share/firmlinks`、`/Library/Preferences/com.apple.dt.Xcode.plist`、`/Library/Developer/PrivateFrameworks`、`/Library/Apple/System/Library/PrivateFrameworks`，后三类分别用于系统元数据与已安装工具链的框架依赖。文件读授权不授予框架所能调用的系统服务。

普通用户沙盒配置未保存这些临时权限；未安装软件、接受许可证、修改系统开发工具选择或宿主安全设置，未启用网络、签名、设备、模拟器服务。未提交、合并或推送。原始工程未修改。

## 定位与修复

1. **工具链选择与资源读取。** `developer_dir` 由可信设置显式提供，必须位于已批准读取范围内，且不能与可写范围交叠；不继承项目注入的同名环境变量。增加 CLI 对应配置入口。
2. **系统路径别名。** `/tmp`、`/var`、`/etc` 的符号链接节点不符合上游目录型元数据规则，造成工具误报工程不存在。补充仅这些链接的元数据读取；已批准的系统 shell selector 也仅补链接节点读取，不开放父目录。
3. **SDK 查询崩溃。** Xcode 文件路径初始化在缺少 `/usr/share/firmlinks` 时出现 DVTFilePathEventWatcher 崩溃。临时授权该系统元数据后 SDK 查询成功；没有保留 FSEvents 服务放权。
4. **构建缓存。** 保留 Core 已准备的安全缓存变量，路径必须位于可写根内；显式隔离 HOME、TMPDIR、xcrun 缓存、Clang/Swift 模块缓存。Foundation 使用的系统 T/C 目录通过每次唯一的 `DIRHELPER_USER_DIR_SUFFIX` 对应到本次专用目录，后代仍在外层 SRT 内。
5. **进程监督。** 选定 Apple 工具链时使用 ibtool 直接执行模式，避免默认池化服务器脱离监督组；不据此宣称所有 Apple 子进程形态都已覆盖。
6. **正式验证。** Runner 使用审批后的超时值，取消隐藏的 120 秒截断；正式 SwiftPM/Xcode 产物计划补充模块缓存位置。
7. **错误事实。** 新增结构化 `cleanup_error`。执行后的清理错误保留实际退出码、stdout、stderr，并返回 `sandbox_cleanup_failed`；不通过猜测 stderr 判断状态，不再把已经执行的命令描述为未启动。

## 当前证据

原始结果和复现脚本保存在 [证据目录](../evals/artifacts/0089-apple-toolchain-2026-09-28/README.md)。均为 Intel macOS、真实 SRT 执行；自动 harness 不替代 CLI 人工审批体验。

| 验证 | 事实 | 判定 |
|---|---|---|
| xcrun / Xcode SDK 枚举 | 查询成功；无需 FSEvents Mach 服务权限 | 本次查询通过 |
| 无远程依赖 SwiftPM XCTest | 原始执行 exit 0、1 个 XCTest 通过，但当时清理失败；临时目录修复后重新运行，1 个 XCTest 通过，exit 0、产物根 cleaned、工作区无 `.build` | 本次 Intel 假工程复验通过；原始失败记录保留 |
| 原生 Xcode C 命令行工程 | 最终生产 Planner 输出直接交给 Runner/SRT，`BUILD SUCCEEDED`、进程 exit 0；产物根 cleaned、workspace_mutations 为空 | 构建通过；整体结果仍 error / sandbox_cleanup_failed |
| iOS VeraTestDemo 测试副本 | Storyboard 编译失败，日志含 CoreSimulator 服务不可用和 Platform Not Installed | 未通过；不能仅据该提示认定宿主未安装 SDK |
| 边界回归 | 工作区读取成功；外部读、外部写、后代读均拒绝，标记未改且外部目标未生成 | 本轮有限边界通过 |
| 定向测试 | sandbox toolchain/backend/Git compatibility、verification runner、bash 共 48 passed | 通过；未运行全量 |
| 静态检查 | Ruff check、16 文件格式检查、8 源文件 Mypy | 通过 |

SwiftPM 测试 argv 显式包含 `--disable-sandbox`，仅避免 SwiftPM 自己的 manifest 内层沙盒与已生效的外层 SRT 冲突。Vera 的命令及后代 OS 边界未关闭；不自动替换用户命令或偷偷增加该参数。

Xcode 在 Intel 主机编译了 x86_64/arm64 目标，不代表 Apple Silicon 实机验收。用户延期安排继续有效。Xcode 成功构建仍伴随专用 HOME 中 DerivedData 日志/info 写入警告，不将其描述为完全兼容。

### 2026-09-28 补充诊断

- 宿主基线 `/usr/bin/xcrun simctl list runtimes` 正常退出 0，列出 iOS 17.4 与 iOS 26.0。临时 VeraTestDemo 副本以 `-scheme VeraTestDemo -sdk iphoneos -destination generic/platform=iOS` 在宿主直接构建成功（exit 0）。因此本机 SDK 与模拟器运行时已安装，先前的 “iOS 26.0 Platform Not Installed” 不是宿主缺少平台的证据。
- SRT 下对两个确切 CoreSimulator bundle 的递归只读授权消除了 `Malformed bundle` 日志，但 Storyboard 仍报 `Platform Not Installed`。再对诊断进程临时放行指定 CoreSimulator Mach 服务后，构建仍失败；`xcrun simctl list runtimes` 在同一临时隔离内以信号 -11 退出。继续临时加入 FSEvents Mach 名称后，`simctl` 仍以 -11 退出。探针未启动/修改模拟器设备，也未写入产品沙盒规则。
- `simctl --set <测试工作区路径> list runtimes` 宿主基线成功，测试设备集没有产生设备；同一命令在 SRT 内、指定服务临时放行后仍以 -11 退出。将设备集重定向到假路径不足以修复服务连接。
- 一次只读的 `xcodebuild -showBuildSettings` 未指定 destination，Xcode 枚举并输出了宿主物理设备信息；未执行设备操作，也未把设备名/标识写入证据。后续验收必须显式使用 `generic/platform=iOS`，不得使用会枚举宿主设备的缺省 destination。
- 这说明仅加文件读取规则或一个已知 Mach 服务不足以修复；继续增加系统服务权限会扩大沙盒能力。当前 Accepted 规格没有建模此类按命令审批的服务授权，因此本轮不加入默认放行规则。需要先定义明确、可审阅、按命令生效的系统服务权限与撤销行为，才可实现此能力。
- 新临时目录布局后的 iOS 假工程复验：`-target` + `-destination generic/platform=iOS` 仍在 Storyboard 阶段 exit 65；`cleanup_error=null`、产物根 cleaned，排除了旧 scratch 清理失败对结果的混淆。按本机 `xcodebuild -help` 的命令形式，另以与宿主成功基线相同的 `-scheme VeraTestDemo -destination generic/platform=iOS` 复验：仍 exit 65，失败提前到目标平台解析（supported platforms 为空），没有进入 Storyboard；CoreSimulatorService / simdiskimaged 连接错误仍在。两次日志分别 6 次与 2 次引用真实用户的 CoreSimulator Devices 路径，尽管 destination 为 generic；这不证明已经更改了设备，但足以说明不能假设它使用独立假 device set。两项都使用临时假工程副本、关闭签名，没有连接物理设备。
- 只读 `simctl --set <空假 device set> list runtimes` 在诊断 profile 中仅对 `com.apple.CoreSimulator.CoreSimulatorService` 与 `com.apple.CoreSimulator.simdiskimaged` 添加精确 Mach lookup，仍以信号 `-11` 退出，stdout 空，假 device set 没有生成设备，执行 scratch 清理正常。该次进程的系统日志还出现 FileCoordination、FSEvents、coreservicesd 等受限访问，说明两个 Mach 名称不是完整依赖清单；不能据此推断继续逐项放权一定可行。安全摘要见[诊断证据](../evals/artifacts/0089-apple-toolchain-2026-09-28/ios-service-boundary-diagnostic.json)。本机 Xcode 26 的 `ibtool` 不接受 `--cocoatouch-compiler-mode`，不能借用新版本的该选项绕开当前路径。
- 用户允许按单次操作申请系统服务后，又执行了两项限定诊断：空假 device set 的只读 `simctl list runtimes` 在五个精确服务（CoreSimulatorService、simdiskimaged、FileCoordination、FSEvents、coreservicesd）以及补充 cfprefsd agent/daemon 后，均仍 exit `-11`，stdout/stderr 空，设备集为空且 scratch 清理成功。相同隔离环境变量下的宿主只读对照 exit 0。五服务下、关闭签名的假工程 `-scheme` generic iOS 构建仍 exit 65，supported platforms 为空；此次不再出现 CoreSimulatorService 字样，但 DerivedData info/log 写入报 EPERM。相同 SRT 中 `/private/tmp` 与 `/tmp` 别名下的普通 `touch` 均 exit 0，因此不能把 Xcode 的 EPERM 简化成整个工作区不可写。诊断脚本保存在证据目录，仅使用临时副本，未写普通产品 profile、未启动设备。
- 经用户批准的后续窄诊断见[新增证据](../evals/artifacts/0089-apple-toolchain-2026-09-28/ios-followup-diagnostic.json)。指定 `simctl` 崩溃报告的故障线程在 CoreFoundation `_CFGetNonObjCTypeID → CFDateFormatterSetFormat → CFDateFormatterCreateISO8601Formatter`，调用来自 Foundation `NSISO8601DateFormatter` 与 CoreSimulator utility；为 `EXC_BAD_ACCESS/SIGSEGV`，不能据此断言 Mach 服务拒绝是根因。仅在一次临时假工程诊断中对 iPhone 16e device type 与 iOS 26 runtime bundle 递归只读，并保留五个先前服务后，`Malformed bundle` 和 CoreSimulator/simdiskimaged 日志消失；`xcodebuild` 仍 exit 65，supported platforms 为空，输出含 10 个 `Operation not permitted` 文本标记，且日志显示 DerivedData 日志 manifest 写入被拒；产物与执行 scratch 清理成功。之后同版 SRT 下在预建的 `DerivedData/Logs/Launch` 执行嵌套 `touch` 与同目录 `mv` 均 exit 0，说明一般嵌套创建/重命名可用。代码检查发现该次构建的 HOME/DerivedData 位于 Foundation 的 `T/<本次后缀>` 路径，而 profile 只对其私有 symlink 节点授予读取；已补充仅针对该精确节点的 `file-write*` 规则，目标仍是本次私有 scratch。此为与日志吻合的根因假设，最终规则尚未重跑，不能称构建已修复。后续 Xcode/simctl 验收由用户执行。
- **服务授权机制已实现，构建仍失败。** `BashTool` 仅将明确的项目/方案 `xcodebuild -sdk iphoneos -destination generic/platform=iOS ... build` 且显式关闭签名的动作标记为 `apple_ios_build_services`；Policy 硬拒绝优先，强制每动作审批且只提供 `once`。审批绑定 argv、cwd、timeout、workspace、policy hash、五服务集合和解析后的 `xcodebuild` 路径；恢复校验只接受 Core 固定服务名。审批展示五个精确服务、命令及后代继承、可能访问当前用户模拟器状态。执行器只在该动作获批后设置进程能力；SRT backend 再校验选定 `DEVELOPER_DIR/usr/bin/xcodebuild` 身份，通过固定 0.0.77 正式 `allowMachLookup` 接口传入五个 Core 名称，默认 profile 仍无这些服务。其他命令（含 `simctl`）不能获得该能力。聚焦回归 91 passed，Ruff、格式、15 个源文件 Mypy、`git diff --check` 通过；真实 profile 只生成并检查，没有执行 Xcode。没有更改普通沙盒配置。
- 旧清单中的 8 个 Core 专用临时根均留下 `TemporaryItems` 节点。已逐一移除这些明确归属本任务的 `home` 与 `cache` 子目录；根目录 `rmdir` 均返回 `ENOTEMPTY`，宿主 `find` 进入一个确切的 `TemporaryItems` 也收到 EPERM。不会声称已完整清理，也不尝试移除 provenance 元数据或改变系统设置。普通临时文件及一般目录的清理探针仍通过，但这不能覆盖 Apple 管理的该节点。直接宿主基线构建产生的专用 DerivedData 与错误 ResultBundle 已删除。

## 尚未解决及后续完成条件

### 1. 系统临时目录清理：新执行已修复，旧残留未清除

原布局把每条命令的 scratch 直接建在 Darwin `T` 下。系统工具产生 `TemporaryItems` 后，普通目录删除、Python 和 Foundation 删除均返回 EPERM。旧布局的 8 个已登记残留根仍在[清单](../evals/artifacts/0089-apple-toolchain-2026-09-28/retained-temporary-roots.json)中，未尝试更改系统保护或删除它们；尚未证明拒绝由 TCC、DataVault 或其他特定系统机制引起。

新布局在每条命令的私有 `T/vera-scratch-*` 容器内建立 `vera-command-*` 实际目录，仅在 `T` 顶层建立同名精确符号链接，让 Foundation 的 `DIRHELPER_USER_DIR_SUFFIX` 落到该实际目录。沙盒只新增此链接节点的精确只读规则，实际目录仍按原有 scratch 规则授权；清理按顺序移除执行内容、链接和容器。假目录真实 SRT 复现中，命令 exit 0、`cleanup_error=null` 且容器/链接/缓存均消失；链接节点未授权时 SwiftPM 报 `couldNotFindTmpDir`，补充精确节点只读后，已有临时 SwiftPM XCTest 脚本重新运行，1 项测试通过、exit 0、产物根 cleaned、无工作区 `.build`，证据为[进程结果](../evals/artifacts/0089-apple-toolchain-2026-09-28/swiftpm-scratch-cleanup-process-result.json)与[验证结果](../evals/artifacts/0089-apple-toolchain-2026-09-28/swiftpm-scratch-cleanup-result.json)。同版后端下外部假文件读取仍为 EPERM，stdout 空；浅层检查未发现新 `vera-scratch-*` 残留。

这解决了新执行的该类清理失败，不追认旧失败，也不把旧受保护根称为已清理。正式 VerificationArtifactPlan 产物根与执行 scratch 是两项独立清理结果。取消路径与更多 Apple 工具的组合仍须按 0089 总验收检查；本节不宣称全量 macOS 工具链兼容。

### 2. iOS Storyboard / 模拟器服务（历史调查）

后续内容是早期失败和当时假设，仅保留作调查记录；最新根因和通过证据见本文开头。

## iOS 子问题判定

Intel 假工程 iOS 构建阻塞已由最终生产 SRT backend 复验通过，不需要启动独立 macOS VM。剩余 Apple 子项为实时 CLI 构建流程，以及 APFS 卷取消/超时清理验收；Apple Silicon 按用户决定延期。通用 Coding Agent 的 iOS/Swift 目标保留。

## 后续未验收边界

- 未测试取消/超时期间的 APFS 卸载清理。
- 未做实时 CLI 会话人工验收；审批事件由 FakeModel 构造，HumanPresenter 展示回归已通过。
- 常规 SRT VerificationRunner 成功/失败/越界闭环已通过，但没有 Apple 服务审批路径。
- Apple Silicon 实机验收仍按用户决定延期。
