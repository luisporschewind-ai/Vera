# Core 执行沙盒：Intel macOS 可行性记录

**状态：** 本机原型已收口；整体可行性 `Blocked`，尚无后端选型结论
**规格：** [Core 执行沙盒与通用项目能力边界](../specs/2026-09-24-core-execution-sandbox.md)
**计划：** [任务 0086](../tasks/0086-core-sandbox-feasibility.md)
**执行方式：** 2026-09-25 用户选择 Native；只运行仓库外、假数据原型

## 环境与证据口径

- 开发机：`x86_64`、macOS `15.7.9`；Xcode 选择路径 `/Applications/Xcode.app/Contents/Developer`，Swift 编译器为其中 `Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc`，签名工具为 `/usr/bin/codesign`。
- 临时原型根：`/private/tmp/vera-sandbox-feasibility.6iMmi7/`。所有哨兵、可执行探针、签名包和日志均位于该根；无真实 Provider Key、其他工程或用户秘密。
- 原始证据：临时 `logs/baseline.json`（SHA-256 `2d6dbe6bf01935e3c01c457762b3140f5f3a340108c5e92291ca8bbb731344a9`）、`logs/probe-results.json`（`35dc6bdff9e62e84586c2ca85469e7ec32df4327395ecf3acb9ab47f0461add8`）、`logs/chain-results.json`（`f5e19670972c11196566171bb2f628e316cb3853efb67a0b7979933c5593e9a6`）与 `logs/quarantine-control.json`（`bcf2c1e811d9fc0d945ba71b8406a8e9b9c010e058f07a8f551c4bad55a8283e`）。后三者记录完整 argv、退出码或 OS errno、标准输出和错误输出；记录的环境变量只有临时 `HOME`、`TMPDIR`、`PATH` 与禁用 bytecode 的开关。它们是临时证据，清理前须另行决定是否将脱敏版本纳入正式评测夹具。
- 独立安装机：先前记录为第二台 Intel Mac，本轮尚未取得其实际版本与运行环境，结果暂记 `Blocked`。
- Linux 与 Windows：本记录没有运行原型，均为 `Not run`；macOS 的通过或失败不能推断两平台的后端表现。
- 原型版本哈希：初版 `ProbeV1.swift` 为 `6a438c3b4fd40b4c89ce275e064b772e5bcd9dc192fa2c6fdc46d8ae3acf58fd`，含 Unix socket 的 `ProbeV2.swift` 为 `d4a0e7d2e7f4f0c6031ab5983c030bd519425d806799861b4f23dfbce8638ccd`，最终 `Probe.swift` 为 `cd2c2b23f0c10d11a923fed4d3c1b63d99fa722a68b3e209ae43c84d9da9d46c`；离线 Fake Model 使用的 wheel 为 `377213c2801d5fd318a7a7217b963909dd42838f92dde4e69c6fa70b50fe5454`。`CoreStatic.entitlements`、`CoreNetwork.entitlements`、`RunnerStatic.entitlements` 的 SHA-256 依次为 `f1d9e1c040160a90fe6e5451652ba695eb366a2a554d7dba7aa3b74bb068ca59`、`2c376f7d837ca11c103de2ee02bb953b672910c5990286f9b3a3b25d3f53e5d9`、`226b563257a429e61fc12ab16cc895befe73ff5d2fffd4114a4656f0cb4728dc`。
- 结论 `Verified` 仅表示所列具体用例与运行环境有证据；不能从单条正反例推断任意项目、所有后代进程或整个 Vera Core 已受保护。`Failed` 表示实测违背对应要求，`Blocked` 表示缺少必要环境或无法归因，`Not run` 表示尚未执行。

## 当前原型事实

无沙盒基线成功读取临时 `outside/` 哨兵、写入该目录、执行临时 `bin/` 自定义脚本、启动脚本后代并连接临时 loopback 端口。这只证明夹具有效。原始结果在临时 `logs/baseline.json`，不作为安全通过。

直接签名的 App Sandbox CLI 虽通过 `codesign --verify`，启动即以 `SIGILL` 退出。macOS crash report 的 `asiSignatures` 指出签名中缺少 `CFBundleIdentifier`；将同一可执行文件放入含 `Info.plist` 的 `.app` 后可以启动。因此后续均以签名 `.app` 原型测量，不能把启动崩溃算作文件拒绝。

