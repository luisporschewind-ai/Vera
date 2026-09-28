# Apple iOS 构建系统服务授权边界

**状态：** Accepted（2026-09-28，用户明确要求允许此类系统服务授权并解决构建阻塞）；Intel 假工程最终 SRT backend 构建与聚焦审批验收通过，实时 CLI 与取消/超时清理仍待验收。
**关联：** [任务 0089](../tasks/0089-apple-toolchain-repair.md)、[已接受的工作区权限规格](2026-09-26-workspace-permission-sandbox.md)。

## 2026-09-28 已证实的实现路径

真实 SRT 假工程组合诊断已完整构建 exit 0，历史失败原因及证据见任务 0089。产品接入采用每次可销毁 APFS 产物卷，避免 Apple 签名工具在共享宿主临时目录创建原子替换文件。Core 为批准的 scheme build 追加 `-derivedDataPath <owned-volume>/DerivedData`；审批必须展示这个固定转换、8 GiB 逻辑容量及结束销毁产物/缓存，绑定存储方案，并在执行结果保留原始与实际 argv。拒绝显式输出覆盖及非 build 动作；挂载/卸载失败明确报告，不退回其他执行方式。

文件授权仍独立：ICU 数据与指定 runtime/device type bundle 只读；显式祖先目录权限只允许列出该目录节点，不递归读取子内容。Intel 固定服务集合增加已证实需要的 `com.apple.CoreSimulator.SimLaunchHost-x86`，不猜测 ARM 服务名。最终接入代码尚待用户生产流程验收；以下诊断描述为先前背景。

## 问题与目标

Vera 需要在指定工作区内完成真实 iOS 工程构建，同时保持项目命令及后代的文件、网络和系统能力边界。Intel macOS 上，假 `VeraTestDemo` 副本使用 `-scheme VeraTestDemo -destination generic/platform=iOS`、关闭签名，宿主构建成功。新临时目录布局已消除执行 scratch 清理错误；当前 SRT 下用 `-target` 的构建在 Storyboard 阶段报 `iOS 26.0 Platform Not Installed`，改用与宿主一致的 `-scheme` 后，在目标平台解析阶段报 supported platforms 为空，仍未进入 Storyboard 编译。两次都伴随 CoreSimulatorService / simdiskimaged 连接失败。平台文件实际已安装，不能提示用户重复安装。

对两个精确服务名临时放行后，带空假 device set 的只读 `simctl list runtimes` 仍以信号 `-11` 退出。同期本机日志还显示 FileCoordination、FSEvents、coreservicesd 等受限访问。这个结果只证明两个服务不足，不证明继续增加服务既足够又安全。两次沙盒内 `xcodebuild` 日志都引用真实用户的 CoreSimulator Devices 路径，尽管 destination 为 generic；没有证据表明它会使用独立假 device set。当前 `xcodebuild -help` 没有独立 device set 参数；`simctl --set` 仅证明 `simctl` 可接受该参数，不能证明 `xcodebuild`、`ibtoold` 使用同一设备集。本机 Xcode 26 的 `ibtool` 不接受 `--cocoatouch-compiler-mode`。

## 授权边界与实现条件

用户决定允许经明确审批接入 Apple 构建所需系统服务。原 Draft 要求先证明 Xcode 全命令树使用独立模拟器设备集，才允许此授权；此条件现改为风险披露与验证目标，而非授权机制的前置门槛。generic destination 下 Xcode 仍引用真实用户的 CoreSimulator Devices 路径。审批必须如实告知：服务进程可能访问或改变当前用户的模拟器状态，Vera 的文件沙盒无法约束服务进程内部行为，取消进程也不能回滚服务端副作用。

Core 增加可审批的 `apple_ios_build_services` 具名能力时，须满足：

1. **独立权限类型。** 工作区、文件、工具链只读授权及普通命令审批均不隐含系统服务权限。默认拒绝；不能由模型、项目内容、环境变量或命令参数提交任意服务名。具名能力只适用于经 Core 识别的指定构建操作。
2. **有限服务集合。** 从日志与最小探针逐项确定必需的精确 Mach 服务名及可见副作用，由 Core 维护固定清单；不采用通配符、`mach-lookup` 全开放、宿主无沙盒执行或默认放行。服务集合不足时报告后端不支持，不以宽泛放权凑通过。
3. **Core 审批契约。** 授权只针对一条经 Core 绑定的构建操作，`scope=once`，绑定 argv、cwd、工作区与工具链身份、超时及策略版本；不延续到其他命令或会话。审批卡列出具名能力、服务清单、命令及后代继承范围、可能触及的当前用户模拟器状态。用户拒绝、绑定失效或无法生成精确规则时不以服务权限启动进程；批准后仍保留原文件和禁网规则；撤销、取消、超时终止整棵受监督进程树。服务端已发生的副作用须如实报告，不能声称进程终止可回滚服务状态。
4. **受限命令。** 只允许用户明确选择的 Xcode 可执行文件和 `generic/platform=iOS` 的假工程/受审工程构建；测试阶段禁用签名、联网、物理设备和模拟器启动。`simctl` 只可用于临时只读诊断，不能据其成功宣称 Xcode 构建可用。项目脚本及编译器插件继续继承沙盒，不能被 Xcode 服务许可转换为无限制执行。
5. **验收。** 假工程 Storyboard 全量构建 exit 0，产物及执行 scratch 完整清理，工作区外**直接**读写和网络仍被拒绝；批准 A 不开放其他系统服务；拒绝、撤销、取消、超时均有真实进程与文件证据。系统服务可能代为访问宿主资源，文件沙盒负例不证明服务端绝对隔离。再分别验证真实工程副本与 CLI 审批展示。Intel 结果不代替已封存的 Apple Silicon 验收。

## 若首选条件不成立

当前 SRT 后端对需要 CoreSimulator 服务的 iOS 构建保持明确的“不支持”，直到有限服务集合与假工程构建得到实测。不得把 `Platform Not Installed` 误写成宿主缺少 SDK，也不得暗中退回宿主执行。若该后端仍不能完成构建，另立 Apple 工具链专用执行后端评估独立 macOS 用户会话或含 Xcode/运行时的可销毁 macOS 虚拟环境。它们需要另行审阅宿主改动、性能和清理证据，不作为本规格已实现能力。

## 决策与当前进度

用户已允许实现**按单次构建审批**的系统服务授权；不将服务加入其他命令的默认规则。历史 `simctl` 崩溃探针已由 ICU 根因对照解释。Intel 最终生产 SRT backend 假工程 Storyboard 构建通过，APFS 卷清理与外部读拒绝通过；Apple 审批展示回归 7 passed、拒绝零执行。实时 CLI 人工流程及取消/超时卷清理仍待验收；Apple Silicon 实机延期。