| case_id | backend / host | command / requested_grant | expected / observed | os_evidence / artifact_hash | conclusion |
|---|---|---|---|---|---|
| `baseline-fixture` | none / dev-intel | 无沙盒 Python 夹具；无 Grant | 所有五项动作可用；实际均成功 | `logs/baseline.json` | `Verified`，仅夹具 |
| `core-default-outside-read` | signed App Sandbox Core / dev-intel | `ProbeCore.app` 读临时 `outside/secret.txt`；无文件 Grant | 拒绝；`NSPOSIXErrorDomain Code=1 Operation not permitted` | `codesign` entitlement 含 `com.apple.security.app-sandbox=true`；Swift 源哈希 `6a438c3b4fd40b4c89ce275e064b772e5bcd9dc192fa2c6fdc46d8ae3acf58fd` | `Verified` |
| `core-default-workspace-read` | signed App Sandbox Core / dev-intel | 读临时 workspace；仅声明 user-selected entitlement，未通过 UI 授权 | 拒绝；`Operation not permitted` | 同上；表明 entitlement 不自动授予 CLI 参数路径 | `Verified` |
| `core-default-outside-write` | signed App Sandbox Core / dev-intel | 写临时 `outside/`；无文件 Grant | 拒绝；`Operation not permitted` | 同上 | `Verified` |
| `core-static-workspace` | signed App Sandbox Core + 固定路径临时例外 / dev-intel | 签名时写入 workspace 读写、bin 只读路径 | workspace 读写与自定义脚本执行成功，`outside/` 仍拒绝 | `CoreStatic.entitlements` 和 `ProbeCoreStatic.app`；路径在签名前固定 | `Verified`，只证明固定路径候选 |
| `runner-static-boundary` | signed App Sandbox Runner + 固定路径临时例外 / dev-intel | workspace/bin 只读，artifacts 读写，无网络 Grant | 自定义脚本后代读取假秘密、假 Key 和写 workspace 均报 `Operation not permitted`；写 artifacts 成功 | `RunnerStatic.entitlements` 和 `ProbeRunner.app` | `Verified`，只证明固定路径候选 |
| `network-default` | signed App Sandbox Core/Runner / dev-intel | 两者连接临时 loopback 端口；无 network.client | 两者均返回 errno 1 | `ProbeCoreStatic.app`、`ProbeRunner.app` | `Verified` |
| `core-network-client` | signed App Sandbox Core / dev-intel | `ProbeCoreNetwork.app` 增加 `com.apple.security.network.client` 后连接临时本地监听端口 | 连接成功；授权粒度宽于固定 Provider 目的地 | `CoreNetwork.entitlements`；本用例只证明 loopback，不推断全部远程网络 | `Verified`，不满足精确目的地要求 |
| `broker-unix-socket` | signed App Sandbox Core / dev-intel | Core 获临时 `ipc/` 文件读写授权；分别在无、有 `network.client` 下连接 `ipc/broker.sock` | 两次均 errno 1；原因仍需查证 | `CoreStatic.entitlements` 与 `Probe.swift` v2；不能以此宣称所有 IPC 不可用 | `Blocked` |
| `installed-vera-core` | signed App Sandbox Core / dev-intel | 临时 venv 中 wheel 安装，`env -i` 清空真实环境变量；Core 通过 Runner 式进程继承方式启动 `vera --version`、`vera eval validate --json`、`plain-answer`、`create-file`、`forbidden-command` | 全部返回 0；三条 Fake Model 用例均 `status=pass`。移除 Core `network.client` 后重跑 `create-file` 仍 `pass` | venv `vera.__file__` 位于临时 `site-packages`；输出均在临时 `artifacts/`；`TMPDIR` 指向该根 | `Verified`，限这些离线 Core 路径 |
| `venv-symlink-toolchain` | signed App Sandbox Core / dev-intel | 起初只授权 venv 只读并运行 `venv/bin/vera`，后追加真实 Python Framework 根的固定只读路径 | 起初 `Process.run` errno 1；追加 `/usr/local/Cellar/python@3.12/3.12.2_1/` 后 `vera --version` 成功 | `venv/bin/python` 最终解析至 Homebrew Framework；属临时固定路径授权 | `Verified`，证明路径依赖，未证明动态可授予 |
| `xcrun-wrapper` | signed App Sandbox Runner / dev-intel | Runner 运行 `/usr/bin/xcrun --find swiftc` 和 `/usr/bin/git --version` | 两者均返回 `xcrun: error: cannot be used within an App Sandbox.` | Runner 没有网络权限；系统 `git` 是工具链包装路径 | `Failed`，对通用原生项目的硬门槛 |
| `swift-direct-compile` | signed App Sandbox Runner / dev-intel | 直接运行所选 Xcode 的 `swiftc`，workspace 只读、artifacts 可写；先无 SDK，后显式 `-sdk` | `swiftc --version` 成功；未指定 SDK 时无法加载标准库；指定 `/Applications/Xcode.app/.../MacOSX.sdk` 后编译成功 | 临时 `workspace/main.swift` 和 `artifacts/swift-project`；不等同项目原有构建脚本成功 | `Verified`，仅受控直调 |
| `generated-binary-quarantine` | signed App Sandbox Runner / dev-intel | 运行上一步生成的二进制，并对临时副本只改变 quarantine 属性 | 生成物带 `com.apple.quarantine`；在沙盒内外均 `Operation not permitted`。同一临时副本从宿主移除该属性后，沙盒内外均可运行 | `logs/chain-results.json` 与 `logs/quarantine-control.json` 中有前后对照；不把宿主清除属性当作产品方案 | `Failed`，当前编译后运行工作流 |
| `dynamic-workspace-grant` | signed App Sandbox Core / dev-intel | 用户选择任意目录、重启续用、从所选目录运行任意可执行文件 | UI/安全书签未实验 | 固定路径例外不能代表动态 Grant；Apple DTS 指出动态执行授权的限制 | `Not run` |

## 候选比较与判定

本机结果否定 **当前 App Sandbox + 普通 `Process` 子进程** 作为通用 Coding Agent 的唯一后端：系统常用 `xcrun` 包装路径拒绝在沙盒中运行；直调 Swift 编译器需要绕开项目既有命令并显式传 SDK；编译产物的 quarantine 阻断运行。即使单独解决这些问题，动态执行授权、Core→Broker IPC 与独立安装机仍无通过证据。Apple DTS 的[开发工具说明](https://developer.apple.com/forums/thread/746478)也明确区分固定与动态沙盒中的可执行访问，警告复杂工具的兼容性；Apple 的[子进程说明](https://developer.apple.com/documentation/foundation/process)指出普通 `Process` 后代继承父沙盒，权限更窄的 Runner 需要独立进程边界。本判断只覆盖本机实测配置，不把某个报错推断成所有 macOS 隔离技术不可行。

| 下一候选 | 潜在收益 | 尚需验证的代价与边界 | 本任务状态 |
|---|---|---|---|
| 独立系统身份运行受限 Core/Runner | 可利用不同 UID 与文件权限划开私有状态、Provider Broker 和项目命令，工具链仍在原生 macOS 上 | 需要创建或管理身份；用户家目录中的任意工具链可能不可读；网络、进程与 IPC 还需额外 OS 约束。不得把 UID 分离本身写成完整沙盒 | 仅文档比较，未实验 |
| [Apple Virtualization](https://developer.apple.com/documentation/virtualization) 或其他 VM 后端 | 可在虚拟机中隔离项目进程与主机资源，并显式共享目录 | 要验证 Intel 目标机可用的 guest、原生 Xcode/Simulator 兼容、安装体积、性能、持久化、网络与文件共享。Linux guest 不能直接代表本机 macOS 工具链 | 仅文档比较，未实验 |
| App Sandbox + 独立 XPC/helper | [Apple XPC](https://developer.apple.com/documentation/xpc) 支持分离权限；或可解决 Core→Broker 通信 | 仍须证明任意项目工具在更窄 Runner 中可用，且 helper 不退化为不受限宿主执行 | `Not run`；现有 `xcrun` 负例仍在 |

不选定后端 ADR（现预留 ADR-0023），不修改阶段八/九/十门禁。若继续验证，先把“原生任意工具链可用且项目进程权限更窄”作为独立系统身份或 VM 候选的硬门槛；涉及新账户、VM 安装或系统设置时，先形成具体方案再实施。

## 未完成项

1. 动态选择 workspace、执行用户自装于任意路径的工具、授权重启续用；本机固定路径签名无法代表该能力。
2. Core→Broker 的最小 IPC、假 Key 保管与固定 Provider 出口。普通 Unix socket 原型未连通，不推断 XPC 或 Mach 服务结果。
3. 系统 Git Hook、符号链接与硬链接、继承 FD、路径替换、取消后孤儿进程；因 App Sandbox 候选已在 `xcrun` 硬门槛失败，本轮未继续铺开这些用例。
4. Activity Monitor 的 Sandbox 列人工观察、完整产品进程封装，以及第二台 Intel Mac 独立安装复验、签名和性能测量。本机签名与 OS 拒绝证据不能替代这些安装态检查。

没有证据支持现在接受 App Sandbox 作为 Vera 唯一后端；也没有证据否定通过更窄 IPC 或其他 OS 机制实现目标。正式产品实现保持阻断。
